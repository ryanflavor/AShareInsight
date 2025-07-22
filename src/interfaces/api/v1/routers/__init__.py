"""
API v1 routers.

This module exports all router instances for the API endpoints.
"""

from src.interfaces.api.v1.routers import health, search

__all__ = ["health", "search"]
