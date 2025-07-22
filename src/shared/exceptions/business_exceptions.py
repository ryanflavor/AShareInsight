"""Business-specific exceptions for the AShareInsight application."""


class BusinessException(Exception):  # noqa: N818
    """Base exception for all business logic errors."""

    pass


class OptimisticLockError(BusinessException):
    """Raised when a concurrent update conflict occurs due to version mismatch."""

    pass


class EntityNotFoundError(BusinessException):
    """Raised when a requested entity is not found."""

    pass


class DuplicateEntityError(BusinessException):
    """Raised when attempting to create an entity that already exists."""

    pass


class InvalidStateError(BusinessException):
    """Raised when an operation is attempted on an entity in an invalid state."""

    pass
