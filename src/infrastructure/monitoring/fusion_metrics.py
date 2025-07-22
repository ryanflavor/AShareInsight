"""Metrics collection for master data fusion operations.

This module provides metrics collection and instrumentation for
the business concept master data fusion process.
"""

import time
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import structlog
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

logger = structlog.get_logger(__name__)

# Initialize tracer and meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Define metrics
fusion_operations_counter = meter.create_counter(
    name="fusion.operations.total",
    description="Total number of fusion operations",
    unit="1",
)

fusion_concepts_created = meter.create_counter(
    name="fusion.concepts.created",
    description="Number of new business concepts created",
    unit="1",
)

fusion_concepts_updated = meter.create_counter(
    name="fusion.concepts.updated",
    description="Number of business concepts updated",
    unit="1",
)

fusion_concepts_skipped = meter.create_counter(
    name="fusion.concepts.skipped",
    description="Number of business concepts skipped due to errors",
    unit="1",
)

fusion_batch_duration = meter.create_histogram(
    name="fusion.batch.duration_ms",
    description="Duration of batch processing in milliseconds",
    unit="ms",
)

fusion_total_duration = meter.create_histogram(
    name="fusion.total.duration_ms",
    description="Total duration of fusion operation in milliseconds",
    unit="ms",
)

fusion_retry_counter = meter.create_counter(
    name="fusion.conflicts.retry_count",
    description="Number of optimistic lock retries",
    unit="1",
)

active_fusion_operations = meter.create_up_down_counter(
    name="fusion.operations.active",
    description="Number of currently active fusion operations",
    unit="1",
)


class FusionMetrics:
    """Helper class for recording fusion operation metrics."""

    @staticmethod
    @contextmanager
    def track_fusion_operation(
        doc_id: UUID,
        company_code: str,
        total_concepts: int,
    ):
        """Track a complete fusion operation with timing and metrics.

        Args:
            doc_id: The source document ID
            company_code: The company code being processed
            total_concepts: Total number of concepts to process

        Yields:
            A context object for recording operation results
        """
        start_time = time.time()

        # Start span for tracing
        with tracer.start_as_current_span(
            "fusion.operation",
            attributes={
                "doc_id": str(doc_id),
                "company_code": company_code,
                "total_concepts": total_concepts,
            },
        ) as span:
            # Increment active operations
            active_fusion_operations.add(1, {"company_code": company_code})

            try:
                # Create context object to collect results
                context = FusionOperationContext()
                yield context

                # Record successful operation
                fusion_operations_counter.add(
                    1,
                    {
                        "company_code": company_code,
                        "status": "success",
                        "partial": str(context.has_errors),
                    },
                )

                # Set span status
                if context.has_errors:
                    span.set_status(
                        Status(
                            StatusCode.OK,
                            "Fusion completed with some errors",
                        )
                    )
                else:
                    span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record failed operation
                fusion_operations_counter.add(
                    1,
                    {"company_code": company_code, "status": "failed"},
                )

                # Set error status on span
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

            finally:
                # Record duration
                duration_ms = (time.time() - start_time) * 1000
                fusion_total_duration.record(
                    duration_ms,
                    {"company_code": company_code},
                )

                # Decrement active operations
                active_fusion_operations.add(-1, {"company_code": company_code})

                # Add final attributes to span
                span.set_attributes(
                    {
                        "concepts_created": context.concepts_created,
                        "concepts_updated": context.concepts_updated,
                        "concepts_skipped": context.concepts_skipped,
                        "duration_ms": duration_ms,
                    }
                )

    @staticmethod
    @contextmanager
    def track_batch_processing(batch_size: int, batch_index: int):
        """Track processing of a single batch.

        Args:
            batch_size: Number of concepts in the batch
            batch_index: Index of the current batch

        Yields:
            None
        """
        start_time = time.time()

        with tracer.start_as_current_span(
            "fusion.batch",
            attributes={
                "batch_size": batch_size,
                "batch_index": batch_index,
            },
        ) as span:
            try:
                yield
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                fusion_batch_duration.record(
                    duration_ms,
                    {"batch_index": str(batch_index)},
                )
                span.set_attribute("duration_ms", duration_ms)

    @staticmethod
    def record_concept_created(company_code: str, concept_name: str):
        """Record creation of a new business concept.

        Args:
            company_code: The company code
            concept_name: The name of the created concept
        """
        fusion_concepts_created.add(
            1,
            {
                "company_code": company_code,
                "concept_name": concept_name,
            },
        )

        logger.info(
            "fusion_concept_created",
            company_code=company_code,
            concept_name=concept_name,
        )

    @staticmethod
    def record_concept_updated(
        company_code: str,
        concept_name: str,
        version: int,
    ):
        """Record update of an existing business concept.

        Args:
            company_code: The company code
            concept_name: The name of the updated concept
            version: The new version number
        """
        fusion_concepts_updated.add(
            1,
            {
                "company_code": company_code,
                "concept_name": concept_name,
                "version": str(version),
            },
        )

        logger.info(
            "fusion_concept_updated",
            company_code=company_code,
            concept_name=concept_name,
            version=version,
        )

    @staticmethod
    def record_concept_skipped(
        company_code: str,
        concept_name: str,
        reason: str,
    ):
        """Record skipping of a business concept.

        Args:
            company_code: The company code
            concept_name: The name of the skipped concept
            reason: The reason for skipping
        """
        fusion_concepts_skipped.add(
            1,
            {
                "company_code": company_code,
                "concept_name": concept_name,
                "reason": reason,
            },
        )

        logger.warning(
            "fusion_concept_skipped",
            company_code=company_code,
            concept_name=concept_name,
            reason=reason,
        )

    @staticmethod
    def record_retry(company_code: str, concept_name: str, attempt: int):
        """Record a retry attempt due to optimistic lock conflict.

        Args:
            company_code: The company code
            concept_name: The concept name
            attempt: The retry attempt number
        """
        fusion_retry_counter.add(
            1,
            {
                "company_code": company_code,
                "concept_name": concept_name,
                "attempt": str(attempt),
            },
        )

        logger.info(
            "fusion_retry_attempt",
            company_code=company_code,
            concept_name=concept_name,
            attempt=attempt,
        )


class FusionOperationContext:
    """Context object for collecting fusion operation results."""

    def __init__(self):
        """Initialize the context."""
        self.concepts_created = 0
        self.concepts_updated = 0
        self.concepts_skipped = 0
        self.has_errors = False

    def record_created(self):
        """Record a created concept."""
        self.concepts_created += 1

    def record_updated(self):
        """Record an updated concept."""
        self.concepts_updated += 1

    def record_skipped(self):
        """Record a skipped concept."""
        self.concepts_skipped += 1
        self.has_errors = True

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the operation results.

        Returns:
            Dictionary with operation statistics
        """
        return {
            "concepts_created": self.concepts_created,
            "concepts_updated": self.concepts_updated,
            "concepts_skipped": self.concepts_skipped,
            "total_processed": self.concepts_created + self.concepts_updated,
            "has_errors": self.has_errors,
        }
