"""Company aggregation service for grouping and ranking search results.

This module provides domain services for aggregating business concepts
by company and calculating company-level relevance scores.
"""

from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from src.domain.value_objects import Document


class AggregatedCompany(NamedTuple):
    """Represents a company with aggregated business concepts.

    Attributes:
        company_code: Stock code of the company
        company_name: Full name of the company
        company_name_short: Short name of the company
        relevance_score: Aggregated relevance score (highest concept score)
        matched_concepts: List of matched business concepts
    """

    company_code: str
    company_name: str
    company_name_short: str | None
    relevance_score: float
    matched_concepts: list[Document]


class CompanyConceptGroup(BaseModel):
    """Model for grouping business concepts by company.

    This model represents all business concepts associated with a single
    company, providing structure for aggregation operations.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    company_code: str = Field(..., max_length=10)
    company_name: str = Field(..., max_length=255)
    company_name_short: str | None = Field(None, max_length=100)
    concepts: list[Document] = Field(default_factory=list)

    @property
    def max_similarity_score(self) -> float:
        """Get the highest similarity score among all concepts.

        Returns:
            Maximum similarity score, or 0.0 if no concepts
        """
        if not self.concepts:
            return 0.0
        return max(concept.similarity_score for concept in self.concepts)

    @property
    def average_similarity_score(self) -> float:
        """Get the average similarity score of all concepts.

        Returns:
            Average similarity score, or 0.0 if no concepts
        """
        if not self.concepts:
            return 0.0
        return sum(concept.similarity_score for concept in self.concepts) / len(
            self.concepts
        )


class CompanyAggregator:
    """Service for aggregating search results by company.

    This service groups individual business concept documents by company
    and calculates company-level relevance scores based on the aggregation
    strategy.
    """

    def aggregate_by_company(
        self, documents: list[Document], strategy: str = "max"
    ) -> list[AggregatedCompany]:
        """Aggregate documents by company with specified scoring strategy.

        Groups documents by company_code and calculates relevance scores
        based on the specified strategy.

        Args:
            documents: List of Document objects to aggregate
            strategy: Aggregation strategy ('max' or 'average')
                     'max' - use highest concept score as company score
                     'average' - use average of all concept scores

        Returns:
            List of AggregatedCompany objects sorted by relevance score

        Raises:
            ValueError: If an invalid strategy is specified
        """
        if strategy not in ["max", "average"]:
            raise ValueError(f"Invalid aggregation strategy: {strategy}")

        # Group documents by company
        company_groups = self._group_by_company(documents)

        # Create aggregated companies
        aggregated_companies = []
        for group in company_groups.values():
            relevance_score = (
                group.max_similarity_score
                if strategy == "max"
                else group.average_similarity_score
            )

            aggregated_company = AggregatedCompany(
                company_code=group.company_code,
                company_name=group.company_name,
                company_name_short=group.company_name_short,
                relevance_score=relevance_score,
                matched_concepts=sorted(
                    group.concepts, key=lambda doc: doc.similarity_score, reverse=True
                ),
            )
            aggregated_companies.append(aggregated_company)

        # Sort by relevance score (descending), then by company code for stability
        return sorted(
            aggregated_companies,
            key=lambda company: (-company.relevance_score, company.company_code),
        )

    def _group_by_company(
        self, documents: list[Document]
    ) -> dict[str, CompanyConceptGroup]:
        """Group documents by company code.

        Args:
            documents: List of documents to group

        Returns:
            Dictionary mapping company codes to CompanyConceptGroup objects
        """
        groups: dict[str, CompanyConceptGroup] = {}

        for doc in documents:
            if doc.company_code not in groups:
                groups[doc.company_code] = CompanyConceptGroup(
                    company_code=doc.company_code,
                    company_name=doc.company_name,
                    company_name_short=doc.company_name_short,
                    concepts=[doc],
                )
            else:
                # Create a new group with updated concepts list
                existing_group = groups[doc.company_code]
                groups[doc.company_code] = CompanyConceptGroup(
                    company_code=existing_group.company_code,
                    company_name=existing_group.company_name,
                    company_name_short=existing_group.company_name_short
                    or doc.company_name_short,
                    concepts=existing_group.concepts + [doc],
                )

        return groups

    def get_top_concepts_per_company(
        self, aggregated_company: AggregatedCompany, limit: int = 5
    ) -> list[Document]:
        """Get top N concepts for a company by similarity score.

        Args:
            aggregated_company: The aggregated company object
            limit: Maximum number of concepts to return

        Returns:
            List of top Document objects (already sorted by similarity)
        """
        return aggregated_company.matched_concepts[:limit]
