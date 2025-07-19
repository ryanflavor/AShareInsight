"""Dependency injection for FastAPI application.

This module provides dependency functions that can be injected
into FastAPI route handlers.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import Depends

from src.application.ports import RerankerPort
from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.infrastructure.llm.qwen import QwenServiceAdapter, QwenServiceConfig
from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository
from src.shared.config import settings

logger = logging.getLogger(__name__)

# Global repository instance (will be initialized once)
_vector_store_repository: PostgresVectorStoreRepository | None = None
_reranker: RerankerPort | None = None


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

    if not settings.reranker_enabled:
        yield None
        return

    if _reranker is None:
        try:
            # Use HTTP service adapter
            config = QwenServiceConfig(
                service_url=settings.reranker_service_url,
                timeout_seconds=settings.reranker_timeout_seconds,
                max_retries=settings.reranker_max_retries,
                retry_backoff=settings.reranker_retry_backoff,
            )
            _reranker = QwenServiceAdapter(config)
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


async def get_search_similar_companies_use_case(
    vector_store: PostgresVectorStoreRepository = Depends(get_vector_store_repository),
    reranker: RerankerPort | None = Depends(get_reranker),
) -> SearchSimilarCompaniesUseCase:
    """Get the search similar companies use case.

    Args:
        vector_store: Injected vector store repository
        reranker: Optional injected reranker service

    Returns:
        SearchSimilarCompaniesUseCase instance
    """
    return SearchSimilarCompaniesUseCase(vector_store=vector_store, reranker=reranker)


async def shutdown_dependencies():
    """Cleanup function to close connections on shutdown."""
    global _vector_store_repository, _reranker

    if _vector_store_repository:
        await _vector_store_repository.close()
        _vector_store_repository = None
        logger.info("Closed vector store repository connections")

    if _reranker:
        try:
            await _reranker.close()
            _reranker = None
            logger.info("Closed reranker connections")
        except Exception as e:
            logger.error(f"Error closing reranker: {e}")
