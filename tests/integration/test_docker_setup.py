"""
Integration test to verify Docker setup is correct.
"""

from pathlib import Path

import pytest
import yaml


class TestDockerSetup:
    """Test that Docker configuration is properly set up."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parents[2]

    def test_docker_compose_exists(self, project_root):
        """Test that docker-compose.yaml exists."""
        docker_compose_path = project_root / "docker" / "docker-compose.yaml"
        assert docker_compose_path.exists(), "docker-compose.yaml does not exist"

    def test_docker_compose_structure(self, project_root):
        """Test that docker-compose.yaml has required services."""
        docker_compose_path = project_root / "docker" / "docker-compose.yaml"

        with open(docker_compose_path) as f:
            config = yaml.safe_load(f)

        # Check version
        assert "version" in config
        assert config["version"] == "3.9"

        # Check services
        assert "services" in config
        services = config["services"]

        # Check PostgreSQL service
        assert "postgres" in services
        postgres = services["postgres"]
        assert postgres["image"] == "pgvector/pgvector:pg16"
        assert "5432:5432" in postgres["ports"]
        assert "environment" in postgres
        assert "volumes" in postgres
        assert "healthcheck" in postgres

        # Check Redis service
        assert "redis" in services
        redis = services["redis"]
        assert "redis:7-alpine" in redis["image"]
        assert "6379:6379" in redis["ports"]

        # Check volumes
        assert "volumes" in config
        assert "postgres_data" in config["volumes"]
        assert "redis_data" in config["volumes"]

        # Check networks
        assert "networks" in config
        assert "ashareinsight-network" in config["networks"]

    def test_env_example_exists(self, project_root):
        """Test that .env.example exists with required variables."""
        env_example_path = project_root / ".env.example"
        assert env_example_path.exists(), ".env.example does not exist"

        with open(env_example_path) as f:
            content = f.read()

        # Check required environment variables
        required_vars = [
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_DB",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "REDIS_HOST",
            "REDIS_PORT",
            "API_HOST",
            "API_PORT",
            "LOG_LEVEL",
        ]

        for var in required_vars:
            assert var in content, f"Missing required variable: {var}"

    def test_pgvector_configuration(self, project_root):
        """Test that PostgreSQL is configured with pgvector."""
        docker_compose_path = project_root / "docker" / "docker-compose.yaml"

        with open(docker_compose_path) as f:
            config = yaml.safe_load(f)

        postgres = config["services"]["postgres"]

        # Check that pgvector image is used
        assert "pgvector/pgvector" in postgres["image"]

        # Check that shared_preload_libraries includes vector
        command = postgres.get("command", "")
        assert "shared_preload_libraries='vector'" in command
