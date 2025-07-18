"""
Integration tests for HNSW index performance validation.

This test validates that vector similarity search meets the < 10ms
performance requirement specified in the architecture.

NOTE: These tests are currently skipped because pgvector's HNSW index
has a 2000 dimension limit, but our embeddings are 2560 dimensions.
We use exact nearest neighbor search without index instead.
"""

import os
import random
import time
from statistics import mean, stdev

import pytest

# Skip all tests in this module due to HNSW dimension limit
pytestmark = pytest.mark.skip(
    reason="HNSW index not used due to 2560 > 2000 dimension limit"
)

from packages.core.src.core.database import DatabaseOperations
from packages.core.src.core.models import BusinessConcept, Company, SourceDocument


@pytest.fixture
def db_ops():
    """Create database operations instance for testing."""
    db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:test123@localhost:5432/ashareinsight_test",
    )
    db = DatabaseOperations(db_url)

    # Clean up before test
    db.execute_query("DELETE FROM business_concepts_master")
    db.execute_query("DELETE FROM source_documents")
    db.execute_query("DELETE FROM companies")

    yield db

    # Clean up after test
    db.close()


def generate_random_embedding(
    base_value: float = 0.5, variance: float = 0.1
) -> list[float]:
    """Generate a random 2560-dimensional embedding."""
    return [base_value + random.uniform(-variance, variance) for _ in range(2560)]


