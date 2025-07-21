#!/usr/bin/env python3
"""
Batch extraction script for processing 5000+ company documents.
Supports parallel processing, resume capability, and comprehensive logging.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from structlog import get_logger

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.application.use_cases.extract_document_data import ExtractDocumentDataUseCase
from src.infrastructure.llm import GeminiLLMAdapter
from src.shared.config.settings import get_settings

logger = get_logger(__name__)
console = Console()


class DocumentScanner:
    """Scans data directory for documents to process."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.annual_reports_dir = data_dir / "annual_reports"
        self.research_reports_dir = data_dir / "research_reports"
        self.extracted_dir = data_dir / "extracted"

    def scan_documents(self) -> tuple[list[Path], list[Path]]:
        """Scan for all documents that need processing."""
        annual_reports = []
        research_reports = []

        # Scan annual reports
        for year_dir in sorted(self.annual_reports_dir.glob("*")):
            if year_dir.is_dir():
                for doc in year_dir.glob("*.md"):
                    if not self._is_processed(doc, "annual_reports"):
                        annual_reports.append(doc)
                for doc in year_dir.glob("*.txt"):
                    if not self._is_processed(doc, "annual_reports"):
                        annual_reports.append(doc)

        # Scan research reports
        for year_dir in sorted(self.research_reports_dir.glob("*")):
            if year_dir.is_dir():
                for doc in year_dir.glob("*.md"):
                    if not self._is_processed(doc, "research_reports"):
                        research_reports.append(doc)
                for doc in year_dir.glob("*.txt"):
                    if not self._is_processed(doc, "research_reports"):
                        research_reports.append(doc)

        return annual_reports, research_reports

    def _is_processed(self, doc_path: Path, doc_type: str) -> bool:
        """Check if document has already been processed."""
        # First check exact filename match
        extracted_file = (
            self.extracted_dir / doc_type / f"{doc_path.stem}_extracted.json"
        )
        if extracted_file.exists():
            return True

        # Also check if same company/year already processed
        # This prevents processing duplicates with different filenames
        import re

        filename = doc_path.stem

        # Extract company name and year from filename
        # Pattern 1: {stock_code}_{company}_{year}_...
        match = re.match(r"^\d{6}_(.+?)_(\d{4})_", filename)
        if match:
            company, year = match.groups()
        else:
            # Pattern 2: {company}_{year}年...
            match = re.match(r"^(.+?)_(\d{4})年", filename)
            if match:
                company, year = match.groups()
            else:
                return False

        # Check if any file with same company and year exists
        extracted_dir = self.extracted_dir / doc_type
        if extracted_dir.exists():
            for existing in extracted_dir.glob("*.json"):
                if f"_{company}_" in existing.stem and f"_{year}_" in existing.stem:
                    logger.info(
                        f"Skip {filename}: already processed as {existing.name}"
                    )
                    return True

        return False


