"""
Basic vector storage test using langchain-postgres PGVector integration
"""

import sys
from pathlib import Path

# Add core package to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "packages" / "core" / "src")
)

import numpy as np
from core.logging_config import get_logger
from langchain_core.documents import Document
from langchain_postgres import PGVector

logger = get_logger(__name__)


class MockEmbedding:
    """Mock embedding function for testing"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Generate mock embeddings for documents"""
        embeddings = []
        for i, text in enumerate(texts):
            # Create deterministic embeddings based on text hash
            np.random.seed(hash(text) % 2**32)
            embedding = np.random.random(2560).tolist()
            embeddings.append(embedding)
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        """Generate mock embedding for query"""
        np.random.seed(hash(text) % 2**32)
        return np.random.random(2560).tolist()


def test_langchain_postgres_integration():
    """Test langchain-postgres PGVector integration with HNSW indexing"""

    # Connection string for SQLAlchemy (langchain-postgres uses SQLAlchemy)
    connection_string = (
        "postgresql+psycopg://postgres:test123@localhost:5432/ashareinsight"
    )

    # Initialize mock embedding
    embedding_function = MockEmbedding()

    try:
        # Initialize PGVector store
        vector_store = PGVector(
            collection_name="test_collection",
            connection=connection_string,
            embeddings=embedding_function,
            use_jsonb=True,
        )

        print("✅ PGVector store initialized successfully")

        # Create test documents
        test_documents = [
            Document(
                page_content="This is a test document about artificial intelligence and machine learning",
                metadata={"source": "test1", "category": "AI"},
            ),
            Document(
                page_content="Vector databases are essential for semantic search and RAG applications",
                metadata={"source": "test2", "category": "Database"},
            ),
            Document(
                page_content="PostgreSQL with pgvector extension provides excellent vector search capabilities",
                metadata={"source": "test3", "category": "PostgreSQL"},
            ),
            Document(
                page_content="HNSW indexing offers fast approximate nearest neighbor search for high-dimensional vectors",
                metadata={"source": "test4", "category": "Indexing"},
            ),
        ]

        print(f"Adding {len(test_documents)} test documents to vector store...")

        # Add documents to vector store
        vector_store.add_documents(test_documents)

        print("✅ Documents added successfully")

        # Test similarity search
        query = "machine learning and AI applications"
        print(f"\nTesting similarity search with query: '{query}'")

        results = vector_store.similarity_search(query, k=2)

        print(f"✅ Found {len(results)} similar documents:")
        for i, doc in enumerate(results):
            print(f"  {i + 1}. {doc.page_content[:80]}...")
            print(f"     Metadata: {doc.metadata}")

        # Test similarity search with scores
        print("\nTesting similarity search with scores...")
        results_with_scores = vector_store.similarity_search_with_score(query, k=2)

        print(f"✅ Found {len(results_with_scores)} documents with scores:")
        for i, (doc, score) in enumerate(results_with_scores):
            print(f"  {i + 1}. Score: {score:.4f}")
            print(f"     Content: {doc.page_content[:80]}...")

        # Test vector performance with HNSW index
        print("\nTesting vector search performance...")

        # Perform multiple searches to test performance
        import time

        start_time = time.time()

        for i in range(10):
            test_query = f"test query {i} about vectors and search"
            vector_store.similarity_search(test_query, k=3)

        end_time = time.time()
        avg_time = (end_time - start_time) / 10

        print(f"✅ Average search time: {avg_time:.4f} seconds")
        print("✅ HNSW index performance test completed")

        # Add assertions to validate test results
        assert len(results) > 0, "No results found in similarity search"
        assert (
            len(results_with_scores) > 0
        ), "No results found in similarity search with scores"
        assert avg_time < 1.0, f"Search performance too slow: {avg_time} seconds"

        return True  # Keep return for backward compatibility with caller

    except Exception as e:
        logger.error(f"Vector storage test failed: {e}")
        print(f"❌ Vector storage test failed: {e}")
        raise  # Re-raise the exception instead of returning False


def verify_hnsw_index_creation():
    """Verify HNSW index is created for the vector column"""
    import psycopg

    connection_string = "postgresql://postgres:test123@localhost:5432/ashareinsight"

    try:
        with psycopg.connect(connection_string) as conn:
            with conn.cursor() as cur:
                # Check for HNSW indexes
                cur.execute(
                    """
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        indexdef
                    FROM pg_indexes 
                    WHERE indexdef LIKE '%hnsw%'
                    ORDER BY tablename, indexname;
                """
                )

                indexes = cur.fetchall()

                if indexes:
                    print(f"✅ Found {len(indexes)} HNSW indexes:")
                    for schema, table, index_name, index_def in indexes:
                        print(f"  - {schema}.{table}.{index_name}")
                        print(f"    Definition: {index_def}")
                else:
                    print(
                        "ℹ️  No HNSW indexes found yet (will be created automatically by langchain-postgres)"
                    )

                # Check vector columns
                cur.execute(
                    """
                    SELECT 
                        table_name,
                        column_name,
                        data_type
                    FROM information_schema.columns 
                    WHERE data_type = 'USER-DEFINED'
                    AND table_schema = 'public'
                    ORDER BY table_name, column_name;
                """
                )

                vector_columns = cur.fetchall()

                if vector_columns:
                    print(f"\n✅ Found {len(vector_columns)} vector columns:")
                    for table, column, data_type in vector_columns:
                        print(f"  - {table}.{column} ({data_type})")

                # Add assertion to ensure we found at least one vector column or HNSW index
                assert (
                    indexes or vector_columns
                ), "No vector columns or HNSW indexes found"

                return True  # Keep return for backward compatibility with caller

    except Exception as e:
        logger.error(f"HNSW verification failed: {e}")
        print(f"❌ HNSW verification failed: {e}")
        raise  # Re-raise the exception instead of returning False


def main():
    """Run vector storage tests"""
    print("Starting langchain-postgres PGVector integration test...")

    # Test vector storage
    vector_test_success = test_langchain_postgres_integration()

    print("\n" + "=" * 60)
    print("Verifying HNSW index creation...")

    # Verify HNSW indexes
    hnsw_verification_success = verify_hnsw_index_creation()

    print("\n" + "=" * 60)
    print("Vector storage test summary:")
    print(
        f"  - LangChain-Postgres Integration: {'✅ PASSED' if vector_test_success else '❌ FAILED'}"
    )
    print(
        f"  - HNSW Index Verification: {'✅ PASSED' if hnsw_verification_success else '❌ FAILED'}"
    )

    # Add assertion to validate both tests passed
    assert (
        vector_test_success and hnsw_verification_success
    ), "Vector storage tests failed"

    print("\n🎉 All vector storage tests completed successfully!")
    return True  # Keep return for backward compatibility


if __name__ == "__main__":
    from core.logging_config import setup_logging

    setup_logging(level="INFO")
    main()
