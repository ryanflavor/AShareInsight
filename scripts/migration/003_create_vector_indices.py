#!/usr/bin/env python
"""Create HNSW vector indices for optimized similarity search.

This migration creates HNSW (Hierarchical Navigable Small World) indices
on the embedding columns to enable high-speed vector similarity search.

Run this migration after vectors have been populated in the database.
"""

import asyncio
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv
from sqlalchemy import text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_db_connection

logger = structlog.get_logger(__name__)


async def create_vector_indices():
    """Create HNSW indices for vector similarity search."""
    logger.info("starting_vector_index_creation")

    # Get database connection
    db_connection = await get_db_connection()

    try:
        async with db_connection.engine.begin() as conn:
            # Check if pgvector extension is enabled
            result = await conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            if not result.fetchone():
                logger.info("enabling_pgvector_extension")
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Check if index already exists
            result = await conn.execute(
                text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'business_concepts_master' 
                AND indexname = 'idx_business_concepts_embedding_hnsw'
                """)
            )

            if result.fetchone():
                logger.info(
                    "index_already_exists",
                    index_name="idx_business_concepts_embedding_hnsw",
                )
            else:
                # Create HNSW index on business_concepts_master.embedding
                logger.info(
                    "creating_hnsw_index",
                    table="business_concepts_master",
                    column="embedding",
                )

                # Use CONCURRENTLY to avoid locking the table
                # Note: CONCURRENTLY cannot be used inside a transaction block
                # So we need to commit the transaction first
                await conn.commit()

                # Create new connection for concurrent index creation
                async with db_connection.engine.connect() as new_conn:
                    await new_conn.execute(text("SET statement_timeout = '30min'"))

                    await new_conn.execute(
                        text("""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_business_concepts_embedding_hnsw
                        ON business_concepts_master 
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 200)
                        """)
                    )
                    await new_conn.commit()

                logger.info("hnsw_index_created_successfully")

            # Update table statistics for query planner
            async with db_connection.engine.begin() as conn:
                logger.info("updating_table_statistics")
                await conn.execute(text("VACUUM ANALYZE business_concepts_master"))

            # Verify index configuration
            async with db_connection.engine.begin() as conn:
                result = await conn.execute(
                    text("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        indexdef
                    FROM pg_indexes
                    WHERE tablename = 'business_concepts_master'
                    AND indexname LIKE '%embedding%'
                    """)
                )

                indices = result.fetchall()
                for idx in indices:
                    logger.info(
                        "index_info",
                        schema=idx[0],
                        table=idx[1],
                        index_name=idx[2],
                        definition=idx[3],
                    )

            logger.info("vector_index_creation_completed")

    except Exception as e:
        logger.error("vector_index_creation_failed", error=str(e), exc_info=True)
        raise

    finally:
        await db_connection.close()


async def drop_vector_indices():
    """Drop HNSW indices (for rollback purposes)."""
    logger.info("starting_vector_index_removal")

    # Get database connection
    db_connection = await get_db_connection()

    try:
        async with db_connection.engine.begin() as conn:
            # Drop index if exists
            await conn.execute(
                text("DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw")
            )
            logger.info("vector_index_dropped_successfully")

    except Exception as e:
        logger.error("vector_index_removal_failed", error=str(e), exc_info=True)
        raise

    finally:
        await db_connection.close()


def main():
    """Main entry point for the migration script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Create or drop HNSW vector indices for optimized similarity search"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Drop the vector indices instead of creating them",
    )

    args = parser.parse_args()

    # Configure logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Load environment variables
    load_dotenv(override=True)

    try:
        if args.rollback:
            asyncio.run(drop_vector_indices())
        else:
            asyncio.run(create_vector_indices())
    except KeyboardInterrupt:
        logger.warning("migration_interrupted_by_user")
        sys.exit(1)
    except Exception as e:
        logger.error("migration_failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
