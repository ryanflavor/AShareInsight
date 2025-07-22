"""Performance logging and monitoring for AShareInsight.

This module provides utilities for tracking query performance,
search metrics, and system health indicators.
"""

import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Container for performance metrics data."""

    def __init__(self):
        """Initialize metrics storage."""
        self.query_times: list[float] = []
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_queries = 0
        self.failed_queries = 0
        self._start_time = time.time()

        # Reranking metrics
        self.rerank_times: list[float] = []
        self.total_reranks = 0
        self.failed_reranks = 0
        self.total_documents_reranked = 0

    def add_query_time(self, duration_ms: float):
        """Add a query execution time."""
        self.query_times.append(duration_ms)
        self.total_queries += 1

        # Keep only last 1000 measurements to avoid memory growth
        if len(self.query_times) > 1000:
            self.query_times = self.query_times[-1000:]

    def add_cache_hit(self):
        """Increment cache hit counter."""
        self.cache_hits += 1

    def add_cache_miss(self):
        """Increment cache miss counter."""
        self.cache_misses += 1

    def add_failed_query(self):
        """Increment failed query counter."""
        self.failed_queries += 1

    def add_rerank_time(self, duration_ms: float, doc_count: int):
        """Add a reranking execution time.

        Args:
            duration_ms: Duration in milliseconds
            doc_count: Number of documents reranked
        """
        self.rerank_times.append(duration_ms)
        self.total_reranks += 1
        self.total_documents_reranked += doc_count

        # Keep only last 1000 measurements
        if len(self.rerank_times) > 1000:
            self.rerank_times = self.rerank_times[-1000:]

    def add_failed_rerank(self):
        """Increment failed rerank counter."""
        self.failed_reranks += 1

    def get_p95_latency(self) -> float | None:
        """Calculate P95 latency in milliseconds."""
        if not self.query_times:
            return None

        sorted_times = sorted(self.query_times)
        p95_index = int(len(sorted_times) * 0.95)
        return (
            sorted_times[p95_index]
            if p95_index < len(sorted_times)
            else sorted_times[-1]
        )

    def get_average_latency(self) -> float | None:
        """Calculate average latency in milliseconds."""
        if not self.query_times:
            return None
        return sum(self.query_times) / len(self.query_times)

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops == 0:
            return 0.0
        return (self.cache_hits / total_cache_ops) * 100

    def get_success_rate(self) -> float:
        """Calculate query success rate as percentage."""
        if self.total_queries == 0:
            return 100.0
        return ((self.total_queries - self.failed_queries) / self.total_queries) * 100

    def get_uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self._start_time

    def get_rerank_p95_latency(self) -> float | None:
        """Calculate P95 reranking latency in milliseconds."""
        if not self.rerank_times:
            return None

        sorted_times = sorted(self.rerank_times)
        p95_index = int(len(sorted_times) * 0.95)
        return (
            sorted_times[p95_index]
            if p95_index < len(sorted_times)
            else sorted_times[-1]
        )

    def get_average_rerank_latency(self) -> float | None:
        """Calculate average reranking latency in milliseconds."""
        if not self.rerank_times:
            return None
        return sum(self.rerank_times) / len(self.rerank_times)

    def get_average_docs_per_rerank(self) -> float:
        """Calculate average documents per rerank operation."""
        if self.total_reranks == 0:
            return 0.0
        return self.total_documents_reranked / self.total_reranks

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary format."""
        return {
            "total_queries": self.total_queries,
            "failed_queries": self.failed_queries,
            "success_rate": self.get_success_rate(),
            "average_latency_ms": self.get_average_latency(),
            "p95_latency_ms": self.get_p95_latency(),
            "cache_hit_rate": self.get_cache_hit_rate(),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "reranking": {
                "total_reranks": self.total_reranks,
                "failed_reranks": self.failed_reranks,
                "total_documents": self.total_documents_reranked,
                "average_latency_ms": self.get_average_rerank_latency(),
                "p95_latency_ms": self.get_rerank_p95_latency(),
                "average_docs_per_request": self.get_average_docs_per_rerank(),
            },
            "uptime_seconds": self.get_uptime_seconds(),
            # Use UTC timezone for compatibility
            "timestamp": datetime.now(
                getattr(datetime, "UTC", None) or __import__("datetime").timezone.utc
            ).isoformat(),
        }


