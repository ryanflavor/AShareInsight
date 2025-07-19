"""
Integration test to verify project structure follows hexagonal architecture.
"""

import os
from pathlib import Path

import pytest


class TestProjectStructure:
    """Test that the project structure follows the defined architecture."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parents[2]

    def test_main_directories_exist(self, project_root):
        """Test that all main directories exist."""
        expected_dirs = [
            "src",
            "src/domain",
            "src/domain/entities",
            "src/domain/services",
            "src/application",
            "src/application/use_cases",
            "src/application/ports",
            "src/infrastructure",
            "src/infrastructure/persistence",
            "src/infrastructure/persistence/postgres",
            "src/infrastructure/llm",
            "src/infrastructure/llm/langchain",
            "src/infrastructure/document_processing",
            "src/infrastructure/monitoring",
            "src/interfaces",
            "src/interfaces/api",
            "src/interfaces/api/v1",
            "src/interfaces/api/v1/routers",
            "src/interfaces/api/v1/schemas",
            "src/interfaces/cli",
            "src/shared",
            "src/shared/config",
            "src/shared/exceptions",
            "tests",
            "tests/unit",
            "tests/integration",
            "tests/e2e",
            "scripts",
            "scripts/migration",
            "scripts/evaluation",
            "config",
            "docker",
        ]

        for dir_path in expected_dirs:
            full_path = project_root / dir_path
            assert full_path.exists(), f"Directory {dir_path} does not exist"
            assert full_path.is_dir(), f"{dir_path} is not a directory"

    def test_config_files_exist(self, project_root):
        """Test that configuration files exist."""
        expected_files = [
            "pyproject.toml",
            ".gitignore",
        ]

        for file_path in expected_files:
            full_path = project_root / file_path
            assert full_path.exists(), f"File {file_path} does not exist"

    def test_python_packages_initialized(self, project_root):
        """Test that all Python packages have __init__.py files."""
        src_path = project_root / "src"

        for root, dirs, _ in os.walk(src_path):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            init_file = Path(root) / "__init__.py"
            assert init_file.exists(), f"Missing __init__.py in {root}"

    def test_pyproject_toml_structure(self, project_root):
        """Test that pyproject.toml has the required sections."""
        import tomllib

        pyproject_path = project_root / "pyproject.toml"

        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        # Check project metadata
        assert "project" in config
        assert config["project"]["name"] == "ashareinsight"
        assert config["project"]["requires-python"] == ">=3.13"

        # Check dependencies
        deps = config["project"]["dependencies"]
        assert any("langchain>=" in dep for dep in deps)
        assert any("fastapi>=" in dep for dep in deps)
        assert any("pgvector>=" in dep for dep in deps)

        # Check dev dependencies
        assert "dev" in config["project"]["optional-dependencies"]
        dev_deps = config["project"]["optional-dependencies"]["dev"]
        assert any("pytest>=" in dep for dep in dev_deps)
        assert any("black>=" in dep for dep in dev_deps)
        assert any("ruff>=" in dep for dep in dev_deps)

        # Check tool configurations
        assert "tool" in config
        assert "ruff" in config["tool"]
        assert "black" in config["tool"]
        assert "pytest" in config["tool"]
