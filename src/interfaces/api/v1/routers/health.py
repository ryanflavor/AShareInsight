"""
Health check endpoint for API monitoring.

This module provides a simple health check endpoint that can be used
by load balancers and monitoring systems to verify API availability.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health", response_class=JSONResponse)
async def health_check() -> dict[str, str]:
    """
    Check the health status of the API.

    Returns:
        dict: Health status response
    """
    return {"status": "ok"}
