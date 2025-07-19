"""
Integration test to verify configuration files are properly set up.
"""

from pathlib import Path

import pytest
import yaml


class TestConfigurationFiles:
    """Test that configuration files are properly set up."""

    @pytest.fixture
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parents[2]

    def test_gitignore_exists(self, project_root):
        """Test that .gitignore exists with proper content."""
        gitignore_path = project_root / ".gitignore"
        assert gitignore_path.exists(), ".gitignore does not exist"

        with open(gitignore_path) as f:
            content = f.read()

        # Check for essential patterns
        essential_patterns = [
            "__pycache__/",
            ".env",
            ".venv/",
            "*.py[cod]",  # This covers *.pyc, *.pyo, *.pyd
            ".pytest_cache/",
            ".coverage",
            "uv.lock",
        ]

        for pattern in essential_patterns:
            assert pattern in content, f"Missing pattern in .gitignore: {pattern}"

    def test_env_example_exists(self, project_root):
        """Test that .env.example exists."""
        env_example_path = project_root / ".env.example"
        assert env_example_path.exists(), ".env.example does not exist"

    def test_config_directory_structure(self, project_root):
        """Test that config directory has required files."""
        config_dir = project_root / "config"
        assert config_dir.exists(), "config directory does not exist"
        assert config_dir.is_dir(), "config is not a directory"

        # Check for environment-specific configs
        required_configs = ["development.yaml", "production.yaml"]

        for config_name in required_configs:
            config_path = config_dir / config_name
            assert config_path.exists(), f"{config_name} does not exist"

    def test_development_config_structure(self, project_root):
        """Test development.yaml has required sections."""
        dev_config_path = project_root / "config" / "development.yaml"

        with open(dev_config_path) as f:
            config = yaml.safe_load(f)

        # Check main sections
        required_sections = [
            "app",
            "database",
            "redis",
            "api",
            "models",
            "logging",
            "monitoring",
        ]

        for section in required_sections:
            assert section in config, f"Missing section in development.yaml: {section}"

        # Check database config
        assert "host" in config["database"]
        assert "port" in config["database"]
        assert "pool" in config["database"]

        # Check models config
        assert "gemini" in config["models"]
        assert "embedding" in config["models"]
        assert "reranker" in config["models"]

    def test_production_config_structure(self, project_root):
        """Test production.yaml has required sections."""
        prod_config_path = project_root / "config" / "production.yaml"

        with open(prod_config_path) as f:
            config = yaml.safe_load(f)

        # Check that production has additional security settings
        assert "security" in config, "Missing security section in production config"
        assert (
            "performance" in config
        ), "Missing performance section in production config"

        # Check that debug is false in production
        assert config["app"]["debug"] is False, "Debug should be false in production"

    def test_readme_exists(self, project_root):
        """Test that README.md exists with proper content."""
        readme_path = project_root / "README.md"
        assert readme_path.exists(), "README.md does not exist"

        with open(readme_path) as f:
            content = f.read()

        # Check for essential sections
        assert "# AShareInsight" in content
        assert "## Overview" in content
        assert "## Quick Start" in content
        assert "## Project Structure" in content

    def test_pyproject_toml_tools_config(self, project_root):
        """Test that pyproject.toml has tool configurations."""
        import tomllib

        pyproject_path = project_root / "pyproject.toml"

        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)

        # Check tool configurations
        assert "tool" in config
        assert "ruff" in config["tool"], "Ruff configuration missing"
        assert "black" in config["tool"], "Black configuration missing"
        assert "pytest" in config["tool"], "Pytest configuration missing"

        # Check Ruff config
        assert config["tool"]["ruff"]["line-length"] == 88
        assert config["tool"]["ruff"]["target-version"] == "py313"

        # Check Black config
        assert config["tool"]["black"]["line-length"] == 88
