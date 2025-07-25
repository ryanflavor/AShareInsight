"""Custom logger configuration for AShareInsight."""

import os
import sys

import structlog
from structlog.processors import (
    TimeStamper,
    add_log_level,
    format_exc_info,
)
from structlog.stdlib import BoundLogger


def get_logger(name: str) -> BoundLogger:
    """Get a configured structlog logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog BoundLogger instance
    """
    # Configure structlog if not already configured
    if not structlog.is_configured():
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer()
                if sys.stderr.isatty()
                else structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Set stdlib logging level
        import logging

        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=getattr(logging, log_level, logging.INFO),
        )

    return structlog.get_logger(name)
