#!/usr/bin/env python3
"""
Migration 004: Add unique constraint on file_path

This migration adds a unique constraint on the file_path column
in the source_documents table to prevent duplicate documents
from being inserted for the same file.
"""

import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_session

logger = structlog.get_logger(__name__)


async def run_migration():
    """Add unique constraint on file_path."""
    async with get_session() as session:
        try:
            # First, check if the constraint already exists
            check_constraint_query = text("""
                SELECT COUNT(*)
                FROM pg_constraint
                WHERE conname = 'uq_source_documents_file_path'
            """)
            result = await session.execute(check_constraint_query)
            constraint_exists = result.scalar() > 0

            if constraint_exists:
                logger.info("Unique constraint on file_path already exists, skipping")
                return

            # Check for existing duplicates that would violate the constraint
            logger.info("Checking for duplicate file_path values...")
            duplicate_check_query = text("""
                SELECT file_path, COUNT(*) as count
                FROM source_documents
                WHERE file_path IS NOT NULL
                GROUP BY file_path
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """)
            result = await session.execute(duplicate_check_query)
            duplicates = result.fetchall()

            if duplicates:
                logger.warning(
                    f"Found {len(duplicates)} duplicate file_path values. "
                    "These must be resolved before adding the constraint."
                )
                for dup in duplicates[:5]:  # Show first 5
                    logger.warning(f"  {dup[0]}: {dup[1]} occurrences")
                if len(duplicates) > 5:
                    logger.warning(f"  ... and {len(duplicates) - 5} more")

                # Offer to clean up duplicates
                logger.info(
                    "Run the cleanup_duplicates.py script first to resolve duplicates."
                )
                return

            # Add the unique constraint
            logger.info("Adding unique constraint on file_path...")
            add_constraint_query = text("""
                ALTER TABLE source_documents
                ADD CONSTRAINT uq_source_documents_file_path UNIQUE (file_path)
            """)
            await session.execute(add_constraint_query)
            await session.commit()

            logger.info("✅ Successfully added unique constraint on file_path")

            # Commit the constraint first
            await session.commit()

            # Create index outside of transaction for CONCURRENTLY
            logger.info("Creating index on file_path for better query performance...")

            # Close the current session to end transaction
            await session.close()

            # Create a new session for the index creation
            async with get_session() as new_session:
                await new_session.execute(text("COMMIT"))  # Ensure no transaction
                create_index_query = text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_source_documents_file_path
                    ON source_documents (file_path)
                    WHERE file_path IS NOT NULL
                """)
                await new_session.execute(create_index_query)
                logger.info("✅ Successfully created index on file_path")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            await session.rollback()
            raise


async def rollback_migration():
    """Rollback the migration by removing the constraint and index."""
    async with get_session() as session:
        try:
            # Drop the constraint
            logger.info("Dropping unique constraint on file_path...")
            drop_constraint_query = text("""
                ALTER TABLE source_documents
                DROP CONSTRAINT IF EXISTS uq_source_documents_file_path
            """)
            await session.execute(drop_constraint_query)

            # Drop the index
            logger.info("Dropping index on file_path...")
            drop_index_query = text("""
                DROP INDEX IF EXISTS idx_source_documents_file_path
            """)
            await session.execute(drop_index_query)

            await session.commit()
            logger.info("✅ Successfully rolled back migration")

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            await session.rollback()
            raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add unique constraint on file_path")
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback the migration instead of applying it",
    )
    args = parser.parse_args()

    if args.rollback:
        asyncio.run(rollback_migration())
    else:
        asyncio.run(run_migration())
