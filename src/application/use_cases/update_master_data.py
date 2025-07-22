"""Use case for updating master data with business concept fusion.

This module implements the business logic for intelligently updating the
BusinessConceptsMaster table with new data from source documents.
"""

import asyncio
from typing import Any
from uuid import UUID

import structlog

from src.application.ports.business_concept_master_repository import (
    BusinessConceptMasterRepositoryPort,
)
from src.application.ports.embedding_service_port import EmbeddingServicePort
from src.application.ports.source_document_repository import (
    SourceDocumentRepositoryPort,
)
from src.application.use_cases.build_vector_index import BuildVectorIndexUseCase
from src.domain.entities.company import BusinessConcept
from src.domain.services.data_fusion_service import DataFusionService
from src.domain.services.vectorization_service import VectorizationService
from src.infrastructure.monitoring.fusion_metrics import FusionMetrics
from src.shared.config.settings import get_settings
from src.shared.exceptions.business_exceptions import OptimisticLockError

logger = structlog.get_logger(__name__)


class UpdateMasterDataUseCase:
    """Use case for updating master data with smart fusion of business concepts."""

    def __init__(
        self,
        source_document_repo: SourceDocumentRepositoryPort,
        business_concept_repo: BusinessConceptMasterRepositoryPort,
        data_fusion_service: DataFusionService,
        embedding_service: EmbeddingServicePort | None = None,
        vectorization_service: VectorizationService | None = None,
        batch_size: int | None = None,
        enable_async_vectorization: bool = True,
    ):
        """Initialize the use case with dependencies.

        Args:
            source_document_repo: Repository for source documents
            business_concept_repo: Repository for business concept master data
            data_fusion_service: Service for data fusion logic
            embedding_service: Optional service for generating embeddings
            vectorization_service: Optional service for text preparation
            batch_size: Number of concepts to process in each batch
            enable_async_vectorization: Whether to enable async vector building
        """
        self.source_document_repo = source_document_repo
        self.business_concept_repo = business_concept_repo
        self.data_fusion_service = data_fusion_service
        self.embedding_service = embedding_service
        self.vectorization_service = vectorization_service

        # Load settings
        settings = get_settings()
        self.batch_size = batch_size or settings.fusion.fusion_batch_size
        self.batch_delay = settings.fusion.fusion_batch_delay_seconds
        self.max_retries = settings.fusion.fusion_max_retries
        self.retry_base_delay = settings.fusion.fusion_retry_base_delay
        self.enable_async_vectorization = enable_async_vectorization

        # Create vector index use case if services are provided
        self.vector_index_use_case = None
        if embedding_service and vectorization_service:
            self.vector_index_use_case = BuildVectorIndexUseCase(
                repository=business_concept_repo,
                embedding_service=embedding_service,
                vectorization_service=vectorization_service,
                batch_size=batch_size,
            )

    async def execute(self, doc_id: UUID) -> dict[str, Any]:
        """Execute the master data update for a specific document.

        This method:
        1. Retrieves the source document with raw LLM output
        2. Parses business concepts from the extraction data
        3. Processes concepts in batches for optimal performance
        4. Creates new concepts or updates existing ones using fusion rules

        Args:
            doc_id: The UUID of the source document to process

        Returns:
            Dictionary with processing statistics:
            - concepts_created: Number of new concepts created
            - concepts_updated: Number of existing concepts updated
            - concepts_skipped: Number of concepts skipped (errors)
            - total_concepts: Total number of concepts processed
            - processing_time_ms: Total processing time in milliseconds

        Raises:
            ValueError: If document not found or has no business concepts
        """
        logger.info("starting_master_data_update", doc_id=str(doc_id))

        # Retrieve source document
        source_doc = await self.source_document_repo.find_by_id(doc_id)
        if not source_doc:
            raise ValueError(f"Source document {doc_id} not found")

        # Extract business concepts
        business_concepts = self._extract_business_concepts(source_doc.raw_llm_output)
        if not business_concepts:
            logger.warning("no_business_concepts_found", doc_id=str(doc_id))
            return {
                "concepts_created": 0,
                "concepts_updated": 0,
                "concepts_skipped": 0,
                "total_concepts": 0,
                "processing_time_ms": 0,
                "concepts_needing_vectorization": 0,
                "vectorization_triggered": False,
            }

        # Process concepts with monitoring
        with FusionMetrics.track_fusion_operation(
            doc_id=doc_id,
            company_code=source_doc.company_code,
            total_concepts=len(business_concepts),
        ) as context:
            # Process concepts in batches
            for i in range(0, len(business_concepts), self.batch_size):
                batch = business_concepts[i : i + self.batch_size]
                batch_index = i // self.batch_size

                with FusionMetrics.track_batch_processing(
                    batch_size=len(batch),
                    batch_index=batch_index,
                ):
                    await self._process_batch(
                        batch, source_doc.company_code, doc_id, context
                    )

                # Small delay between batches to prevent resource exhaustion
                if i + self.batch_size < len(business_concepts):
                    await asyncio.sleep(self.batch_delay)

            # Get final statistics
            stats = context.get_summary()
            stats["total_concepts"] = len(business_concepts)
            stats["processing_time_ms"] = 0  # Will be set by the context manager

            # Track concepts needing vectorization
            stats["concepts_needing_vectorization"] = (
                context.concepts_needing_vectorization
            )

            # Trigger async vectorization if enabled and we have new/updated concepts
            if (
                self.enable_async_vectorization
                and self.vector_index_use_case
                and context.concepts_needing_vectorization > 0
            ):
                # Run vectorization asynchronously without awaiting
                asyncio.create_task(
                    self._run_async_vectorization(source_doc.company_code)
                )
                stats["vectorization_triggered"] = True
            else:
                stats["vectorization_triggered"] = False

            logger.info(
                "master_data_update_completed",
                doc_id=str(doc_id),
                **stats,
            )

            return stats

    def _extract_business_concepts(
        self, raw_llm_output: dict[str, Any]
    ) -> list[BusinessConcept]:
        """Extract business concepts from raw LLM output.

        Args:
            raw_llm_output: The raw JSON from LLM extraction

        Returns:
            List of BusinessConcept domain entities
        """
        extraction_data = raw_llm_output.get("extraction_data", {})
        concepts_data = extraction_data.get("business_concepts", [])

        business_concepts = []
        for concept_data in concepts_data:
            try:
                concept = BusinessConcept(**concept_data)
                business_concepts.append(concept)
            except Exception as e:
                logger.error(
                    "failed_to_parse_business_concept",
                    error=str(e),
                    concept_data=concept_data,
                )

        return business_concepts

    async def _process_batch(
        self,
        concepts: list[BusinessConcept],
        company_code: str,
        doc_id: UUID,
        context: Any,
    ) -> dict[str, int]:
        """Process a batch of business concepts.

        Args:
            concepts: List of business concepts to process
            company_code: The company code
            doc_id: The source document ID
            context: Metrics collection context

        Returns:
            Dictionary with batch statistics
        """
        batch_stats = {"created": 0, "updated": 0, "skipped": 0}

        # Track concepts needing vectorization
        if not hasattr(context, "concepts_needing_vectorization"):
            context.concepts_needing_vectorization = 0

        for concept in concepts:
            try:
                success = await self._process_single_concept(
                    concept, company_code, doc_id
                )
                if success == "created":
                    batch_stats["created"] += 1
                    context.record_created()
                    context.concepts_needing_vectorization += 1
                    FusionMetrics.record_concept_created(
                        company_code, concept.concept_name
                    )
                elif success == "updated":
                    batch_stats["updated"] += 1
                    context.record_updated()
                    context.concepts_needing_vectorization += 1
            except Exception as e:
                logger.error(
                    "failed_to_process_concept",
                    concept_name=concept.concept_name,
                    company_code=company_code,
                    error=str(e),
                )
                batch_stats["skipped"] += 1
                context.record_skipped()
                FusionMetrics.record_concept_skipped(
                    company_code, concept.concept_name, str(e)
                )

        return batch_stats

    async def _process_single_concept(
        self,
        concept: BusinessConcept,
        company_code: str,
        doc_id: UUID,
    ) -> str:
        """Process a single business concept.

        Args:
            concept: The business concept to process
            company_code: The company code
            doc_id: The source document ID

        Returns:
            "created" if new concept was created, "updated" if existing was updated

        Raises:
            Exception: If processing fails
        """
        # Check if concept already exists
        existing = await self.business_concept_repo.find_by_company_and_name(
            company_code, concept.concept_name
        )

        if existing:
            # Update existing concept with retry for optimistic lock conflicts
            for attempt in range(self.max_retries):
                try:
                    # Merge the data
                    updated = self.data_fusion_service.merge_business_concepts(
                        existing, concept, doc_id
                    )

                    # Save the update
                    await self.business_concept_repo.update(updated)

                    FusionMetrics.record_concept_updated(
                        company_code, concept.concept_name, updated.version
                    )

                    return "updated"

                except OptimisticLockError:
                    if attempt == self.max_retries - 1:
                        raise

                    # Record retry
                    FusionMetrics.record_retry(
                        company_code, concept.concept_name, attempt + 1
                    )

                    # Refresh the entity and retry
                    await asyncio.sleep(self.retry_base_delay * (attempt + 1))
                    existing = (
                        await self.business_concept_repo.find_by_company_and_name(
                            company_code, concept.concept_name
                        )
                    )
                    if not existing:
                        # Concept was deleted, treat as new
                        break

        # Create new concept
        new_master = self.data_fusion_service.create_from_new_concept(
            concept, company_code, doc_id
        )

        await self.business_concept_repo.save(new_master)

        return "created"

    async def _run_async_vectorization(self, company_code: str) -> None:
        """Run vectorization asynchronously for a company.

        Args:
            company_code: The company code to vectorize concepts for
        """
        try:
            logger.info(
                "starting_async_vectorization",
                company_code=company_code,
            )

            # Run vectorization for the specific company
            if self.vector_index_use_case:
                result = await self.vector_index_use_case.execute(
                    rebuild_all=False,
                    company_code=company_code,
                )

                logger.info(
                    "async_vectorization_completed",
                    company_code=company_code,
                    **result,
                )

        except Exception as e:
            logger.error(
                "async_vectorization_failed",
                company_code=company_code,
                error=str(e),
                exc_info=True,
            )
