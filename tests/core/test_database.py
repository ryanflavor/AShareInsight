"""
Unit tests for database connection functionality.

Tests the legacy DatabaseConnection wrapper class.
"""

import os
import sys
from unittest.mock import Mock, patch

# Add packages to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../packages/core/src"))

import pytest
from core.database import DatabaseConnection


class TestDatabaseConnection:
    """Test legacy database connection wrapper."""

    def setup_method(self):
        """Setup test fixtures."""
        self.connection_string = "postgresql://test:test@localhost:5432/test"

    @patch("core.database.DatabaseOperations")
    def test_initialization(self, mock_operations_class):
        """Test DatabaseConnection initialization."""
        # Mock DatabaseOperations
        mock_operations = Mock()
        mock_pool = Mock()
        mock_operations.pool = mock_pool
        mock_operations_class.return_value = mock_operations

        db = DatabaseConnection(self.connection_string)

        assert db.operations == mock_operations
        assert db.pool == mock_pool
        mock_operations_class.assert_called_once_with(self.connection_string)

    @patch("core.database.DatabaseOperations")
    def test_close(self, mock_operations_class):
        """Test closing the connection."""
        # Mock DatabaseOperations
        mock_operations = Mock()
        mock_operations_class.return_value = mock_operations

        db = DatabaseConnection(self.connection_string)
        db.close()

        mock_operations.close.assert_called_once()

    @patch("core.database.DatabaseOperations")
    def test_pool_access(self, mock_operations_class):
        """Test accessing the pool through the wrapper."""
        # Mock DatabaseOperations with a pool
        mock_operations = Mock()
        # Use MagicMock for pool to support context manager
        from unittest.mock import MagicMock

        mock_pool = MagicMock()
        mock_operations.pool = mock_pool
        mock_operations_class.return_value = mock_operations

        db = DatabaseConnection(self.connection_string)

        # Pool should be accessible
        assert db.pool is mock_pool

        # Test that pool can be used as context manager
        mock_connection = Mock()
        mock_pool.connection.return_value.__enter__.return_value = mock_connection

        with db.pool.connection() as conn:
            assert conn is mock_connection

        mock_pool.connection.assert_called_once()

    @patch("core.database.DatabaseOperations")
    def test_error_propagation(self, mock_operations_class):
        """Test that errors are properly propagated."""
        # Mock DatabaseOperations to raise an error
        mock_operations_class.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            DatabaseConnection(self.connection_string)


# Additional tests to ensure halfvec support
class TestHalfvecSupport:
    """Test halfvec-related functionality."""

    @patch("core.database.ConnectionPool")
    def test_halfvec_operations_available(self, mock_pool_class):
        """Test that DatabaseOperations has halfvec support methods."""
        from core.database import DatabaseOperations

        # Create mock pool
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool

        db_ops = DatabaseOperations("postgresql://test:test@localhost:5432/test")

        # Check that halfvec methods exist
        assert hasattr(db_ops, "check_halfvec_support")
        assert callable(db_ops.check_halfvec_support)

        # Check that vector operations use halfvec casting
        assert hasattr(db_ops, "search_concepts_by_similarity")
        assert hasattr(db_ops, "create_business_concept")
        assert hasattr(db_ops, "update_concept_embedding")
