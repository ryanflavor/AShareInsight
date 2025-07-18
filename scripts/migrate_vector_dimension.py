#!/usr/bin/env python3
"""
Migration script to update vector dimension from 1024 to 2560.

This script handles the dimension mismatch between story 1.1 (1024) and story 1.2 (2560).
"""

import sys
from pathlib import Path

# Add core package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "core" / "src"))

import psycopg
from core.config import get_settings
from core.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


def migrate_vector_dimension():
    """Migrate vector dimension from 1024 to 2560."""
    settings = get_settings()
    connection_string = settings.database.connection_string

    logger.info("Starting vector dimension migration from 1024 to 2560...")

    try:
        with psycopg.connect(connection_string) as conn:
            with conn.cursor() as cur:
                # Check if migration is needed
                cur.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        udt_name,
                        character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = 'business_concepts_master'
                    AND column_name = 'embedding'
                """)

                result = cur.fetchone()
                if not result:
                    logger.error(
                        "Table business_concepts_master or column embedding not found!"
                    )
                    return False

                logger.info(f"Current column info: {result}")

                # Check current vector dimension
                cur.execute("""
                    SELECT 
                        typmod 
                    FROM pg_attribute a
                    JOIN pg_class c ON a.attrelid = c.oid
                    JOIN pg_type t ON a.atttypid = t.oid
                    WHERE c.relname = 'business_concepts_master'
                    AND a.attname = 'embedding'
                    AND t.typname = 'vector'
                """)

                typmod = cur.fetchone()
                if typmod and typmod[0]:
                    current_dim = typmod[0] - 4  # PostgreSQL typmod offset
                    logger.info(f"Current vector dimension: {current_dim}")

                    if current_dim == 2560:
                        logger.info(
                            "Vector dimension is already 2560. No migration needed."
                        )
                        return True
                    elif current_dim != 1024:
                        logger.warning(f"Unexpected vector dimension: {current_dim}")

                # Check if table has data
                cur.execute("SELECT COUNT(*) FROM business_concepts_master")
                row_count = cur.fetchone()[0]

                if row_count > 0:
                    logger.warning(
                        f"Table has {row_count} rows. Migration will DELETE all data!"
                    )
                    response = input(
                        "Do you want to continue? This will DELETE all data in business_concepts_master! (yes/no): "
                    )
                    if response.lower() != "yes":
                        logger.info("Migration cancelled by user.")
                        return False

                # Perform migration
                logger.info("Starting migration...")

                # Drop dependent objects
                logger.info("Dropping HNSW index...")
                cur.execute("DROP INDEX IF EXISTS idx_business_concepts_embedding_hnsw")

                # Delete all data (required for dimension change)
                if row_count > 0:
                    logger.info("Deleting all data from business_concepts_master...")
                    cur.execute("DELETE FROM business_concepts_master")

                # Alter column type
                logger.info("Altering column type to VECTOR(2560)...")
                cur.execute(
                    "ALTER TABLE business_concepts_master ALTER COLUMN embedding TYPE VECTOR(2560)"
                )

                # Note: Cannot create HNSW index due to pgvector's 2000 dimension limit
                logger.info(
                    "Skipping HNSW index creation (pgvector limit: max 2000 dimensions)"
                )
                logger.info("Will use exact nearest neighbor search without index")

                # Verify migration
                cur.execute("""
                    SELECT 
                        typmod 
                    FROM pg_attribute a
                    JOIN pg_class c ON a.attrelid = c.oid
                    JOIN pg_type t ON a.atttypid = t.oid
                    WHERE c.relname = 'business_concepts_master'
                    AND a.attname = 'embedding'
                    AND t.typname = 'vector'
                """)

                new_typmod = cur.fetchone()
                if new_typmod and new_typmod[0]:
                    new_dim = new_typmod[0] - 4
                    logger.info(f"New vector dimension: {new_dim}")

                    if new_dim == 2560:
                        logger.info("✅ Migration completed successfully!")
                        return True
                    else:
                        logger.error(
                            f"Migration failed! Dimension is {new_dim}, expected 2560"
                        )
                        return False

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def main():
    """Main entry point."""
    setup_logging(level="INFO")

    logger.info("=" * 60)
    logger.info("Vector Dimension Migration Script")
    logger.info("=" * 60)

    success = migrate_vector_dimension()

    if success:
        logger.info("\n🎉 Migration completed successfully!")
        logger.info("The database is now ready for 2560-dimensional vectors.")
        return 0
    else:
        logger.error("\n❌ Migration failed! Please check the logs.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
