"""Unit tests for vectorization metrics collection."""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import metrics, trace
from opentelemetry.trace import StatusCode

from src.infrastructure.monitoring.vectorization_metrics import (
    VectorizationMetrics,
    VectorizationOperationContext,
)


@pytest.fixture
def mock_tracer():
    """Mock OpenTelemetry tracer."""
    tracer = MagicMock(spec=trace.Tracer)
    span = MagicMock()
    span.__enter__ = MagicMock(return_value=span)
    span.__exit__ = MagicMock(return_value=None)
    tracer.start_as_current_span.return_value = span
    return tracer, span


@pytest.fixture
def mock_meter():
    """Mock OpenTelemetry meter."""
    meter = MagicMock(spec=metrics.Meter)
    counter = MagicMock()
    histogram = MagicMock()
    up_down_counter = MagicMock()

    meter.create_counter.return_value = counter
    meter.create_histogram.return_value = histogram
    meter.create_up_down_counter.return_value = up_down_counter

    return meter, counter, histogram, up_down_counter


class TestVectorizationMetrics:
    """Test cases for VectorizationMetrics class."""

    @patch("src.infrastructure.monitoring.vectorization_metrics.tracer")
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.active_vectorization_operations"
    )
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vectorization_operations_counter"
    )
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vectorization_total_duration"
    )
    def test_track_vectorization_operation_success(
        self,
        mock_duration,
        mock_counter,
        mock_active_ops,
        mock_tracer,
    ):
        """Test successful vectorization operation tracking."""
        # Setup
        span = MagicMock()
        span.__enter__ = MagicMock(return_value=span)
        span.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = span

        # Execute
        with VectorizationMetrics.track_vectorization_operation(
            company_code="TEST001",
            total_concepts=100,
            operation_type="batch",
        ) as context:
            context.record_embedding(50)
            context.record_embedding(50)

        # Verify
        mock_tracer.start_as_current_span.assert_called_once_with(
            "vectorization.operation",
            attributes={
                "company_code": "TEST001",
                "total_concepts": 100,
                "operation_type": "batch",
            },
        )

        # Verify active operations counter
        assert mock_active_ops.add.call_count == 2
        mock_active_ops.add.assert_any_call(1, {"company_code": "TEST001"})
        mock_active_ops.add.assert_any_call(-1, {"company_code": "TEST001"})

        # Verify operation counter
        mock_counter.add.assert_called_once_with(
            1,
            {
                "company_code": "TEST001",
                "status": "success",
                "operation_type": "batch",
                "partial": "False",
            },
        )

        # Verify span status
        span.set_status.assert_called_once()
        status_call = span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.OK

        # Verify final attributes
        span.set_attributes.assert_called_once()
        attrs = span.set_attributes.call_args[0][0]
        assert attrs["embeddings_generated"] == 2
        assert attrs["tokens_processed"] == 100

    @patch("src.infrastructure.monitoring.vectorization_metrics.tracer")
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.active_vectorization_operations"
    )
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vectorization_operations_counter"
    )
    def test_track_vectorization_operation_with_errors(
        self,
        mock_counter,
        mock_active_ops,
        mock_tracer,
    ):
        """Test vectorization operation tracking with errors."""
        # Setup
        span = MagicMock()
        span.__enter__ = MagicMock(return_value=span)
        span.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = span

        # Execute
        with VectorizationMetrics.track_vectorization_operation(
            company_code="TEST001",
            total_concepts=100,
        ) as context:
            context.record_embedding(50)
            context.record_model_error()
            context.record_dimension_error()

        # Verify partial success status
        span.set_status.assert_called_once()
        status_call = span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.OK
        # OpenTelemetry doesn't support descriptions for OK status

        # Verify operation counter shows partial success
        mock_counter.add.assert_called_once()
        call_args = mock_counter.add.call_args[0]
        assert call_args[1]["partial"] == "True"

    @patch("src.infrastructure.monitoring.vectorization_metrics.tracer")
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.active_vectorization_operations"
    )
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vectorization_operations_counter"
    )
    def test_track_vectorization_operation_exception(
        self,
        mock_counter,
        mock_active_ops,
        mock_tracer,
    ):
        """Test vectorization operation tracking with exception."""
        # Setup
        span = MagicMock()
        span.__enter__ = MagicMock(return_value=span)
        span.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = span

        # Execute
        with pytest.raises(ValueError):
            with VectorizationMetrics.track_vectorization_operation(
                company_code="TEST001",
                total_concepts=100,
            ):
                raise ValueError("Test error")

        # Verify error handling
        span.set_status.assert_called_once()
        status_call = span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.ERROR

        span.record_exception.assert_called_once()

        # Verify operation counter shows failure
        mock_counter.add.assert_called_once_with(
            1,
            {
                "company_code": "TEST001",
                "status": "failed",
                "operation_type": "batch",
            },
        )

    @patch("src.infrastructure.monitoring.vectorization_metrics.tracer")
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.embedding_generation_duration"
    )
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.model_call_errors_counter"
    )
    def test_track_embedding_generation(
        self,
        mock_error_counter,
        mock_duration,
        mock_tracer,
    ):
        """Test embedding generation tracking."""
        # Setup
        span = MagicMock()
        span.__enter__ = MagicMock(return_value=span)
        span.__exit__ = MagicMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = span

        # Execute success case
        with VectorizationMetrics.track_embedding_generation(
            batch_size=10,
            model="qwen",
            expected_dimension=2560,
        ):
            pass

        # Verify
        mock_tracer.start_as_current_span.assert_called_once_with(
            "vectorization.embedding.generate",
            attributes={
                "batch_size": 10,
                "model": "qwen",
                "expected_dimension": 2560,
            },
        )

        span.set_status.assert_called_once()
        status_call = span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.OK
        mock_duration.record.assert_called_once()

        # Execute error case
        with pytest.raises(RuntimeError):
            with VectorizationMetrics.track_embedding_generation(
                batch_size=10,
                model="qwen",
            ):
                raise RuntimeError("Model error")

        # Verify error tracking
        mock_error_counter.add.assert_called_once_with(
            1,
            {"model": "qwen", "error_type": "RuntimeError"},
        )

    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.embeddings_generated_counter"
    )
    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.tokens_processed_counter"
    )
    @patch("src.infrastructure.monitoring.vectorization_metrics.vector_norm_histogram")
    @patch("src.infrastructure.monitoring.vectorization_metrics.logger")
    def test_record_embedding_generated(
        self,
        mock_logger,
        mock_norm_hist,
        mock_tokens_counter,
        mock_embeddings_counter,
    ):
        """Test recording successful embedding generation."""
        VectorizationMetrics.record_embedding_generated(
            company_code="TEST001",
            concept_name="Test Concept",
            dimension=2560,
            tokens=100,
            norm=1.5,
        )

        # Verify metrics
        mock_embeddings_counter.add.assert_called_once_with(
            1,
            {
                "company_code": "TEST001",
                "dimension": "2560",
            },
        )

        mock_tokens_counter.add.assert_called_once_with(
            100,
            {"company_code": "TEST001"},
        )

        mock_norm_hist.record.assert_called_once_with(
            1.5,
            {"company_code": "TEST001"},
        )

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "embedding_generated",
            company_code="TEST001",
            concept_name="Test Concept",
            dimension=2560,
            tokens=100,
            norm=1.5,
        )

    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vector_dimension_errors_counter"
    )
    @patch("src.infrastructure.monitoring.vectorization_metrics.logger")
    def test_record_dimension_error(
        self,
        mock_logger,
        mock_dimension_errors,
    ):
        """Test recording vector dimension errors."""
        VectorizationMetrics.record_dimension_error(
            company_code="TEST001",
            concept_name="Test Concept",
            expected=2560,
            actual=1024,
        )

        # Verify metrics
        mock_dimension_errors.add.assert_called_once_with(
            1,
            {
                "company_code": "TEST001",
                "expected": "2560",
                "actual": "1024",
            },
        )

        # Verify logging
        mock_logger.error.assert_called_once_with(
            "vector_dimension_error",
            company_code="TEST001",
            concept_name="Test Concept",
            expected=2560,
            actual=1024,
        )

    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vectorization_queue_depth"
    )
    @patch("src.infrastructure.monitoring.vectorization_metrics.logger")
    def test_update_queue_depth(
        self,
        mock_logger,
        mock_queue_depth,
    ):
        """Test queue depth updates."""
        # Test with company code
        VectorizationMetrics.update_queue_depth(10, "TEST001")

        mock_queue_depth.add.assert_called_once_with(
            10,
            {"company_code": "TEST001"},
        )

        # Test without company code
        VectorizationMetrics.update_queue_depth(-5)

        assert mock_queue_depth.add.call_count == 2
        last_call = mock_queue_depth.add.call_args_list[-1]
        assert last_call[0][0] == -5
        assert last_call[0][1] == {}

    @patch(
        "src.infrastructure.monitoring.vectorization_metrics.vectorization_batch_duration"
    )
    @patch("src.infrastructure.monitoring.vectorization_metrics.logger")
    def test_record_batch_completed(
        self,
        mock_logger,
        mock_batch_duration,
    ):
        """Test batch completion recording."""
        VectorizationMetrics.record_batch_completed(
            batch_size=50,
            successful=48,
            failed=2,
            duration_ms=1500.0,
        )

        # Verify metrics
        mock_batch_duration.record.assert_called_once_with(
            1500.0,
            {
                "batch_size": "50",
                "success_rate": "96.0",
            },
        )

        # Verify logging
        mock_logger.info.assert_called_once()
        log_args = mock_logger.info.call_args[1]
        assert log_args["batch_size"] == 50
        assert log_args["successful"] == 48
        assert log_args["failed"] == 2
        assert log_args["duration_ms"] == 1500.0
        assert log_args["throughput"] == pytest.approx(33.33, rel=0.01)


