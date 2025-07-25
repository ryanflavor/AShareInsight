#!/usr/bin/env python3
"""Document extraction CLI interface.

This module provides a command-line interface for extracting structured data
from financial documents using LLM services.
"""

import logging
import sys
import time
from pathlib import Path

import click
import structlog
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from src.application.use_cases.extract_document_data import ExtractDocumentDataUseCase
from src.infrastructure.document_processing.loader import DocumentLoader
from src.infrastructure.llm import GeminiLLMAdapter
from src.shared.config.settings import Settings
from src.shared.exceptions import (
    DocumentProcessingError,
    LLMServiceError,
)
from src.shared.exceptions import (
    ValidationError as AppValidationError,
)
from src.shared.utils.timezone import now_china

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


def setup_logging(debug: bool) -> None:
    """Configure logging based on debug mode."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


def format_extraction_result(result) -> Table:
    """Format extraction result as a rich table."""
    table = Table(title="Extraction Result", show_header=True, header_style="bold cyan")
    table.add_column("Field", style="green", width=30)
    table.add_column("Value", style="white")

    # Basic info
    # Handle both enum and string document_type
    doc_type_value = (
        result.document_type.value
        if hasattr(result.document_type, "value")
        else result.document_type
    )
    table.add_row("Document Type", doc_type_value)
    if hasattr(result, "extraction_metadata") and result.extraction_metadata:
        table.add_row(
            "Processing Time",
            f"{result.extraction_metadata.processing_time_seconds:.2f}s",
        )
        # Model info
        if result.extraction_metadata.model_version:
            table.add_row("Model Version", result.extraction_metadata.model_version)
        if result.extraction_metadata.prompt_version:
            table.add_row("Prompt Version", result.extraction_metadata.prompt_version)

        # Token usage
        if result.extraction_metadata.token_usage:
            table.add_row(
                "Token Usage",
                (
                    f"In: "
                    f"{result.extraction_metadata.token_usage.get('input_tokens', 0)}, "
                    f"Out: "
                    f"{result.extraction_metadata.token_usage.get('output_tokens', 0)}"
                ),
            )

    # Company/Report info - handle both extraction_data and extracted_data
    data = getattr(result, "extraction_data", None) or getattr(
        result, "extracted_data", None
    )
    if data:
        if hasattr(data, "company_name_full"):
            table.add_row("Company Name", data.company_name_full)
        if hasattr(data, "company_code"):
            table.add_row("Company Code", data.company_code)
        if hasattr(data, "exchange"):
            table.add_row("Exchange", data.exchange)
        if hasattr(data, "business_concepts"):
            table.add_row(
                "Business Concepts",
                str(len(data.business_concepts)),
            )
        if hasattr(data, "report_title"):
            table.add_row("Report Title", data.report_title)
        if hasattr(data, "investment_rating"):
            table.add_row("Investment Rating", data.investment_rating)

    return table


def save_result_to_file(result, output_path: Path | None) -> Path:
    """Save extraction result to JSON file."""
    if output_path is None:
        timestamp = now_china().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"extraction_result_{timestamp}.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return output_path


@click.command()
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--document-type",
    type=click.Choice(["annual_report", "research_report"]),
    required=True,
    help="Type of document to extract",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path for JSON result",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable progress indicators",
)
@click.option(
    "--skip-archive",
    is_flag=True,
    help="Skip archiving extraction result to database",
)
def extract_document(
    file_path: Path,
    document_type: str,
    output: Path | None,
    debug: bool,
    no_progress: bool,
    skip_archive: bool,
) -> None:
    """Extract structured data from financial documents using LLM.

    This command processes a document file and extracts structured information
    using Gemini LLM API. The extraction may take 2-3 minutes for large documents.

    Example:
        $ python -m src.interfaces.cli.extract_document report.txt \
            --document-type annual_report

    """
    setup_logging(debug)

    try:
        # Initialize components
        logger.info("Initializing document extraction", file_path=str(file_path))
        settings = Settings()

        # Validate settings
        if not settings.llm.gemini_api_key.get_secret_value():
            console.print(
                "[red]Error: GEMINI_API_KEY environment variable not set[/red]"
            )
            sys.exit(1)

        # Create progress context
        progress_context = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeRemainingColumn(),
            console=console,
            disable=no_progress,
        )

        with progress_context as progress:
            # Load document
            task_load = progress.add_task("[cyan]Loading document...", total=None)
            loader = DocumentLoader()
            document = loader.load(file_path)
            progress.update(task_load, completed=100)

            # Initialize LLM service
            task_init = progress.add_task(
                "[cyan]Initializing LLM service...", total=None
            )
            llm_service = GeminiLLMAdapter(settings)

            # Initialize use case (archive repository will be set up in async context)
            use_case = ExtractDocumentDataUseCase(llm_service, None)
            progress.update(task_init, completed=100)

            # Extract data
            task_extract = progress.add_task(
                "[yellow]Calling LLM API (this may take 2-3 minutes)...", total=None
            )

            start_time = time.time()
            logger.info(
                "Starting LLM extraction",
                document_type=document_type,
                file_size=len(document.content),
            )

            # Run async execute method
            async def run_extraction():
                # Set up archive repository in async context if needed
                if not skip_archive:
                    from src.infrastructure.persistence.postgres.connection import (
                        get_session,
                    )
                    from src.infrastructure.persistence.postgres.source_document_repository import (  # noqa: E501
                        PostgresSourceDocumentRepository,
                    )

                    async with get_session() as session:
                        repo = PostgresSourceDocumentRepository(session)
                        from src.application.use_cases.archive_extraction_result import (  # noqa: E501
                            ArchiveExtractionResultUseCase,
                        )

                        use_case.archive_use_case = ArchiveExtractionResultUseCase(repo)

                        return await use_case.execute(
                            file_path=str(file_path),
                            company_name=None,
                            document_type_override=document_type,
                        )
                else:
                    return await use_case.execute(
                        file_path=str(file_path),
                        company_name=None,
                        document_type_override=document_type,
                    )

            # Run the async function
            import asyncio

            result = asyncio.run(run_extraction())

            elapsed_time = time.time() - start_time
            progress.update(task_extract, completed=100)

            logger.info(
                "Extraction completed",
                elapsed_time=f"{elapsed_time:.2f}s",
            )

        # Display results (if we get here, extraction was successful)
        console.print(
            f"\n[green]✓ Extraction completed successfully "
            f"in {elapsed_time:.2f}s[/green]\n"
        )
        console.print(format_extraction_result(result))

        # Save to file
        output_file = save_result_to_file(result, output)
        console.print(f"[cyan]Result saved to:[/cyan] {output_file}")

    except DocumentProcessingError as e:
        logger.error("Document processing error", error=str(e))
        console.print(f"[red]Document processing error: {e}[/red]")
        sys.exit(1)

    except LLMServiceError as e:
        logger.error("LLM service error", error=str(e))
        console.print(f"[red]LLM service error: {e}[/red]")
        if debug:
            console.print("[yellow]Check your API key and network connection[/yellow]")
        sys.exit(1)

    except (ValidationError, AppValidationError) as e:
        logger.error("Validation error", error=str(e))
        console.print(f"[red]Validation error: {e}[/red]")
        if debug:
            console.print(
                "[yellow]The LLM output did not match expected format[/yellow]"
            )
        sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(130)

    except Exception as e:
        logger.exception("Unexpected error occurred")
        console.print(f"[red]Unexpected error: {e}[/red]")
        if debug:
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    extract_document()
