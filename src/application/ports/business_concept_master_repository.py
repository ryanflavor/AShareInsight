"""Business Concept Master Repository Port interface."""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.business_concept_master import BusinessConceptMaster


class BusinessConceptMasterRepositoryPort(ABC):
    """Port interface for BusinessConceptMaster repository operations."""

    @abstractmethod
    async def find_by_company_and_name(
        self, company_code: str, concept_name: str
    ) -> BusinessConceptMaster | None:
        """Find a business concept by company code and concept name.

        Args:
            company_code: The company code
            concept_name: The business concept name

        Returns:
            The business concept if found, None otherwise
        """
        pass

    @abstractmethod
    async def save(
        self, business_concept: BusinessConceptMaster
    ) -> BusinessConceptMaster:
        """Save a new business concept.

        Args:
            business_concept: The business concept to save

        Returns:
            The saved business concept with generated ID
        """
        pass

    @abstractmethod
    async def update(
        self, business_concept: BusinessConceptMaster
    ) -> BusinessConceptMaster:
        """Update an existing business concept.

        Args:
            business_concept: The business concept to update

        Returns:
            The updated business concept

        Raises:
            OptimisticLockError: If version conflict occurs
        """
        pass

    @abstractmethod
    async def find_all_by_company(
        self, company_code: str
    ) -> list[BusinessConceptMaster]:
        """Find all business concepts for a company.

        Args:
            company_code: The company code

        Returns:
            List of business concepts for the company
        """
        pass

    @abstractmethod
    async def find_by_id(self, concept_id: UUID) -> BusinessConceptMaster | None:
        """Find a business concept by ID.

        Args:
            concept_id: The concept UUID

        Returns:
            The business concept if found, None otherwise
        """
        pass

    @abstractmethod
    async def update_embedding(self, concept_id: UUID, embedding: list[float]) -> None:
        """Update only the embedding field for a business concept.

        Args:
            concept_id: The concept UUID
            embedding: The embedding vector as a list of floats

        Note:
            This method does not update the version field to avoid
            triggering business data version changes.
        """
        pass

    @abstractmethod
    async def batch_update_embeddings(
        self, embeddings: list[tuple[UUID, list[float]]]
    ) -> None:
        """Batch update embeddings for multiple business concepts.

        Args:
            embeddings: List of tuples containing (concept_id, embedding)

        Note:
            This method does not update the version field to avoid
            triggering business data version changes.
        """
        pass

    @abstractmethod
    async def find_concepts_needing_embeddings(
        self, limit: int | None = None
    ) -> list[BusinessConceptMaster]:
        """Find concepts that need embeddings (embedding is null).

        Args:
            limit: Optional limit on number of concepts to return

        Returns:
            List of business concepts needing embeddings
        """
        pass
