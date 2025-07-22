#!/usr/bin/env python
"""Build vector indices for business concepts.

This script provides a standalone way to build or rebuild vector embeddings
for business concepts in the master data table.

Usage:
    python scripts/offline/build_vector_indices.py [OPTIONS]

Options:
    --rebuild-all        Rebuild all vectors, not just missing ones
    --company-code       Process only concepts for a specific company
    --limit              Maximum number of concepts to process
    --batch-size         Number of concepts to process in each batch (default: 50)
    --dry-run            Show what would be done without making changes
    --parallel-workers   Number of parallel workers for processing (default: 1)
    --checkpoint-file    File to save progress for resuming interrupted runs
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import click
import structlog
from dotenv import load_dotenv
from tqdm import tqdm

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.application.use_cases.build_vector_index import BuildVectorIndexUseCase
from src.domain.services.vectorization_service import VectorizationService
from src.infrastructure.llm.qwen.qwen_embedding_adapter import QwenEmbeddingAdapter
from src.infrastructure.persistence.postgres.business_concept_master_repository import (
    PostgresBusinessConceptMasterRepository,
)
from src.infrastructure.persistence.postgres.connection import get_db_connection
from src.infrastructure.persistence.postgres.session_factory import SessionFactory
from src.shared.config.settings import Settings

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class CheckpointManager:
    """Manages checkpoints for resumable vector building."""

    def __init__(self, checkpoint_file: str | None):
        """Initialize checkpoint manager.

        Args:
            checkpoint_file: Path to checkpoint file, or None to disable
        """
        self.checkpoint_file = checkpoint_file
        self.processed_ids = set()

    def load(self) -> set[str]:
        """Load processed IDs from checkpoint file.

        Returns:
            Set of processed concept IDs
        """
        if not self.checkpoint_file or not os.path.exists(self.checkpoint_file):
            return set()

        try:
            with open(self.checkpoint_file) as f:
                data = json.load(f)
                self.processed_ids = set(data.get("processed_ids", []))
                logger.info(
                    "checkpoint_loaded",
                    file=self.checkpoint_file,
                    processed_count=len(self.processed_ids),
                )
                return self.processed_ids
        except Exception as e:
            logger.error(
                "checkpoint_load_failed",
                file=self.checkpoint_file,
                error=str(e),
            )
            return set()

    def save(self) -> None:
        """Save current progress to checkpoint file."""
        if not self.checkpoint_file:
            return

        try:
            data = {
                "processed_ids": list(self.processed_ids),
                "timestamp": time.time(),
            }
            with open(self.checkpoint_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(
                "checkpoint_save_failed",
                file=self.checkpoint_file,
                error=str(e),
            )

    def mark_processed(self, concept_id: str) -> None:
        """Mark a concept as processed.

        Args:
            concept_id: The concept ID to mark as processed
        """
        self.processed_ids.add(concept_id)


async def build_vectors(
    rebuild_all: bool,
    company_code: str | None,
    limit: int | None,
    batch_size: int,
    dry_run: bool,
    parallel_workers: int,
    checkpoint_manager: CheckpointManager,
) -> dict[str, Any]:
    """Build vector indices for business concepts.

    Args:
        rebuild_all: Whether to rebuild all vectors
        company_code: Optional company code filter
        limit: Maximum number of concepts to process
        batch_size: Batch size for processing
        dry_run: Whether to run in dry-run mode
        parallel_workers: Number of parallel workers
        checkpoint_manager: Checkpoint manager for resumable runs

    Returns:
        Processing statistics
    """
    # Load configuration
    load_dotenv()
    settings = Settings()

    # Initialize database connection

    db_connection = await get_db_connection()
    session_factory = SessionFactory(db_connection.engine)

    async with session_factory.get_session() as session:
        # Initialize repository
        repository = PostgresBusinessConceptMasterRepository(session)

        # Initialize embedding service
        from src.infrastructure.llm.qwen.qwen_embedding_adapter import (
            QwenEmbeddingConfig,
        )

        embedding_config = QwenEmbeddingConfig.from_settings(settings.qwen_embedding)
        # Override batch size if provided
        if batch_size != settings.qwen_embedding.qwen_max_batch_size:
            embedding_config = QwenEmbeddingConfig(
                **embedding_config.model_dump(),
                max_batch_size=batch_size,
            )
        embedding_service = QwenEmbeddingAdapter(config=embedding_config)

        # Initialize vectorization service
        vectorization_service = VectorizationService(
            embedding_service=embedding_service,
            qwen_settings=settings.qwen_embedding,
        )

        if dry_run:
            # In dry-run mode, just show what would be done
            concepts = await repository.find_concepts_needing_embeddings(limit=limit)
            if company_code:
                concepts = [c for c in concepts if c.company_code == company_code]

            # Filter out already processed concepts
            processed_ids = checkpoint_manager.load()
            concepts = [c for c in concepts if str(c.concept_id) not in processed_ids]

            logger.info(
                "dry_run_summary",
                total_concepts=len(concepts),
                company_filter=company_code,
                rebuild_all=rebuild_all,
            )

            for concept in concepts[:10]:  # Show first 10
                logger.info(
                    "would_process",
                    concept_id=str(concept.concept_id),
                    company_code=concept.company_code,
                    concept_name=concept.concept_name,
                )

            if len(concepts) > 10:
                logger.info("and_more", count=len(concepts) - 10)

            return {
                "total_concepts": len(concepts),
                "dry_run": True,
            }

        # Create use case
        use_case = BuildVectorIndexUseCase(
            repository=repository,
            embedding_service=embedding_service,
            vectorization_service=vectorization_service,
            batch_size=batch_size,
        )

        # Load checkpoint
        processed_ids = checkpoint_manager.load()

        # If we have processed IDs and not rebuilding all, we need custom logic
        if processed_ids and not rebuild_all:
            # Get concepts needing embeddings
            concepts = await repository.find_concepts_needing_embeddings(limit=None)
            if company_code:
                concepts = [c for c in concepts if c.company_code == company_code]

            # Filter out already processed
            concepts = [c for c in concepts if str(c.concept_id) not in processed_ids]

            if limit:
                concepts = concepts[:limit]

            logger.info(
                "resuming_from_checkpoint",
                previously_processed=len(processed_ids),
                remaining=len(concepts),
            )

            # Process with progress tracking
            stats = {
                "total_concepts": len(concepts),
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [],
            }

            for i in tqdm(
                range(0, len(concepts), batch_size), desc="Processing batches"
            ):
                batch = concepts[i : i + batch_size]
                await use_case._process_batch(batch, stats)

                # Mark as processed and save checkpoint
                for concept in batch:
                    checkpoint_manager.mark_processed(str(concept.concept_id))
                checkpoint_manager.save()

            return stats

        else:
            # Normal execution through use case
            result = await use_case.execute(
                rebuild_all=rebuild_all,
                limit=limit,
                company_code=company_code,
            )

            # If successful, clear checkpoint
            if result.get("succeeded", 0) > 0:
                checkpoint_manager.processed_ids.clear()
                checkpoint_manager.save()

            return result


@click.command()
@click.option(
    "--rebuild-all",
    is_flag=True,
    help="Rebuild all vectors, not just missing ones",
)
@click.option(
    "--company-code",
    help="Process only concepts for a specific company",
)
@click.option(
    "--limit",
    type=int,
    help="Maximum number of concepts to process",
)
@click.option(
    "--batch-size",
    type=int,
    default=50,
    help="Number of concepts to process in each batch",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
@click.option(
    "--parallel-workers",
    type=int,
    default=1,
    help="Number of parallel workers for processing",
)
@click.option(
    "--checkpoint-file",
    help="File to save progress for resuming interrupted runs",
)
def main(
    rebuild_all: bool,
    company_code: str | None,
    limit: int | None,
    batch_size: int,
    dry_run: bool,
    parallel_workers: int,
    checkpoint_file: str | None,
):
    """Build vector indices for business concepts in the master data table."""
    logger.info(
        "starting_vector_index_build",
        rebuild_all=rebuild_all,
        company_code=company_code,
        limit=limit,
        batch_size=batch_size,
        dry_run=dry_run,
        parallel_workers=parallel_workers,
        checkpoint_file=checkpoint_file,
    )

    # Create checkpoint manager
    checkpoint_manager = CheckpointManager(checkpoint_file)

    try:
        # Run async function
        result = asyncio.run(
            build_vectors(
                rebuild_all=rebuild_all,
                company_code=company_code,
                limit=limit,
                batch_size=batch_size,
                dry_run=dry_run,
                parallel_workers=parallel_workers,
                checkpoint_manager=checkpoint_manager,
            )
        )

        # Print summary
        if not dry_run:
            click.echo("\n" + "=" * 60)
            click.echo("Vector Index Build Summary")
            click.echo("=" * 60)
            click.echo(f"Total concepts:     {result.get('total_concepts', 0)}")
            click.echo(f"Processed:          {result.get('processed', 0)}")
            click.echo(f"Succeeded:          {result.get('succeeded', 0)}")
            click.echo(f"Failed:             {result.get('failed', 0)}")
            click.echo(f"Skipped:            {result.get('skipped', 0)}")
            click.echo(f"Processing time:    {result.get('processing_time', 0):.2f}s")

            if result.get("errors"):
                click.echo("\nErrors:")
                for error in result["errors"]:
                    click.echo(f"  - {error}")

        logger.info("vector_index_build_completed", **result)

    except KeyboardInterrupt:
        logger.warning("interrupted_by_user")
        click.echo("\nInterrupted by user. Progress saved to checkpoint.")
        sys.exit(1)
    except Exception as e:
        logger.error("vector_index_build_failed", error=str(e), exc_info=True)
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
