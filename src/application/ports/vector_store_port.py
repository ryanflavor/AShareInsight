"""Vector store port interface for the application layer.

This module defines the abstract interface for vector store operations,
following the hexagonal architecture pattern.
"""

from abc import ABC, abstractmethod

from src.domain.value_objects import BusinessConceptQuery, Document


class VectorStorePort(ABC):
    """Abstract interface for vector store operations.

    This port defines the contract for vector similarity search operations
    that the infrastructure layer must implement.
    """

    @abstractmethod
    async def search_similar_concepts(
        self, query: BusinessConceptQuery
    ) -> list[Document]:
        """Search for similar business concepts based on the query.

        Args:
            query: Query parameters including target company and search criteria

        Returns:
            List of Document objects representing similar concepts,
            sorted by similarity score in descending order

        Raises:
            CompanyNotFoundError: If the target company cannot be found
            DatabaseConnectionError: If database connection fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the vector store connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        pass
