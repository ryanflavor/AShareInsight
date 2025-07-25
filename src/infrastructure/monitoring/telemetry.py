"""OpenTelemetry monitoring and observability module."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    HAS_OTLP_EXPORTER = True
except ImportError:
    HAS_OTLP_EXPORTER = False

try:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    HAS_LOGGING_INSTRUMENTOR = True
except ImportError:
    HAS_LOGGING_INSTRUMENTOR = False

from src.shared.config.settings import Settings

logger = structlog.get_logger(__name__)

# Type variable for decorators
F = TypeVar("F", bound=Callable[..., Any])

# Global tracer instance
_tracer: trace.Tracer | None = None


def setup_telemetry(settings: Settings) -> None:
    """Initialize OpenTelemetry with the given settings."""
    global _tracer

    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": settings.monitoring.otel_service_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.environment,
        }
    )

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add exporters based on configuration
    if settings.monitoring.otel_exporter_otlp_endpoint and HAS_OTLP_EXPORTER:
        # OTLP exporter for production
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.monitoring.otel_exporter_otlp_endpoint,
            # insecure should only be True for local development
            insecure=settings.environment == "local",
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        logger.info(
            "OpenTelemetry OTLP exporter configured",
            extra={"endpoint": settings.monitoring.otel_exporter_otlp_endpoint},
        )
    else:
        # Console exporter for development
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("OpenTelemetry console exporter configured")

    # Set the tracer provider
    trace.set_tracer_provider(provider)

    # Get tracer
    _tracer = trace.get_tracer(__name__)

    # Instrument logging to inject trace context
    if HAS_LOGGING_INSTRUMENTOR:
        LoggingInstrumentor().instrument()

    logger.info("OpenTelemetry initialized successfully")


def get_tracer() -> trace.Tracer:
    """Get the configured tracer instance."""
    if _tracer is None:
        # Return a no-op tracer if not initialized
        return trace.get_tracer(__name__)
    return _tracer


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
) -> Generator[trace.Span]:
    """Context manager for creating a traced span."""
    tracer = get_tracer()
    with tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=attributes or {},
    ) as span:
        try:
            yield span
        except Exception as e:
            # Record exception in span
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        finally:
            # Span automatically ends when exiting context
            pass


def trace_method(
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """Decorator to trace a method or function."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = name or f"{func.__module__}.{func.__name__}"
            span_attributes = attributes or {}

            # Add function metadata to attributes
            span_attributes.update(
                {
                    "function.module": func.__module__,
                    "function.name": func.__name__,
                }
            )

            with trace_span(span_name, span_attributes):
                return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def add_span_attributes(attributes: dict[str, Any]) -> None:
    """Add attributes to the current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_error(error: Exception, description: str | None = None) -> None:
    """Record an error in the current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(error)
        status_description = description or str(error)
        span.set_status(Status(StatusCode.ERROR, status_description))


def set_span_ok(description: str | None = None) -> None:
    """Set the current span status to OK."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_status(
            Status(StatusCode.OK, description or "Operation completed successfully")
        )


class LLMMetrics:
    """Helper class for recording LLM-specific metrics."""

    @staticmethod
    def record_llm_call(
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        duration_seconds: float,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Record metrics for an LLM API call."""
        attributes = {
            "llm.model": model,
            "llm.prompt_version": prompt_version,
            "llm.input_tokens": input_tokens,
            "llm.output_tokens": output_tokens,
            "llm.total_tokens": input_tokens + output_tokens,
            "llm.duration_seconds": duration_seconds,
            "llm.success": success,
        }

        if error:
            attributes["llm.error"] = error

        add_span_attributes(attributes)

        # Log metrics for aggregation
        logger.info(
            "LLM API call completed",
            extra={
                "model": model,
                "prompt_version": prompt_version,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_seconds": duration_seconds,
                "success": success,
                "error": error,
            },
        )

    @staticmethod
    def record_document_processing(
        document_type: str,
        document_size: int,
        processing_time: float,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Record metrics for document processing."""
        attributes = {
            "document.type": document_type,
            "document.size_bytes": document_size,
            "document.processing_time_seconds": processing_time,
            "document.success": success,
        }

        if error:
            attributes["document.error"] = error

        add_span_attributes(attributes)

        # Log metrics
        logger.info(
            "Document processing completed",
            extra={
                "document_type": document_type,
                "document_size": document_size,
                "processing_time": processing_time,
                "success": success,
                "error": error,
            },
        )
