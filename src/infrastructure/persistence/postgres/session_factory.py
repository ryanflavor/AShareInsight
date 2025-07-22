"""Session factory for PostgreSQL with dependency injection support.

This module provides a session factory that creates database sessions
with proper transaction management for use case layer injection.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)


class SessionFactory:
    """Factory for creating database sessions with dependency injection support."""

    def __init__(self, engine: AsyncEngine):
        """Initialize the session factory with an async engine.

        Args:
            engine: The SQLAlchemy async engine
        """
        self.engine = engine
        self.async_session = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Important for async operations
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        """Get a database session with automatic transaction management.

        This method creates a new session and automatically manages the transaction.
        If an exception occurs, the transaction is rolled back.

        Yields:
            AsyncSession: A database session

        Example:
            async with session_factory.get_session() as session:
                # Use session for database operations
                # Transaction is automatically committed on success
                # or rolled back on exception
        """
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def begin_nested(self, session: AsyncSession) -> AsyncGenerator[AsyncSession]:
        """Begin a nested transaction (SAVEPOINT).

        This is useful for implementing partial rollbacks within a larger transaction.

        Args:
            session: The parent session

        Yields:
            AsyncSession: The same session with a nested transaction

        Example:
            async with session_factory.get_session() as session:
                # Main transaction
                await archive_document(session)

                async with session_factory.begin_nested(session) as nested_session:
                    # Nested transaction for fusion
                    await update_master_data(nested_session)
                    # If this fails, only the fusion is rolled back
        """
        async with session.begin_nested():
            try:
                yield session
            except Exception:
                logger.warning("nested_transaction_rollback")
                raise

    async def execute_in_transaction(self, operation, *args, **kwargs) -> any:
        """Execute an operation within a transaction.

        This is a convenience method for executing a single operation
        with automatic transaction management.

        Args:
            operation: An async callable that takes a session as first argument
            *args: Additional positional arguments for the operation
            **kwargs: Additional keyword arguments for the operation

        Returns:
            The result of the operation

        Example:
            result = await session_factory.execute_in_transaction(
                repository.save, entity
            )
        """
        async with self.get_session() as session:
            return await operation(session, *args, **kwargs)
