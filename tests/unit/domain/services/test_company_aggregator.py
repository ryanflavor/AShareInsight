"""Unit tests for CompanyAggregator domain service.

This module tests the company aggregation functionality including
grouping by company and different scoring strategies.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.services import CompanyAggregator
from src.domain.value_objects import Document


class TestCompanyAggregator:
    """Test cases for CompanyAggregator service."""

    @pytest.fixture
    def sample_documents(self) -> list[Document]:
        """Create sample documents for testing."""
        base_time = datetime.now(UTC)

        return [
            # Company A - multiple concepts
            Document(
                concept_id=uuid4(),
                company_code="000001",
                company_name="Company A",
                concept_name="Electric Vehicles",
                concept_category="Technology",
                importance_score=Decimal("0.9"),
                similarity_score=0.95,
                source_concept_id=uuid4(),
                matched_at=base_time,
            ),
            Document(
                concept_id=uuid4(),
                company_code="000001",
                company_name="Company A",
                concept_name="Battery Technology",
                concept_category="Technology",
                importance_score=Decimal("0.8"),
                similarity_score=0.88,
                source_concept_id=uuid4(),
                matched_at=base_time,
            ),
            Document(
                concept_id=uuid4(),
                company_code="000001",
                company_name="Company A",
                concept_name="Autonomous Driving",
                concept_category="Technology",
                importance_score=Decimal("0.7"),
                similarity_score=0.75,
                source_concept_id=uuid4(),
                matched_at=base_time,
            ),
            # Company B - single concept
            Document(
                concept_id=uuid4(),
                company_code="000002",
                company_name="Company B",
                concept_name="Electric Vehicles",
                concept_category="Technology",
                importance_score=Decimal("0.85"),
                similarity_score=0.92,
                source_concept_id=uuid4(),
                matched_at=base_time,
            ),
            # Company C - multiple concepts
            Document(
                concept_id=uuid4(),
                company_code="000003",
                company_name="Company C",
                concept_name="Solar Energy",
                concept_category="Energy",
                importance_score=Decimal("0.9"),
                similarity_score=0.80,
                source_concept_id=uuid4(),
                matched_at=base_time,
            ),
            Document(
                concept_id=uuid4(),
                company_code="000003",
                company_name="Company C",
                concept_name="Energy Storage",
                concept_category="Energy",
                importance_score=Decimal("0.8"),
                similarity_score=0.85,
                source_concept_id=uuid4(),
                matched_at=base_time,
            ),
        ]

    @pytest.fixture
    def aggregator(self) -> CompanyAggregator:
        """Create CompanyAggregator instance."""
        return CompanyAggregator()

    def test_aggregate_by_company_max_strategy(
        self, aggregator: CompanyAggregator, sample_documents: list[Document]
    ):
        """Test aggregation with max score strategy."""
        # Act
        result = aggregator.aggregate_by_company(
            documents=sample_documents, strategy="max"
        )

        # Assert
        assert len(result) == 3  # 3 unique companies

        # Check Company A (highest max score: 0.95)
        company_a = result[0]
        assert company_a.company_code == "000001"
        assert company_a.company_name == "Company A"
        assert company_a.relevance_score == 0.95
        assert len(company_a.matched_concepts) == 3
        # Concepts should be sorted by similarity score
        assert company_a.matched_concepts[0].similarity_score == 0.95
        assert company_a.matched_concepts[1].similarity_score == 0.88
        assert company_a.matched_concepts[2].similarity_score == 0.75

        # Check Company B (second highest: 0.92)
        company_b = result[1]
        assert company_b.company_code == "000002"
        assert company_b.relevance_score == 0.92
        assert len(company_b.matched_concepts) == 1

        # Check Company C (lowest max: 0.85)
        company_c = result[2]
        assert company_c.company_code == "000003"
        assert company_c.relevance_score == 0.85
        assert len(company_c.matched_concepts) == 2

    def test_aggregate_by_company_average_strategy(
        self, aggregator: CompanyAggregator, sample_documents: list[Document]
    ):
        """Test aggregation with average score strategy."""
        # Act
        result = aggregator.aggregate_by_company(
            documents=sample_documents, strategy="average"
        )

        # Assert
        assert len(result) == 3

        # Check Company B (highest average: 0.92)
        company_b = result[0]
        assert company_b.company_code == "000002"
        assert company_b.relevance_score == 0.92

        # Check Company A (average: (0.95 + 0.88 + 0.75) / 3 ≈ 0.86)
        company_a = result[1]
        assert company_a.company_code == "000001"
        assert abs(company_a.relevance_score - 0.86) < 0.01

        # Check Company C (average: (0.80 + 0.85) / 2 = 0.825)
        company_c = result[2]
        assert company_c.company_code == "000003"
        assert abs(company_c.relevance_score - 0.825) < 0.001

    def test_aggregate_empty_documents(self, aggregator: CompanyAggregator):
        """Test aggregation with empty document list."""
        # Act
        result = aggregator.aggregate_by_company(documents=[], strategy="max")

        # Assert
        assert result == []

    def test_aggregate_single_document(self, aggregator: CompanyAggregator):
        """Test aggregation with single document."""
        # Arrange
        doc = Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="Test Company",
            concept_name="Test Concept",
            concept_category="Test",
            importance_score=Decimal("0.8"),
            similarity_score=0.85,
            matched_at=datetime.now(UTC),
        )

        # Act
        result = aggregator.aggregate_by_company(documents=[doc], strategy="max")

        # Assert
        assert len(result) == 1
        assert result[0].company_code == "000001"
        assert result[0].relevance_score == 0.85
        assert len(result[0].matched_concepts) == 1

    def test_aggregate_invalid_strategy(
        self, aggregator: CompanyAggregator, sample_documents: list[Document]
    ):
        """Test aggregation with invalid strategy raises error."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid aggregation strategy: invalid"):
            aggregator.aggregate_by_company(
                documents=sample_documents, strategy="invalid"
            )

    def test_get_top_concepts_per_company(
        self, aggregator: CompanyAggregator, sample_documents: list[Document]
    ):
        """Test getting top N concepts for a company."""
        # Arrange
        aggregated = aggregator.aggregate_by_company(
            documents=sample_documents, strategy="max"
        )
        company_a = aggregated[0]  # Company A with 3 concepts

        # Act - get top 2 concepts
        top_concepts = aggregator.get_top_concepts_per_company(
            aggregated_company=company_a, limit=2
        )

        # Assert
        assert len(top_concepts) == 2
        assert top_concepts[0].similarity_score == 0.95
        assert top_concepts[1].similarity_score == 0.88

    def test_stable_sorting(self, aggregator: CompanyAggregator):
        """Test that companies with same score are sorted by company code."""
        # Arrange - create documents with same scores
        docs = [
            Document(
                concept_id=uuid4(),
                company_code="000003",
                company_name="Company C",
                concept_name="Concept",
                concept_category="Test",
                importance_score=Decimal("0.8"),
                similarity_score=0.85,
                matched_at=datetime.now(UTC),
            ),
            Document(
                concept_id=uuid4(),
                company_code="000001",
                company_name="Company A",
                concept_name="Concept",
                concept_category="Test",
                importance_score=Decimal("0.8"),
                similarity_score=0.85,
                matched_at=datetime.now(UTC),
            ),
            Document(
                concept_id=uuid4(),
                company_code="000002",
                company_name="Company B",
                concept_name="Concept",
                concept_category="Test",
                importance_score=Decimal("0.8"),
                similarity_score=0.85,
                matched_at=datetime.now(UTC),
            ),
        ]

        # Act
        result = aggregator.aggregate_by_company(documents=docs, strategy="max")

        # Assert - should be sorted by company code when scores are equal
        assert len(result) == 3
        assert result[0].company_code == "000001"
        assert result[1].company_code == "000002"
        assert result[2].company_code == "000003"

    def test_concepts_sorted_within_company(
        self, aggregator: CompanyAggregator, sample_documents: list[Document]
    ):
        """Test that concepts within a company are sorted by similarity score."""
        # Act
        result = aggregator.aggregate_by_company(
            documents=sample_documents, strategy="max"
        )

        # Assert - check Company A's concepts are sorted
        company_a = next(c for c in result if c.company_code == "000001")
        scores = [c.similarity_score for c in company_a.matched_concepts]
        assert scores == sorted(scores, reverse=True)