# Global metrics instance
_metrics = PerformanceMetrics()


def get_metrics() -> PerformanceMetrics:
    """Get the global metrics instance."""
    return _metrics


@asynccontextmanager
async def track_query_performance(operation: str, target_identifier: str | None = None):
    """Context manager for tracking query performance.

    Args:
        operation: Name of the operation being tracked
        target_identifier: Optional identifier for the query target

    Yields:
        None
    """
    start_time = time.time()

    try:
        logger.info(
            f"Starting {operation}",
            extra={
                "operation": operation,
                "target": target_identifier,
                "start_time": start_time,
            },
        )

        yield

        # Calculate duration
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        # Update metrics
        _metrics.add_query_time(duration_ms)

        # Log performance
        logger.info(
            f"Completed {operation}",
            extra={
                "operation": operation,
                "target": target_identifier,
                "duration_ms": duration_ms,
                "success": True,
            },
        )

        # Warn if exceeding performance threshold
        if duration_ms > 500:
            logger.warning(
                f"Slow query detected: {operation} took {duration_ms:.2f}ms",
                extra={
                    "operation": operation,
                    "target": target_identifier,
                    "duration_ms": duration_ms,
                },
            )

    except Exception as e:
        # Track failed query
        _metrics.add_failed_query()

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        logger.error(
            f"Failed {operation}",
            extra={
                "operation": operation,
                "target": target_identifier,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e),
            },
        )

        # Re-raise the exception
        raise


def track_performance(operation: str):
    """Decorator for tracking synchronous function performance.

    Args:
        operation: Name of the operation being tracked

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                _metrics.add_query_time(duration_ms)

                logger.info(
                    f"Completed {operation}",
                    extra={
                        "operation": operation,
                        "duration_ms": duration_ms,
                        "success": True,
                    },
                )

                return result

            except Exception as e:
                _metrics.add_failed_query()
                duration_ms = (time.time() - start_time) * 1000

                logger.error(
                    f"Failed {operation}",
                    extra={
                        "operation": operation,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error": str(e),
                    },
                )
                raise

        return wrapper

    return decorator


def track_async_performance(operation: str):
    """Decorator for tracking async function performance.

    Args:
        operation: Name of the operation being tracked

    Returns:
        Decorated async function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000

                _metrics.add_query_time(duration_ms)

                logger.info(
                    f"Completed {operation}",
                    extra={
                        "operation": operation,
                        "duration_ms": duration_ms,
                        "success": True,
                    },
                )

                return result

            except Exception as e:
                _metrics.add_failed_query()
                duration_ms = (time.time() - start_time) * 1000

                logger.error(
                    f"Failed {operation}",
                    extra={
                        "operation": operation,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error": str(e),
                    },
                )
                raise

        return wrapper

    return decorator


# Cache tracking utilities
def track_cache_hit():
    """Record a cache hit."""
    _metrics.add_cache_hit()
    logger.debug("Cache hit")


def track_cache_miss():
    """Record a cache miss."""
    _metrics.add_cache_miss()
    logger.debug("Cache miss")


# Reranking tracking utilities
@asynccontextmanager
async def track_rerank_performance(doc_count: int):
    """Context manager for tracking reranking performance.

    Args:
        doc_count: Number of documents being reranked

    Yields:
        None
    """
    start_time = time.time()

    try:
        logger.info(
            "Starting reranking operation",
            extra={
                "operation": "rerank_documents",
                "document_count": doc_count,
                "start_time": start_time,
            },
        )

        yield

        # Calculate duration
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        # Update metrics
        _metrics.add_rerank_time(duration_ms, doc_count)

        # Log performance
        logger.info(
            "Completed reranking operation",
            extra={
                "operation": "rerank_documents",
                "document_count": doc_count,
                "duration_ms": duration_ms,
                "success": True,
                "avg_ms_per_doc": duration_ms / doc_count if doc_count > 0 else 0,
            },
        )

    except Exception as e:
        # Track failed rerank
        _metrics.add_failed_rerank()

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        logger.error(
            "Failed reranking operation",
            extra={
                "operation": "rerank_documents",
                "document_count": doc_count,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e),
            },
        )

        # Re-raise the exception
        raise
