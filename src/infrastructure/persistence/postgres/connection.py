"""PostgreSQL database connection management.

This module provides async database connection management using SQLAlchemy 2.0
with connection pooling and proper session handling.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.shared.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class DatabaseConnection:
    """Manages PostgreSQL database connections with async support."""

    def __init__(self, database_url: str | None = None):
        """Initialize database connection manager.

        Args:
            database_url: Optional database URL, defaults to settings
        """
        self.database_url = database_url or self._build_async_url()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def _build_async_url(self) -> str:
        """Build async database URL from settings."""
        from sqlalchemy.engine.url import URL

        db_settings = settings.database
        # Use SQLAlchemy's URL builder to properly handle special characters
        return URL.create(
            drivername="postgresql+asyncpg",
            username=db_settings.postgres_user,
            password=db_settings.postgres_password.get_secret_value(),
            host=db_settings.postgres_host,
            port=db_settings.postgres_port,
            database=db_settings.postgres_db,
        ).render_as_string(hide_password=False)

    async def initialize(self) -> None:
        """Initialize the database engine and session factory."""
        if self._engine is None:
            self._engine = create_async_engine(
                self.database_url,
                echo=settings.debug_mode,
                pool_size=20,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True,  # Enable connection health checks
                connect_args={
                    "server_settings": {"timezone": "Asia/Shanghai"},
                    "command_timeout": 60,
                },
            )
            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("database_connection_initialized", url=self.database_url)

    async def close(self) -> None:
        """Close the database engine."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("database_connection_closed")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        """Get an async database session.

        Yields:
            AsyncSession: Database session with automatic cleanup

        Raises:
            RuntimeError: If connection not initialized
        """
        if self._session_factory is None:
            await self.initialize()

        assert (  # noqa: S101
            self._session_factory is not None
        )  # Type narrowing for mypy
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @property
    def engine(self) -> AsyncEngine:
        """Get the async engine instance.

        Returns:
            AsyncEngine: The database engine

        Raises:
            RuntimeError: If not initialized
        """
        if self._engine is None:
            raise RuntimeError("Database connection not initialized")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory.

        Returns:
            async_sessionmaker: The session factory

        Raises:
            RuntimeError: If not initialized
        """
        if self._session_factory is None:
            raise RuntimeError("Database connection not initialized")
        return self._session_factory


# Global connection instance
_db_connection: DatabaseConnection | None = None


async def get_db_connection() -> DatabaseConnection:
    """Get or create the global database connection.

    Returns:
        DatabaseConnection: The initialized connection manager
    """
    global _db_connection
    if _db_connection is None:
        _db_connection = DatabaseConnection()
        await _db_connection.initialize()
    return _db_connection


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    """Get a database session from the global connection.

    Yields:
        AsyncSession: Database session with automatic cleanup
    """
    connection = await get_db_connection()
    async with connection.get_session() as session:
        yield session