class TestVectorizationOperationContext:
    """Test cases for VectorizationOperationContext."""

    def test_context_initialization(self):
        """Test context initialization."""
        context = VectorizationOperationContext()
        assert context.embeddings_generated == 0
        assert context.model_errors == 0
        assert context.dimension_errors == 0
        assert context.tokens_processed == 0
        assert context.has_errors is False

    def test_record_embedding(self):
        """Test recording successful embeddings."""
        context = VectorizationOperationContext()

        context.record_embedding(100)
        context.record_embedding(150)

        assert context.embeddings_generated == 2
        assert context.tokens_processed == 250
        assert context.has_errors is False

    def test_record_errors(self):
        """Test recording various errors."""
        context = VectorizationOperationContext()

        context.record_model_error()
        context.record_dimension_error()

        assert context.model_errors == 1
        assert context.dimension_errors == 1
        assert context.has_errors is True

    def test_get_summary(self):
        """Test getting operation summary."""
        context = VectorizationOperationContext()

        # Record some operations
        context.record_embedding(100)
        context.record_embedding(150)
        context.record_model_error()

        summary = context.get_summary()

        assert summary["embeddings_generated"] == 2
        assert summary["model_errors"] == 1
        assert summary["dimension_errors"] == 0
        assert summary["tokens_processed"] == 250
        assert summary["has_errors"] is True
        assert summary["success_rate"] == pytest.approx(0.6667, rel=0.01)

    def test_get_summary_all_failed(self):
        """Test summary when all operations failed."""
        context = VectorizationOperationContext()

        context.record_model_error()
        context.record_model_error()

        summary = context.get_summary()

        assert summary["success_rate"] == 0
