"""
Integration test for complete environment initialization.
This test validates all acceptance criteria from Story 1.1.
"""

import subprocess
from pathlib import Path

import psycopg
import pytest
import redis
import yaml
from psycopg.rows import dict_row


class TestEnvironmentInitialization:
    """Test complete environment initialization."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parents[2]

    @pytest.fixture
    def db_connection(self):
        """Create database connection."""
        conn_string = (
            "postgresql://ashareinsight:ashareinsight_password@"
            "localhost:5432/ashareinsight_db"
        )
        conn = psycopg.connect(conn_string, row_factory=dict_row)
        yield conn
        conn.close()

    @pytest.fixture
    def redis_client(self):
        """Create Redis client."""
        client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        yield client
        client.close()

    def test_acceptance_criteria_1_git_repository(self, project_root):
        """AC1: A new Git repository has been created locally."""
        git_dir = project_root / ".git"
        assert git_dir.exists(), "Git repository not initialized"
        assert git_dir.is_dir(), ".git is not a directory"

    def test_acceptance_criteria_2_docker_compose(self, project_root):
        """AC2: docker-compose.yml exists and can start PostgreSQL with pgvector."""
        docker_compose_path = project_root / "docker" / "docker-compose.yaml"
        assert docker_compose_path.exists(), "docker-compose.yaml does not exist"

        # Check if containers are running
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )

        running_containers = result.stdout.strip().split("\n")
        assert "ashareinsight-postgres" in running_containers
        assert "ashareinsight-redis" in running_containers
        assert "ashareinsight-adminer" in running_containers

    def test_postgresql_with_pgvector(self, db_connection):
        """Test PostgreSQL has pgvector extension."""
        with db_connection.cursor() as cur:
            # Check pgvector extension
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            result = cur.fetchone()
            assert result is not None, "pgvector extension not installed"

            # Check version supports halfvec
            version = result["extversion"]
            major, minor, patch = map(int, version.split("."))
            assert (
                major > 0 or minor >= 7
            ), f"pgvector version {version} does not support halfvec"

    def test_acceptance_criteria_3_database_schema(self, db_connection):
        """AC3: Database migration creates all tables matching architecture docs."""
        with db_connection.cursor() as cur:
            # Test companies table
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'companies'
                ORDER BY ordinal_position
            """
            )
            companies_columns = cur.fetchall()

            # Verify required columns exist
            column_names = [col["column_name"] for col in companies_columns]
            assert "company_code" in column_names
            assert "company_name_full" in column_names
            assert "company_name_short" in column_names
            assert "exchange" in column_names
            assert "created_at" in column_names
            assert "updated_at" in column_names

            # Test source_documents table
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'source_documents'
                AND column_name IN ('raw_llm_output', 'extraction_metadata')
            """
            )
            jsonb_columns = cur.fetchall()
            assert len(jsonb_columns) == 2
            for col in jsonb_columns:
                assert col["data_type"] == "jsonb"

            # Test business_concepts_master table with halfvec
            cur.execute(
                """
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = 'business_concepts_master'
                AND column_name = 'embedding'
            """
            )
            embedding_col = cur.fetchone()
            assert embedding_col is not None
            assert "halfvec" in embedding_col["udt_name"]

            # Verify HNSW index exists
            cur.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'business_concepts_master'
                AND indexname = 'idx_concepts_embedding'
            """
            )
            index_def = cur.fetchone()
            assert index_def is not None
            assert "hnsw" in index_def["indexdef"].lower()
            assert "halfvec_cosine_ops" in index_def["indexdef"]

    def test_foreign_key_constraints(self, db_connection):
        """Test foreign key constraints are properly set up."""
        with db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    tc.constraint_name,
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
            """
            )

            foreign_keys = cur.fetchall()

            # Check source_documents -> companies FK
            source_docs_fk = [
                fk
                for fk in foreign_keys
                if fk["table_name"] == "source_documents"
                and fk["foreign_table_name"] == "companies"
            ]
            assert (
                len(source_docs_fk) > 0
            ), "Missing FK from source_documents to companies"

            # Check business_concepts_master -> companies FK
            concepts_company_fk = [
                fk
                for fk in foreign_keys
                if fk["table_name"] == "business_concepts_master"
                and fk["foreign_table_name"] == "companies"
            ]
            assert (
                len(concepts_company_fk) > 0
            ), "Missing FK from business_concepts_master to companies"

    def test_database_functions_and_views(self, db_connection):
        """Test custom functions and views are created."""
        with db_connection.cursor() as cur:
            # Test search_similar_concepts function
            cur.execute(
                """
                SELECT routine_name
                FROM information_schema.routines
                WHERE routine_schema = 'public'
                AND routine_name = 'search_similar_concepts'
            """
            )
            assert (
                cur.fetchone() is not None
            ), "search_similar_concepts function not found"

            # Test v_active_concepts view
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public'
                AND table_name = 'v_active_concepts'
            """
            )
            assert cur.fetchone() is not None, "v_active_concepts view not found"

    def test_redis_connectivity(self, redis_client):
        """Test Redis is properly configured and accessible."""
        # Test ping
        assert redis_client.ping() is True

        # Test basic operations
        test_key = "_test_ashareinsight"
        redis_client.set(test_key, "test_value", ex=60)
        value = redis_client.get(test_key)
        assert value == "test_value"

        # Cleanup
        redis_client.delete(test_key)

    def test_configuration_files_content(self, project_root):
        """Test configuration files have correct content."""
        # Test development.yaml
        dev_config_path = project_root / "config" / "development.yaml"
        with open(dev_config_path) as f:
            dev_config = yaml.safe_load(f)

        assert dev_config["app"]["environment"] == "development"
        assert dev_config["app"]["debug"] is True
        assert "database" in dev_config
        assert "redis" in dev_config
        assert "models" in dev_config

        # Test production.yaml has different settings
        prod_config_path = project_root / "config" / "production.yaml"
        with open(prod_config_path) as f:
            prod_config = yaml.safe_load(f)

        assert prod_config["app"]["environment"] == "production"
        assert prod_config["app"]["debug"] is False
        assert "security" in prod_config
        assert "performance" in prod_config

    def test_project_metadata(self, project_root):
        """Test project metadata in pyproject.toml."""
        import tomllib

        pyproject_path = project_root / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        project = config["project"]
        assert project["name"] == "ashareinsight"
        assert project["requires-python"] == ">=3.13"

        # Check key dependencies
        deps = project["dependencies"]
        assert any("langchain>=" in d for d in deps)
        assert any("langchain-postgres>=" in d for d in deps)
        assert any("pgvector>=" in d for d in deps)
        assert any("fastapi>=" in d for d in deps)
