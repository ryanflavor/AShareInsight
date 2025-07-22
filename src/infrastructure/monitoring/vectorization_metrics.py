"""Metrics collection for vectorization operations.

This module provides metrics collection and instrumentation for
the business concept vectorization and embedding generation process.
"""

import time
from contextlib import contextmanager
from typing import Any

import structlog
from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

logger = structlog.get_logger(__name__)

# Initialize tracer and meter
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Define metrics
vectorization_operations_counter = meter.create_counter(
    name="vectorization.operations.total",
    description="Total number of vectorization operations",
    unit="1",
)

embeddings_generated_counter = meter.create_counter(
    name="vectorization.embeddings.generated",
    description="Number of embeddings generated",
    unit="1",
)

embedding_generation_duration = meter.create_histogram(
    name="vectorization.embedding.duration_ms",
    description="Duration of embedding generation in milliseconds",
    unit="ms",
)

vectorization_batch_duration = meter.create_histogram(
    name="vectorization.batch.duration_ms",
    description="Duration of batch vectorization in milliseconds",
    unit="ms",
)

vectorization_total_duration = meter.create_histogram(
    name="vectorization.total.duration_ms",
    description="Total duration of vectorization operation in milliseconds",
    unit="ms",
)

model_call_errors_counter = meter.create_counter(
    name="vectorization.model.errors",
    description="Number of model call errors",
    unit="1",
)

vector_dimension_errors_counter = meter.create_counter(
    name="vectorization.dimension.errors",
    description="Number of vector dimension mismatch errors",
    unit="1",
)

db_update_duration = meter.create_histogram(
    name="vectorization.db_update.duration_ms",
    description="Duration of database update operations in milliseconds",
    unit="ms",
)

active_vectorization_operations = meter.create_up_down_counter(
    name="vectorization.operations.active",
    description="Number of currently active vectorization operations",
    unit="1",
)

vectorization_queue_depth = meter.create_up_down_counter(
    name="vectorization.queue.depth",
    description="Number of concepts pending vectorization",
    unit="1",
)

tokens_processed_counter = meter.create_counter(
    name="vectorization.tokens.processed",
    description="Total number of tokens processed",
    unit="1",
)

vector_norm_histogram = meter.create_histogram(
    name="vectorization.vector.norm",
    description="L2 norm of generated vectors",
    unit="1",
)


