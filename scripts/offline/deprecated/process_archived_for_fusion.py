#!/usr/bin/env python3
"""Process archived documents for master data fusion.

This script processes all archived documents in the source_documents table
that haven't been processed for business concept fusion yet.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import structlog
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from sqlalchemy import distinct, func, select

from src.infrastructure.factories import create_standalone_fusion_use_case
from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import (
    BusinessConceptMasterModel,
    SourceDocumentModel,
)

logger = structlog.get_logger()
console = Console()


class FusionProcessor:
    """Process archived documents for master data fusion."""

    def __init__(self):
        self.results = {
            "success": [],
            "failed": [],
            "skipped": [],
            "already_processed": [],
        }
        self.fusion_use_case = None

    async def find_unprocessed_documents(self) -> list[dict[str, Any]]:
        """Find all documents that haven't been processed for fusion yet.

        Returns:
            List of documents with their processing status
        """
        async with get_session() as session:
            # Query to find documents and check if they have been processed
            # A document is considered processed if ANY concept references it
            subquery = (
                select(BusinessConceptMasterModel.last_updated_from_doc_id)
                .where(BusinessConceptMasterModel.last_updated_from_doc_id.isnot(None))
                .distinct()
            )

            stmt = (
                select(
                    SourceDocumentModel.doc_id,
                    SourceDocumentModel.company_code,
                    SourceDocumentModel.doc_type,
                    SourceDocumentModel.doc_date,
                    SourceDocumentModel.report_title,
                    SourceDocumentModel.processing_status,
                    SourceDocumentModel.created_at,
                )
                .where(
                    SourceDocumentModel.processing_status == "completed",
                    SourceDocumentModel.doc_id.notin_(subquery),
                )
                .order_by(
                    SourceDocumentModel.company_code, SourceDocumentModel.doc_date
                )
            )

            result = await session.execute(stmt)
            documents = []
            for row in result:
                documents.append(
                    {
                        "doc_id": row.doc_id,
                        "company_code": row.company_code,
                        "doc_type": row.doc_type,
                        "doc_date": row.doc_date,
                        "report_title": row.report_title
                        or f"{row.doc_type} - {row.doc_date}",
                        "created_at": row.created_at,
                    }
                )

            # Also get count of already processed documents for reporting
            processed_stmt = select(
                func.count(distinct(SourceDocumentModel.doc_id))
            ).where(
                SourceDocumentModel.processing_status == "completed",
                SourceDocumentModel.doc_id.in_(subquery),
            )
            processed_result = await session.execute(processed_stmt)
            processed_count = processed_result.scalar()

            logger.info(
                f"Found {len(documents)} unprocessed documents "
                f"(and {processed_count} already processed)"
            )

            return documents

    async def process_document(self, doc_info: dict[str, Any]) -> bool:
        """Process a single document for fusion.

        Args:
            doc_info: Document information dictionary

        Returns:
            True if successful, False otherwise
        """
        doc_id = doc_info["doc_id"]

        try:
            logger.info(
                "processing_document_for_fusion",
                doc_id=str(doc_id),
                company_code=doc_info["company_code"],
                doc_type=doc_info["doc_type"],
            )

            # Execute fusion
            result = await self.fusion_use_case.execute(doc_id)

            # Record success
            self.results["success"].append(
                {
                    **doc_info,
                    "concepts_created": result["concepts_created"],
                    "concepts_updated": result["concepts_updated"],
                    "concepts_skipped": result["concepts_skipped"],
                    "total_concepts": result["total_concepts"],
                }
            )

            logger.info(
                "fusion_completed",
                doc_id=str(doc_id),
                **result,
            )

            return True

        except ValueError as e:
            # Handle specific business logic errors
            error_msg = str(e)
            if "no business concepts found" in error_msg.lower():
                self.results["skipped"].append(
                    {
                        **doc_info,
                        "reason": "No business concepts in document",
                    }
                )
                logger.warning(
                    "document_skipped",
                    doc_id=str(doc_id),
                    reason="No business concepts",
                )
            else:
                self.results["failed"].append(
                    {
                        **doc_info,
                        "error": error_msg,
                    }
                )
                logger.error(
                    "fusion_failed",
                    doc_id=str(doc_id),
                    error=error_msg,
                )
            return False

        except Exception as e:
            # Handle unexpected errors
            self.results["failed"].append(
                {
                    **doc_info,
                    "error": str(e),
                }
            )
            logger.error(
                "fusion_failed",
                doc_id=str(doc_id),
                error=str(e),
                exc_info=True,
            )
            return False

    async def run(self, dry_run: bool = False, limit: int | None = None) -> None:
        """Run the fusion processing for all unprocessed documents.

        Args:
            dry_run: If True, only show what would be processed
            limit: Maximum number of documents to process
        """
        console.print("\n[bold cyan]=== MASTER DATA FUSION PROCESSOR ===[/bold cyan]\n")

        # Initialize fusion use case
        if not dry_run:
            console.print("Initializing fusion service...")
            self.fusion_use_case = await create_standalone_fusion_use_case()

        # Find unprocessed documents
        console.print("Scanning for unprocessed documents...")
        documents = await self.find_unprocessed_documents()

        if not documents:
            console.print(
                "\n[green]All documents have been processed for fusion![/green]"
            )
            return

        # Apply limit if specified
        if limit and limit < len(documents):
            console.print(
                f"\n[yellow]Processing limited to first {limit} documents[/yellow]"
            )
            documents = documents[:limit]

        # Display what will be processed
        console.print(f"\n[bold]Found {len(documents)} documents to process:[/bold]")
        self._display_documents_summary(documents)

        if dry_run:
            console.print("\n[yellow]Dry run mode - no processing performed[/yellow]")
            self._display_documents_table(documents)
            return

        # Process documents
        console.print(f"\n[bold]Processing {len(documents)} documents...[/bold]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Processing documents for fusion...", total=len(documents)
            )

            for doc_info in documents:
                # Update progress description
                progress.update(
                    task,
                    description=(
                        f"[cyan]Processing {doc_info['company_code']} - "
                        f"{doc_info['doc_date']}"
                    ),
                )

                # Process document
                await self.process_document(doc_info)

                # Update progress
                progress.advance(task)

                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)

        # Display summary
        self._display_summary()

    def _display_documents_summary(self, documents: list[dict[str, Any]]) -> None:
        """Display a summary of documents by type and company."""
        # Count by type
        by_type = {}
        by_company = {}

        for doc in documents:
            # Count by type
            doc_type = doc["doc_type"]
            by_type[doc_type] = by_type.get(doc_type, 0) + 1

            # Count by company
            company = doc["company_code"]
            by_company[company] = by_company.get(company, 0) + 1

        console.print("\n[bold]By Document Type:[/bold]")
        for doc_type, count in sorted(by_type.items()):
            console.print(f"  • {doc_type.replace('_', ' ').title()}: {count}")

        console.print(f"\n[bold]Unique Companies:[/bold] {len(by_company)}")

    def _display_documents_table(self, documents: list[dict[str, Any]]) -> None:
        """Display a detailed table of documents."""
        table = Table(title="Documents to Process")
        table.add_column("Company", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Date", style="green")
        table.add_column("Title", style="blue", max_width=50)
        table.add_column("Archived", style="magenta")

        for doc in documents[:20]:  # Show first 20
            table.add_row(
                doc["company_code"],
                doc["doc_type"].replace("_", " ").title(),
                str(doc["doc_date"]),
                (
                    doc["report_title"][:50] + "..."
                    if len(doc["report_title"]) > 50
                    else doc["report_title"]
                ),
                doc["created_at"].strftime("%Y-%m-%d %H:%M"),
            )

        if len(documents) > 20:
            table.add_row(
                "...",
                "...",
                "...",
                f"... and {len(documents) - 20} more documents",
                "...",
            )

        console.print(table)

    def _display_summary(self) -> None:
        """Display processing summary."""
        console.print("\n[bold]=== PROCESSING SUMMARY ===[/bold]\n")

        total_processed = (
            len(self.results["success"])
            + len(self.results["failed"])
            + len(self.results["skipped"])
        )

        console.print(f"[bold]Total Processed:[/bold] {total_processed}")
        console.print(f"  ✅ Successful: {len(self.results['success'])}")
        console.print(f"  ⏭️  Skipped: {len(self.results['skipped'])}")
        console.print(f"  ❌ Failed: {len(self.results['failed'])}")

        # Show concept statistics
        if self.results["success"]:
            total_created = sum(
                doc["concepts_created"] for doc in self.results["success"]
            )
            total_updated = sum(
                doc["concepts_updated"] for doc in self.results["success"]
            )
            total_concepts = sum(
                doc["total_concepts"] for doc in self.results["success"]
            )

            console.print("\n[bold]Concept Statistics:[/bold]")
            console.print(f"  📊 Total Concepts Processed: {total_concepts}")
            console.print(f"  ➕ New Concepts Created: {total_created}")
            console.print(f"  🔄 Existing Concepts Updated: {total_updated}")

        # Show failed documents
        if self.results["failed"]:
            console.print("\n[red]Failed Documents:[/red]")
            table = Table()
            table.add_column("Company", style="cyan")
            table.add_column("Date", style="yellow")
            table.add_column("Error", style="red", max_width=60)

            for doc in self.results["failed"][:10]:
                table.add_row(
                    doc["company_code"],
                    str(doc["doc_date"]),
                    (
                        doc["error"][:60] + "..."
                        if len(doc["error"]) > 60
                        else doc["error"]
                    ),
                )

            if len(self.results["failed"]) > 10:
                table.add_row(
                    "...", "...", f"... and {len(self.results['failed']) - 10} more"
                )

            console.print(table)

        # Show skipped documents summary
        if self.results["skipped"]:
            console.print(
                f"\n[yellow]Skipped {len(self.results['skipped'])} documents "
                f"(no business concepts)[/yellow]"
            )


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Process archived documents for master data fusion"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually running fusion",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of documents to process",
    )

    args = parser.parse_args()

    processor = FusionProcessor()
    await processor.run(args.dry_run, args.limit)


if __name__ == "__main__":
    asyncio.run(main())
