"""
Integration test to verify database migration scripts.
"""

import re
from pathlib import Path

import pytest


class TestDatabaseMigration:
    """Test database migration scripts."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parents[2]

    def test_migration_script_exists(self, project_root):
        """Test that migration scripts exist."""
        migration_dir = project_root / "scripts" / "migration"
        assert migration_dir.exists(), "Migration directory does not exist"

        # Check for SQL migration files
        sql_files = list(migration_dir.glob("*.sql"))
        assert len(sql_files) > 0, "No SQL migration files found"

        # Check for Python migration runner
        init_db_script = migration_dir / "init_db.py"
        assert init_db_script.exists(), "init_db.py script does not exist"

    def test_initial_schema_structure(self, project_root):
        """Test that initial schema SQL is properly structured."""
        initial_schema = (
            project_root / "scripts" / "migration" / "001_initial_schema.sql"
        )
        assert initial_schema.exists(), "Initial schema SQL file does not exist"

        with open(initial_schema) as f:
            sql_content = f.read()

        # Check for pgvector extension
        assert "CREATE EXTENSION IF NOT EXISTS vector" in sql_content

        # Check for all required tables
        required_tables = [
            "companies",
            "source_documents",
            "business_concepts_master",
            "schema_versions",
        ]

        for table in required_tables:
            pattern = rf"CREATE TABLE IF NOT EXISTS {table}"
            assert re.search(
                pattern, sql_content, re.IGNORECASE
            ), f"Missing table: {table}"

        # Check for halfvec column type with parameterized dimension
        assert (
            "halfvec(${VECTOR_DIMENSION})" in sql_content
        ), "Missing parameterized halfvec column type"

        # Check for HNSW index
        assert "USING hnsw" in sql_content, "Missing HNSW index"
        assert "halfvec_cosine_ops" in sql_content, "Missing cosine distance operator"

    def test_migration_script_structure(self, project_root):
        """Test that migration Python script has required components."""
        init_db_script = project_root / "scripts" / "migration" / "init_db.py"

        with open(init_db_script) as f:
            script_content = f.read()

        # Check for required classes
        assert "class DatabaseSettings" in script_content
        assert "class MigrationRunner" in script_content

        # Check for required methods
        required_methods = [
            "check_database_exists",
            "check_pgvector_extension",
            "run_migration",
            "verify_schema",
            "verify_indexes",
        ]

        for method in required_methods:
            assert f"def {method}" in script_content, f"Missing method: {method}"

    def test_table_constraints(self, project_root):
        """Test that tables have proper constraints."""
        initial_schema = (
            project_root / "scripts" / "migration" / "001_initial_schema.sql"
        )

        with open(initial_schema) as f:
            sql_content = f.read()

        # Check foreign key constraints
        assert "REFERENCES companies(company_code)" in sql_content
        assert "REFERENCES source_documents(doc_id)" in sql_content

        # Check unique constraints
        assert "company_name_full VARCHAR(255) UNIQUE NOT NULL" in sql_content
        assert "idx_unique_active_concept" in sql_content

        # Check check constraints
        assert "CHECK (importance_score >= 0 AND importance_score <= 1)" in sql_content
        assert "CHECK (doc_type IN" in sql_content
        assert "CHECK (processing_status IN" in sql_content

    def test_indexes_defined(self, project_root):
        """Test that all required indexes are defined."""
        initial_schema = (
            project_root / "scripts" / "migration" / "001_initial_schema.sql"
        )

        with open(initial_schema) as f:
            sql_content = f.read()

        required_indexes = [
            "idx_company_name_short",
            "idx_source_docs_company_date",
            "idx_source_docs_status",
            "idx_source_docs_raw_output",
            "idx_concepts_company",
            "idx_concepts_importance",
            "idx_concepts_embedding",
            "idx_unique_active_concept",
        ]

        for index in required_indexes:
            assert index in sql_content, f"Missing index: {index}"

    def test_functions_and_views(self, project_root):
        """Test that required functions and views are defined."""
        initial_schema = (
            project_root / "scripts" / "migration" / "001_initial_schema.sql"
        )

        with open(initial_schema) as f:
            sql_content = f.read()

        # Check for update trigger function
        assert "CREATE OR REPLACE FUNCTION update_updated_at_column()" in sql_content

        # Check for search function
        assert "CREATE OR REPLACE FUNCTION search_similar_concepts(" in sql_content

        # Check for view
        assert "CREATE OR REPLACE VIEW v_active_concepts" in sql_content