class VectorizationMetrics:
    """Helper class for recording vectorization operation metrics."""

    @staticmethod
    @contextmanager
    def track_vectorization_operation(
        company_code: str,
        total_concepts: int,
        operation_type: str = "batch",
    ):
        """Track a complete vectorization operation with timing and metrics.

        Args:
            company_code: The company code being processed
            total_concepts: Total number of concepts to process
            operation_type: Type of operation (batch, incremental, full)

        Yields:
            A context object for recording operation results
        """
        start_time = time.time()

        # Start span for tracing
        with tracer.start_as_current_span(
            "vectorization.operation",
            attributes={
                "company_code": company_code,
                "total_concepts": total_concepts,
                "operation_type": operation_type,
            },
        ) as span:
            # Increment active operations
            active_vectorization_operations.add(1, {"company_code": company_code})

            try:
                # Create context object to collect results
                context = VectorizationOperationContext()
                yield context

                # Record successful operation
                vectorization_operations_counter.add(
                    1,
                    {
                        "company_code": company_code,
                        "status": "success",
                        "operation_type": operation_type,
                        "partial": str(context.has_errors),
                    },
                )

                # Set span status
                if context.has_errors:
                    span.set_status(
                        Status(
                            StatusCode.OK,
                            "Vectorization completed with some errors",
                        )
                    )
                else:
                    span.set_status(Status(StatusCode.OK))

            except Exception as e:
                # Record failed operation
                vectorization_operations_counter.add(
                    1,
                    {
                        "company_code": company_code,
                        "status": "failed",
                        "operation_type": operation_type,
                    },
                )

                # Set error status on span
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

            finally:
                # Record duration
                duration_ms = (time.time() - start_time) * 1000
                vectorization_total_duration.record(
                    duration_ms,
                    {"company_code": company_code, "operation_type": operation_type},
                )

                # Decrement active operations
                active_vectorization_operations.add(-1, {"company_code": company_code})

                # Add final attributes to span
                span.set_attributes(
                    {
                        "embeddings_generated": context.embeddings_generated,
                        "model_errors": context.model_errors,
                        "dimension_errors": context.dimension_errors,
                        "duration_ms": duration_ms,
                        "tokens_processed": context.tokens_processed,
                    }
                )

    @staticmethod
    @contextmanager
    def track_embedding_generation(
        batch_size: int,
        model: str = "qwen",
        expected_dimension: int = 2560,
    ):
        """Track embedding generation for a batch of texts.

        Args:
            batch_size: Number of texts in the batch
            model: Model being used for embedding
            expected_dimension: Expected embedding dimension

        Yields:
            None
        """
        start_time = time.time()

        with tracer.start_as_current_span(
            "vectorization.embedding.generate",
            attributes={
                "batch_size": batch_size,
                "model": model,
                "expected_dimension": expected_dimension,
            },
        ) as span:
            try:
                yield
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                model_call_errors_counter.add(
                    1,
                    {"model": model, "error_type": type(e).__name__},
                )
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                embedding_generation_duration.record(
                    duration_ms,
                    {"model": model, "batch_size": str(batch_size)},
                )
                span.set_attribute("duration_ms", duration_ms)

    @staticmethod
    @contextmanager
    def track_db_update(batch_size: int, operation: str = "update"):
        """Track database update operations.

        Args:
            batch_size: Number of records being updated
            operation: Type of database operation

        Yields:
            None
        """
        start_time = time.time()

        with tracer.start_as_current_span(
            "vectorization.db.update",
            attributes={
                "batch_size": batch_size,
                "operation": operation,
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
                db_update_duration.record(
                    duration_ms,
                    {"operation": operation, "batch_size": str(batch_size)},
                )
                span.set_attribute("duration_ms", duration_ms)

    @staticmethod
    def record_embedding_generated(
        company_code: str,
        concept_name: str,
        dimension: int,
        tokens: int,
        norm: float,
    ):
        """Record successful embedding generation.

        Args:
            company_code: The company code
            concept_name: The name of the concept
            dimension: Dimension of the generated embedding
            tokens: Number of tokens processed
            norm: L2 norm of the vector
        """
        embeddings_generated_counter.add(
            1,
            {
                "company_code": company_code,
                "dimension": str(dimension),
            },
        )

        tokens_processed_counter.add(
            tokens,
            {"company_code": company_code},
        )

        vector_norm_histogram.record(
            norm,
            {"company_code": company_code},
        )

        logger.info(
            "embedding_generated",
            company_code=company_code,
            concept_name=concept_name,
            dimension=dimension,
            tokens=tokens,
            norm=norm,
        )

    @staticmethod
    def record_dimension_error(
        company_code: str,
        concept_name: str,
        expected: int,
        actual: int,
    ):
        """Record vector dimension mismatch error.

        Args:
            company_code: The company code
            concept_name: The concept name
            expected: Expected dimension
            actual: Actual dimension received
        """
        vector_dimension_errors_counter.add(
            1,
            {
                "company_code": company_code,
                "expected": str(expected),
                "actual": str(actual),
            },
        )

        logger.error(
            "vector_dimension_error",
            company_code=company_code,
            concept_name=concept_name,
            expected=expected,
            actual=actual,
        )

    @staticmethod
    def record_model_error(
        company_code: str,
        error_type: str,
        error_message: str,
    ):
        """Record model call error.

        Args:
            company_code: The company code
            error_type: Type of error
            error_message: Error message
        """
        model_call_errors_counter.add(
            1,
            {
                "company_code": company_code,
                "error_type": error_type,
            },
        )

        logger.error(
            "vectorization_model_error",
            company_code=company_code,
            error_type=error_type,
            error_message=error_message,
        )

    @staticmethod
    def update_queue_depth(delta: int, company_code: str | None = None):
        """Update the vectorization queue depth.

        Args:
            delta: Change in queue depth (positive for additions,
                negative for completions)
            company_code: Optional company code for filtering
        """
        attributes = {}
        if company_code:
            attributes["company_code"] = company_code

        vectorization_queue_depth.add(delta, attributes)

        logger.info(
            "vectorization_queue_updated",
            delta=delta,
            company_code=company_code,
        )

    @staticmethod
    def record_batch_completed(
        batch_size: int,
        successful: int,
        failed: int,
        duration_ms: float,
    ):
        """Record completion of a vectorization batch.

        Args:
            batch_size: Total size of the batch
            successful: Number of successful vectorizations
            failed: Number of failed vectorizations
            duration_ms: Duration in milliseconds
        """
        vectorization_batch_duration.record(
            duration_ms,
            {
                "batch_size": str(batch_size),
                "success_rate": str(round(successful / batch_size * 100, 2)),
            },
        )

        logger.info(
            "vectorization_batch_completed",
            batch_size=batch_size,
            successful=successful,
            failed=failed,
            duration_ms=duration_ms,
            throughput=batch_size / (duration_ms / 1000) if duration_ms > 0 else 0,
        )


class VectorizationOperationContext:
    """Context object for collecting vectorization operation results."""

    def __init__(self):
        """Initialize the context."""
        self.embeddings_generated = 0
        self.model_errors = 0
        self.dimension_errors = 0
        self.tokens_processed = 0
        self.has_errors = False

    def record_embedding(self, tokens: int = 0):
        """Record a successfully generated embedding.

        Args:
            tokens: Number of tokens processed
        """
        self.embeddings_generated += 1
        self.tokens_processed += tokens

    def record_model_error(self):
        """Record a model error."""
        self.model_errors += 1
        self.has_errors = True

    def record_dimension_error(self):
        """Record a dimension error."""
        self.dimension_errors += 1
        self.has_errors = True

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the operation results.

        Returns:
            Dictionary with operation statistics
        """
        return {
            "embeddings_generated": self.embeddings_generated,
            "model_errors": self.model_errors,
            "dimension_errors": self.dimension_errors,
            "tokens_processed": self.tokens_processed,
            "has_errors": self.has_errors,
            "success_rate": (
                self.embeddings_generated
                / (
                    self.embeddings_generated
                    + self.model_errors
                    + self.dimension_errors
                )
                if (
                    self.embeddings_generated
                    + self.model_errors
                    + self.dimension_errors
                )
                > 0
                else 0
            ),
        }
