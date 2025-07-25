"""Unit tests for market filter with advanced scoring."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.services.company_aggregator import AggregatedCompany
from src.domain.services.market_filter import (
    FilterResult,
    MarketData,
    MarketDataRepository,
    MarketFilter,
    MarketFilters,
)
from src.shared.config.market_filter_config import MarketFilterConfig, TierConfig


class TestMarketFilter:
    """Test cases for MarketFilter with advanced scoring."""

    @pytest.fixture
    def mock_market_data_repo(self):
        """Create mock market data repository."""
        return AsyncMock(spec=MarketDataRepository)

    @pytest.fixture
    def market_filter_config(self):
        """Create test market filter configuration."""
        return MarketFilterConfig(
            max_market_cap=85e8,
            max_avg_volume_5d=2e8,
            market_cap_tiers=[
                TierConfig(
                    min_value=60e8, max_value=85e8, score=1.0, label="Quality mid-cap"
                ),
                TierConfig(
                    min_value=40e8, max_value=60e8, score=2.0, label="Standard mid-cap"
                ),
                TierConfig(min_value=0, max_value=40e8, score=3.0, label="Small-cap"),
            ],
            volume_tiers=[
                TierConfig(
                    min_value=1e8, max_value=2e8, score=1.0, label="High liquidity"
                ),
                TierConfig(
                    min_value=0.5e8, max_value=1e8, score=2.0, label="Medium liquidity"
                ),
                TierConfig(
                    min_value=0, max_value=0.5e8, score=3.0, label="Low liquidity"
                ),
            ],
            relevance_mapping_enabled=False,
        )

    @pytest.fixture
    def market_filter(self, mock_market_data_repo, market_filter_config):
        """Create market filter instance."""
        return MarketFilter(mock_market_data_repo, market_filter_config)

    @pytest.fixture
    def sample_companies(self):
        """Create sample aggregated companies."""
        # Create mock documents for matched concepts
        from src.domain.value_objects import Document

        doc1 = MagicMock(spec=Document)
        doc2 = MagicMock(spec=Document)
        doc3 = MagicMock(spec=Document)

        return [
            AggregatedCompany(
                company_code="000001",
                company_name="Company A",
                company_name_short="A",
                relevance_score=0.9,
                matched_concepts=[doc1, doc2],
            ),
            AggregatedCompany(
                company_code="000002",
                company_name="Company B",
                company_name_short="B",
                relevance_score=0.7,
                matched_concepts=[doc3],
            ),
            AggregatedCompany(
                company_code="000003",
                company_name="Company C",
                company_name_short="C",
                relevance_score=0.5,
                matched_concepts=[],
            ),
        ]

    @pytest.fixture
    def sample_market_data(self):
        """Create sample market data."""
        return {
            "000001": MarketData(
                company_code="000001",
                market_cap_cny=Decimal("70e8"),  # 70亿 - Quality mid-cap
                avg_volume_5day=Decimal("1.5e8"),  # 1.5亿 - High liquidity
            ),
            "000002": MarketData(
                company_code="000002",
                market_cap_cny=Decimal("50e8"),  # 50亿 - Standard mid-cap
                avg_volume_5day=Decimal("0.8e8"),  # 0.8亿 - Medium liquidity
            ),
            "000003": MarketData(
                company_code="000003",
                market_cap_cny=Decimal("90e8"),  # 90亿 - Exceeds max filter
                avg_volume_5day=Decimal("2.5e8"),  # 2.5亿 - Exceeds max filter
            ),
        }

    @pytest.mark.asyncio
    async def test_apply_filters_with_scoring(
        self, market_filter, mock_market_data_repo, sample_companies, sample_market_data
    ):
        """Test applying filters with advanced scoring algorithm."""
        # Setup mock
        mock_market_data_repo.get_market_data.return_value = sample_market_data

        # Apply filters
        result = await market_filter.apply_filters(sample_companies)

        # Verify result
        assert isinstance(result, FilterResult)
        assert len(result.scored_companies) == 2  # Company C filtered out
        assert result.total_before_filter == 3
        assert result.filters_applied["advanced_scoring"] is True

        # Check scoring for Company A
        company_a = next(
            sc for sc in result.scored_companies if sc.company.company_code == "000001"
        )
        assert company_a.market_cap_score == 1.0  # Quality mid-cap
        assert company_a.volume_score == 1.0  # High liquidity
        assert company_a.relevance_coefficient == 0.9
        assert company_a.l_score == 0.9 * (1.0 + 1.0)  # 1.8

        # Check scoring for Company B
        company_b = next(
            sc for sc in result.scored_companies if sc.company.company_code == "000002"
        )
        assert company_b.market_cap_score == 2.0  # Standard mid-cap
        assert company_b.volume_score == 2.0  # Medium liquidity
        assert company_b.relevance_coefficient == 0.7
        assert company_b.l_score == 0.7 * (2.0 + 2.0)  # 2.8

        # Verify sorting by L score (descending)
        assert (
            result.scored_companies[0].company.company_code == "000002"
        )  # Higher L score
        assert result.scored_companies[1].company.company_code == "000001"

    @pytest.mark.asyncio
    async def test_apply_filters_with_custom_thresholds(
        self, market_filter, mock_market_data_repo, sample_companies, sample_market_data
    ):
        """Test applying custom filter thresholds."""
        mock_market_data_repo.get_market_data.return_value = sample_market_data

        # Apply with custom filters
        custom_filters = MarketFilters(
            max_market_cap_cny=Decimal("60e8"),  # More restrictive
            max_avg_volume_5day=Decimal("1e8"),  # More restrictive
        )

        result = await market_filter.apply_filters(sample_companies, custom_filters)

        # Only Company B should pass (50亿 < 60亿 and 0.8亿 < 1亿)
        assert len(result.scored_companies) == 1
        assert result.scored_companies[0].company.company_code == "000002"

    @pytest.mark.asyncio
    async def test_apply_filters_no_market_data(
        self, market_filter, mock_market_data_repo, sample_companies
    ):
        """Test graceful degradation when no market data available."""
        mock_market_data_repo.get_market_data.return_value = {}

        result = await market_filter.apply_filters(sample_companies)

        # Should return all companies with default scores
        assert len(result.scored_companies) == 3
        assert all(sc.l_score == 0.0 for sc in result.scored_companies)
        assert result.filters_applied["advanced_scoring"] is False

    @pytest.mark.asyncio
    async def test_apply_filters_partial_market_data(
        self, market_filter, mock_market_data_repo, sample_companies
    ):
        """Test handling when market data is only available for some companies."""
        # Only data for company A
        partial_data = {
            "000001": MarketData(
                company_code="000001",
                market_cap_cny=Decimal("70e8"),
                avg_volume_5day=Decimal("1.5e8"),
            )
        }
        mock_market_data_repo.get_market_data.return_value = partial_data

        result = await market_filter.apply_filters(sample_companies)

        # Only company A should be in results
        assert len(result.scored_companies) == 1
        assert result.scored_companies[0].company.company_code == "000001"

    def test_market_filter_config_tier_scoring(self, market_filter_config):
        """Test tier-based scoring configuration."""
        # Market cap scoring
        assert market_filter_config.get_market_cap_score(70e8) == 1.0  # Quality mid-cap
        assert (
            market_filter_config.get_market_cap_score(50e8) == 2.0
        )  # Standard mid-cap
        assert market_filter_config.get_market_cap_score(30e8) == 3.0  # Small-cap

        # Volume scoring
        assert market_filter_config.get_volume_score(1.5e8) == 1.0  # High liquidity
        assert market_filter_config.get_volume_score(0.7e8) == 2.0  # Medium liquidity
        assert market_filter_config.get_volume_score(0.3e8) == 3.0  # Low liquidity

    def test_relevance_coefficient_continuous(self, market_filter_config):
        """Test relevance coefficient without mapping (continuous values)."""
        assert market_filter_config.get_relevance_coefficient(0.95) == 0.95
        assert market_filter_config.get_relevance_coefficient(0.5) == 0.5
        assert market_filter_config.get_relevance_coefficient(0.1) == 0.1

    def test_relevance_coefficient_with_mapping(self):
        """Test relevance coefficient with discrete mapping enabled."""
        config = MarketFilterConfig(relevance_mapping_enabled=True)

        assert config.get_relevance_coefficient(0.9) == 1.0  # High relevance
        assert config.get_relevance_coefficient(0.6) == 0.5  # Medium relevance
        assert config.get_relevance_coefficient(0.3) == 0.1  # Low relevance
