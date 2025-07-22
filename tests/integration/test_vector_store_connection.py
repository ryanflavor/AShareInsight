"""Integration test for vector store database connection.

This test verifies that the PostgresVectorStoreRepository can
successfully connect to the database and that pgvector is available.
"""

import asyncio

import pytest

from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository


@pytest.mark.asyncio
async def test_vector_store_health_check():
    """Test that vector store can connect and pgvector is available."""
    repository = PostgresVectorStoreRepository()

    try:
        # Perform health check
        is_healthy = await repository.health_check()

        # Assert connection is healthy
        assert is_healthy is True, "Vector store health check failed"

    finally:
        # Clean up connection
        await repository.close()


@pytest.mark.asyncio
async def test_vector_store_connection_pool():
    """Test that connection pool initializes correctly."""
    repository = PostgresVectorStoreRepository()

    try:
        # Ensure pool is created
        pool = await repository._ensure_pool()

        # Verify pool exists
        assert pool is not None, "Connection pool was not created"
        assert (
            repository._is_initialized is True
        ), "Repository not marked as initialized"

        # Test basic query through pool
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1, "Basic query failed"

    finally:
        # Clean up
        await repository.close()
        assert repository._pool is None, "Pool was not properly closed"
        assert (
            repository._is_initialized is False
        ), "Repository still marked as initialized"


if __name__ == "__main__":
    # Run tests directly
    asyncio.run(test_vector_store_health_check())
    asyncio.run(test_vector_store_connection_pool())
    print("All connection tests passed!")
