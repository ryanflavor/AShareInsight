"""PostgreSQL vector store repository implementation.

This module implements the VectorStorePort interface using PostgreSQL
with pgvector extension for efficient vector similarity search.
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.application.ports import VectorStorePort
from src.domain.entities import BusinessConceptEntity as BusinessConcept
from src.domain.value_objects import BusinessConceptQuery, Document
from src.infrastructure.caching.simple_cache import (
    create_cache_key,
    get_search_cache,
)
from src.shared.config import settings
from src.shared.exceptions import CompanyNotFoundError, DatabaseConnectionError

logger = logging.getLogger(__name__)


class PostgresVectorStoreRepository(VectorStorePort):
    """PostgreSQL implementation of the vector store repository.

    This repository uses pgvector extension with halfvec type for
    efficient 2560-dimensional vector storage and HNSW indexing.
    """

    def __init__(self, connection_pool: Pool | None = None):
        """Initialize the repository with optional connection pool.

        Args:
            connection_pool: Optional asyncpg connection pool
        """
        self._pool = connection_pool
        self._is_initialized = False
        self._cache = get_search_cache()

        # Import CircuitBreaker here to avoid import issues
        from src.infrastructure.resilience import CircuitBreaker

        # Initialize circuit breaker for database operations
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=asyncpg.PostgresError,
        )

    async def _ensure_pool(self) -> Pool:
        """Ensure connection pool is initialized.

        Returns:
            Initialized connection pool

        Raises:
            DatabaseConnectionError: If pool initialization fails
        """
        if not self._pool:
            try:
                self._pool = await asyncpg.create_pool(
                    settings.database.postgres_dsn_sync,
                    min_size=settings.database.db_pool_min_size,
                    max_size=settings.database.db_pool_max_size,
                    timeout=settings.database.db_pool_timeout,
                    command_timeout=60,
                )
                self._is_initialized = True
                logger.info("PostgreSQL connection pool initialized")
            except Exception as e:
                logger.error(f"Failed to create connection pool: {e}")
                raise DatabaseConnectionError(
                    database_name=settings.database.postgres_db, reason=str(e)
                ) from e
        return self._pool

    async def warmup_pool(self) -> None:
        """Warm up the connection pool by creating min_size connections.

        This ensures connections are established and ready for use,
        reducing latency on first queries.
        """
        pool = await self._ensure_pool()
        logger.info("Starting connection pool warmup...")

        try:
            # Acquire and release connections up to min_size to force creation
            warmup_tasks = []
            for _ in range(settings.database.db_pool_min_size):
                warmup_tasks.append(self._warmup_single_connection(pool))

            await asyncio.gather(*warmup_tasks, return_exceptions=True)
            logger.info(
                f"Connection pool warmup completed with "
                f"{settings.database.db_pool_min_size} connections"
            )
        except Exception as e:
            logger.warning(f"Connection pool warmup partially failed: {e}")
            # Don't fail startup on warmup errors

    async def _warmup_single_connection(self, pool: Pool) -> None:
        """Warm up a single connection by acquiring and testing it."""
        async with pool.acquire() as conn:
            # Execute a simple query to ensure the connection is fully established
            await conn.fetchval("SELECT 1")

    async def health_check(self) -> bool:
        """Check if the vector store connection is healthy.

        Returns:
            True if connection is healthy and pgvector is available
        """
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                # Check basic connectivity
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    return False

                # Check pgvector extension
                ext_version = await conn.fetchval(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
                )
                if not ext_version:
                    logger.error("pgvector extension not found")
                    return False

                logger.info(f"Health check passed, pgvector version: {ext_version}")
                return True

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def search_similar_concepts(
        self, query: BusinessConceptQuery
    ) -> list[Document]:
        """Search for similar business concepts based on the query.

        Args:
            query: Query parameters including target company

        Returns:
            List of Document objects sorted by similarity score

        Raises:
            CompanyNotFoundError: If target company not found
            DatabaseConnectionError: If database operation fails
        """
        from src.infrastructure.monitoring import track_query_performance

        # Generate cache key
        cache_key = create_cache_key(
            "search",
            query.target_identifier,
            top_k=query.top_k,
            threshold=query.similarity_threshold,
        )

        # Check cache first
        cached_result = await self._cache.get(cache_key)
        if cached_result:
            logger.info(f"Cache hit for query: {query.target_identifier}")
            return cached_result

        async with track_query_performance(
            "vector_similarity_search", query.target_identifier
        ):
            try:
                pool = await self._ensure_pool()

                # First, identify the company
                company_info = await self._identify_company(
                    pool, query.target_identifier
                )

                if not company_info:
                    raise CompanyNotFoundError(query.target_identifier)

                company_code = company_info["company_code"]
                company_name = company_info["company_name"]

                # Get all active concepts for the company
                source_concepts = await self._get_company_concepts(pool, company_code)

                if not source_concepts:
                    logger.warning(
                        f"No active concepts found for company {company_code}"
                    )
                    return []

                # Perform parallel similarity search for each concept
                search_tasks = [
                    self._search_similar_for_concept(
                        pool,
                        concept,
                        query.similarity_threshold,
                        query.top_k * 2,  # Get more to deduplicate later
                    )
                    for concept in source_concepts
                ]

                # Execute searches in parallel
                search_results = await asyncio.gather(*search_tasks)

                # Merge and deduplicate results
                merged_documents = self._merge_and_deduplicate_results(
                    search_results, source_concepts, company_name, query.top_k
                )

                # Cache the results before returning
                await self._cache.set(cache_key, merged_documents, ttl_seconds=300)
                logger.info(f"Cached results for query: {query.target_identifier}")

                return merged_documents

            except CompanyNotFoundError:
                raise
            except Exception as e:
                logger.error(f"Search failed: {e}")
                raise DatabaseConnectionError(
                    database_name=settings.database.postgres_db,
                    reason=f"Search operation failed: {str(e)}",
                ) from e

    async def _identify_company(
        self, pool: Pool, identifier: str
    ) -> dict[str, str] | None:
        """Identify company by code or name.

        Args:
            pool: Database connection pool
            identifier: Company code or name

        Returns:
            Dict with company_code and company_name, or None if not found
        """

        async def query_func(conn):
            # Try exact match on company code first
            result = await conn.fetchrow(
                """
                SELECT company_code, company_name_full as company_name
                FROM companies
                WHERE company_code = $1
                """,
                identifier,
            )

            if result:
                return dict(result)

            # Try case-insensitive match on company name
            result = await conn.fetchrow(
                """
                SELECT company_code, company_name_full as company_name
                FROM companies
                WHERE LOWER(company_name_full) = LOWER($1)
                """,
                identifier,
            )

            if result:
                return dict(result)

            # Try partial match on company name
            result = await conn.fetchrow(
                """
                SELECT company_code, company_name_full as company_name
                FROM companies
                WHERE LOWER(company_name_full) LIKE LOWER($1)
                LIMIT 1
                """,
                f"%{identifier}%",
            )

            return dict(result) if result else None

        return await self._execute_query_with_circuit_breaker(query_func, pool)

    async def _get_company_concepts(
        self, pool: Pool, company_code: str
    ) -> list[BusinessConcept]:
        """Get all active business concepts for a company.

        Args:
            pool: Database connection pool
            company_code: Company stock code

        Returns:
            List of BusinessConcept entities
        """

        async def query_func(conn):
            rows = await conn.fetch(
                """
                SELECT
                    concept_id,
                    company_code,
                    concept_name,
                    concept_category,
                    importance_score,
                    last_updated_from_doc_id as source_document_id,
                    created_at,
                    updated_at,
                    is_active
                FROM business_concepts_master
                WHERE company_code = $1 AND is_active = true
                ORDER BY importance_score DESC
                """,
                company_code,
            )

            concepts = []
            for row in rows:
                # Create BusinessConcept with only the fields it actually has
                concept = BusinessConcept(
                    concept_id=row["concept_id"],
                    company_code=row["company_code"],
                    concept_name=row["concept_name"],
                    concept_category=row["concept_category"],
                    importance_score=Decimal(str(row["importance_score"])),
                    source_document_id=row["source_document_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    is_active=row["is_active"],
                )
                concepts.append(concept)

            return concepts

        return await self._execute_query_with_circuit_breaker(query_func, pool)

    async def _search_similar_for_concept(
        self,
        pool: Pool,
        source_concept: BusinessConcept,
        similarity_threshold: float,
        limit: int,
    ) -> list[dict]:
        """Search for similar concepts to a single source concept.

        Args:
            pool: Database connection pool
            source_concept: Source business concept
            similarity_threshold: Minimum similarity score
            limit: Maximum number of results

        Returns:
            List of search results as dictionaries
        """

        async def query_func(conn):
            # First get the embedding for the source concept
            embedding = await conn.fetchval(
                "SELECT embedding FROM business_concepts_master WHERE concept_id = $1",
                source_concept.concept_id,
            )

            if not embedding:
                logger.warning(
                    f"No embedding found for concept {source_concept.concept_id}"
                )
                return []

            # Use the pre-created search function
            rows = await conn.fetch(
                """
                SELECT
                    r.concept_id,
                    r.company_code,
                    r.concept_name,
                    r.concept_category,
                    r.importance_score,
                    r.similarity_score,
                    c.company_name_full as company_name
                FROM search_similar_concepts($1::halfvec(2560), $2, $3) r
                JOIN companies c ON r.company_code = c.company_code
                WHERE r.company_code != $4  -- Exclude source company
                """,
                embedding,
                similarity_threshold,
                limit,
                source_concept.company_code,
            )

            results = []
            for row in rows:
                results.append(
                    {
                        "concept_id": row["concept_id"],
                        "company_code": row["company_code"],
                        "company_name": row["company_name"],
                        "concept_name": row["concept_name"],
                        "concept_category": row["concept_category"],
                        "importance_score": Decimal(str(row["importance_score"])),
                        "similarity_score": float(row["similarity_score"]),
                        "source_concept_id": source_concept.concept_id,
                    }
                )

            return results

        return await self._execute_query_with_circuit_breaker(query_func, pool)

    def _merge_and_deduplicate_results(
        self,
        search_results: list[list[dict]],
        source_concepts: list[BusinessConcept],
        source_company_name: str,
        top_k: int,
    ) -> list[Document]:
        """Merge and deduplicate search results from multiple concepts.

        Args:
            search_results: List of search results from each concept
            source_concepts: Original source concepts
            source_company_name: Name of the source company
            top_k: Number of top results to return

        Returns:
            List of deduplicated Document objects
        """
        # Track best scores for each target concept
        best_scores: dict[UUID, dict] = {}

        for results in search_results:
            for result in results:
                concept_id = result["concept_id"]

                # Keep the result with highest similarity score
                if (
                    concept_id not in best_scores
                    or result["similarity_score"]
                    > best_scores[concept_id]["similarity_score"]
                ):
                    best_scores[concept_id] = result

        # Convert to Document objects
        documents = []

        now = datetime.now(UTC)

        for result in best_scores.values():
            doc = Document(
                concept_id=result["concept_id"],
                company_code=result["company_code"],
                company_name=result["company_name"],
                concept_name=result["concept_name"],
                concept_category=result["concept_category"],
                importance_score=result["importance_score"],
                similarity_score=result["similarity_score"],
                source_concept_id=result["source_concept_id"],
                matched_at=now,
            )
            documents.append(doc)

        # Sort by similarity score descending
        documents.sort(key=lambda d: d.similarity_score, reverse=True)

        # Return top K results
        return documents[:top_k]

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._is_initialized = False
            logger.info("PostgreSQL connection pool closed")

    async def _execute_with_circuit_breaker(self, func, *args, **kwargs):
        """Execute a database operation through the circuit breaker.

        This provides resilience against database failures by preventing
        cascading failures when the database is unavailable.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            CircuitOpenError: If circuit is open
            DatabaseConnectionError: If database operation fails
        """
        try:
            return await self._circuit_breaker.call(func, *args, **kwargs)
        except Exception as e:
            # Import here to avoid circular import
            from src.infrastructure.resilience.circuit_breaker import CircuitOpenError

            if isinstance(e, CircuitOpenError):
                logger.error("Database circuit breaker is open - too many failures")
                raise DatabaseConnectionError(
                    database_name=settings.database.postgres_db,
                    reason="Database temporarily unavailable (circuit breaker open)",
                ) from e
            raise

    async def _execute_query_with_circuit_breaker(self, query_func, pool: Pool):
        """Execute a database query function with circuit breaker protection.

        Args:
            query_func: Async function that takes a connection and executes queries
            pool: Database connection pool

        Returns:
            Result from query_func
        """

        async def _wrapped():
            async with pool.acquire() as conn:
                return await query_func(conn)

        return await self._execute_with_circuit_breaker(_wrapped)
