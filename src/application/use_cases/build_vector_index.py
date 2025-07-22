"""Build vector index use case.

This module provides the use case for building and updating vector embeddings
for business concepts in the master data table.
"""

import time
from datetime import datetime
from typing import Any, cast

import structlog
from tqdm import tqdm

from src.application.ports.business_concept_master_repository import (
    BusinessConceptMasterRepositoryPort,
)
from src.application.ports.embedding_service_port import EmbeddingServicePort
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.domain.services.vectorization_service import VectorizationService
from src.infrastructure.monitoring.vectorization_metrics import VectorizationMetrics

logger = structlog.get_logger(__name__)


class BuildVectorIndexUseCase:
    """Use case for building vector indices for business concepts."""

    def __init__(
        self,
        repository: BusinessConceptMasterRepositoryPort,
        embedding_service: EmbeddingServicePort,
        vectorization_service: VectorizationService,
        batch_size: int | None = None,
    ):
        """Initialize the use case.

        Args:
            repository: Repository for business concept master data operations
            embedding_service: Service for generating embeddings
            vectorization_service: Service for preparing text for vectorization
            batch_size: Number of concepts to process in each batch (defaults to embedding service config)
        """
        self.repository = repository
        self.embedding_service = embedding_service
        self.vectorization_service = vectorization_service
        # Use vectorization service's qwen_settings if available, otherwise default to 50
        default_batch_size = getattr(
            self.vectorization_service, 'qwen_settings', None
        ) and self.vectorization_service.qwen_settings.qwen_max_batch_size or 50
        self.batch_size = batch_size or default_batch_size

    async def execute(
        self,
        rebuild_all: bool = False,
        limit: int | None = None,
        company_code: str | None = None,
    ) -> dict[str, Any]:
        """Execute the vector index building process.

        Args:
            rebuild_all: If True, rebuild vectors for all concepts,
                not just those missing embeddings
            limit: Optional limit on number of concepts to process
            company_code: Optional filter to process only concepts
                for a specific company

        Returns:
            Dictionary containing processing statistics
        """
        start_time = time.time()
        stats = {
            "total_concepts": 0,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "processing_time": 0.0,
            "errors": [],
        }

        # Determine operation type and company code for metrics
        operation_type = "full" if rebuild_all else "incremental"
        metrics_company_code = company_code or "all"

        with VectorizationMetrics.track_vectorization_operation(
            company_code=metrics_company_code,
            total_concepts=0,  # Will be updated once we know
            operation_type=operation_type,
        ) as metrics_context:
            try:
                # Get concepts that need vectorization
                if rebuild_all:
                    if company_code:
                        concepts = await self.repository.find_all_by_company(
                            company_code
                        )
                    else:
                        # For rebuild_all without company filter, we need to
                        # fetch all. This is a limitation needing a new method
                        logger.warning(
                            "rebuild_all_without_company_not_optimal",
                            message="Rebuild all without company filter "
                            "requires fetching all concepts",
                        )
                        concepts = (
                            await self.repository.find_concepts_needing_embeddings(
                                limit=None
                            )
                        )
                else:
                    concepts = await self.repository.find_concepts_needing_embeddings(
                        limit=limit
                    )

                stats["total_concepts"] = len(concepts)

                # Update queue depth metric
                VectorizationMetrics.update_queue_depth(
                    len(concepts), metrics_company_code
                )

                if not concepts:
                    logger.info("no_concepts_to_vectorize")
                    VectorizationMetrics.update_queue_depth(
                        -len(concepts), metrics_company_code
                    )
                    return stats

                logger.info(
                    "starting_vectorization",
                    total_concepts=len(concepts),
                    batch_size=self.batch_size,
                    rebuild_all=rebuild_all,
                )

                # Process in batches
                for i in tqdm(
                    range(0, len(concepts), self.batch_size),
                    desc="Processing vector batches",
                ):
                    batch = concepts[i : i + self.batch_size]
                    await self._process_batch(batch, stats, metrics_context)

                    # Update queue depth as we process
                    VectorizationMetrics.update_queue_depth(
                        -len(batch), metrics_company_code
                    )

                stats["processing_time"] = time.time() - start_time

                logger.info(
                    "vectorization_completed",
                    **stats,
                )

                # Update metrics context with final counts
                metrics_context.embeddings_generated = stats["succeeded"]
                metrics_context.model_errors = stats["failed"]

                return stats

            except Exception as e:
                logger.error("vectorization_failed", error=str(e), exc_info=True)
                cast(list[str], stats["errors"]).append(f"Fatal error: {str(e)}")
                stats["processing_time"] = time.time() - start_time
                metrics_context.has_errors = True
                return stats

    async def _process_batch(
        self,
        concepts: list[BusinessConceptMaster],
        stats: dict[str, Any],
        metrics_context,
    ) -> None:
        """Process a batch of concepts.

        Args:
            concepts: List of concepts to process
            stats: Statistics dictionary to update
        """
        try:
            # Prepare texts for embedding
            texts_to_embed = []
            concept_ids = []

            for concept in concepts:
                try:
                    # Prepare text using vectorization service
                    prepared_text = (
                        self.vectorization_service.prepare_text_for_embedding(
                            concept_name=concept.concept_name,
                            description=concept.concept_details.get("description", ""),
                        )
                    )

                    if prepared_text:
                        texts_to_embed.append(prepared_text)
                        concept_ids.append(concept.concept_id)
                    else:
                        logger.warning(
                            "empty_text_after_preparation",
                            concept_id=str(concept.concept_id),
                            concept_name=concept.concept_name,
                        )
                        stats["skipped"] += 1

                except Exception as e:
                    logger.error(
                        "text_preparation_failed",
                        concept_id=str(concept.concept_id),
                        error=str(e),
                    )
                    stats["failed"] += 1
                    stats["errors"].append(
                        f"Text preparation failed for {concept.concept_id}: {str(e)}"
                    )

            if not texts_to_embed:
                return

            # Generate embeddings
            try:
                embeddings = await self.embedding_service.embed_texts(texts_to_embed)

                # Verify embedding dimensions
                expected_dim = self.embedding_service.get_embedding_dimension()
                for embedding in embeddings:
                    if len(embedding) != expected_dim:
                        raise ValueError(
                            f"Embedding dimension mismatch: "
                            f"expected {expected_dim}, got {len(embedding)}"
                        )

                # Prepare batch update data
                # Convert numpy arrays to lists for database storage
                embedding_lists = [emb.tolist() for emb in embeddings]
                update_data = list(zip(concept_ids, embedding_lists, strict=False))

                # Update embeddings in database with monitoring
                with VectorizationMetrics.track_db_update(
                    batch_size=len(update_data),
                    operation="batch_update",
                ):
                    await self.repository.batch_update_embeddings(update_data)

                stats["processed"] += len(texts_to_embed)
                stats["succeeded"] += len(texts_to_embed)

                # Record successful embeddings in metrics
                for i, (concept_id, embedding) in enumerate(update_data):
                    concept = next(c for c in concepts if c.concept_id == concept_id)
                    # Calculate vector norm for quality check
                    import numpy as np

                    vector_norm = float(np.linalg.norm(embedding))

                    VectorizationMetrics.record_embedding_generated(
                        company_code=concept.company_code,
                        concept_name=concept.concept_name,
                        dimension=len(embedding),
                        tokens=len(
                            texts_to_embed[i].split()
                        ),  # Approximate token count
                        norm=vector_norm,
                    )
                    metrics_context.record_embedding(
                        tokens=len(texts_to_embed[i].split())
                    )

                logger.info(
                    "batch_vectorization_success",
                    batch_size=len(texts_to_embed),
                    concept_ids=[str(cid) for cid in concept_ids],
                )

            except Exception as e:
                logger.error(
                    "batch_embedding_generation_failed",
                    batch_size=len(texts_to_embed),
                    error=str(e),
                    exc_info=True,
                )
                stats["failed"] += len(texts_to_embed)
                stats["errors"].append(f"Batch embedding failed: {str(e)}")
                metrics_context.record_model_error()

        except Exception as e:
            logger.error(
                "batch_processing_failed",
                error=str(e),
                exc_info=True,
            )
            stats["errors"].append(f"Batch processing error: {str(e)}")

    async def get_vectorization_status(
        self, company_code: str | None = None
    ) -> dict[str, Any]:
        """Get the current vectorization status.

        Args:
            company_code: Optional filter for specific company

        Returns:
            Dictionary containing vectorization status information
        """
        try:
            if company_code:
                all_concepts = await self.repository.find_all_by_company(company_code)
                concepts_needing_vectors = [
                    c for c in all_concepts if c.embedding is None
                ]
            else:
                # Get count of concepts needing embeddings
                concepts_needing_vectors = (
                    await self.repository.find_concepts_needing_embeddings()
                )
                # This might not give us total count without another method
                all_concepts = concepts_needing_vectors

            status = {
                "total_concepts": len(all_concepts) if company_code else "unknown",
                "concepts_with_embeddings": (
                    len(all_concepts) - len(concepts_needing_vectors)
                    if company_code
                    else "unknown"
                ),
                "concepts_needing_embeddings": len(concepts_needing_vectors),
                "embedding_dimension": (
                    self.embedding_service.get_embedding_dimension()
                ),
                "timestamp": datetime.utcnow().isoformat(),
            }

            if company_code:
                status["company_code"] = company_code

            return status

        except Exception as e:
            logger.error(
                "get_vectorization_status_failed",
                error=str(e),
                exc_info=True,
            )
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
