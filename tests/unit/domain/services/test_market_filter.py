"""Unit tests for MarketFilter domain service.

This module tests the market data filtering functionality including
filter application and graceful degradation.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

from src.domain.services import (
    AggregatedCompany,
    MarketData,
    MarketDataRepository,
    MarketFilter,
    MarketFilters,
    StubMarketDataRepository,
)
from src.domain.value_objects import Document


class MockMarketDataRepository(MarketDataRepository):
    """Mock implementation of MarketDataRepository for testing."""

    def __init__(self, market_data: dict[str, MarketData] | None = None):
        """Initialize with optional market data."""
        self.market_data = market_data or {}
        self.calls = []  # Track method calls for verification

    async def get_market_data(self, company_codes: list[str]) -> dict[str, MarketData]:
        """Return configured market data."""
        self.calls.append(company_codes)
        return {
            code: data
            for code, data in self.market_data.items()
            if code in company_codes
        }


class TestMarketFilter:
    """Test cases for MarketFilter service."""

    @pytest.fixture
    def sample_companies(self) -> list[AggregatedCompany]:
        """Create sample aggregated companies for testing."""
        base_time = datetime.now(UTC)

        # Create mock documents for each company
        doc1 = Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="Large Cap Company",
            concept_name="Tech",
            concept_category="Technology",
            importance_score=Decimal("0.9"),
            similarity_score=0.95,
            matched_at=base_time,
        )

        doc2 = Document(
            concept_id=uuid4(),
            company_code="000002",
            company_name="Mid Cap Company",
            concept_name="Finance",
            concept_category="Financial",
            importance_score=Decimal("0.8"),
            similarity_score=0.88,
            matched_at=base_time,
        )

        doc3 = Document(
            concept_id=uuid4(),
            company_code="000003",
            company_name="Small Cap Company",
            concept_name="Retail",
            concept_category="Consumer",
            importance_score=Decimal("0.7"),
            similarity_score=0.82,
            matched_at=base_time,
        )

        return [
            AggregatedCompany(
                company_code="000001",
                company_name="Large Cap Company",
                relevance_score=0.95,
                matched_concepts=[doc1],
            ),
            AggregatedCompany(
                company_code="000002",
                company_name="Mid Cap Company",
                relevance_score=0.88,
                matched_concepts=[doc2],
            ),
            AggregatedCompany(
                company_code="000003",
                company_name="Small Cap Company",
                relevance_score=0.82,
                matched_concepts=[doc3],
            ),
        ]

    @pytest.fixture
    def market_data(self) -> dict[str, MarketData]:
        """Create sample market data."""
        return {
            "000001": MarketData(
                company_code="000001",
                market_cap_cny=Decimal("100000000000"),  # 100B
                avg_volume_5day=Decimal("5000000"),  # 5M
            ),
            "000002": MarketData(
                company_code="000002",
                market_cap_cny=Decimal("10000000000"),  # 10B
                avg_volume_5day=Decimal("1000000"),  # 1M
            ),
            "000003": MarketData(
                company_code="000003",
                market_cap_cny=Decimal("1000000000"),  # 1B
                avg_volume_5day=Decimal("100000"),  # 100K
            ),
        }

    @pytest_asyncio.fixture
    async def market_filter_with_data(
        self, market_data: dict[str, MarketData]
    ) -> MarketFilter:
        """Create MarketFilter with mock data repository."""
        repository = MockMarketDataRepository(market_data)
        return MarketFilter(repository)

    @pytest_asyncio.fixture
    async def market_filter_stub(self) -> MarketFilter:
        """Create MarketFilter with stub repository."""
        repository = StubMarketDataRepository()
        return MarketFilter(repository)

    async def test_filter_by_market_cap(
        self,
        market_filter_with_data: MarketFilter,
        sample_companies: list[AggregatedCompany],
    ):
        """Test filtering by maximum market cap."""
        # Arrange
        filters = MarketFilters(
            max_market_cap_cny=Decimal("50000000000"),  # 50B max
            min_5day_avg_volume=None,
        )

        # Act
        result = await market_filter_with_data.apply_filters(
            companies=sample_companies, filters=filters
        )

        # Assert
        assert len(result.filtered_companies) == 2  # Only companies 2 and 3
        assert result.filtered_companies[0].company_code == "000002"
        assert result.filtered_companies[1].company_code == "000003"
        assert result.filters_applied["market_cap_filter"] is True
        assert result.filters_applied["volume_filter"] is False
        assert result.total_before_filter == 3

    async def test_filter_by_volume(
        self,
        market_filter_with_data: MarketFilter,
        sample_companies: list[AggregatedCompany],
    ):
        """Test filtering by minimum volume."""
        # Arrange
        filters = MarketFilters(
            max_market_cap_cny=None,
            min_5day_avg_volume=Decimal("500000"),  # 500K minimum
        )

        # Act
        result = await market_filter_with_data.apply_filters(
            companies=sample_companies, filters=filters
        )

        # Assert
        assert len(result.filtered_companies) == 2  # Companies 1 and 2
        assert result.filtered_companies[0].company_code == "000001"
        assert result.filtered_companies[1].company_code == "000002"
        assert result.filters_applied["market_cap_filter"] is False
        assert result.filters_applied["volume_filter"] is True
        assert result.total_before_filter == 3

    async def test_filter_by_both_criteria(
        self,
        market_filter_with_data: MarketFilter,
        sample_companies: list[AggregatedCompany],
    ):
        """Test filtering by both market cap and volume."""
        # Arrange
        filters = MarketFilters(
            max_market_cap_cny=Decimal("50000000000"),  # 50B max
            min_5day_avg_volume=Decimal("500000"),  # 500K minimum
        )

        # Act
        result = await market_filter_with_data.apply_filters(
            companies=sample_companies, filters=filters
        )

        # Assert
        assert len(result.filtered_companies) == 1  # Only company 2
        assert result.filtered_companies[0].company_code == "000002"
        assert result.filters_applied["market_cap_filter"] is True
        assert result.filters_applied["volume_filter"] is True
        assert result.total_before_filter == 3

    async def test_no_filters_applied(
        self,
        market_filter_with_data: MarketFilter,
        sample_companies: list[AggregatedCompany],
    ):
        """Test with empty filters returns all companies."""
        # Arrange
        filters = MarketFilters(max_market_cap_cny=None, min_5day_avg_volume=None)

        # Act
        result = await market_filter_with_data.apply_filters(
            companies=sample_companies, filters=filters
        )

        # Assert
        assert len(result.filtered_companies) == 3  # All companies
        assert result.filters_applied["market_cap_filter"] is False
        assert result.filters_applied["volume_filter"] is False
        assert result.total_before_filter == 3

    async def test_graceful_degradation_no_data(
        self,
        market_filter_stub: MarketFilter,
        sample_companies: list[AggregatedCompany],
    ):
        """Test graceful degradation when no market data available."""
        # Arrange
        filters = MarketFilters(
            max_market_cap_cny=Decimal("50000000000"),
            min_5day_avg_volume=Decimal("500000"),
        )

        # Act
        result = await market_filter_stub.apply_filters(
            companies=sample_companies, filters=filters
        )

        # Assert - all companies returned, filters not applied
        assert len(result.filtered_companies) == 3
        assert result.filters_applied["market_cap_filter"] is False
        assert result.filters_applied["volume_filter"] is False
        assert result.total_before_filter == 3

    async def test_missing_market_data_for_company(
        self, sample_companies: list[AggregatedCompany]
    ):
        """Test behavior when market data missing for specific companies."""
        # Arrange - only data for company 1
        partial_data = {
            "000001": MarketData(
                company_code="000001",
                market_cap_cny=Decimal("100000000000"),
                avg_volume_5day=Decimal("5000000"),
            )
        }
        repository = MockMarketDataRepository(partial_data)
        market_filter = MarketFilter(repository)

        filters = MarketFilters(
            max_market_cap_cny=Decimal("200000000000"),  # Should pass
            min_5day_avg_volume=None,
        )

        # Act
        result = await market_filter.apply_filters(
            companies=sample_companies, filters=filters
        )

        # Assert - only company with data is returned
        assert len(result.filtered_companies) == 1
        assert result.filtered_companies[0].company_code == "000001"
        assert result.filters_applied["market_cap_filter"] is True

    async def test_null_market_data_values(
        self, sample_companies: list[AggregatedCompany]
    ):
        """Test handling of null values in market data."""
        # Arrange
        partial_data = {
            "000001": MarketData(
                company_code="000001",
                market_cap_cny=None,  # Null market cap
                avg_volume_5day=Decimal("5000000"),
            ),
            "000002": MarketData(
                company_code="000002",
                market_cap_cny=Decimal("10000000000"),
                avg_volume_5day=None,  # Null volume
            ),
        }
        repository = MockMarketDataRepository(partial_data)
        market_filter = MarketFilter(repository)

        filters = MarketFilters(
            max_market_cap_cny=Decimal("50000000000"),
            min_5day_avg_volume=Decimal("1000000"),
        )

        # Act
        result = await market_filter.apply_filters(
            companies=sample_companies[:2],
            filters=filters,  # Only first 2 companies
        )

        # Assert - both excluded due to null values not meeting criteria
        assert len(result.filtered_companies) == 0
        assert result.filters_applied["market_cap_filter"] is True
        assert result.filters_applied["volume_filter"] is True

    async def test_empty_company_list(self, market_filter_with_data: MarketFilter):
        """Test filtering empty company list."""
        # Arrange
        filters = MarketFilters(
            max_market_cap_cny=Decimal("50000000000"),
            min_5day_avg_volume=Decimal("500000"),
        )

        # Act
        result = await market_filter_with_data.apply_filters(
            companies=[], filters=filters
        )

        # Assert
        assert len(result.filtered_companies) == 0
        assert result.total_before_filter == 0

    def test_market_filters_is_empty(self):
        """Test MarketFilters.is_empty() method."""
        # Test all None
        empty_filters = MarketFilters(max_market_cap_cny=None, min_5day_avg_volume=None)
        assert empty_filters.is_empty() is True

        # Test with market cap
        cap_filters = MarketFilters(
            max_market_cap_cny=Decimal("1000000"), min_5day_avg_volume=None
        )
        assert cap_filters.is_empty() is False

        # Test with volume
        vol_filters = MarketFilters(
            max_market_cap_cny=None, min_5day_avg_volume=Decimal("1000")
        )
        assert vol_filters.is_empty() is False

        # Test with both
        both_filters = MarketFilters(
            max_market_cap_cny=Decimal("1000000"), min_5day_avg_volume=Decimal("1000")
        )
        assert both_filters.is_empty() is False

    async def test_stub_repository_warning(
        self, sample_companies: list[AggregatedCompany], caplog
    ):
        """Test that stub repository logs warning."""
        # Arrange
        repository = StubMarketDataRepository()

        # Act
        await repository.get_market_data(["000001", "000002"])

        # Assert
        assert "Market data requested for 2 companies" in caplog.text
        assert "no data source is configured" in caplog.text
