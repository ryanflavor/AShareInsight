"""Custom exceptions for AShareInsight."""


class AShareInsightError(Exception):
    """Base exception for AShareInsight application."""

    pass


class LLMServiceError(AShareInsightError):
    """Exception raised when LLM service operations fail."""

    pass


class DocumentProcessingError(AShareInsightError):
    """Exception raised when document processing fails."""

    pass


class ValidationError(AShareInsightError):
    """Exception raised when validation fails."""

    pass


class ConfigurationError(AShareInsightError):
    """Exception raised when configuration is invalid."""

    pass
