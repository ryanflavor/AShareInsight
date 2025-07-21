#!/usr/bin/env python3
"""Smart incremental extraction script that handles all edge cases automatically.

This unified script:
1. Automatically processes documents in the correct order (annual reports first)
2. Handles missing companies gracefully (skips archiving for research reports)
3. Retries with alternative document type on validation errors
4. Provides comprehensive reporting of all processing results
"""

import asyncio
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import structlog
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.application.use_cases.extract_document_data import ExtractDocumentDataUseCase
from src.infrastructure.document_processing.company_info_extractor import (
    CompanyInfoExtractor,
)
from src.infrastructure.llm.gemini_llm_adapter import GeminiLLMAdapter
from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)
from src.shared.config.settings import Settings

logger = structlog.get_logger()
console = Console()


class SmartIncrementalExtractor:
    """Unified extractor that handles all document processing intelligently."""

    def __init__(self):
        self.settings = Settings()
        self.llm_service = GeminiLLMAdapter(self.settings)
        self.company_extractor = CompanyInfoExtractor()

        # Track processing results
        self.results = {
            "success": [],
            "skipped_archive": [],
            "failed": [],
            "skipped_duplicate": [],
            "fallback_used": {},
        }

        # Cache for processed combinations and existing companies
        self.processed_combinations: set[tuple[str, str, int]] = set()
        self.existing_companies: set[str] = set()

    async def load_existing_data(self) -> None:
        """Load existing companies and processed documents from database."""
        async with get_session() as session:
            repository = PostgresSourceDocumentRepository(session)

            # Load existing companies
            from sqlalchemy import select

            from src.infrastructure.persistence.postgres.models import (
                CompanyModel,
                SourceDocumentModel,
            )

            # Get all company codes
            company_stmt = select(CompanyModel.company_code)
            company_result = await session.execute(company_stmt)
            self.existing_companies = {row[0] for row in company_result}

            # Get all processed combinations
            from sqlalchemy import extract

            doc_stmt = select(
                SourceDocumentModel.company_code,
                SourceDocumentModel.doc_type,
                extract("year", SourceDocumentModel.doc_date).label("year"),
            ).distinct()

            doc_result = await session.execute(doc_stmt)
            for row in doc_result:
                if row.company_code:
                    self.processed_combinations.add(
                        (row.company_code, row.doc_type, int(row.year))
                    )

        logger.info(
            f"Loaded {len(self.existing_companies)} existing companies and "
            f"{len(self.processed_combinations)} processed documents"
        )

    def extract_company_info(self, file_path: Path) -> tuple[str | None, int | None]:
        """Extract company code and year from file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            info = self.company_extractor.extract_info(file_path, content)
            return info["code"], info["year"]
        except Exception as e:
            logger.warning(f"Failed to extract info from {file_path}: {e}")
            return None, None

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def find_all_documents(self) -> tuple[list, list]:
        """Find all new documents, separated into annual and research reports.

        Returns:
            Tuple of (annual_reports, research_reports) lists
        """
        annual_reports = []
        research_reports = []

        # Get processed file hashes
        processed_hashes = set()
        async with get_session() as session:
            repository = PostgresSourceDocumentRepository(session)
            processed_hashes = await repository.get_all_file_hashes()

        # Also check for existing extracted JSON files
        extracted_files = set()
        for extracted_dir in [
            "data/extracted/annual_reports",
            "data/extracted/research_reports",
        ]:
            extracted_path = Path(extracted_dir)
            if extracted_path.exists():
                for json_file in extracted_path.glob("*.json"):
                    # Extract base name without extension to match with source files
                    base_name = json_file.stem.replace("_extracted", "")
                    extracted_files.add(base_name)

        # Scan both directories
        for base_dir, doc_type in [
            ("data/annual_reports", "annual_report"),
            ("data/research_reports", "research_report"),
        ]:
            scan_dir = Path(base_dir)
            if not scan_dir.exists():
                continue

            for pattern in ["**/*.md", "**/*.txt"]:
                for file_path in scan_dir.glob(pattern):
                    if not file_path.is_file():
                        continue

                    # Skip if already processed by hash
                    file_hash = self._calculate_file_hash(file_path)
                    if file_hash in processed_hashes:
                        continue

                    # Skip if already extracted to JSON
                    file_stem = file_path.stem
                    if file_stem in extracted_files:
                        logger.info(
                            f"Skipping {file_path.name} - already extracted to JSON"
                        )
                        self.results["skipped_duplicate"].append(
                            {
                                "path": file_path,
                                "reason": "Already extracted to JSON",
                            }
                        )
                        continue

                    # Extract company info
                    company_code, year = self.extract_company_info(file_path)

                    # Check if combination already exists
                    if company_code and year:
                        combination = (company_code, doc_type, year)
                        if combination in self.processed_combinations:
                            self.results["skipped_duplicate"].append(
                                {
                                    "path": file_path,
                                    "reason": f"Already have {doc_type} for {company_code} in {year}",
                                }
                            )
                            continue

                    # Add to appropriate list
                    doc_info = {
                        "path": file_path,
                        "company_code": company_code,
                        "year": year,
                        "doc_type": doc_type,
                        "size": file_path.stat().st_size,
                    }

                    if doc_type == "annual_report":
                        annual_reports.append(doc_info)
                    else:
                        research_reports.append(doc_info)

        return annual_reports, research_reports

    async def extract_document_smart(self, doc_info: dict) -> bool:
        """Extract a single document with smart fallback and error handling.

        Returns:
            bool: True if successful, False otherwise
        """
        file_path = doc_info["path"]
        initial_type = doc_info["doc_type"]
        company_code = doc_info["company_code"]

        # For research reports without company records, note it
        if (
            initial_type == "research_report"
            and company_code
            and company_code not in self.existing_companies
        ):
            logger.info(
                f"Research report {file_path.name} for company {company_code} "
                f"will proceed without archiving (company not in database)"
            )

        # Try extraction with initial type, then fallback if needed
        types_to_try = [initial_type]
        if initial_type == "annual_report":
            types_to_try.append("research_report")
        else:
            types_to_try.append("annual_report")

        for doc_type_str in types_to_try:
            try:
                logger.info(
                    "attempting_extraction",
                    path=str(file_path),
                    doc_type=doc_type_str,
                    attempt=types_to_try.index(doc_type_str) + 1,
                )

                async with get_session() as session:
                    archive_repository = PostgresSourceDocumentRepository(session)
                    extract_use_case = ExtractDocumentDataUseCase(
                        self.llm_service, archive_repository
                    )

                    result = await extract_use_case.execute(
                        file_path,
                        document_type_override=doc_type_str,
                    )

                    # Success!
                    if doc_type_str != initial_type:
                        self.results["fallback_used"][str(file_path)] = doc_type_str

                    # Check if it was a research report without company
                    if (
                        doc_type_str == "research_report"
                        and company_code
                        and company_code not in self.existing_companies
                    ):
                        self.results["skipped_archive"].append(
                            {
                                "path": file_path,
                                "company_code": company_code,
                                "reason": "Company not in database",
                            }
                        )
                    else:
                        self.results["success"].append(
                            {
                                "path": file_path,
                                "doc_type": doc_type_str,
                                "company_code": company_code,
                            }
                        )

                    # If it's an annual report, add company to our cache
                    if doc_type_str == "annual_report" and company_code:
                        self.existing_companies.add(company_code)

                    return True

            except Exception as e:
                error_str = str(e)

                # Check if it's a validation error that might be fixed by trying another type
                if (
                    any(
                        indicator in error_str
                        for indicator in [
                            "validation error",
                            "Validation failed",
                            "company_name_full",
                            "JSON structure doesn't match",
                        ]
                    )
                    and types_to_try.index(doc_type_str) < len(types_to_try) - 1
                ):
                    logger.warning(
                        "validation_error_trying_fallback",
                        path=str(file_path),
                        doc_type=doc_type_str,
                        error=error_str[:200],
                    )
                    continue
                else:
                    # Final failure
                    logger.error(
                        "extraction_failed",
                        path=str(file_path),
                        error=error_str,
                    )
                    self.results["failed"].append(
                        {
                            "path": file_path,
                            "error": error_str[:200],
                            "doc_type": doc_type_str,
                        }
                    )
                    return False

        return False

    async def run(self, dry_run: bool = False) -> None:
        """Run the smart extraction process."""
        console.print("\n[bold cyan]=== SMART INCREMENTAL EXTRACTION ===[/bold cyan]\n")

        # Load existing data
        console.print("Loading existing data from database...")
        await self.load_existing_data()

        # Find all documents
        console.print("Scanning for new documents...")
        annual_reports, research_reports = await self.find_all_documents()

        total_docs = len(annual_reports) + len(research_reports)

        if total_docs == 0:
            console.print("\n[green]No new documents to process![/green]")
            self._display_summary()
            return

        # Display what will be processed
        console.print(f"\n[bold]Found {total_docs} new documents:[/bold]")
        console.print(f"  • Annual Reports: {len(annual_reports)}")
        console.print(f"  • Research Reports: {len(research_reports)}")

        if dry_run:
            self._display_documents_table(annual_reports + research_reports)
            console.print("\n[yellow]Dry run mode - no extraction performed[/yellow]")
            return

        # Process documents in order: annual reports first
        all_documents = annual_reports + research_reports

        console.print(
            f"\n[bold]Processing {len(all_documents)} documents "
            f"(annual reports first)...[/bold]\n"
        )

        # Process with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Extracting documents...", total=len(all_documents)
            )

            # Process documents with limited concurrency
            semaphore = asyncio.Semaphore(5)  # Max 5 concurrent

            async def process_with_limit(doc_info):
                async with semaphore:
                    return await self.extract_document_smart(doc_info)

            # Create tasks
            tasks = [process_with_limit(doc) for doc in all_documents]

            # Process and update progress
            for coro in asyncio.as_completed(tasks):
                await coro
                progress.advance(task)

        # Display comprehensive summary
        self._display_summary()

    def _display_documents_table(self, documents: list) -> None:
        """Display a table of documents to be processed."""
        table = Table(title="Documents to Process")
        table.add_column("Type", style="cyan")
        table.add_column("Path", style="yellow")
        table.add_column("Company", style="green")
        table.add_column("Year", style="blue")
        table.add_column("Size", style="magenta")

        for doc in documents:
            table.add_row(
                doc["doc_type"].replace("_", " ").title(),
                doc["path"].name,
                doc["company_code"] or "Unknown",
                str(doc["year"]) if doc["year"] else "Unknown",
                f"{doc['size'] / 1024:.1f} KB",
            )

        console.print(table)

    def _display_summary(self) -> None:
        """Display comprehensive processing summary."""
        console.print("\n[bold]=== PROCESSING SUMMARY ===[/bold]\n")

        # Overall stats
        total_processed = (
            len(self.results["success"])
            + len(self.results["skipped_archive"])
            + len(self.results["failed"])
        )

        console.print(f"[bold]Total Processed:[/bold] {total_processed}")
        console.print(f"  ✅ Successful: {len(self.results['success'])}")
        console.print(
            f"  ⚠️  Extracted without archiving: {len(self.results['skipped_archive'])}"
        )
        console.print(f"  ❌ Failed: {len(self.results['failed'])}")
        console.print(f"  🔄 Used fallback type: {len(self.results['fallback_used'])}")
        console.print(
            f"  ⏭️  Skipped (duplicates): {len(self.results['skipped_duplicate'])}"
        )

        # Show details for each category
        if self.results["skipped_archive"]:
            console.print("\n[yellow]Documents extracted without archiving:[/yellow]")
            table = Table()
            table.add_column("File", style="cyan")
            table.add_column("Company", style="yellow")
            table.add_column("Reason", style="red")

            for doc in self.results["skipped_archive"]:
                table.add_row(
                    doc["path"].name,
                    doc["company_code"],
                    doc["reason"],
                )
            console.print(table)

            console.print(
                "\n💡 [yellow]To archive these research reports, "
                "add annual reports for the missing companies first.[/yellow]"
            )

        if self.results["failed"]:
            console.print("\n[red]Failed extractions:[/red]")
            table = Table()
            table.add_column("File", style="cyan")
            table.add_column("Type", style="yellow")
            table.add_column("Error", style="red")

            for doc in self.results["failed"]:
                table.add_row(
                    doc["path"].name,
                    doc["doc_type"],
                    doc["error"],
                )
            console.print(table)

        if self.results["fallback_used"]:
            console.print("\n[blue]Documents that used fallback type:[/blue]")
            table = Table()
            table.add_column("File", style="cyan")
            table.add_column("Final Type", style="yellow")

            for file_path, doc_type in self.results["fallback_used"].items():
                table.add_row(Path(file_path).name, doc_type)

            console.print(table)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Smart incremental extraction with automatic handling of all edge cases"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually extracting",
    )

    args = parser.parse_args()

    extractor = SmartIncrementalExtractor()
    await extractor.run(args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
