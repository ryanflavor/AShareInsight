"""Infrastructure-specific exceptions for the AShareInsight application."""


class InfrastructureException(Exception):  # noqa: N818
    """Base exception for all infrastructure-related errors."""

    pass


class ExternalServiceError(InfrastructureException):
    """Raised when an external service call fails."""

    pass


class DatabaseError(InfrastructureException):
    """Raised when a database operation fails."""

    pass


class ConfigurationError(InfrastructureException):
    """Raised when there's a configuration issue."""

    pass
