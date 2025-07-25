#!/usr/bin/env python3
"""Retry fusion for companies that have source documents but no business concepts."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from src.infrastructure.factories import create_standalone_fusion_use_case
from src.infrastructure.persistence.postgres.connection import get_session


async def find_companies_needing_fusion():
    """Find companies with source documents but no business concepts."""
    async with get_session() as session:
        query = text("""
            SELECT DISTINCT 
                sd.company_code,
                sd.doc_id,
                c.company_name_full,
                sd.created_at
            FROM source_documents sd
            JOIN companies c ON c.company_code = sd.company_code
            LEFT JOIN business_concepts_master bcm ON bcm.company_code = sd.company_code
            WHERE bcm.company_code IS NULL
                AND sd.processing_status = 'completed'
                AND sd.raw_llm_output IS NOT NULL
            ORDER BY sd.created_at DESC
        """)

        result = await session.execute(query)
        return result.fetchall()


async def run_fusion_for_document(doc_id):
    """Run fusion for a specific document."""
    try:
        print(f"\n  Running fusion for document {doc_id}...")

        # Create fusion use case
        fusion_use_case = await create_standalone_fusion_use_case()

        # Execute fusion
        result = await fusion_use_case.execute(doc_id)

        print("  ✅ Fusion completed successfully!")
        if hasattr(result, "companies_updated"):
            print(f"     Companies updated: {result.companies_updated}")
            print(
                f"     Business concepts: {result.business_concepts_created} created, {result.business_concepts_updated} updated"
            )
        elif isinstance(result, dict):
            print(
                f"     Total concepts processed: {result.get('total_processed', 'N/A')}"
            )
            print(f"     Concepts created: {result.get('concepts_created', 'N/A')}")
            print(f"     Concepts updated: {result.get('concepts_updated', 'N/A')}")
        else:
            print(f"     Result: {result}")

        return True

    except Exception as e:
        print(f"  ❌ Fusion failed: {e}")
        return False


async def main():
    print("Finding companies that need fusion...")

    companies = await find_companies_needing_fusion()

    if not companies:
        print("✅ All companies have business concepts!")
        return

    print(f"\n Found {len(companies)} companies without business concepts:")

    for company in companies:
        print(f"\n{'=' * 60}")
        print(f"Company: {company.company_name_full} ({company.company_code})")
        print(f"Document: {company.doc_id}")
        print(f"Created: {company.created_at}")

        # Ask for confirmation
        response = input("\nRun fusion for this company? (y/n/all): ").lower()

        if response == "all":
            # Run for all remaining companies
            for comp in companies[companies.index(company) :]:
                await run_fusion_for_document(comp.doc_id)
            break
        elif response == "y":
            await run_fusion_for_document(company.doc_id)
        else:
            print("  Skipped.")


if __name__ == "__main__":
    asyncio.run(main())
