"""Metrics API endpoint for monitoring and observability.

This module provides endpoints for accessing performance metrics
and system health information.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.infrastructure.caching import get_search_cache
from src.infrastructure.monitoring import get_metrics

router = APIRouter()


class MetricsResponse(BaseModel):
    """Response model for metrics endpoint."""

    total_queries: int = Field(..., description="Total number of queries processed")
    failed_queries: int = Field(..., description="Number of failed queries")
    success_rate: float = Field(..., description="Query success rate percentage")
    average_latency_ms: float | None = Field(
        None, description="Average query latency in milliseconds"
    )
    p95_latency_ms: float | None = Field(
        None, description="95th percentile latency in milliseconds"
    )
    cache_hit_rate: float = Field(..., description="Cache hit rate percentage")
    cache_hits: int = Field(..., description="Number of cache hits")
    cache_misses: int = Field(..., description="Number of cache misses")
    cache_size: int = Field(..., description="Current cache size")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")


@router.get(
    "/performance",
    response_model=MetricsResponse,
    summary="Get performance metrics",
    description="Retrieve current performance metrics and system statistics",
)
async def get_performance_metrics() -> MetricsResponse:
    """Get current performance metrics.

    Returns:
        MetricsResponse with current metrics
    """
    # Get metrics from monitoring
    metrics = get_metrics()
    metrics_dict = metrics.to_dict()

    # Get cache stats
    cache = get_search_cache()
    cache_size = await cache.size()

    return MetricsResponse(
        total_queries=metrics_dict["total_queries"],
        failed_queries=metrics_dict["failed_queries"],
        success_rate=metrics_dict["success_rate"],
        average_latency_ms=metrics_dict["average_latency_ms"],
        p95_latency_ms=metrics_dict["p95_latency_ms"],
        cache_hit_rate=metrics_dict["cache_hit_rate"],
        cache_hits=metrics_dict["cache_hits"],
        cache_misses=metrics_dict["cache_misses"],
        cache_size=cache_size,
        uptime_seconds=metrics_dict["uptime_seconds"],
    )
