"""
Exception handlers for the API layer.

This module provides centralized exception handling to ensure consistent
error responses across all API endpoints.
"""

import uuid
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.shared.exceptions import AShareInsightException, CompanyNotFoundError


def create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        error_code: Machine-readable error code
        message: User-friendly error message
        status_code: HTTP status code
        request_id: Optional request ID for tracking
        details: Optional additional error details

    Returns:
        JSONResponse: Standardized error response
    """
    content = {
        "error": {
            "code": error_code,
            "message": message,
        }
    }

    if request_id:
        content["error"]["request_id"] = request_id

    if details:
        content["error"]["details"] = details

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError | ValidationError
) -> JSONResponse:
    """
    Handle validation errors from Pydantic models.

    Args:
        request: The incoming request
        exc: The validation exception

    Returns:
        JSONResponse: Formatted validation error response
    """
    errors = exc.errors() if hasattr(exc, "errors") else []
    formatted_errors = []

    for error in errors:
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        formatted_errors.append(
            {
                "field": loc,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "validation_error"),
            }
        )

    return create_error_response(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request_id=str(uuid.uuid4()),
        details={"validation_errors": formatted_errors},
    )


async def company_not_found_handler(
    request: Request, exc: CompanyNotFoundError
) -> JSONResponse:
    """
    Handle CompanyNotFoundError exceptions.

    Args:
        request: The incoming request
        exc: The CompanyNotFoundError exception

    Returns:
        JSONResponse: Formatted not found error response
    """
    return create_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=status.HTTP_404_NOT_FOUND,
        request_id=str(uuid.uuid4()),
        details=exc.details,
    )


async def ashare_insight_exception_handler(
    request: Request, exc: AShareInsightException
) -> JSONResponse:
    """
    Handle all custom AShareInsight exceptions.

    Args:
        request: The incoming request
        exc: The AShareInsightException

    Returns:
        JSONResponse: Formatted error response
    """
    # Map exception types to HTTP status codes
    status_code_map = {
        "INVALID_FILTER": status.HTTP_400_BAD_REQUEST,
        "SEARCH_SERVICE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
    }

    status_code = status_code_map.get(
        exc.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR
    )

    return create_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=status_code,
        request_id=str(uuid.uuid4()),
        details=exc.details,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all unhandled exceptions.

    Args:
        request: The incoming request
        exc: The unhandled exception

    Returns:
        JSONResponse: Generic error response
    """
    # In production, we should log the full exception details
    # but not expose them to the client
    return create_error_response(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request_id=str(uuid.uuid4()),
    )


def register_exception_handlers(app) -> None:
    """
    Register all exception handlers with the FastAPI app.

    Args:
        app: The FastAPI application instance
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(CompanyNotFoundError, company_not_found_handler)
    app.add_exception_handler(AShareInsightException, ashare_insight_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