class TestHNSWPerformance:
    """Test HNSW index performance with various data sizes."""

    def test_hnsw_search_performance_small_dataset(self, db_ops):
        """Test HNSW search performance with 1,000 vectors."""
        num_vectors = 1000
        self._test_performance(db_ops, num_vectors, max_time_ms=10)

    def test_hnsw_search_performance_medium_dataset(self, db_ops):
        """Test HNSW search performance with 10,000 vectors."""
        num_vectors = 10000
        self._test_performance(db_ops, num_vectors, max_time_ms=10)

    @pytest.mark.slow
    def test_hnsw_search_performance_large_dataset(self, db_ops):
        """Test HNSW search performance with 100,000 vectors."""
        num_vectors = 100000
        self._test_performance(db_ops, num_vectors, max_time_ms=10)

    def _test_performance(self, db_ops, num_vectors: int, max_time_ms: float):
        """Test HNSW search performance with specified number of vectors."""
        print(f"\n🔍 Testing HNSW performance with {num_vectors:,} vectors...")

        # Setup: Create company and document
        company = Company(
            company_code="PERF001", company_name_full="Performance Test Company"
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="PERF001",
            doc_type="annual_report",
            doc_date="2023-12-31",
            report_title="Performance Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        # Insert vectors in batches
        print(f"   📝 Inserting {num_vectors:,} vectors...")
        batch_size = 1000
        start_time = time.time()

        for i in range(0, num_vectors, batch_size):
            batch_concepts = []
            for j in range(min(batch_size, num_vectors - i)):
                concept = BusinessConcept(
                    company_code="PERF001",
                    concept_name=f"Concept_{i + j}",
                    embedding=generate_random_embedding(
                        base_value=0.5 + (i + j) / num_vectors
                    ),
                    concept_details={"index": i + j},
                    last_updated_from_doc_id=created_doc.doc_id,
                )
                batch_concepts.append(concept)

            # Insert batch
            for concept in batch_concepts:
                db_ops.create_business_concept(concept)

            if (i + batch_size) % 10000 == 0:
                print(f"      Inserted {i + batch_size:,} vectors...")

        insert_time = time.time() - start_time
        print(f"   ✅ Inserted {num_vectors:,} vectors in {insert_time:.2f}s")

        # Run multiple search queries to get average performance
        num_queries = 100
        search_times = []

        print(f"   🔎 Running {num_queries} search queries...")

        for i in range(num_queries):
            # Generate a random query vector
            query_embedding = generate_random_embedding(
                base_value=random.uniform(0.3, 0.7), variance=0.15
            )

            # Measure search time
            start_time = time.time()
            results = db_ops.search_similar_concepts(
                query_embedding, company_code="PERF001", limit=10
            )
            search_time_ms = (time.time() - start_time) * 1000
            search_times.append(search_time_ms)

            # Verify we got results
            assert len(results) > 0
            assert len(results) <= 10

        # Calculate statistics
        avg_time = mean(search_times)
        std_dev = stdev(search_times) if len(search_times) > 1 else 0
        min_time = min(search_times)
        max_time = max(search_times)
        p95_time = sorted(search_times)[int(len(search_times) * 0.95)]

        print(f"\n   📊 Performance Results ({num_vectors:,} vectors):")
        print(f"      Average search time: {avg_time:.2f}ms")
        print(f"      Standard deviation: {std_dev:.2f}ms")
        print(f"      Min time: {min_time:.2f}ms")
        print(f"      Max time: {max_time:.2f}ms")
        print(f"      95th percentile: {p95_time:.2f}ms")

        # Assert performance requirement
        assert avg_time < max_time_ms, (
            f"Average search time {avg_time:.2f}ms exceeds requirement of {max_time_ms}ms"
        )
        assert p95_time < max_time_ms * 1.5, (
            f"95th percentile {p95_time:.2f}ms exceeds 1.5x requirement"
        )

        print(
            f"   ✅ Performance test passed! Average {avg_time:.2f}ms < {max_time_ms}ms requirement"
        )

    def test_hnsw_accuracy(self, db_ops):
        """Test HNSW search accuracy for vector similarity."""
        print("\n🎯 Testing HNSW search accuracy...")

        # Setup
        company = Company(
            company_code="ACC001", company_name_full="Accuracy Test Company"
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="ACC001",
            doc_type="annual_report",
            doc_date="2023-12-31",
            report_title="Accuracy Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        # Create known vectors with specific patterns
        vectors = {
            "exact_match": [0.5] * 2560,
            "very_similar": [0.49] * 512 + [0.51] * 512,  # 98% similar
            "somewhat_similar": [0.4] * 512 + [0.6] * 512,  # 80% similar
            "different": [0.1] * 512 + [0.9] * 512,  # Very different
            "opposite": [0.9] * 512 + [0.1] * 512,  # Opposite pattern
        }

        # Insert vectors
        for name, embedding in vectors.items():
            concept = BusinessConcept(
                company_code="ACC001",
                concept_name=name,
                embedding=embedding,
                concept_details={"type": "test_vector"},
                last_updated_from_doc_id=created_doc.doc_id,
            )
            db_ops.create_business_concept(concept)

        # Search with exact match query
        query = [0.5] * 2560
        results = db_ops.search_similar_concepts(query, company_code="ACC001", limit=5)

        # Verify results are ordered by similarity
        assert len(results) == 5
        assert results[0]["concept_name"] == "exact_match"
        assert results[0]["distance"] < 0.001  # Should be nearly 0

        assert results[1]["concept_name"] == "very_similar"
        assert results[1]["distance"] < results[2]["distance"]

        # Verify distance ordering
        for i in range(len(results) - 1):
            assert results[i]["distance"] <= results[i + 1]["distance"], (
                f"Results not ordered by distance: {results[i]['distance']} > {results[i + 1]['distance']}"
            )

        print("   ✅ HNSW accuracy test passed!")
        print(
            f"   📊 Distance ordering: {[f'{r["concept_name"]}: {r["distance"]:.4f}' for r in results]}"
        )

    def test_hnsw_index_rebuild_performance(self, db_ops):
        """Test performance after HNSW index rebuild."""
        print("\n🔧 Testing HNSW index rebuild performance...")

        # Setup initial data
        company = Company(
            company_code="REBUILD001", company_name_full="Rebuild Test Company"
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="REBUILD001",
            doc_type="annual_report",
            doc_date="2023-12-31",
            report_title="Rebuild Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        # Insert 1000 vectors
        print("   📝 Inserting initial vectors...")
        for i in range(1000):
            concept = BusinessConcept(
                company_code="REBUILD001",
                concept_name=f"Concept_{i}",
                embedding=generate_random_embedding(),
                concept_details={},
                last_updated_from_doc_id=created_doc.doc_id,
            )
            db_ops.create_business_concept(concept)

        # Drop and recreate HNSW index
        print("   🔄 Rebuilding HNSW index...")
        with db_ops.pool.connection() as conn:
            with conn.cursor() as cur:
                # Drop existing index
                cur.execute("DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw")

                # Recreate with different parameters
                cur.execute("""
                    CREATE INDEX idx_business_concepts_embedding_hnsw
                    ON business_concepts_master
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 32, ef_construction = 128)
                """)
                conn.commit()

        # Test performance after rebuild
        query = generate_random_embedding()
        times = []

        for _ in range(10):
            start = time.time()
            results = db_ops.search_similar_concepts(
                query, company_code="REBUILD001", limit=10
            )
            times.append((time.time() - start) * 1000)
            assert len(results) > 0

        avg_time = mean(times)
        print(f"   ✅ Post-rebuild average search time: {avg_time:.2f}ms")
        assert avg_time < 10, (
            f"Post-rebuild performance {avg_time:.2f}ms exceeds 10ms requirement"
        )
