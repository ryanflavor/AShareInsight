"""
Centralized logging configuration with structured JSON formatting.

This module provides unified logging configuration that implements the architectural
requirement for "结构化JSON日志" (Structured JSON logging) as specified in
docs/architecture/1-高阶架构-high-level-architecture.md.

Features:
- Structured JSON output format
- Context enrichment with correlation IDs and module information
- Centralized configuration to replace scattered logging.basicConfig() calls
- Support for both development and production environments
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

# Context variable for correlation ID tracking across async operations
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class StructuredJSONFormatter(logging.Formatter):
    """
    Custom JSON formatter that creates structured log entries with context enrichment.

    Each log entry includes:
    - timestamp: ISO 8601 formatted timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - module: Module name where the log originated
    - message: The actual log message
    - correlation_id: Request/operation correlation ID for tracing
    - extra_fields: Any additional context provided with the log call
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        # Build base log entry structure
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.name,  # Use logger name as module identifier
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the log call
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
            }:
                extra_fields[key] = value

        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def set_correlation_id(correlation_id: str | None = None) -> str:
    """
    Set correlation ID for current context.

    Args:
        correlation_id: Custom correlation ID, or None to generate a new one

    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    correlation_id_var.set(correlation_id)
    return correlation_id


def get_correlation_id() -> str | None:
    """Get current correlation ID from context."""
    return correlation_id_var.get()


def setup_logging(
    level: str = "INFO", json_format: bool = True, correlation_id: str | None = None
) -> None:
    """
    Configure centralized logging with structured JSON format.

    This function replaces all scattered logging.basicConfig() calls throughout
    the codebase to provide unified, architecturally-compliant logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to use structured JSON formatting (default: True)
        correlation_id: Optional correlation ID to set for this session
    """
    # Set correlation ID if provided
    if correlation_id:
        set_correlation_id(correlation_id)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove any existing handlers to avoid duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)

    if json_format:
        # Use structured JSON formatter for production compliance
        formatter = StructuredJSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S.%fZ")
    else:
        # Use simple formatter for development/debugging
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger(name: str, **context: Any) -> logging.Logger | logging.LoggerAdapter:
    """
    Get a logger instance with module context.

    Args:
        name: Logger name (typically __name__ or module name)
        **context: Additional context to include in all log messages

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Add context as extra fields if provided
    if context:
        # Create a logger adapter to automatically include context
        class ContextAdapter(logging.LoggerAdapter):
            def process(self, msg: str, kwargs: dict[str, Any]) -> tuple:
                # Merge provided context with any extra kwargs
                extra = kwargs.get("extra", {})
                extra.update(self.extra)
                kwargs["extra"] = extra
                return msg, kwargs

        logger = ContextAdapter(logger, context)

    return logger


# Pre-configured logger for this module
logger = get_logger(__name__)
