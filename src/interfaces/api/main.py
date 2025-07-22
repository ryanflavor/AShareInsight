"""
Main FastAPI application module for AShareInsight API.

This module initializes and configures the FastAPI application instance,
following hexagonal architecture principles where the API layer serves
as an inbound adapter for external HTTP interactions.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.interfaces.api.exception_handlers import register_exception_handlers
from src.interfaces.api.v1.routers import health, search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Manages application lifecycle events.

    Args:
        app: The FastAPI application instance

    Yields:
        None
    """
    # Startup logic
    # Database connections are initialized lazily on first use

    yield

    # Shutdown logic
    from src.interfaces.api.dependencies import shutdown_dependencies

    await shutdown_dependencies()


def create_application() -> FastAPI:
    """
    Creates and configures the FastAPI application instance.

    Returns:
        FastAPI: Configured FastAPI application
    """
    app = FastAPI(
        title="AShareInsight API",
        description=(
            "Enterprise-grade concept retrieval system for A-share listed companies. "
            "This API provides semantic search capabilities to find similar companies "
            "based on business concepts and market characteristics."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Register routers
    app.include_router(
        health.router,
        tags=["Health"],
    )
    app.include_router(
        search.router,
        prefix="/api/v1/search",
        tags=["Search"],
    )

    # Import and register metrics router
    from src.interfaces.api.v1.routers import metrics

    app.include_router(
        metrics.router,
        prefix="/api/v1/metrics",
        tags=["Metrics"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    return app


# Create the application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.interfaces.api.main:app",
        host="127.0.0.1",  # Use localhost for development
        port=8000,
        reload=True,
        log_level="info",
    )
