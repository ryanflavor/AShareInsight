"""Metrics collection for archiving operations.

This module provides specialized metrics for tracking document archiving
operations in the AShareInsight system.
"""

from typing import Any

import structlog

from src.infrastructure.monitoring.telemetry import add_span_attributes

logger = structlog.get_logger(__name__)


class ArchiveMetrics:
    """Helper class for recording archive-specific metrics."""

    @staticmethod
    def record_archive_operation(
        operation: str,
        company_code: str,
        doc_type: str,
        doc_id: str | None,
        file_hash: str | None,
        raw_data_size: int,
        duration_seconds: float,
        success: bool = True,
        already_exists: bool = False,
        error: str | None = None,
    ) -> None:
        """Record metrics for an archive operation.

        Args:
            operation: Type of archive operation (save, find, exists)
            company_code: Company stock code
            doc_type: Document type (annual_report, research_report)
            doc_id: Document UUID if available
            file_hash: File SHA-256 hash if available
            raw_data_size: Size of raw LLM output in bytes
            duration_seconds: Operation duration in seconds
            success: Whether operation succeeded
            already_exists: Whether document already existed (for save operations)
            error: Error message if operation failed
        """
        attributes = {
            "archive.operation": operation,
            "archive.company_code": company_code,
            "archive.doc_type": doc_type,
            "archive.raw_data_size_bytes": raw_data_size,
            "archive.duration_seconds": duration_seconds,
            "archive.success": success,
            "archive.already_exists": already_exists,
        }

        if doc_id:
            attributes["archive.doc_id"] = doc_id
        if file_hash:
            attributes["archive.file_hash"] = file_hash
        if error:
            attributes["archive.error"] = error

        # Add to current span
        add_span_attributes(attributes)

        # Log metrics for aggregation
        logger.info(
            "Archive operation completed",
            extra={
                "operation": operation,
                "company_code": company_code,
                "doc_type": doc_type,
                "doc_id": doc_id,
                "file_hash": file_hash,
                "raw_data_size": raw_data_size,
                "duration_seconds": duration_seconds,
                "success": success,
                "already_exists": already_exists,
                "error": error,
            },
        )

    @staticmethod
    def record_repository_stats(stats: dict[str, Any]) -> None:
        """Record repository statistics.

        Args:
            stats: Statistics dictionary from repository
        """
        attributes = {
            "archive.total_documents": stats.get("total_documents", 0),
            "archive.latest_document_date": stats.get("latest_document_date"),
        }

        # Add document counts by type
        for doc_type, count in stats.get("documents_by_type", {}).items():
            attributes[f"archive.documents.{doc_type}"] = count

        # Add document counts by status
        for status, count in stats.get("documents_by_status", {}).items():
            attributes[f"archive.status.{status}"] = count

        add_span_attributes(attributes)

        logger.info(
            "Archive repository statistics",
            extra=stats,
        )
