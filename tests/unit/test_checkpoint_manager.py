"""Unit tests for CheckpointManager."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.offline.build_vector_indices import CheckpointManager


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
