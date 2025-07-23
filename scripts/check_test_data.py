#!/usr/bin/env python3
"""
Check what test data (companies) exists in the database.
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()

from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import (
    BusinessConceptMasterModel,
    CompanyModel,
    SourceDocumentModel,
)

console = Console()


async def check_companies():
    """Check what companies exist in the database."""
    async with get_session() as session:
        # Get all companies
        result = await session.execute(
            select(CompanyModel).order_by(CompanyModel.company_code)
        )
        companies = result.scalars().all()

        if not companies:
            console.print("[red]No companies found in the database![/red]")
            return

        # Create a table to display companies
        table = Table(title=f"Companies in Database (Total: {len(companies)})")
        table.add_column("Company Code", style="cyan")
        table.add_column("Full Name", style="green")
        table.add_column("Short Name", style="yellow")
        table.add_column("Exchange", style="magenta")

        for company in companies[:20]:  # Show first 20
            table.add_row(
                company.company_code,
                company.company_name_full,
                company.company_name_short or "N/A",
                company.exchange or "N/A",
            )

        if len(companies) > 20:
            table.add_row("...", f"... and {len(companies) - 20} more", "...", "...")

        console.print(table)

        # Get companies with documents and concepts
        console.print("\n[bold]Companies with Data:[/bold]")

        # Query companies with document counts
        doc_counts = await session.execute(
            select(
                SourceDocumentModel.company_code,
                func.count(SourceDocumentModel.doc_id).label("doc_count"),
            ).group_by(SourceDocumentModel.company_code)
        )
        doc_count_dict = {row[0]: row[1] for row in doc_counts}

        # Query companies with concept counts
        concept_counts = await session.execute(
            select(
                BusinessConceptMasterModel.company_code,
                func.count(BusinessConceptMasterModel.concept_id).label(
                    "concept_count"
                ),
            )
            .where(BusinessConceptMasterModel.is_active == True)
            .group_by(BusinessConceptMasterModel.company_code)
        )
        concept_count_dict = {row[0]: row[1] for row in concept_counts}

        # Create summary table
        summary_table = Table(title="Companies with Documents and Concepts")
        summary_table.add_column("Company Code", style="cyan")
        summary_table.add_column("Company Name", style="green")
        summary_table.add_column("Documents", style="yellow", justify="right")
        summary_table.add_column("Concepts", style="magenta", justify="right")
        summary_table.add_column("Has Vectors", style="blue")

        companies_with_data = []
        for company in companies:
            doc_count = doc_count_dict.get(company.company_code, 0)
            concept_count = concept_count_dict.get(company.company_code, 0)

            if doc_count > 0 or concept_count > 0:
                companies_with_data.append((company, doc_count, concept_count))

        # Sort by concept count descending
        companies_with_data.sort(key=lambda x: x[2], reverse=True)

        for company, doc_count, concept_count in companies_with_data[:10]:
            # Check if company has vectors
            has_vectors = "Yes" if concept_count > 0 else "No"

            summary_table.add_row(
                company.company_code,
                company.company_name_short or company.company_name_full[:30],
                str(doc_count),
                str(concept_count),
                has_vectors,
            )

        if len(companies_with_data) > 10:
            summary_table.add_row(
                "...",
                f"... and {len(companies_with_data) - 10} more",
                "...",
                "...",
                "...",
            )

        console.print(summary_table)

        # Show commonly used test companies
        console.print("\n[bold]Commonly Used Test Companies:[/bold]")
        test_companies = ["002170", "300637", "000333", "600309", "000001", "000002"]

        test_table = Table(title="Test Company Status")
        test_table.add_column("Company Code", style="cyan")
        test_table.add_column("Exists", style="green")
        test_table.add_column("Has Documents", style="yellow")
        test_table.add_column("Has Concepts", style="magenta")
        test_table.add_column("Company Name", style="white")

        for code in test_companies:
            company = next((c for c in companies if c.company_code == code), None)
            exists = "✓" if company else "✗"
            has_docs = str(doc_count_dict.get(code, 0)) if company else "N/A"
            has_concepts = str(concept_count_dict.get(code, 0)) if company else "N/A"
            name = company.company_name_short if company else "Not Found"

            test_table.add_row(code, exists, has_docs, has_concepts, name)

        console.print(test_table)

        # Summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"Total companies: {len(companies)}")
        console.print(f"Companies with documents: {len(doc_count_dict)}")
        console.print(f"Companies with concepts: {len(concept_count_dict)}")
        console.print(f"Companies with data: {len(companies_with_data)}")


async def main():
    """Main entry point."""
    console.print("[bold cyan]Checking Test Data in Database...[/bold cyan]\n")

    try:
        await check_companies()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
