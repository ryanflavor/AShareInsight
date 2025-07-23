#!/usr/bin/env python3
"""
Migration script to import orphaned files with extracted JSON but not in database.

This handles the specific issue where files have extracted JSON but their
file hashes don't match what's in the database.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID

import click
import structlog
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select

from src.application.use_cases.archive_extraction_result import (
    ArchiveExtractionResultUseCase,
)
from src.domain.entities.extraction import DocumentType
from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import (
    SourceDocumentModel,
)
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)

logger = structlog.get_logger()
console = Console()


class OrphanedFileMigrator:
    """Migrate files with extracted JSON but not in database."""

    def __init__(self):
        self.stats = {"total_orphaned": 0, "imported": 0, "skipped": 0, "failed": 0}

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def find_orphaned_files(self) -> list[tuple[Path, Path]]:
        """Find files with extracted JSON but not in database."""
        orphaned = []

        async with get_session() as session:
            # Get all file hashes from database
            stmt = select(SourceDocumentModel.file_hash)
            result = await session.execute(stmt)
            db_hashes = {row[0] for row in result}

            # Check annual reports
            for source_dir, extract_dir in [
                ("data/annual_reports/2024", "data/extracted/annual_reports"),
                ("data/research_reports/2024", "data/extracted/research_reports"),
            ]:
                source_path = Path(source_dir)
                extract_path = Path(extract_dir)

                if not source_path.exists():
                    continue

                for md_file in source_path.glob("*.md"):
                    file_hash = self._calculate_file_hash(md_file)
                    json_file = extract_path / f"{md_file.stem}_extracted.json"

                    # File has extracted JSON but not in DB
                    if json_file.exists() and file_hash not in db_hashes:
                        orphaned.append((md_file, json_file))

        self.stats["total_orphaned"] = len(orphaned)
        return orphaned

    async def import_orphaned_file(self, source_file: Path, json_file: Path) -> bool:
        """Import a single orphaned file."""
        try:
            # Read extracted JSON
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            # Determine document type
            doc_type_str = data.get("document_type", "annual_report")
            doc_type = (
                DocumentType.ANNUAL_REPORT
                if doc_type_str == "annual_report"
                else DocumentType.RESEARCH_REPORT
            )

            # Prepare metadata for archiving
            import re
            from datetime import date

            # Extract date from filename or use today
            date_match = re.search(r"(\d{4})", source_file.name)
            doc_date = (
                date(int(date_match.group(1)), 12, 31) if date_match else date.today()
            )

            # Get company code from extraction data
            company_code = data["extraction_data"].get("company_code", "unknown")

            # Calculate file hash
            import hashlib

            with open(source_file, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            metadata = {
                "company_code": company_code,
                "doc_type": doc_type_str,
                "doc_date": doc_date,
                "report_title": data["extraction_data"].get(
                    "company_name_full", source_file.name
                ),
                "file_path": str(source_file),
                "file_hash": file_hash,
                "original_content": None,  # We don't have the original content in JSON
            }

            # Archive to database
            async with get_session() as session:
                repository = PostgresSourceDocumentRepository(session)
                use_case = ArchiveExtractionResultUseCase(repository)

                doc_id = await use_case.execute(raw_llm_output=data, metadata=metadata)

                if isinstance(doc_id, UUID):
                    logger.info(f"Imported {source_file.name} -> {doc_id}")
                    return True
                else:
                    logger.warning(f"Failed to import {source_file.name}: {doc_id}")
                    return False

        except Exception as e:
            logger.error(f"Error importing {source_file.name}: {e}")
            return False

    async def run(self, dry_run: bool = False):
        """Run the migration."""
        console.print("[bold]Orphaned File Migration[/bold]")
        console.print("Finding files with extracted JSON but not in database...\n")

        orphaned_files = await self.find_orphaned_files()

        if not orphaned_files:
            console.print("[green]No orphaned files found![/green]")
            return

        # Display orphaned files
        table = Table(title="Orphaned Files")
        table.add_column("Source File", style="cyan")
        table.add_column("Has JSON", style="green")

        for source, json_file in orphaned_files[:10]:  # Show first 10
            table.add_row(source.name, "✓")

        if len(orphaned_files) > 10:
            table.add_row("...", f"... and {len(orphaned_files) - 10} more")

        console.print(table)

        if dry_run:
            console.print("\n[yellow]Dry run - no import performed[/yellow]")
            return

        # Import orphaned files
        console.print(f"\nImporting {len(orphaned_files)} orphaned files...")

        for source_file, json_file in orphaned_files:
            success = await self.import_orphaned_file(source_file, json_file)

            if success:
                self.stats["imported"] += 1
            else:
                self.stats["failed"] += 1

        # Display results
        console.print("\n[bold]=== MIGRATION RESULTS ===[/bold]")

        results_table = Table()
        results_table.add_column("Metric", style="cyan")
        results_table.add_column("Count", style="green")

        results_table.add_row("Total Orphaned", str(self.stats["total_orphaned"]))
        results_table.add_row("Imported", str(self.stats["imported"]))
        results_table.add_row("Failed", str(self.stats["failed"]))

        console.print(results_table)

        if self.stats["failed"] > 0:
            console.print(
                "\n[red]⚠️  Some files failed to import. Check logs for details.[/red]"
            )
        else:
            console.print("\n[green]✅ Migration completed successfully![/green]")


@click.command()
@click.option(
    "--dry-run", is_flag=True, help="Show what would be imported without executing"
)
def main(dry_run):
    """Import orphaned files with extracted JSON but not in database."""
    migrator = OrphanedFileMigrator()
    asyncio.run(migrator.run(dry_run))


if __name__ == "__main__":
    main()
