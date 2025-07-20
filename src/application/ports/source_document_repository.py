"""Port interface for SourceDocument repository.

This module defines the abstract interface for persisting and retrieving
source documents, following the hexagonal architecture pattern.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from src.domain.entities.source_document import SourceDocument


class SourceDocumentRepositoryPort(ABC):
    """Abstract interface for SourceDocument persistence operations.

    This port defines the contract that any persistence adapter must implement
    to handle source document storage and retrieval.
    """

    @abstractmethod
    async def save(self, document: SourceDocument) -> UUID:
        """Save a source document to the repository.

        Args:
            document: The SourceDocument entity to save

        Returns:
            UUID: The generated document ID

        Raises:
            IntegrityError: If a document with the same file_hash already exists
            OperationalError: If there's a database connection issue
        """
        pass

    @abstractmethod
    async def find_by_id(self, doc_id: UUID) -> SourceDocument | None:
        """Find a source document by its ID.

        Args:
            doc_id: The UUID of the document to find

        Returns:
            SourceDocument if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_by_file_hash(self, file_hash: str) -> SourceDocument | None:
        """Find a source document by its file hash.

        This method is used to check for duplicate processing of the same file.

        Args:
            file_hash: The SHA-256 hash of the file

        Returns:
            SourceDocument if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_by_company_and_date_range(
        self,
        company_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        doc_type: str | None = None,
    ) -> list[SourceDocument]:
        """Find source documents by company code and optional date range.

        Args:
            company_code: The stock code of the company
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            doc_type: Optional document type filter

        Returns:
            List of matching SourceDocument entities
        """
        pass

    @abstractmethod
    async def update_status(
        self, doc_id: UUID, status: str, error_message: str | None = None
    ) -> bool:
        """Update the processing status of a document.

        Args:
            doc_id: The document ID to update
            status: The new status
            error_message: Optional error message if status is 'failed'

        Returns:
            True if update was successful, False if document not found
        """
        pass

    @abstractmethod
    async def get_statistics(self) -> dict[str, Any]:
        """Get repository statistics.

        Returns:
            Dictionary containing statistics like:
            - total_documents: Total number of documents
            - documents_by_type: Count by document type
            - documents_by_status: Count by processing status
            - latest_document_date: Most recent document date
        """
        pass

    @abstractmethod
    async def exists(self, file_hash: str) -> bool:
        """Check if a document with the given file hash exists.

        Args:
            file_hash: The SHA-256 hash to check

        Returns:
            True if a document with this hash exists, False otherwise
        """
        pass
