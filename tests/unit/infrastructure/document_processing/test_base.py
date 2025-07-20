"""Unit tests for base document processing functionality."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.document_processing.base import (
    BaseDocumentLoader,
    DocumentMetadata,
    ProcessedDocument,
)
from src.shared.exceptions import DocumentProcessingError


class TestDocumentMetadata:
    """Test cases for DocumentMetadata model."""

    def test_valid_metadata_creation(self):
        """Test creating valid document metadata."""
        now = datetime.now()
        metadata = DocumentMetadata(
            file_path="/path/to/document.txt",
            file_name="document.txt",
            file_extension=".txt",
            file_size_bytes=1024,
            file_hash="abc123def456",
            created_at=now,
            modified_at=now,
            encoding="utf-8",
        )

        assert metadata.file_path == "/path/to/document.txt"
        assert metadata.file_name == "document.txt"
        assert metadata.file_extension == ".txt"
        assert metadata.file_size_bytes == 1024
        assert metadata.file_hash == "abc123def456"
        assert metadata.encoding == "utf-8"

    def test_metadata_default_encoding(self):
        """Test metadata with default encoding."""
        metadata = DocumentMetadata(
            file_path="/test.txt",
            file_name="test.txt",
            file_extension=".txt",
            file_size_bytes=100,
            file_hash="hash",
            created_at=datetime.now(),
            modified_at=datetime.now(),
        )
        assert metadata.encoding == "utf-8"


class TestProcessedDocument:
    """Test cases for ProcessedDocument model."""

    def test_processed_document_creation(self):
        """Test creating a processed document."""
        metadata = DocumentMetadata(
            file_path="/test.txt",
            file_name="test.txt",
            file_extension=".txt",
            file_size_bytes=100,
            file_hash="hash",
            created_at=datetime.now(),
            modified_at=datetime.now(),
        )

        doc = ProcessedDocument(
            content="Test content",
            metadata=metadata,
        )

        assert doc.content == "Test content"
        assert doc.metadata == metadata
        assert isinstance(doc.processing_timestamp, datetime)

    def test_processed_document_custom_timestamp(self):
        """Test processed document with custom timestamp."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        metadata = DocumentMetadata(
            file_path="/test.txt",
            file_name="test.txt",
            file_extension=".txt",
            file_size_bytes=100,
            file_hash="hash",
            created_at=datetime.now(),
            modified_at=datetime.now(),
        )

        doc = ProcessedDocument(
            content="Test",
            metadata=metadata,
            processing_timestamp=custom_time,
        )

        assert doc.processing_timestamp == custom_time


class ConcreteDocumentLoader(BaseDocumentLoader):
    """Concrete implementation for testing."""

    def can_load(self, file_path: Path) -> bool:
        """Check if this loader can handle .test files."""
        return file_path.suffix == ".test"

    def load_content(self, file_path: Path) -> str:
        """Load content from test file."""
        with open(file_path, encoding=self.encoding) as f:
            return f.read()


class TestBaseDocumentLoader:
    """Test cases for BaseDocumentLoader abstract class."""

    @pytest.fixture
    def loader(self):
        """Create a concrete loader instance."""
        return ConcreteDocumentLoader()

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a test file."""
        test_file = tmp_path / "test.test"
        test_file.write_text("Test content", encoding="utf-8")
        return test_file

    def test_loader_initialization(self):
        """Test loader initialization with different encodings."""
        loader = ConcreteDocumentLoader()
        assert loader.encoding == "utf-8"

        loader_gbk = ConcreteDocumentLoader(encoding="gbk")
        assert loader_gbk.encoding == "gbk"

    def test_load_success(self, loader, test_file):
        """Test successful document loading."""
        doc = loader.load(test_file)

        assert isinstance(doc, ProcessedDocument)
        assert doc.content == "Test content"
        assert doc.metadata.file_name == "test.test"
        assert doc.metadata.file_extension == ".test"
        assert doc.metadata.encoding == "utf-8"

        # Check hash calculation
        expected_hash = loader._calculate_hash("Test content")
        assert doc.metadata.file_hash == expected_hash

    def test_load_string_path(self, loader, test_file):
        """Test loading with string path."""
        doc = loader.load(str(test_file))
        assert doc.content == "Test content"

    def test_file_not_found(self, loader):
        """Test error when file doesn't exist."""
        with pytest.raises(DocumentProcessingError) as exc_info:
            loader.load("/non/existent/file.test")
        assert "File not found" in str(exc_info.value)

    def test_path_not_file(self, loader, tmp_path):
        """Test error when path is directory."""
        with pytest.raises(DocumentProcessingError) as exc_info:
            loader.load(tmp_path)
        assert "Path is not a file" in str(exc_info.value)

    def test_unsupported_file_type(self, loader, tmp_path):
        """Test error with unsupported file type."""
        wrong_file = tmp_path / "test.wrong"
        wrong_file.write_text("content")

        with pytest.raises(DocumentProcessingError) as exc_info:
            loader.load(wrong_file)
        assert "Cannot load file type" in str(exc_info.value)

    def test_load_content_error(self, loader, test_file):
        """Test error during content loading."""
        with patch.object(loader, "load_content", side_effect=Exception("Read error")):
            with pytest.raises(DocumentProcessingError) as exc_info:
                loader.load(test_file)
            assert "Failed to load document" in str(exc_info.value)
            assert "Read error" in str(exc_info.value)

    def test_calculate_hash(self, loader):
        """Test hash calculation."""
        content = "Test content 123"
        hash1 = loader._calculate_hash(content)
        hash2 = loader._calculate_hash(content)

        # Same content should produce same hash
        assert hash1 == hash2

        # Different content should produce different hash
        hash3 = loader._calculate_hash("Different content")
        assert hash1 != hash3

        # Hash should be hex string
        assert all(c in "0123456789abcdef" for c in hash1)
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

    def test_file_stats_extraction(self, loader, tmp_path):
        """Test that file stats are correctly extracted."""
        test_file = tmp_path / "stats_test.test"
        test_content = "Content for stats test"
        test_file.write_text(test_content)

        # Get actual stats
        stats = test_file.stat()

        doc = loader.load(test_file)

        assert doc.metadata.file_size_bytes == len(test_content.encode("utf-8"))
        assert (
            abs(
                (
                    doc.metadata.created_at - datetime.fromtimestamp(stats.st_ctime)
                ).total_seconds()
            )
            < 1
        )
        assert (
            abs(
                (
                    doc.metadata.modified_at - datetime.fromtimestamp(stats.st_mtime)
                ).total_seconds()
            )
            < 1
        )

    def test_abstract_methods_not_implemented(self):
        """Test that abstract methods must be implemented."""
        with pytest.raises(TypeError):
            # Should fail because abstract methods aren't implemented
            BaseDocumentLoader()

    def test_can_load_abstract(self):
        """Test can_load method behavior."""
        loader = ConcreteDocumentLoader()

        assert loader.can_load(Path("file.test"))
        assert not loader.can_load(Path("file.txt"))
        assert not loader.can_load(Path("file.md"))
