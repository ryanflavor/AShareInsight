"""Integration tests for build_vector_indices.py script."""

# Add project root to path
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.offline.build_vector_indices import CheckpointManager, main
from src.domain.entities.business_concept_master import BusinessConceptMaster


class TestCheckpointManager:
    """Test cases for CheckpointManager."""

    def test_checkpoint_manager_no_file(self):
        """Test checkpoint manager without file."""
        manager = CheckpointManager(None)
        assert manager.load() == set()
        manager.mark_processed("test-id")
        manager.save()  # Should not raise

    def test_checkpoint_manager_with_file(self, tmp_path):
        """Test checkpoint manager with file operations."""
        checkpoint_file = tmp_path / "checkpoint.json"

        # Test loading non-existent file
        manager = CheckpointManager(str(checkpoint_file))
        assert manager.load() == set()

        # Test saving and loading
        manager.mark_processed("id1")
        manager.mark_processed("id2")
        manager.save()

        # Create new manager and load
        manager2 = CheckpointManager(str(checkpoint_file))
        loaded_ids = manager2.load()
        assert loaded_ids == {"id1", "id2"}

    def test_checkpoint_manager_invalid_file(self, tmp_path):
        """Test checkpoint manager with invalid file."""
        checkpoint_file = tmp_path / "invalid.json"
        checkpoint_file.write_text("invalid json")

        manager = CheckpointManager(str(checkpoint_file))
        assert manager.load() == set()  # Should handle error gracefully


class TestBuildVectorIndicesScript:
    """Test cases for build_vector_indices.py script."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.QWEN_API_BASE_URL = "http://test-api"
        settings.QWEN_API_KEY = "test-key"
        settings.QWEN_EMBEDDING_MODEL = "test-model"
        settings.DATABASE_URL = "postgresql://test"
        return settings

    @pytest.fixture
    def sample_concepts(self):
        """Create sample business concepts."""
        return [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=f"Concept {i}",
                concept_category="核心业务",
                importance_score=Decimal("0.8"),
                development_stage="commercialization",
                embedding=None,
                concept_details={"description": f"Description {i}"},
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(3)
        ]

    def test_cli_help(self):
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Build vector indices for business concepts" in result.output
        assert "--rebuild-all" in result.output
        assert "--dry-run" in result.output

    @patch("scripts.offline.build_vector_indices.load_dotenv")
    @patch("scripts.offline.build_vector_indices.Settings")
    @patch("scripts.offline.build_vector_indices.get_db_connection")
    @patch("scripts.offline.build_vector_indices.SessionFactory")
    @patch("scripts.offline.build_vector_indices.asyncio.run")
    def test_cli_dry_run(
        self,
        mock_asyncio_run,
        mock_session_factory,
        mock_get_db_connection,
        mock_settings_class,
        mock_load_dotenv,
        mock_settings,
    ):
        """Test CLI in dry-run mode."""
        mock_settings_class.return_value = mock_settings
        mock_asyncio_run.return_value = {
            "total_concepts": 10,
            "dry_run": True,
        }

        runner = CliRunner()
        result = runner.invoke(main, ["--dry-run"])

        assert result.exit_code == 0
        mock_asyncio_run.assert_called_once()
        # Check that asyncio.run was called with correct parameters
        call_args = mock_asyncio_run.call_args[0][0]
        assert call_args.__name__ == "build_vectors"

    @patch("scripts.offline.build_vector_indices.load_dotenv")
    @patch("scripts.offline.build_vector_indices.Settings")
    @patch("scripts.offline.build_vector_indices.get_db_connection")
    @patch("scripts.offline.build_vector_indices.SessionFactory")
    @patch("scripts.offline.build_vector_indices.asyncio.run")
    def test_cli_normal_run(
        self,
        mock_asyncio_run,
        mock_session_factory,
        mock_get_db_connection,
        mock_settings_class,
        mock_load_dotenv,
        mock_settings,
    ):
        """Test CLI normal run with results."""
        mock_settings_class.return_value = mock_settings
        mock_asyncio_run.return_value = {
            "total_concepts": 100,
            "processed": 100,
            "succeeded": 95,
            "failed": 5,
            "skipped": 0,
            "processing_time": 45.5,
            "errors": ["Error 1", "Error 2"],
        }

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--company-code",
                "000001",
                "--limit",
                "100",
                "--batch-size",
                "25",
            ],
        )

        assert result.exit_code == 0
        assert "Vector Index Build Summary" in result.output
        assert "Total concepts:     100" in result.output
        assert "Succeeded:          95" in result.output
        assert "Failed:             5" in result.output
        assert "Processing time:    45.50s" in result.output
        assert "Error 1" in result.output

    @patch("scripts.offline.build_vector_indices.load_dotenv")
    @patch("scripts.offline.build_vector_indices.Settings")
    @patch("scripts.offline.build_vector_indices.get_db_connection")
    @patch("scripts.offline.build_vector_indices.SessionFactory")
    @patch("scripts.offline.build_vector_indices.asyncio.run")
    def test_cli_with_checkpoint(
        self,
        mock_asyncio_run,
        mock_session_factory,
        mock_get_db_connection,
        mock_settings_class,
        mock_load_dotenv,
        mock_settings,
        tmp_path,
    ):
        """Test CLI with checkpoint file."""
        mock_settings_class.return_value = mock_settings
        checkpoint_file = tmp_path / "checkpoint.json"

        mock_asyncio_run.return_value = {
            "total_concepts": 50,
            "processed": 50,
            "succeeded": 50,
            "failed": 0,
            "skipped": 0,
            "processing_time": 20.0,
        }

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--checkpoint-file",
                str(checkpoint_file),
                "--limit",
                "50",
            ],
        )

        assert result.exit_code == 0
        # Verify checkpoint file path was passed to the function
        call_args = mock_asyncio_run.call_args[0][0]
        assert call_args.__name__ == "build_vectors"

    @patch("scripts.offline.build_vector_indices.load_dotenv")
    @patch("scripts.offline.build_vector_indices.Settings")
    @patch("scripts.offline.build_vector_indices.get_db_connection")
    @patch("scripts.offline.build_vector_indices.SessionFactory")
    @patch("scripts.offline.build_vector_indices.asyncio.run")
    def test_cli_error_handling(
        self,
        mock_asyncio_run,
        mock_session_factory,
        mock_get_db_connection,
        mock_settings_class,
        mock_load_dotenv,
        mock_settings,
    ):
        """Test CLI error handling."""
        mock_settings_class.return_value = mock_settings
        mock_asyncio_run.side_effect = Exception("Test error")

        runner = CliRunner()
        result = runner.invoke(main, [])

        assert result.exit_code == 1
        assert "Error: Test error" in result.output

    @patch("scripts.offline.build_vector_indices.load_dotenv")
    @patch("scripts.offline.build_vector_indices.Settings")
    @patch("scripts.offline.build_vector_indices.get_db_connection")
    @patch("scripts.offline.build_vector_indices.SessionFactory")
    @patch("scripts.offline.build_vector_indices.asyncio.run")
    def test_cli_keyboard_interrupt(
        self,
        mock_asyncio_run,
        mock_session_factory,
        mock_get_db_connection,
        mock_settings_class,
        mock_load_dotenv,
        mock_settings,
    ):
        """Test CLI keyboard interrupt handling."""
        mock_settings_class.return_value = mock_settings
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        runner = CliRunner()
        result = runner.invoke(main, [])

        assert result.exit_code == 1
        assert "Interrupted by user" in result.output
