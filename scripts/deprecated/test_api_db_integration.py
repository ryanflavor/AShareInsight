#!/usr/bin/env python3
"""Test script to verify API and database integration for Story 2.1."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.domain.services import StubMarketDataRepository
from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository


async def test_integration():
    """Test the integration between API components and database."""
    print("🔍 Testing API-Database Integration\n")

    try:
        # Initialize repositories
        print("1. Initializing repositories...")
        vector_store = PostgresVectorStoreRepository()
        market_data_repo = StubMarketDataRepository()

        # Check vector store health
        health = await vector_store.health_check()
        print(f"   ✅ Vector store health check: {'PASSED' if health else 'FAILED'}")

        # Create use case
        print("\n2. Creating SearchSimilarCompaniesUseCase...")
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=vector_store,
            reranker=None,  # No reranker for basic test
            market_data_repository=market_data_repo,
        )
        print("   ✅ Use case created successfully")

        # Test search
        print("\n3. Testing search functionality...")
        query_identifier = "002170"  # An actual company code in the database

        try:
            results, filters_applied = await use_case.execute(
                target_identifier=query_identifier,
                text_to_embed=None,
                top_k=5,
                similarity_threshold=0.7,
                market_filters=None,
            )

            print("   ✅ Search completed successfully!")
            print(f"   Found {len(results)} similar companies:")

            for i, company in enumerate(results[:3], 1):
                print(f"\n   {i}. {company.company_name} ({company.company_code})")
                print(f"      Relevance Score: {company.relevance_score:.3f}")
                print(f"      Matched Concepts: {len(company.matched_concepts)}")
                if company.matched_concepts:
                    top_concept = company.matched_concepts[0]
                    print(
                        f"      Top Concept: {top_concept.concept_name} (score: {top_concept.similarity_score:.3f})"
                    )

        except Exception as e:
            print(f"   ❌ Search failed: {e}")
            print(f"      Error type: {type(e).__name__}")
            import traceback

            traceback.print_exc()

    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Cleanup
        if "vector_store" in locals():
            await vector_store.close()
            print("\n✅ Cleaned up connections")


async def main():
    """Run the integration test."""
    await test_integration()


if __name__ == "__main__":
    asyncio.run(main())
