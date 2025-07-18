"""
Unit tests for database connection functionality
"""

import os
import sys
from unittest.mock import MagicMock, Mock, patch

# Add packages to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../packages/core/src"))

import pytest
from core.database import DatabaseConnection
from psycopg.rows import dict_row


class TestDatabaseConnection:
    """Test database connection functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.connection_string = "postgresql://test:test@localhost:5432/test"
        # Mock the pool creation since it happens automatically
        with patch("core.database.ConnectionPool") as mock_pool:
            self.db = DatabaseConnection(self.connection_string)
            self.mock_pool = mock_pool.return_value

    @patch("core.database.ConnectionPool")
    def test_initialization(self, mock_pool_class):
        """Test DatabaseConnection initialization"""
        # Pool is auto-created on initialization
        mock_pool = Mock()
        mock_pool_class.return_value = mock_pool

        db = DatabaseConnection(self.connection_string)

        assert db.connection_string == self.connection_string
        assert db.pool == mock_pool
        mock_pool_class.assert_called_once_with(
            self.connection_string,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )

    @patch("core.database.psycopg.connect")
    def test_basic_connectivity_success(self, mock_connect):
        """Test successful basic connectivity"""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Mock query results
        mock_cursor.fetchone.side_effect = [
            ("PostgreSQL 16.9",),  # version query
            ("vector", "0.8.0"),  # vector extension query
            ("testdb", "testuser"),  # database info query
        ]

        result = self.db.test_basic_connectivity()

        assert result["status"] == "success"
        assert "PostgreSQL 16.9" in result["postgresql_version"]
        assert result["vector_extension"]["name"] == "vector"
        assert result["vector_extension"]["version"] == "0.8.0"
        assert result["database"] == "testdb"
        assert result["user"] == "testuser"

    @patch("core.database.psycopg.connect")
    def test_basic_connectivity_failure(self, mock_connect):
        """Test basic connectivity failure"""
        mock_connect.side_effect = Exception("Connection failed")

        result = self.db.test_basic_connectivity()

        assert result["status"] == "failed"
        assert "Connection failed" in result["error"]

    def test_create_connection_pool_success(self):
        """Test successful connection pool creation"""
        # Pool already created in __init__, calling create_connection_pool just logs
        with patch("core.database.logger") as mock_logger:
            self.db.create_connection_pool(min_size=2, max_size=5)

            # Should log that pool already exists
            mock_logger.info.assert_called_with("Connection pool already created")

    @patch("core.database.ConnectionPool")
    def test_create_connection_pool_failure(self, mock_pool_class):
        """Test connection pool creation failure during initialization"""
        mock_pool_class.side_effect = Exception("Pool creation failed")

        # Pool creation happens in __init__ and should raise
        with pytest.raises(Exception, match="Pool creation failed"):
            DatabaseConnection(self.connection_string)

    def test_connection_pool_test_no_pool(self):
        """Test connection pool test when pool is None"""
        # Manually set pool to None to test this edge case
        self.db.pool = None
        result = self.db.test_connection_pool()

        assert result["status"] == "failed"
        assert "Connection pool not initialized" in result["error"]

    def test_connection_pool_test_success(self):
        """Test successful connection pool test"""
        # Setup mock pool attributes
        self.mock_pool.min_size = 2
        self.mock_pool.max_size = 10

        # Setup mock connection context manager
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connection_ctx = MagicMock()
        mock_connection_ctx.__enter__.return_value = mock_conn
        mock_connection_ctx.__exit__.return_value = None
        self.mock_pool.connection.return_value = mock_connection_ctx

        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__.return_value = mock_cursor
        mock_cursor_ctx.__exit__.return_value = None
        mock_conn.cursor.return_value = mock_cursor_ctx

        mock_cursor.fetchone.return_value = ("Connection pool test successful",)

        # Test pool
        result = self.db.test_connection_pool()

        assert result["status"] == "success"
        assert result["message"] == "Connection pool test successful"
        assert result["pool_stats"]["min_size"] == 2
        assert result["pool_stats"]["max_size"] == 10

    def test_close_pool_with_pool(self):
        """Test closing connection pool when pool exists"""
        # Pool is already mocked in setup
        self.db.close_pool()

        self.mock_pool.close.assert_called_once()

    def test_close_pool_without_pool(self):
        """Test closing connection pool when no pool exists"""
        # Should not raise exception
        self.db.close_pool()
