#!/usr/bin/env python3
"""
List companies with good test data (documents and concepts).
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


async def find_good_test_companies():
    """Find companies with good test data."""
    async with get_session() as session:
        # Query to find companies with both documents and concepts
        # Using a subquery approach for better performance
        query = (
            select(
                CompanyModel.company_code,
                CompanyModel.company_name_short,
                CompanyModel.company_name_full,
                func.count(func.distinct(SourceDocumentModel.doc_id)).label(
                    "doc_count"
                ),
                func.count(func.distinct(BusinessConceptMasterModel.concept_id)).label(
                    "concept_count"
                ),
            )
            .select_from(CompanyModel)
            .join(
                SourceDocumentModel,
                CompanyModel.company_code == SourceDocumentModel.company_code,
            )
            .join(
                BusinessConceptMasterModel,
                CompanyModel.company_code == BusinessConceptMasterModel.company_code,
            )
            .where(BusinessConceptMasterModel.is_active == True)
            .group_by(
                CompanyModel.company_code,
                CompanyModel.company_name_short,
                CompanyModel.company_name_full,
            )
            .having(
                func.count(func.distinct(BusinessConceptMasterModel.concept_id)) >= 5
            )
            .order_by(
                func.count(func.distinct(BusinessConceptMasterModel.concept_id)).desc()
            )
            .limit(30)
        )

        result = await session.execute(query)
        companies = result.all()

        # Create table
        table = Table(title="Best Companies for Testing (with 5+ concepts)")
        table.add_column("Company Code", style="cyan", width=12)
        table.add_column("Short Name", style="green", width=20)
        table.add_column("Documents", style="yellow", justify="right", width=10)
        table.add_column("Concepts", style="magenta", justify="right", width=10)
        table.add_column("Full Name", style="white", width=40)

        for company in companies:
            table.add_row(
                company.company_code,
                company.company_name_short or "N/A",
                str(company.doc_count),
                str(company.concept_count),
                company.company_name_full[:40] + "..."
                if len(company.company_name_full) > 40
                else company.company_name_full,
            )

        console.print(table)

        # Generate SQL insert statements for test companies
        console.print("\n[bold]SQL Insert Statements for Test Companies:[/bold]")
        console.print("```sql")
        console.print("-- Insert commonly needed test companies that are missing")
        console.print(
            "INSERT INTO companies (company_code, company_name_full, company_name_short, exchange) VALUES"
        )

        missing_companies = [
            ("002170", "深圳市芭田生态工程股份有限公司", "芭田股份", "SZSE"),
            ("000333", "美的集团股份有限公司", "美的集团", "SZSE"),
            ("000001", "平安银行股份有限公司", "平安银行", "SZSE"),
            ("000002", "万科企业股份有限公司", "万科A", "SZSE"),
        ]

        for i, (code, full_name, short_name, exchange) in enumerate(missing_companies):
            comma = "," if i < len(missing_companies) - 1 else ";"
            console.print(
                f"('{code}', '{full_name}', '{short_name}', '{exchange}'){comma}"
            )

        console.print("```")

        # Recommend test companies
        console.print(
            "\n[bold]Recommended Test Companies (already in DB with good data):[/bold]"
        )
        test_recommendations = companies[:10]

        rec_table = Table(title="Use these companies for testing")
        rec_table.add_column("Company Code", style="cyan")
        rec_table.add_column("Company Name", style="green")
        rec_table.add_column("Why Good for Testing", style="yellow")

        for company in test_recommendations:
            reason = f"{company.doc_count} docs, {company.concept_count} concepts"
            rec_table.add_row(
                company.company_code,
                company.company_name_short or company.company_name_full[:20],
                reason,
            )

        console.print(rec_table)

        # Example API test with actual company
        if companies:
            first_company = companies[0]
            console.print("\n[bold]Example API Test with Actual Data:[/bold]")
            console.print("```python")
            console.print("# Use this company code in your API tests:")
            console.print(
                f"test_company_code = '{first_company.company_code}'  # {first_company.company_name_short}"
            )
            console.print(
                f"# This company has {first_company.doc_count} documents and {first_company.concept_count} concepts"
            )
            console.print("```")


async def main():
    """Main entry point."""
    console.print("[bold cyan]Finding Good Test Companies...[/bold cyan]\n")

    try:
        await find_good_test_companies()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
