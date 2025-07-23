#!/usr/bin/env python3
"""
Complete Pipeline Script - Ensures all documents go through the full process

This script addresses gaps in the current pipeline:
1. Processes any documents missing from extracted JSON
2. Ensures all archived documents go through fusion
3. Verifies all business concepts have embeddings
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select

from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import (
    BusinessConceptMasterModel,
    SourceDocumentModel,
)

logger = structlog.get_logger()
console = Console()


class PipelineCompleter:
    """Completes any gaps in the document processing pipeline."""

    def __init__(self):
        self.stats = {
            "missing_extractions": 0,
            "missing_fusions": 0,
            "missing_vectors": 0,
            "documents_processed": 0,
            "fusions_completed": 0,
            "vectors_created": 0,
        }

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    async def find_gaps(self, force_reextract=False):
        """Find all gaps in the pipeline."""
        gaps = {
            "missing_extractions": [],
            "missing_fusions": [],
            "missing_vectors": [],
        }

        async with get_session() as session:
            # 1. Get all archived documents' file hashes
            archived_stmt = select(
                SourceDocumentModel.file_hash,
                SourceDocumentModel.file_path,
                SourceDocumentModel.doc_id,
            ).where(SourceDocumentModel.processing_status == "completed")
            archived_result = await session.execute(archived_stmt)
            archived_hashes = {row.file_hash: row for row in archived_result}

            # 2. Find source files
            source_files = set()
            for base_dir in ["data/annual_reports", "data/research_reports"]:
                base_path = Path(base_dir)
                if base_path.exists():
                    for pattern in ["**/*.md", "**/*.txt"]:
                        source_files.update(base_path.glob(pattern))

            # 3. Check each source file against database
            for source_file in source_files:
                # Calculate file hash
                file_hash = self._calculate_file_hash(source_file)

                # Check if already archived in database
                if force_reextract or file_hash not in archived_hashes:
                    # Also check if extracted JSON exists (fallback)
                    doc_type = (
                        "annual_report"
                        if "annual_report" in str(source_file)
                        else "research_report"
                    )
                    extract_path = Path(
                        f"data/extracted/{doc_type}s/{source_file.stem}_extracted.json"
                    )

                    # Only add to missing if force mode or neither DB record nor extracted file exists
                    if force_reextract or not extract_path.exists():
                        gaps["missing_extractions"].append(source_file)
                    elif not force_reextract:
                        logger.info(
                            "File has extracted JSON but not in DB",
                            file=str(source_file),
                            hash=file_hash,
                        )

            # 2. Find archived documents without fusion (no concepts referencing them)
            # Get all document IDs that have been used for fusion
            fusion_stmt = (
                select(BusinessConceptMasterModel.last_updated_from_doc_id)
                .where(BusinessConceptMasterModel.last_updated_from_doc_id.isnot(None))
                .distinct()
            )
            fusion_result = await session.execute(fusion_stmt)
            fused_doc_ids = {row[0] for row in fusion_result}

            # Get all completed documents
            docs_stmt = select(
                SourceDocumentModel.doc_id,
                SourceDocumentModel.company_code,
                SourceDocumentModel.doc_type,
                SourceDocumentModel.doc_date,
            ).where(SourceDocumentModel.processing_status == "completed")
            docs_result = await session.execute(docs_stmt)

            for row in docs_result:
                if row.doc_id not in fused_doc_ids:
                    gaps["missing_fusions"].append(
                        {
                            "doc_id": row.doc_id,
                            "company_code": row.company_code,
                            "doc_type": row.doc_type,
                            "doc_date": row.doc_date,
                        }
                    )

            # 3. Find concepts without embeddings
            concepts_stmt = select(
                BusinessConceptMasterModel.concept_id,
                BusinessConceptMasterModel.company_code,
                BusinessConceptMasterModel.concept_name,
            ).where(BusinessConceptMasterModel.embedding.is_(None))
            concepts_result = await session.execute(concepts_stmt)

            for row in concepts_result:
                gaps["missing_vectors"].append(
                    {
                        "concept_id": row.concept_id,
                        "company_code": row.company_code,
                        "concept_name": row.concept_name,
                    }
                )

        self.stats["missing_extractions"] = len(gaps["missing_extractions"])
        self.stats["missing_fusions"] = len(gaps["missing_fusions"])
        self.stats["missing_vectors"] = len(gaps["missing_vectors"])

        return gaps

    async def process_missing_extractions(
        self, files, parallel_workers=20, force_reextract=False
    ):
        """Process files that haven't been extracted yet with concurrent execution."""
        if not files:
            return

        self.force_reextract = force_reextract

        console.print(f"\n[yellow]Found {len(files)} files without extraction[/yellow]")
        console.print(
            f"[yellow]Processing with {parallel_workers} concurrent workers[/yellow]"
        )

        # Import extraction use case
        from src.application.use_cases.extract_document_data import (
            ExtractDocumentDataUseCase,
        )
        from src.infrastructure.llm.gemini_llm_adapter import GeminiLLMAdapter
        from src.infrastructure.persistence.postgres.source_document_repository import (
            PostgresSourceDocumentRepository,
        )
        from src.shared.config.settings import Settings

        settings = Settings()
        llm_service = GeminiLLMAdapter(settings)

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(parallel_workers)

        async def process_single_file(file_path, progress, task):
            async with semaphore:
                try:
                    # Double-check file hasn't been processed since gap analysis
                    file_hash = self._calculate_file_hash(file_path)

                    async with get_session() as session:
                        # Check if already in database
                        check_stmt = select(SourceDocumentModel).where(
                            SourceDocumentModel.file_hash == file_hash
                        )
                        result = await session.execute(check_stmt)
                        existing = result.scalar_one_or_none()

                        if existing and not self.force_reextract:
                            logger.info(
                                f"Skipping {file_path.name} - already in database",
                                doc_id=existing.doc_id,
                                company_code=existing.company_code,
                            )
                            progress.advance(task)
                            return

                    # Determine document type
                    if "annual_report" in str(file_path):
                        doc_type = "annual_report"
                    else:
                        doc_type = "research_report"

                    async with get_session() as session:
                        repository = PostgresSourceDocumentRepository(session)
                        use_case = ExtractDocumentDataUseCase(llm_service, repository)

                        result = await use_case.execute(
                            file_path,
                            document_type_override=doc_type,
                        )

                        # Save extracted JSON
                        output_dir = Path(f"data/extracted/{doc_type}s")
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_path = output_dir / f"{file_path.stem}_extracted.json"

                        result_data = {
                            "document_type": result.document_type,
                            "extraction_data": result.extraction_data.model_dump(
                                mode="json"
                            ),
                            "extraction_metadata": result.extraction_metadata.model_dump(
                                mode="json"
                            ),
                        }

                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(result_data, f, ensure_ascii=False, indent=2)

                        self.stats["documents_processed"] += 1
                        logger.info(f"Extracted {file_path.name}")

                except Exception as e:
                    logger.error(f"Failed to extract {file_path}: {e}")
                finally:
                    progress.advance(task)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Extracting missing documents...", total=len(files)
            )

            # Create tasks for all files
            tasks = [
                process_single_file(file_path, progress, task) for file_path in files
            ]

            # Process all files concurrently
            await asyncio.gather(*tasks)

    async def process_missing_fusions(self, documents):
        """Process documents that haven't gone through fusion."""
        if not documents:
            return

        console.print(
            f"\n[yellow]Found {len(documents)} documents without fusion[/yellow]"
        )

        from src.infrastructure.factories import create_standalone_fusion_use_case

        fusion_use_case = await create_standalone_fusion_use_case()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Running fusion for documents...", total=len(documents)
            )

            for doc in documents:
                try:
                    result = await fusion_use_case.execute(doc["doc_id"])
                    self.stats["fusions_completed"] += 1
                    logger.info(
                        f"Fusion completed for {doc['company_code']} - "
                        f"{doc['doc_type']} ({doc['doc_date']})",
                        concepts_created=result["concepts_created"],
                        concepts_updated=result["concepts_updated"],
                    )
                except Exception as e:
                    logger.error(f"Fusion failed for doc {doc['doc_id']}: {e}")

                progress.advance(task)

    async def process_missing_vectors(self, concepts):
        """Build vectors for concepts without embeddings."""
        if not concepts:
            return

        console.print(
            f"\n[yellow]Found {len(concepts)} concepts without vectors[/yellow]"
        )

        from src.application.use_cases.build_vector_index import BuildVectorIndexUseCase
        from src.domain.services.vectorization_service import VectorizationService
        from src.infrastructure.llm.qwen.qwen_embedding_adapter import (
            QwenEmbeddingAdapter,
            QwenEmbeddingConfig,
        )
        from src.infrastructure.persistence.postgres.business_concept_master_repository import (
            PostgresBusinessConceptMasterRepository,
        )
        from src.shared.config.settings import Settings

        settings = Settings()
        embedding_config = QwenEmbeddingConfig.from_settings(settings.qwen_embedding)
        embedding_service = QwenEmbeddingAdapter(config=embedding_config)

        async with get_session() as session:
            repository = PostgresBusinessConceptMasterRepository(session)
            vectorization_service = VectorizationService(
                embedding_service=embedding_service,
                qwen_settings=settings.qwen_embedding,
            )

            use_case = BuildVectorIndexUseCase(
                repository=repository,
                embedding_service=embedding_service,
                vectorization_service=vectorization_service,
                batch_size=50,
            )

            # Get full concept objects
            concept_ids = [c["concept_id"] for c in concepts]
            stmt = select(BusinessConceptMasterModel).where(
                BusinessConceptMasterModel.concept_id.in_(concept_ids)
            )
            result = await session.execute(stmt)
            concept_models = result.scalars().all()

            if concept_models:
                stats = {
                    "total_concepts": len(concept_models),
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "skipped": 0,
                    "errors": [],
                }

                await use_case._process_batch(concept_models, stats)
                self.stats["vectors_created"] = stats["succeeded"]

    async def run(self, dry_run=False, parallel_workers=20, force_reextract=False):
        """Run the complete pipeline to fill all gaps."""
        console.print("\n[bold cyan]=== PIPELINE COMPLETION CHECK ===[/bold cyan]\n")

        if force_reextract:
            console.print(
                "[yellow]Force re-extract mode enabled - will ignore database records[/yellow]\n"
            )

        # Find gaps
        console.print("Analyzing pipeline gaps...")
        gaps = await self.find_gaps(force_reextract=force_reextract)

        # Display gap summary
        table = Table(title="Pipeline Gap Analysis")
        table.add_column("Stage", style="cyan")
        table.add_column("Missing Count", style="red")
        table.add_column("Description", style="yellow")

        table.add_row(
            "Extraction",
            str(self.stats["missing_extractions"]),
            "Source files without extracted JSON",
        )
        table.add_row(
            "Fusion",
            str(self.stats["missing_fusions"]),
            "Archived documents without concept fusion",
        )
        table.add_row(
            "Vectorization",
            str(self.stats["missing_vectors"]),
            "Business concepts without embeddings",
        )

        console.print(table)

        if dry_run:
            console.print("\n[yellow]Dry run mode - no processing performed[/yellow]")

            # Show some examples
            if gaps["missing_extractions"]:
                console.print("\n[bold]Files missing extraction:[/bold]")
                for f in gaps["missing_extractions"][:5]:
                    console.print(f"  - {f}")
                if len(gaps["missing_extractions"]) > 5:
                    console.print(
                        f"  ... and {len(gaps['missing_extractions']) - 5} more"
                    )

            if gaps["missing_fusions"]:
                console.print("\n[bold]Documents missing fusion:[/bold]")
                for d in gaps["missing_fusions"][:5]:
                    console.print(
                        f"  - {d['company_code']} ({d['doc_type']}, {d['doc_date']})"
                    )
                if len(gaps["missing_fusions"]) > 5:
                    console.print(f"  ... and {len(gaps['missing_fusions']) - 5} more")

            return

        # Process gaps
        total_gaps = (
            self.stats["missing_extractions"]
            + self.stats["missing_fusions"]
            + self.stats["missing_vectors"]
        )

        if total_gaps == 0:
            console.print("\n[green]✅ Pipeline is complete! No gaps found.[/green]")
            return

        console.print(f"\n[bold]Processing {total_gaps} gaps...[/bold]")

        # Process in order
        await self.process_missing_extractions(
            gaps["missing_extractions"], parallel_workers, force_reextract
        )
        await self.process_missing_fusions(gaps["missing_fusions"])
        await self.process_missing_vectors(gaps["missing_vectors"])

        # Display results
        console.print("\n[bold]=== COMPLETION RESULTS ===[/bold]")

        results_table = Table()
        results_table.add_column("Metric", style="cyan")
        results_table.add_column("Count", style="green")

        results_table.add_row(
            "Documents Extracted", str(self.stats["documents_processed"])
        )
        results_table.add_row("Fusions Completed", str(self.stats["fusions_completed"]))
        results_table.add_row("Vectors Created", str(self.stats["vectors_created"]))

        console.print(results_table)

        console.print("\n[green]✅ Pipeline completion finished![/green]")


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Analyze gaps without processing",
)
@click.option(
    "--parallel-workers",
    type=int,
    default=20,
    help="Number of parallel workers for LLM extraction (default: 20)",
)
@click.option(
    "--force-reextract",
    is_flag=True,
    help="Force re-extraction of all files, ignoring database records",
)
def main(dry_run, parallel_workers, force_reextract):
    """Complete any gaps in the document processing pipeline."""
    completer = PipelineCompleter()
    asyncio.run(completer.run(dry_run, parallel_workers, force_reextract))


if __name__ == "__main__":
    main()
