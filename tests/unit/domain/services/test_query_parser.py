"""Unit tests for QueryCompanyParser domain service.

This module tests the query parsing functionality for extracting
company information from search queries and results.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.services import (
    AggregatedCompany,
    ParsedQueryCompany,
    QueryCompanyParser,
)
from src.domain.value_objects import Document


class TestQueryCompanyParser:
    """Test cases for QueryCompanyParser service."""

    @pytest.fixture
    def parser(self) -> QueryCompanyParser:
        """Create QueryCompanyParser instance."""
        return QueryCompanyParser()

    @pytest.fixture
    def sample_documents(self) -> list[Document]:
        """Create sample documents for testing."""
        base_time = datetime.now(UTC)

        return [
            Document(
                concept_id=uuid4(),
                company_code="002594",
                company_name="比亚迪股份有限公司",
                concept_name="新能源汽车",
                concept_category="Technology",
                importance_score=Decimal("0.9"),
                similarity_score=0.98,
                matched_at=base_time,
            ),
            Document(
                concept_id=uuid4(),
                company_code="300750",
                company_name="宁德时代新能源科技股份有限公司",
                concept_name="动力电池",
                concept_category="Technology",
                importance_score=Decimal("0.8"),
                similarity_score=0.85,
                matched_at=base_time,
            ),
        ]

    @pytest.fixture
    def sample_aggregated_companies(
        self, sample_documents: list[Document]
    ) -> list[AggregatedCompany]:
        """Create sample aggregated companies from documents."""
        return [
            AggregatedCompany(
                company_code="002594",
                company_name="比亚迪股份有限公司",
                relevance_score=0.98,
                matched_concepts=[sample_documents[0]],
            ),
            AggregatedCompany(
                company_code="300750",
                company_name="宁德时代新能源科技股份有限公司",
                relevance_score=0.85,
                matched_concepts=[sample_documents[1]],
            ),
        ]

    def test_parse_a_share_code(self, parser: QueryCompanyParser):
        """Test parsing A-share stock codes."""
        # Test various A-share patterns
        test_cases = [
            ("002594", ParsedQueryCompany(name="002594", code="002594")),
            ("000001", ParsedQueryCompany(name="000001", code="000001")),
            ("300750", ParsedQueryCompany(name="300750", code="300750")),
            ("600519", ParsedQueryCompany(name="600519", code="600519")),
            ("688111", ParsedQueryCompany(name="688111", code="688111")),
        ]

        for query, expected in test_cases:
            result = parser.parse_query_identifier(query)
            assert result == expected

    def test_parse_hk_stock_code(self, parser: QueryCompanyParser):
        """Test parsing Hong Kong stock codes."""
        test_cases = [
            ("1", ParsedQueryCompany(name="1", code="1")),
            ("700", ParsedQueryCompany(name="700", code="700")),
            ("9988", ParsedQueryCompany(name="9988", code="9988")),
            ("00700", ParsedQueryCompany(name="00700", code="00700")),
        ]

        for query, expected in test_cases:
            result = parser.parse_query_identifier(query)
            assert result == expected

    def test_parse_us_stock_code(self, parser: QueryCompanyParser):
        """Test parsing US stock codes."""
        test_cases = [
            ("AAPL", ParsedQueryCompany(name="AAPL", code="AAPL")),
            ("MSFT", ParsedQueryCompany(name="MSFT", code="MSFT")),
            ("F", ParsedQueryCompany(name="F", code="F")),
            ("aapl", ParsedQueryCompany(name="aapl", code="AAPL")),  # Uppercase
        ]

        for query, expected in test_cases:
            result = parser.parse_query_identifier(query)
            assert result == expected

    def test_parse_company_name(self, parser: QueryCompanyParser):
        """Test parsing company names (not codes)."""
        test_cases = [
            ("比亚迪", ParsedQueryCompany(name="比亚迪", code=None)),
            ("BYD Company", ParsedQueryCompany(name="BYD Company", code=None)),
            ("腾讯控股", ParsedQueryCompany(name="腾讯控股", code=None)),
            ("Apple Inc", ParsedQueryCompany(name="Apple Inc", code=None)),
            ("123456", ParsedQueryCompany(name="123456", code=None)),  # Invalid A-share
        ]

        for query, expected in test_cases:
            result = parser.parse_query_identifier(query)
            assert result == expected

    def test_parse_with_whitespace(self, parser: QueryCompanyParser):
        """Test parsing with leading/trailing whitespace."""
        test_cases = [
            ("  002594  ", ParsedQueryCompany(name="002594", code="002594")),
            ("\t比亚迪\n", ParsedQueryCompany(name="比亚迪", code=None)),
            (" AAPL ", ParsedQueryCompany(name="AAPL", code="AAPL")),
        ]

        for query, expected in test_cases:
            result = parser.parse_query_identifier(query)
            assert result == expected

    def test_resolve_from_results_exact_code_match(
        self,
        parser: QueryCompanyParser,
        sample_aggregated_companies: list[AggregatedCompany],
    ):
        """Test resolving when query matches company code exactly."""
        # Act
        result = parser.resolve_from_results(
            query_identifier="002594",
            aggregated_companies=sample_aggregated_companies,
        )

        # Assert
        assert result.name == "比亚迪股份有限公司"
        assert result.code == "002594"

    def test_resolve_from_results_exact_name_match(
        self,
        parser: QueryCompanyParser,
        sample_aggregated_companies: list[AggregatedCompany],
    ):
        """Test resolving when query matches company name."""
        # Act
        result = parser.resolve_from_results(
            query_identifier="比亚迪",
            aggregated_companies=sample_aggregated_companies,
        )

        # Assert
        assert result.name == "比亚迪股份有限公司"
        assert result.code == "002594"

    def test_resolve_from_results_partial_name_match(
        self,
        parser: QueryCompanyParser,
        sample_aggregated_companies: list[AggregatedCompany],
    ):
        """Test resolving when query partially matches company name."""
        # Act
        result = parser.resolve_from_results(
            query_identifier="宁德时代",
            aggregated_companies=sample_aggregated_companies,
        )

        # Assert
        assert result.name == "宁德时代新能源科技股份有限公司"
        assert result.code == "300750"

    def test_resolve_from_results_high_score_inference(
        self,
        parser: QueryCompanyParser,
    ):
        """Test resolving based on high relevance score."""
        # Arrange
        doc = Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="平安银行股份有限公司",
            concept_name="金融科技",
            concept_category="Finance",
            importance_score=Decimal("0.9"),
            similarity_score=0.96,
            matched_at=datetime.now(UTC),
        )

        companies = [
            AggregatedCompany(
                company_code="000001",
                company_name="平安银行股份有限公司",
                relevance_score=0.96,  # High score > 0.95
                matched_concepts=[doc],
            )
        ]

        # Act
        result = parser.resolve_from_results(
            query_identifier="平安",  # Partial match
            aggregated_companies=companies,
        )

        # Assert - should infer from high score
        assert result.name == "平安银行股份有限公司"
        assert result.code == "000001"

    def test_resolve_from_results_no_match(
        self,
        parser: QueryCompanyParser,
        sample_aggregated_companies: list[AggregatedCompany],
    ):
        """Test resolving when no match found in results."""
        # Act - use a longer query that won't match
        result = parser.resolve_from_results(
            query_identifier="腾讯控股有限公司",  # Longer query won't trigger high score inference
            aggregated_companies=sample_aggregated_companies,
        )

        # Assert - falls back to parsing
        assert result.name == "腾讯控股有限公司"
        assert result.code is None

    def test_resolve_from_results_empty_list(self, parser: QueryCompanyParser):
        """Test resolving with empty results list."""
        # Act
        result = parser.resolve_from_results(
            query_identifier="002594",
            aggregated_companies=[],
        )

        # Assert - falls back to parsing
        assert result.name == "002594"
        assert result.code == "002594"

    def test_resolve_from_documents_exact_match(
        self,
        parser: QueryCompanyParser,
        sample_documents: list[Document],
    ):
        """Test resolving from documents with exact match."""
        # Act
        result = parser.resolve_from_documents(
            query_identifier="002594",
            documents=sample_documents,
        )

        # Assert
        assert result.name == "比亚迪股份有限公司"
        assert result.code == "002594"

    def test_resolve_from_documents_high_score(self, parser: QueryCompanyParser):
        """Test resolving from documents based on high similarity."""
        # Arrange
        doc = Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="测试公司",
            concept_name="测试概念",
            concept_category="Test",
            importance_score=Decimal("0.9"),
            similarity_score=0.97,  # High score > 0.95
            matched_at=datetime.now(UTC),
        )

        # Act
        result = parser.resolve_from_documents(
            query_identifier="test",
            documents=[doc],
        )

        # Assert
        assert result.name == "测试公司"
        assert result.code == "000001"

    def test_resolve_from_documents_empty_list(self, parser: QueryCompanyParser):
        """Test resolving from empty documents list."""
        # Act
        result = parser.resolve_from_documents(
            query_identifier="AAPL",
            documents=[],
        )

        # Assert - falls back to parsing
        assert result.name == "AAPL"
        assert result.code == "AAPL"

    def test_case_insensitive_matching(
        self,
        parser: QueryCompanyParser,
        sample_aggregated_companies: list[AggregatedCompany],
    ):
        """Test that matching is case-insensitive."""
        # Arrange - add a company with English name
        doc = Document(
            concept_id=uuid4(),
            company_code="AAPL",
            company_name="Apple Inc.",
            concept_name="Technology",
            concept_category="Tech",
            importance_score=Decimal("0.9"),
            similarity_score=0.90,
            matched_at=datetime.now(UTC),
        )

        companies = sample_aggregated_companies + [
            AggregatedCompany(
                company_code="AAPL",
                company_name="Apple Inc.",
                relevance_score=0.90,
                matched_concepts=[doc],
            )
        ]

        # Act - test different cases
        result1 = parser.resolve_from_results("aapl", companies)
        result2 = parser.resolve_from_results("APPLE", companies)

        # Assert
        assert result1.code == "AAPL"
        assert result2.name == "Apple Inc."
