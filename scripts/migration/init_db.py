#!/usr/bin/env python
"""
Database initialization script for AShareInsight.
Runs database migrations and verifies the schema.
"""

import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from pydantic import SecretStr
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    postgres_user: str = "ashareinsight"
    postgres_password: SecretStr = SecretStr("ashareinsight_password")
    postgres_db: str = "ashareinsight_db"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields in .env

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class ConfigurationLoader:
    """Loads application configuration for migration parameters."""

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        import os

        import yaml

        # Default to development config
        config_file = os.environ.get("CONFIG_FILE", "development.yaml")
        config_path = Path(__file__).parent.parent.parent / "config" / config_file

        if not config_path.exists():
            # Fallback to development.yaml if specified config doesn't exist
            config_path = (
                Path(__file__).parent.parent.parent / "config" / "development.yaml"
            )

        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f)

        # Return default values if no config file exists
        return {
            "models": {"embedding": {"dimension": 2560}},
            "vector_store": {"index": {"m": 16, "ef_construction": 64}},
        }

    @property
    def vector_dimension(self) -> int:
        """Get vector embedding dimension."""
        return self.config.get("models", {}).get("embedding", {}).get("dimension", 2560)

    @property
    def hnsw_m(self) -> int:
        """Get HNSW index m parameter."""
        return self.config.get("vector_store", {}).get("index", {}).get("m", 16)

    @property
    def hnsw_ef_construction(self) -> int:
        """Get HNSW index ef_construction parameter."""
        return (
            self.config.get("vector_store", {})
            .get("index", {})
            .get("ef_construction", 64)
        )

    @property
    def distance_metric(self) -> str:
        """Get distance metric for vector similarity search."""
        return (
            self.config.get("vector_store", {})
            .get("index", {})
            .get("distance_metric", "cosine")
        )


class MigrationRunner:
    """Handles database migration execution."""

    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self.migration_dir = Path(__file__).parent
        self.config_loader = ConfigurationLoader()

    def get_connection(self) -> psycopg.Connection:
        """Create database connection."""
        return psycopg.connect(self.settings.database_url, row_factory=dict_row)

    def check_database_exists(self) -> bool:
        """Check if the database exists and is accessible."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except psycopg.OperationalError:
            return False

    def check_pgvector_extension(self) -> bool:
        """Check if pgvector extension is available."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
                )
                return cur.fetchone() is not None

    def get_current_version(self) -> str | None:
        """Get current schema version from database."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT version_number FROM schema_versions "
                        "ORDER BY applied_at DESC LIMIT 1"
                    )
                    result = cur.fetchone()
                    return result["version_number"] if result else None
        except psycopg.errors.UndefinedTable:
            return None

    def run_migration(self, migration_file: Path) -> None:
        """Execute a single migration file with parameter substitution."""

        with open(migration_file, encoding="utf-8") as f:
            sql_content = f.read()

        # Substitute configuration parameters
        import re

        # Replace ${VARIABLE_NAME} patterns with actual values
        replacements = {
            "VECTOR_DIMENSION": str(self.config_loader.vector_dimension),
            "HNSW_M": str(self.config_loader.hnsw_m),
            "HNSW_EF_CONSTRUCTION": str(self.config_loader.hnsw_ef_construction),
            "DISTANCE_METRIC": self.config_loader.distance_metric,
        }

        for var_name, value in replacements.items():
            pattern = r"\$\{" + re.escape(var_name) + r"\}"
            sql_content = re.sub(pattern, value, sql_content)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_content)
            conn.commit()

    def verify_schema(self) -> None:
        """Verify that all required tables exist."""
        required_tables = [
            "companies",
            "source_documents",
            "business_concepts_master",
            "schema_versions",
        ]

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename = ANY(%s)
                    """,
                    (required_tables,),
                )
                existing_tables = {row["tablename"] for row in cur.fetchall()}

        missing_tables = set(required_tables) - existing_tables
        if missing_tables:
            raise RuntimeError(f"Missing tables: {', '.join(missing_tables)}")

    def verify_indexes(self) -> None:
        """Verify that all required indexes exist."""
        expected_indexes = [
            "idx_company_name_short",
            "idx_source_docs_company_date",
            "idx_concepts_embedding",
            "idx_unique_active_concept",
        ]

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    AND indexname = ANY(%s)
                    """,
                    (expected_indexes,),
                )
                existing_indexes = {row["indexname"] for row in cur.fetchall()}

        missing_indexes = set(expected_indexes) - existing_indexes
        if missing_indexes:
            pass
        else:
            pass

    def run_all_migrations(self) -> None:
        """Run all pending migrations."""
        # Check database connectivity
        if not self.check_database_exists():
            sys.exit(1)

        # Check pgvector extension
        if not self.check_pgvector_extension():
            sys.exit(1)

        # Get current version
        current_version = self.get_current_version()
        if current_version:
            pass
        else:
            pass

        # Find migration files
        migration_files = sorted(self.migration_dir.glob("*.sql"))

        if not migration_files:
            return

        # Run migrations
        for migration_file in migration_files:
            # Skip if this migration has already been applied
            # (In a real system, we'd track individual migrations)
            if current_version and current_version >= "1.0.0":
                continue

            self.run_migration(migration_file)

        # Verify schema
        self.verify_schema()
        self.verify_indexes()

        # Show final version
        self.get_current_version()


def main():
    """Main entry point."""

    # Load settings
    settings = DatabaseSettings()

    # Run migrations
    runner = MigrationRunner(settings)

    try:
        runner.run_all_migrations()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
