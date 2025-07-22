"""Monitoring and observability infrastructure for AShareInsight."""

from .performance_logger import (
    PerformanceMetrics,
    get_metrics,
    track_async_performance,
    track_cache_hit,
    track_cache_miss,
    track_performance,
    track_query_performance,
    track_rerank_performance,
)
from .telemetry import (
    LLMMetrics,
    add_span_attributes,
    get_tracer,
    record_error,
    set_span_ok,
    setup_telemetry,
    trace_method,
    trace_span,
)

__all__ = [
    # Telemetry
    "setup_telemetry",
    "get_tracer",
    "trace_span",
    "trace_method",
    "add_span_attributes",
    "record_error",
    "set_span_ok",
    "LLMMetrics",
    # Performance
    "PerformanceMetrics",
    "get_metrics",
    "track_query_performance",
    "track_performance",
    "track_async_performance",
    "track_cache_hit",
    "track_cache_miss",
    "track_rerank_performance",
]