class ProcessingTracker:
    """Tracks processing progress and maintains metadata."""

    def __init__(self, metadata_dir: Path):
        self.metadata_dir = metadata_dir
        self.document_index_path = metadata_dir / "document_index.json"
        self.processing_log_path = metadata_dir / "processing_log.json"
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._load_metadata()

    def _load_metadata(self):
        """Load existing metadata."""
        if self.document_index_path.exists():
            with open(self.document_index_path, encoding="utf-8") as f:
                self.document_index = json.load(f)
        else:
            self.document_index = {
                "documents": [],
                "total_count": 0,
                "last_updated": datetime.now().isoformat(),
                "schema_version": "1.0",
            }

        if self.processing_log_path.exists():
            with open(self.processing_log_path, encoding="utf-8") as f:
                self.processing_log = json.load(f)
        else:
            self.processing_log = {
                "processing_sessions": [],
                "statistics": {
                    "total_processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "pending": 0,
                },
                "last_updated": datetime.now().isoformat(),
            }

    def start_session(self, total_documents: int):
        """Start a new processing session."""
        session = {
            "session_id": self.session_id,
            "start_time": datetime.now().isoformat(),
            "total_documents": total_documents,
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "documents": [],
        }
        self.processing_log["processing_sessions"].append(session)
        self._save_processing_log()

    def record_result(
        self,
        doc_path: Path,
        doc_type: str,
        success: bool,
        processing_time: float,
        error_msg: str | None = None,
    ):
        """Record processing result for a document."""
        # Update current session
        current_session = self.processing_log["processing_sessions"][-1]
        current_session["processed"] += 1
        if success:
            current_session["successful"] += 1
        else:
            current_session["failed"] += 1

        doc_record = {
            "file_path": str(doc_path),
            "document_type": doc_type,
            "success": success,
            "processing_time": processing_time,
            "timestamp": datetime.now().isoformat(),
            "error": error_msg,
        }
        current_session["documents"].append(doc_record)

        # Update document index if successful
        if success:
            self._add_to_document_index(doc_path, doc_type)

        # Update global statistics
        self.processing_log["statistics"]["total_processed"] += 1
        if success:
            self.processing_log["statistics"]["successful"] += 1
        else:
            self.processing_log["statistics"]["failed"] += 1

        self._save_metadata()

    def _add_to_document_index(self, doc_path: Path, doc_type: str):
        """Add document to index."""
        doc_entry = {
            "document_id": f"{doc_type}_{doc_path.stem}",
            "file_path": str(doc_path),
            "document_type": doc_type,
            "extracted_path": f"extracted/{doc_type}/{doc_path.stem}_extracted.json",
            "added_date": datetime.now().isoformat(),
        }
        self.document_index["documents"].append(doc_entry)
        self.document_index["total_count"] += 1
        self.document_index["last_updated"] = datetime.now().isoformat()

    def _save_metadata(self):
        """Save all metadata."""
        self._save_document_index()
        self._save_processing_log()

    def _save_document_index(self):
        """Save document index."""
        with open(self.document_index_path, "w", encoding="utf-8") as f:
            json.dump(self.document_index, f, ensure_ascii=False, indent=2)

    def _save_processing_log(self):
        """Save processing log."""
        self.processing_log["last_updated"] = datetime.now().isoformat()
        with open(self.processing_log_path, "w", encoding="utf-8") as f:
            json.dump(self.processing_log, f, ensure_ascii=False, indent=2)

    def get_summary(self) -> dict:
        """Get processing summary."""
        current_session = self.processing_log["processing_sessions"][-1]
        return {
            "session_id": self.session_id,
            "processed": current_session["processed"],
            "successful": current_session["successful"],
            "failed": current_session["failed"],
            "global_stats": self.processing_log["statistics"],
        }


async def process_single_document(
    doc_path: Path,
    doc_type: str,
    use_case: ExtractDocumentDataUseCase,
    tracker: ProcessingTracker,
    progress: Progress,
    task_id: TaskID,
) -> None:
    """Process a single document."""
    try:
        # Extract data
        start_time = datetime.now()
        result = await use_case.execute(
            file_path=doc_path,
            document_type_override=doc_type,
        )
        processing_time = (datetime.now() - start_time).total_seconds()

        # Save result - map singular to plural for directory
        dir_mapping = {
            "annual_report": "annual_reports",
            "research_report": "research_reports",
        }
        save_dir = dir_mapping.get(doc_type, doc_type)
        output_dir = Path("data/extracted") / save_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{doc_path.stem}_extracted.json"

        # Convert ExtractionResult to dict for saving
        try:
            # Handle document_type - it might be an enum
            doc_type_value = result.document_type
            if hasattr(doc_type_value, "value"):
                doc_type_value = doc_type_value.value

            result_data = {
                "document_type": doc_type_value,
                "extraction_data": result.extraction_data.model_dump(mode="json"),
                "extraction_metadata": result.extraction_metadata.model_dump(
                    mode="json"
                ),
                "raw_llm_response": result.raw_llm_response,
            }
        except Exception as e:
            logger.error(f"Error converting result to dict: {e}")
            logger.error(f"Result type: {type(result)}")
            logger.error(
                f"Document type: {result.document_type}, type: {type(result.document_type)}"
            )
            logger.error(f"Extraction data type: {type(result.extraction_data)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        # Record success
        tracker.record_result(doc_path, doc_type, True, processing_time)
        progress.update(task_id, advance=1)
        logger.info(f"Successfully processed: {doc_path.name}")

    except Exception as e:
        import traceback

        full_error = traceback.format_exc()
        logger.error(f"Failed to process {doc_path}", error=str(e))
        logger.error(f"Full traceback:\n{full_error}")
        tracker.record_result(doc_path, doc_type, False, 0, str(e))
        progress.update(task_id, advance=1)


async def process_document_batch(
    documents: list[tuple[Path, str]],
    batch_size: int,
    rate_limit_delay: float,
    tracker: ProcessingTracker,
    progress: Progress,
    task_id: TaskID,
) -> None:
    """Process a batch of documents in parallel."""
    settings = get_settings()
    llm_service = GeminiLLMAdapter(settings)
    use_case = ExtractDocumentDataUseCase(llm_service)

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]

        # Process all documents in the batch concurrently
        logger.info(f"Processing batch of {len(batch)} documents in parallel")
        tasks = [
            process_single_document(
                doc_path, doc_type, use_case, tracker, progress, task_id
            )
            for doc_path, doc_type in batch
        ]

        # Wait for all tasks in the batch to complete
        await asyncio.gather(*tasks)

        # Rate limiting between batches
        if i + batch_size < len(documents):
            logger.info(
                f"Rate limiting: waiting {rate_limit_delay} seconds before next batch"
            )
            await asyncio.sleep(rate_limit_delay)


