"""
Custom exceptions for AShareInsight application.

This module defines domain-specific exceptions that can be raised
throughout the application and handled consistently at the API layer.
"""

from typing import Any


class AShareInsightException(Exception):
    """Base exception for all AShareInsight custom exceptions."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the exception.

        Args:
            message: User-friendly error message
            error_code: Machine-readable error code
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}


class CompanyNotFoundError(AShareInsightException):
    """Raised when a company identifier cannot be found in the database."""

    def __init__(self, identifier: str) -> None:
        """
        Initialize CompanyNotFoundError.

        Args:
            identifier: The company identifier that was not found
        """
        super().__init__(
            message=f"Company with identifier '{identifier}' not found",
            error_code="COMPANY_NOT_FOUND",
            details={"identifier": identifier},
        )


class InvalidFilterError(AShareInsightException):
    """Raised when invalid filter parameters are provided."""

    def __init__(self, filter_name: str, reason: str) -> None:
        """
        Initialize InvalidFilterError.

        Args:
            filter_name: Name of the invalid filter
            reason: Reason why the filter is invalid
        """
        super().__init__(
            message=f"Invalid filter '{filter_name}': {reason}",
            error_code="INVALID_FILTER",
            details={"filter_name": filter_name, "reason": reason},
        )


class SearchServiceError(AShareInsightException):
    """Raised when the search service encounters an error."""

    def __init__(self, operation: str, reason: str) -> None:
        """
        Initialize SearchServiceError.

        Args:
            operation: The search operation that failed
            reason: Reason for the failure
        """
        super().__init__(
            message=f"Search operation '{operation}' failed: {reason}",
            error_code="SEARCH_SERVICE_ERROR",
            details={"operation": operation, "reason": reason},
        )


class DatabaseConnectionError(AShareInsightException):
    """Raised when database connection fails."""

    def __init__(self, database_name: str, reason: str) -> None:
        """
        Initialize DatabaseConnectionError.

        Args:
            database_name: Name of the database
            reason: Reason for the connection failure
        """
        super().__init__(
            message=f"Failed to connect to database '{database_name}': {reason}",
            error_code="DATABASE_CONNECTION_ERROR",
            details={"database_name": database_name, "reason": reason},
        )


class ModelLoadError(AShareInsightException):
    """Raised when model loading fails."""

    def __init__(self, message: str) -> None:
        """
        Initialize ModelLoadError.

        Args:
            message: Detailed error message
        """
        super().__init__(
            message=message,
            error_code="MODEL_LOAD_ERROR",
        )


class ModelInferenceError(AShareInsightException):
    """Raised when model inference fails."""

    def __init__(self, message: str) -> None:
        """
        Initialize ModelInferenceError.

        Args:
            message: Detailed error message
        """
        super().__init__(
            message=message,
            error_code="MODEL_INFERENCE_ERROR",
        )


__all__ = [
    "AShareInsightException",
    "CompanyNotFoundError",
    "InvalidFilterError",
    "SearchServiceError",
    "DatabaseConnectionError",
    "ModelLoadError",
    "ModelInferenceError",
]
