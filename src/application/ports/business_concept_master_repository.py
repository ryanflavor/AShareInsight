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