@click.command()
@click.option(
    "--data-dir",
    type=click.Path(exists=True),
    default="data",
    help="Data directory containing documents",
)
@click.option(
    "--batch-size",
    type=int,
    default=5,
    help="Number of documents to process in parallel",
)
@click.option(
    "--rate-limit-delay",
    type=float,
    default=30.0,
    help="Delay in seconds between batches (for rate limiting)",
)
@click.option(
    "--max-documents",
    type=int,
    default=None,
    help="Maximum number of documents to process (for testing)",
)
@click.option("--dry-run", is_flag=True, help="Scan documents without processing")
def main(
    data_dir: str,
    batch_size: int,
    rate_limit_delay: float,
    max_documents: int | None,
    dry_run: bool,
):
    """Batch process all company documents for LLM extraction."""

    data_path = Path(data_dir)
    if not data_path.exists():
        console.print("[red]Error: Data directory not found![/red]")
        return

    # Initialize components
    scanner = DocumentScanner(data_path)
    tracker = ProcessingTracker(data_path / "metadata")

    # Scan for documents
    console.print("[cyan]Scanning for documents...[/cyan]")
    console.print(f"[dim]Data directory: {data_path.absolute()}[/dim]")
    console.print(
        f"[dim]Annual reports dir exists: {(data_path / 'annual_reports').exists()}[/dim]"
    )
    console.print(
        f"[dim]Research reports dir exists: {(data_path / 'research_reports').exists()}[/dim]"
    )
    annual_reports, research_reports = scanner.scan_documents()

    # Apply max_documents limit if specified
    if max_documents:
        annual_reports = annual_reports[: max_documents // 2]
        research_reports = research_reports[: max_documents // 2]

    total_documents = len(annual_reports) + len(research_reports)

    # Display summary
    table = Table(title="Documents to Process")
    table.add_column("Document Type", style="cyan")
    table.add_column("Count", style="green")
    table.add_row("Annual Reports", str(len(annual_reports)))
    table.add_row("Research Reports", str(len(research_reports)))
    table.add_row("Total", str(total_documents), style="bold")
    console.print(table)

    if dry_run:
        console.print("\n[yellow]Dry run mode - no processing will occur[/yellow]")
        return

    if total_documents == 0:
        console.print("\n[yellow]No documents to process![/yellow]")
        return

    # Estimate processing time
    avg_annual_report_time = 90  # seconds
    avg_research_report_time = 45  # seconds
    estimated_time = (
        len(annual_reports) * avg_annual_report_time
        + len(research_reports) * avg_research_report_time
    )
    estimated_hours = estimated_time / 3600

    console.print(
        f"\n[yellow]Estimated processing time: {estimated_hours:.1f} hours[/yellow]"
    )
    console.print(f"[yellow]Estimated cost: ${total_documents * 0.30:.2f}[/yellow]")

    if not click.confirm("\nProceed with extraction?"):
        return

    # Start processing
    tracker.start_session(total_documents)

    # Prepare document list with types
    all_documents = [(p, "annual_report") for p in annual_reports] + [
        (p, "research_report") for p in research_reports
    ]

    # Process documents with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Processing {total_documents} documents...", total=total_documents
        )

        # Run async processing
        asyncio.run(
            process_document_batch(
                all_documents, batch_size, rate_limit_delay, tracker, progress, task
            )
        )

    # Display summary
    summary = tracker.get_summary()

    console.print("\n[bold green]Processing Complete![/bold green]")
    table = Table(title="Session Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Session ID", summary["session_id"])
    table.add_row("Documents Processed", str(summary["processed"]))
    table.add_row("Successful", str(summary["successful"]))
    table.add_row("Failed", str(summary["failed"]))
    console.print(table)

    console.print("\n[bold]Global Statistics:[/bold]")
    global_stats = summary["global_stats"]
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total Processed", str(global_stats["total_processed"]))
    table.add_row("Total Successful", str(global_stats["successful"]))
    table.add_row("Total Failed", str(global_stats["failed"]))
    console.print(table)


if __name__ == "__main__":
    main()
