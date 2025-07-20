#!/usr/bin/env python3
"""Batch document extraction CLI for processing multiple files."""

import sys
from pathlib import Path

import click
import structlog
from rich.console import Console
from rich.table import Table

from src.application.use_cases.batch_extract_documents import (
    BatchExtractDocumentsUseCase,
)
from src.infrastructure.llm import GeminiLLMAdapter
from src.shared.config.settings import Settings

# Configure structured logging
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
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
console = Console()


def format_batch_results(results: dict) -> Table:
    """Format batch processing results as a rich table."""
    table = Table(title="Batch Processing Results", show_header=True)
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Value", style="green")

    table.add_row("Total Files", str(results["total_files"]))
    table.add_row("Processed", str(results["processed"]))
    table.add_row("Successful", str(results["successful"]))
    table.add_row("Failed", str(results["failed"]))
    table.add_row("Total Time", f"{results['total_time_seconds']:.1f}s")
    table.add_row("Avg Time/File", f"{results['average_time_per_file']:.1f}s")

    if results["failed"] > 0:
        table.add_row("", "")  # Empty row
        table.add_row("[red]Failed Files[/red]", "")
        for file_path, error in list(results["failed_files"].items())[:10]:
            table.add_row(f"  {Path(file_path).name}", f"[red]{error[:50]}...[/red]")
        if len(results["failed_files"]) > 10:
            table.add_row(
                "  ...", f"[red]({len(results['failed_files']) - 10} more)[/red]"
            )

    return table


@click.command()
@click.argument("directory", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--document-type",
    type=click.Choice(["annual_report", "research_report"]),
    required=True,
    help="Type of documents to extract",
)
@click.option(
    "--pattern",
    default="*.txt",
    help="File pattern to match (default: *.txt)",
)
@click.option(
    "--no-resume",
    is_flag=True,
    help="Start fresh, don't resume from checkpoint",
)
@click.option(
    "--max-files",
    type=int,
    help="Maximum number of files to process",
)
@click.option(
    "--skip-archive",
    is_flag=True,
    help="Skip archiving extraction results to database",
)
def batch_extract(
    directory: Path,
    document_type: str,
    pattern: str,
    no_resume: bool,
    max_files: int | None,
    skip_archive: bool,
) -> None:
    """Batch extract structured data from multiple financial documents.

    This command processes all matching files in a directory using concurrent
    LLM calls with rate limiting and progress tracking.

    Example:
        $ python -m src.interfaces.cli.batch_extract ./reports \\
            --document-type annual_report --pattern "*.txt"
    """
    try:
        # Find all matching files
        file_paths = list(directory.glob(pattern))

        if not file_paths:
            console.print(
                f"[yellow]No files found matching pattern: {pattern}[/yellow]"
            )
            sys.exit(0)

        # Apply max files limit if specified
        if max_files:
            file_paths = file_paths[:max_files]

        console.print(f"[cyan]Found {len(file_paths)} files to process[/cyan]")

        # Initialize components
        settings = Settings()

        # Validate settings
        if not settings.llm.gemini_api_key.get_secret_value():
            console.print(
                "[red]Error: GEMINI_API_KEY environment variable not set[/red]"
            )
            sys.exit(1)

        # Show batch configuration
        console.print("\n[bold]Batch Configuration:[/bold]")
        console.print(f"  Concurrent calls: {settings.llm.batch_size}")
        console.print(f"  Rate limit: {settings.llm.rate_limit_per_minute} calls/min")
        console.print(f"  Worker threads: {settings.llm.max_workers}")
        console.print(
            f"  Checkpoint interval: {settings.batch_checkpoint_interval} files"
        )
        console.print(f"  Resume enabled: {not no_resume}\n")

        # Initialize batch processor with optional archive repository
        llm_service = GeminiLLMAdapter(settings)

        # Process files
        import asyncio

        async def run_batch_extraction():
            """Run batch extraction with proper async initialization."""
            # Pass None for archive_repository - the batch processor will handle
            # creating archive use cases with proper session management
            batch_processor = BatchExtractDocumentsUseCase(
                llm_service,
                settings,
                archive_repository=None,  # Will be handled per-file
                skip_archive=skip_archive,
            )

            return await batch_processor.execute(
                file_paths=file_paths,
                document_type=document_type,
                resume=not no_resume,
            )

        results = asyncio.run(run_batch_extraction())

        # Display results
        console.print("\n")
        console.print(format_batch_results(results))

        # Exit with appropriate code
        if results["failed"] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Batch processing cancelled by user[/yellow]")
        sys.exit(130)

    except Exception as e:
        logger.error(
            "Unexpected error in batch processing", error=str(e), exc_info=True
        )
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    batch_extract()
