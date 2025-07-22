"""Base document processing functionality."""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from src.shared.exceptions import DocumentProcessingError


class DocumentMetadata(BaseModel):
    """Metadata for a processed document."""

    file_path: str = Field(..., description="Absolute path to the document")
    file_name: str = Field(..., description="Name of the file")
    file_extension: str = Field(..., description="File extension (e.g., .md, .txt)")
    file_size_bytes: int = Field(..., description="Size of the file in bytes")
    file_hash: str = Field(..., description="SHA-256 hash of the file content")
    created_at: datetime = Field(..., description="File creation time")
    modified_at: datetime = Field(..., description="File last modification time")
    encoding: str = Field(default="utf-8", description="File encoding")


class ProcessedDocument(BaseModel):
    """A document that has been loaded and processed."""

    content: str = Field(..., description="The document content")
    metadata: DocumentMetadata = Field(..., description="Document metadata")
    processing_timestamp: datetime = Field(
        default_factory=datetime.now, description="When the document was processed"
    )


class BaseDocumentLoader(ABC):
    """Base class for document loaders."""

    def __init__(self, encoding: str = "utf-8"):
        """Initialize document loader.

        Args:
            encoding: Default encoding for reading files.
        """
        self.encoding = encoding

    @abstractmethod
    def can_load(self, file_path: Path) -> bool:
        """Check if this loader can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if the loader can handle this file type.
        """
        pass

    @abstractmethod
    def load_content(self, file_path: Path) -> str:
        """Load the content from the file.

        Args:
            file_path: Path to the file.

        Returns:
            The file content as a string.

        Raises:
            DocumentProcessingError: If loading fails.
        """
        pass

    def load(self, file_path: str | Path) -> ProcessedDocument:
        """Load a document with metadata.

        Args:
            file_path: Path to the document.

        Returns:
            ProcessedDocument with content and metadata.

        Raises:
            DocumentProcessingError: If processing fails.
        """
        path = Path(file_path) if isinstance(file_path, str) else file_path

        # Validate file exists
        if not path.exists():
            raise DocumentProcessingError(f"File not found: {path}")

        if not path.is_file():
            raise DocumentProcessingError(f"Path is not a file: {path}")

        if not self.can_load(path):
            raise DocumentProcessingError(f"Cannot load file type: {path.suffix}")

        try:
            # Load content
            content = self.load_content(path)

            # Calculate hash
            file_hash = self._calculate_hash(content)

            # Get file stats
            stats = path.stat()

            # Create metadata
            metadata = DocumentMetadata(
                file_path=str(path.absolute()),
                file_name=path.name,
                file_extension=path.suffix,
                file_size_bytes=stats.st_size,
                file_hash=file_hash,
                created_at=datetime.fromtimestamp(stats.st_ctime),
                modified_at=datetime.fromtimestamp(stats.st_mtime),
                encoding=self.encoding,
            )

            return ProcessedDocument(content=content, metadata=metadata)

        except Exception as e:
            raise DocumentProcessingError(
                f"Failed to load document {path}: {str(e)}"
            ) from e

    def _calculate_hash(self, content: str) -> str:
        """Calculate SHA-256 hash of content.

        Args:
            content: The content to hash.

        Returns:
            Hexadecimal hash string.
        """
        return hashlib.sha256(content.encode(self.encoding)).hexdigest()
