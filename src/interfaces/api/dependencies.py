"""Dependency injection for FastAPI application.

This module provides dependency functions that can be injected
into FastAPI route handlers.
"""

from collections.abc import AsyncGenerator

import structlog
from fastapi import Depends

from src.application.ports import RerankerPort
from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.domain.services import MarketDataRepository
from src.infrastructure.llm.qwen import QwenRerankAdapter, QwenRerankConfig
from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository
from src.shared.config import settings

logger = structlog.get_logger(__name__)

# Global repository instance (will be initialized once)
_vector_store_repository: PostgresVectorStoreRepository | None = None
_reranker: RerankerPort | None = None
_market_data_repository: MarketDataRepository | None = None
_market_data_db_pool = None  # Connection pool for market data repository


async def get_vector_store_repository() -> AsyncGenerator[
    PostgresVectorStoreRepository
]:
    """Get the vector store repository instance.

    This dependency provides a singleton repository instance that
    maintains a connection pool for efficient database access.

    Yields:
        PostgresVectorStoreRepository instance
    """
    global _vector_store_repository

    if _vector_store_repository is None:
        _vector_store_repository = PostgresVectorStoreRepository()
        logger.info("Initialized vector store repository")

        # Warm up the connection pool on first initialization
        try:
            await _vector_store_repository.warmup_pool()
        except Exception as e:
            logger.warning(f"Failed to warm up connection pool: {e}")
            # Continue anyway - warmup is optional optimization

    yield _vector_store_repository


async def get_reranker() -> AsyncGenerator[RerankerPort | None]:
    """Get the reranker instance if enabled.

    This dependency provides a singleton reranker instance that
    loads the model once and reuses it for all requests.

    Yields:
        RerankerPort instance if enabled, None otherwise
    """
    global _reranker

    if not settings.reranker.reranker_enabled:
        yield None
        return

    if _reranker is None:
        try:
            # Use HTTP service adapter
            config = QwenRerankConfig(
                service_url=settings.reranker.reranker_service_url,
                timeout_seconds=settings.reranker.reranker_timeout_seconds,
                max_retries=settings.reranker.reranker_max_retries,
                retry_backoff=settings.reranker.reranker_retry_backoff,
            )
            _reranker = QwenRerankAdapter(config)
            logger.info("Initialized Qwen Service HTTP adapter")

            # Verify reranker is ready
            if not await _reranker.is_ready():
                logger.error("Reranker failed readiness check")
                _reranker = None
                yield None
                return

        except Exception as e:
            logger.error(f"Failed to initialize reranker: {e}")
            yield None
            return

    yield _reranker


async def get_market_data_repository() -> AsyncGenerator[MarketDataRepository]:
    """Get the market data repository instance.

    Yields:
        MarketDataRepository instance
    """
    global _market_data_repository, _market_data_db_pool

    if _market_data_repository is None:
        import asyncpg

        from src.infrastructure.persistence.postgres.market_data_repository import (
            MarketDataRepository as PostgresMarketDataRepo,
        )
        from src.infrastructure.persistence.postgres.market_data_repository_adapter import (
            PostgresMarketDataRepositoryAdapter,
        )
        from src.shared.config import settings

        # Create database connection pool
        _market_data_db_pool = await asyncpg.create_pool(
            settings.database.postgres_dsn_sync,
            min_size=settings.database.db_pool_min_size,
            max_size=settings.database.db_pool_max_size,
            timeout=settings.database.db_pool_timeout,
            command_timeout=60,
        )

        # Create the PostgreSQL repository with the pool and wrap it with the adapter
        postgres_repo = PostgresMarketDataRepo(_market_data_db_pool)
        _market_data_repository = PostgresMarketDataRepositoryAdapter(postgres_repo)
        logger.info("Initialized PostgreSQL market data repository")

    yield _market_data_repository


async def get_search_similar_companies_use_case(
    vector_store: PostgresVectorStoreRepository = Depends(  # noqa: B008
        get_vector_store_repository
    ),
    reranker: RerankerPort | None = Depends(get_reranker),  # noqa: B008
    market_data_repository: MarketDataRepository = Depends(  # noqa: B008
        get_market_data_repository
    ),
) -> SearchSimilarCompaniesUseCase:
    """Get the search similar companies use case.

    Args:
        vector_store: Injected vector store repository
        reranker: Optional injected reranker service
        market_data_repository: Injected market data repository

    Returns:
        SearchSimilarCompaniesUseCase instance
    """
    return SearchSimilarCompaniesUseCase(
        vector_store=vector_store,
        reranker=reranker,
        market_data_repository=market_data_repository,
    )


async def shutdown_dependencies():
    """Cleanup function to close connections on shutdown."""
    global \
        _vector_store_repository, \
        _reranker, \
        _market_data_repository, \
        _market_data_db_pool

    if _vector_store_repository:
        await _vector_store_repository.close()
        _vector_store_repository = None
        logger.info("Closed vector store repository connections")

    if _reranker:
        try:
            # Only call close if the reranker has a close method
            if hasattr(_reranker, "close") and callable(_reranker.close):
                await _reranker.close()
            _reranker = None
            logger.info("Closed reranker connections")
        except Exception as e:
            logger.error(f"Error closing reranker: {e}")

    if _market_data_db_pool:
        await _market_data_db_pool.close()
        _market_data_db_pool = None
        _market_data_repository = None
        logger.info("Closed market data repository connections")
