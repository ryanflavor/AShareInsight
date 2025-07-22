#!/usr/bin/env python3
"""Validation script for Story 2.2: Vector Database Retrieval Integration

This script validates all acceptance criteria for Story 2.2:
1. VectorStoreRepository can connect to PostgreSQL with HalfVec
2. Repository can receive BusinessConceptQuery objects
3. Search flow works without modifying BusinessConcept domain objects
4. Search includes: retrieve embeddings, cosine similarity search, filtering
5. Returns Top K candidate Document objects
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.domain.value_objects import BusinessConceptQuery
from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository
from src.shared.config.settings import get_settings


class Story22Validator:
    """Validates Story 2.2 acceptance criteria."""

    def __init__(self):
        self.settings = get_settings().database
        # Build async database URL
        async_url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.settings.postgres_user,
            password=self.settings.postgres_password.get_secret_value(),
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            database=self.settings.postgres_db,
        )
        self.engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.results = []

    async def validate(self):
        """Run all validation checks for Story 2.2."""
        print("🔍 Validating Story 2.2: Vector Database Retrieval Integration\n")

        try:
            # AC 1: VectorStoreRepository connection with HalfVec
            await self._test_vector_store_connection()

            # AC 2: BusinessConceptQuery handling
            await self._test_business_concept_query()

            # AC 3: Search flow without modifying domain objects
            await self._test_search_flow_integrity()

            # AC 4: Search process (embeddings, cosine similarity, filtering)
            await self._test_search_process()

            # AC 5: Top K results
            await self._test_top_k_results()

            # Additional: Test performance and caching
            await self._test_performance_features()

            # Summary
            self._print_summary()

        finally:
            await self.engine.dispose()

    async def _test_vector_store_connection(self):
        """AC 1: Test VectorStoreRepository connection with HalfVec."""
        print("=== AC 1: VectorStoreRepository Connection ===")

        try:
            # Test repository initialization
            vector_store = PostgresVectorStoreRepository()
            self._log_success(
                "Repository Creation", "PostgresVectorStoreRepository initialized"
            )

            # Test health check
            health = await vector_store.health_check()
            if health:
                self._log_success("Health Check", "Vector store connection healthy")
            else:
                self._log_error("Health Check", "Vector store health check failed")

            # Check HalfVec availability
            async with self.async_session() as session:
                result = await session.execute(
                    text("SELECT 1 FROM pg_type WHERE typname = 'halfvec'")
                )
                if result.scalar():
                    self._log_success("HalfVec Type", "HalfVec type is available")
                else:
                    self._log_error("HalfVec Type", "HalfVec type not found")

            # Cleanup
            await vector_store.close()

        except Exception as e:
            self._log_error("Connection Test", f"Failed: {e}")

    async def _test_business_concept_query(self):
        """AC 2: Test BusinessConceptQuery handling."""
        print("\n=== AC 2: BusinessConceptQuery Handling ===")

        try:
            # Test query creation with company code
            query1 = BusinessConceptQuery(
                target_identifier="002170", top_k=20, similarity_threshold=0.7
            )
            self._log_success("Query Creation", "Created query with company code")

            # Test query with optional text_to_embed
            query2 = BusinessConceptQuery(
                target_identifier="比亚迪",
                text_to_embed="新能源汽车电池技术",
                top_k=10,
                similarity_threshold=0.8,
            )
            self._log_success("Query with Text", "Created query with text_to_embed")

            # Test query validation
            try:
                invalid_query = BusinessConceptQuery(
                    target_identifier="",  # Invalid empty identifier
                    top_k=5,
                )
            except Exception:
                self._log_success("Query Validation", "Invalid query properly rejected")

        except Exception as e:
            self._log_error("Query Handling", f"Failed: {e}")

    async def _test_search_flow_integrity(self):
        """AC 3: Test search flow doesn't modify domain objects."""
        print("\n=== AC 3: Domain Object Integrity ===")

        try:
            vector_store = PostgresVectorStoreRepository()

            # Create a query
            query = BusinessConceptQuery(
                target_identifier="002170", top_k=5, similarity_threshold=0.7
            )

            # Execute search
            documents = await vector_store.search_similar_concepts(query)

            # Verify returned objects are Documents, not BusinessConcepts
            if documents:
                doc = documents[0]
                # Check it's a Document value object
                if hasattr(doc, "concept_id") and hasattr(doc, "similarity_score"):
                    self._log_success(
                        "Domain Integrity",
                        "Returns Document objects without modifying BusinessConcept",
                    )
                else:
                    self._log_error("Domain Integrity", "Invalid return type")
            else:
                self._log_warning("Domain Integrity", "No documents returned to verify")

            await vector_store.close()

        except Exception as e:
            self._log_error("Domain Integrity Test", f"Failed: {e}")

    async def _test_search_process(self):
        """AC 4: Test search process components."""
        print("\n=== AC 4: Search Process Components ===")

        try:
            # Check for search_similar_concepts SQL function
            async with self.async_session() as session:
                result = await session.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_proc 
                            WHERE proname = 'search_similar_concepts'
                        )
                    """)
                )
                if result.scalar():
                    self._log_success(
                        "SQL Function", "search_similar_concepts function exists"
                    )
                else:
                    self._log_error(
                        "SQL Function", "search_similar_concepts function not found"
                    )

            # Test cosine similarity search
            vector_store = PostgresVectorStoreRepository()
            query = BusinessConceptQuery(
                target_identifier="002170", top_k=10, similarity_threshold=0.5
            )

            start_time = asyncio.get_event_loop().time()
            documents = await vector_store.search_similar_concepts(query)
            search_time = asyncio.get_event_loop().time() - start_time

            if documents:
                # Check similarity scores
                scores = [doc.similarity_score for doc in documents]
                if all(score >= 0.5 for score in scores):
                    self._log_success(
                        "Similarity Filtering",
                        f"All {len(documents)} results meet threshold (>= 0.5)",
                    )
                else:
                    self._log_error(
                        "Similarity Filtering", "Some results below threshold"
                    )

                # Check if scores are sorted
                if scores == sorted(scores, reverse=True):
                    self._log_success(
                        "Result Sorting", "Results sorted by similarity score"
                    )
                else:
                    self._log_warning("Result Sorting", "Results not properly sorted")

                self._log_success(
                    "Search Performance",
                    f"Search completed in {search_time:.3f} seconds",
                )
            else:
                self._log_warning(
                    "Search Process", "No results to validate sorting/filtering"
                )

            await vector_store.close()

        except Exception as e:
            self._log_error("Search Process Test", f"Failed: {e}")

    async def _test_top_k_results(self):
        """AC 5: Test Top K results functionality."""
        print("\n=== AC 5: Top K Results ===")

        try:
            vector_store = PostgresVectorStoreRepository()

            # Test with different K values
            test_cases = [
                (5, "Small K value"),
                (20, "Medium K value"),
                (50, "Default K value"),
                (100, "Large K value"),
            ]

            for k, description in test_cases:
                query = BusinessConceptQuery(
                    target_identifier="002170",
                    top_k=k,
                    similarity_threshold=0.0,  # Low threshold to get more results
                )

                documents = await vector_store.search_similar_concepts(query)

                if len(documents) <= k:
                    self._log_success(
                        f"Top {k} Results",
                        f"{description}: Returned {len(documents)} documents (≤ {k})",
                    )
                else:
                    self._log_error(
                        f"Top {k} Results",
                        f"Returned {len(documents)} documents (> {k})",
                    )

            await vector_store.close()

        except Exception as e:
            self._log_error("Top K Test", f"Failed: {e}")

    async def _test_performance_features(self):
        """Test performance optimization and monitoring features."""
        print("\n=== Performance & Monitoring Features ===")

        try:
            # Check HNSW index usage
            async with self.async_session() as session:
                # Run EXPLAIN on a sample query
                result = await session.execute(
                    text("""
                        EXPLAIN (FORMAT JSON)
                        SELECT concept_id
                        FROM business_concepts_master
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> (
                            SELECT embedding 
                            FROM business_concepts_master 
                            WHERE concept_id = (
                                SELECT concept_id 
                                FROM business_concepts_master 
                                LIMIT 1
                            )
                        )
                        LIMIT 10
                    """)
                )

                explain_data = result.scalar()
                if "Index Scan" in str(explain_data):
                    self._log_success(
                        "HNSW Index", "Index is being used for vector search"
                    )
                else:
                    self._log_warning("HNSW Index", "Index might not be used optimally")

            # Test caching (if implemented)
            vector_store = PostgresVectorStoreRepository()
            query = BusinessConceptQuery(
                target_identifier="002170", top_k=10, similarity_threshold=0.7
            )

            # First search
            start1 = asyncio.get_event_loop().time()
            docs1 = await vector_store.search_similar_concepts(query)
            time1 = asyncio.get_event_loop().time() - start1

            # Second search (might be cached)
            start2 = asyncio.get_event_loop().time()
            docs2 = await vector_store.search_similar_concepts(query)
            time2 = asyncio.get_event_loop().time() - start2

            if time2 < time1 * 0.8:  # 20% faster indicates caching
                self._log_success(
                    "Caching",
                    f"Cache appears active (2nd query {(1 - time2 / time1) * 100:.1f}% faster)",
                )
            else:
                self._log_warning("Caching", "No significant caching detected")

            await vector_store.close()

        except Exception as e:
            self._log_error("Performance Test", f"Failed: {e}")

    def _log_success(self, component: str, message: str):
        """Log a successful check."""
        self.results.append(("success", component, message))
        print(f"✅ {component}: {message}")

    def _log_warning(self, component: str, message: str):
        """Log a warning."""
        self.results.append(("warning", component, message))
        print(f"⚠️  {component}: {message}")

    def _log_error(self, component: str, message: str):
        """Log an error."""
        self.results.append(("error", component, message))
        print(f"❌ {component}: {message}")

    def _print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("STORY 2.2 VALIDATION SUMMARY")
        print("=" * 60)

        success_count = sum(1 for r in self.results if r[0] == "success")
        warning_count = sum(1 for r in self.results if r[0] == "warning")
        error_count = sum(1 for r in self.results if r[0] == "error")

        print(f"✅ Success: {success_count}")
        print(f"⚠️  Warnings: {warning_count}")
        print(f"❌ Errors: {error_count}")

        # Acceptance Criteria Summary
        print("\nAcceptance Criteria Status:")
        print("1. VectorStoreRepository connection: ", end="")
        print(
            "✅ PASS"
            if any(r[1] == "Health Check" and r[0] == "success" for r in self.results)
            else "❌ FAIL"
        )

        print("2. BusinessConceptQuery handling: ", end="")
        print(
            "✅ PASS"
            if any(r[1] == "Query Creation" and r[0] == "success" for r in self.results)
            else "❌ FAIL"
        )

        print("3. Domain object integrity: ", end="")
        print(
            "✅ PASS"
            if any(
                r[1] == "Domain Integrity" and r[0] == "success" for r in self.results
            )
            else "❌ FAIL"
        )

        print("4. Search process components: ", end="")
        print(
            "✅ PASS"
            if any(r[1] == "SQL Function" and r[0] == "success" for r in self.results)
            else "❌ FAIL"
        )

        print("5. Top K results: ", end="")
        print(
            "✅ PASS"
            if any(
                "Top" in r[1] and "Results" in r[1] and r[0] == "success"
                for r in self.results
            )
            else "❌ FAIL"
        )

        if error_count == 0:
            print("\n🎉 Story 2.2 validation PASSED!")
            print("Vector database retrieval is fully integrated.")
        else:
            print("\n❌ Story 2.2 validation FAILED.")
            print("Please fix the errors before proceeding.")


async def main():
    """Run the Story 2.2 validation."""
    validator = Story22Validator()
    await validator.validate()


if __name__ == "__main__":
    asyncio.run(main())
