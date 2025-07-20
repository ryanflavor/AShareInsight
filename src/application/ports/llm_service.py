"""LLM Service port definition for hexagonal architecture."""

from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities import (
    DocumentType,
)


class LLMServicePort(ABC):
    """Port interface for LLM services."""

    @abstractmethod
    def extract_annual_report(
        self, document_content: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """Extract data from an annual report.

        Args:
            document_content: The full text content of the annual report.
            company_name: Name of the company.
            document_type_desc: Description of document type (e.g., "2024年年度报告").

        Returns:
            Tuple of (extracted data, extraction metadata).
        """
        pass

    @abstractmethod
    def extract_research_report(
        self, document_content: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """Extract data from a research report.

        Args:
            document_content: The full text content of the research report.

        Returns:
            Tuple of (extracted data, extraction metadata).
        """
        pass

    @abstractmethod
    def detect_document_type(self, content: str) -> DocumentType:
        """Detect the type of document from its content.

        Args:
            content: Document content to analyze.

        Returns:
            Detected document type.
        """
        pass

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """Get information about the LLM model being used.

        Returns:
            Dictionary with model configuration details.
        """
        pass
