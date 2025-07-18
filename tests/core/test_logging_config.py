"""
Tests for centralized logging configuration with structured JSON formatting
"""

import json
import logging
import sys
from io import StringIO
from pathlib import Path

# Add core package to path for imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "packages" / "core" / "src")
)

import pytest
from core.logging_config import (
    StructuredJSONFormatter,
    get_correlation_id,
    get_logger,
    set_correlation_id,
    setup_logging,
)


class TestStructuredJSONFormatter:
    """Test the structured JSON formatter"""

    def test_json_format_basic(self):
        """Test basic JSON formatting"""
        # Create a formatter
        formatter = StructuredJSONFormatter()

        # Create a log record
        logger = logging.getLogger("test.module")
        record = logger.makeRecord(
            name="test.module",
            level=logging.INFO,
            fn="test.py",
            lno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Format the record
        formatted = formatter.format(record)

        # Parse the JSON
        log_data = json.loads(formatted)

        # Verify required fields
        assert "timestamp" in log_data
        assert log_data["level"] == "INFO"
        assert log_data["module"] == "test.module"
        assert log_data["message"] == "Test message"
        assert "correlation_id" in log_data  # May be None

    def test_json_format_with_correlation_id(self):
        """Test JSON formatting with correlation ID"""
        # Set a correlation ID
        test_id = "test-correlation-123"
        set_correlation_id(test_id)

        formatter = StructuredJSONFormatter()
        logger = logging.getLogger("test")
        record = logger.makeRecord(
            name="test.module",
            level=logging.ERROR,
            fn="test.py",
            lno=42,
            msg="Error message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data["correlation_id"] == test_id
        assert log_data["level"] == "ERROR"
        assert log_data["message"] == "Error message"

    def test_json_format_with_extra_fields(self):
        """Test JSON formatting with extra context fields"""
        formatter = StructuredJSONFormatter()
        logger = logging.getLogger("test")
        record = logger.makeRecord(
            name="test.module",
            level=logging.DEBUG,
            fn="test.py",
            lno=42,
            msg="Debug message",
            args=(),
            exc_info=None,
        )

        # Add extra fields to the record
        record.request_id = "req-123"
        record.user_id = "user-456"

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert "extra" in log_data
        assert log_data["extra"]["request_id"] == "req-123"
        assert log_data["extra"]["user_id"] == "user-456"


class TestCorrelationID:
    """Test correlation ID functionality"""

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID"""
        test_id = "test-corr-456"
        result = set_correlation_id(test_id)

        assert result == test_id
        assert get_correlation_id() == test_id

    def test_auto_generate_correlation_id(self):
        """Test auto-generation of correlation ID"""
        result = set_correlation_id()

        assert result is not None
        assert len(result) > 0
        assert get_correlation_id() == result


class TestLoggingSetup:
    """Test logging setup functionality"""

    def test_setup_logging_json_format(self, capfd):
        """Test setup logging with JSON format"""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Setup logging with JSON format
        setup_logging(level="INFO", json_format=True)

        # Create a logger and log a message
        logger = get_logger("test.setup")
        logger.info("Test JSON logging")

        # Capture output
        captured = capfd.readouterr()

        # Verify JSON format
        assert captured.out.strip()  # Should have output
        log_data = json.loads(captured.out.strip())
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test JSON logging"

    def test_setup_logging_simple_format(self, capfd):
        """Test setup logging with simple format"""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Setup logging with simple format
        setup_logging(level="DEBUG", json_format=False)

        # Create a logger and log a message
        logger = get_logger("test.simple")
        logger.debug("Test simple logging")

        # Capture output
        captured = capfd.readouterr()

        # Verify simple format (not JSON)
        assert "Test simple logging" in captured.out
        # Should not be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.out.strip())


class TestGetLogger:
    """Test logger creation with context"""

    def test_get_logger_without_context(self):
        """Test getting logger without context"""
        logger = get_logger("test.module")
        assert logger.name == "test.module"

    def test_get_logger_with_context(self, capfd):
        """Test getting logger with context"""
        # Setup JSON logging
        setup_logging(level="INFO", json_format=True)

        # Create logger with context
        logger = get_logger("test.context", service="test-service", version="1.0.0")
        logger.info("Test with context")

        # Capture and verify output
        captured = capfd.readouterr()
        log_data = json.loads(captured.out.strip())

        assert log_data["message"] == "Test with context"
        assert "extra" in log_data
        assert log_data["extra"]["service"] == "test-service"
        assert log_data["extra"]["version"] == "1.0.0"


def test_integration_architecture_compliance():
    """
    Integration test to verify architecture compliance with
    "结构化JSON日志" requirement from docs/architecture/1-高阶架构-high-level-architecture.md
    """
    # Setup JSON logging (architecture requirement)
    setup_logging(level="INFO", json_format=True, correlation_id="arch-test-123")

    # Create logger with module context
    logger = get_logger(__name__, component="validation", test_type="architecture")

    # Capture logging output
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    formatter = StructuredJSONFormatter()
    handler.setFormatter(formatter)

    # Replace existing handlers with our test handler
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    try:
        # Log various types of messages
        logger.info("Architecture compliance test started")
        logger.warning("This is a warning message", extra={"test_step": "validation"})
        logger.error("This is an error message for testing")

        # Get the logged output
        log_output = log_stream.getvalue()
        log_lines = [line for line in log_output.strip().split("\n") if line]

        # Verify all log entries are valid JSON
        parsed_logs = []
        for line in log_lines:
            log_data = json.loads(line)
            parsed_logs.append(log_data)

        # Verify structured format compliance
        assert len(parsed_logs) == 3

        for log_entry in parsed_logs:
            # Required fields per architecture
            assert "timestamp" in log_entry
            assert "level" in log_entry
            assert "module" in log_entry
            assert "message" in log_entry
            assert "correlation_id" in log_entry

            # Verify correlation ID is set
            assert log_entry["correlation_id"] == "arch-test-123"

            # Verify module context
            if "extra" in log_entry:
                assert log_entry["extra"]["component"] == "validation"
                assert log_entry["extra"]["test_type"] == "architecture"

        print("✅ Architecture compliance verified: 结构化JSON日志 requirement met")

    finally:
        # Restore original handlers
        root_logger.handlers.clear()
        root_logger.handlers.extend(original_handlers)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
