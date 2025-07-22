"""Market data filtering service for company search results.

This module provides domain services for filtering search results based
on market data such as market capitalization and trading volume.
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.services.company_aggregator import AggregatedCompany

logger = logging.getLogger(__name__)


class MarketData(BaseModel):
    """Market data for a company.

    Attributes:
        company_code: Stock code of the company
        market_cap_cny: Market capitalization in CNY
        avg_volume_5day: 5-day average trading volume
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    company_code: str = Field(..., max_length=10)
    market_cap_cny: Decimal | None = Field(None, ge=0)
    avg_volume_5day: Decimal | None = Field(None, ge=0)


class MarketFilters(BaseModel):
    """Market data filters for search results.

    Attributes:
        max_market_cap_cny: Maximum market cap in CNY
        min_5day_avg_volume: Minimum 5-day average volume
    """

    model_config = ConfigDict(frozen=True)

    max_market_cap_cny: Decimal | None = Field(None, gt=0)
    min_5day_avg_volume: Decimal | None = Field(None, ge=0)

    def is_empty(self) -> bool:
        """Check if all filters are None (no filtering needed).

        Returns:
            True if no filters are specified
        """
        return self.max_market_cap_cny is None and self.min_5day_avg_volume is None


class MarketDataRepository(ABC):
    """Abstract repository for market data.

    This interface defines methods for retrieving market data.
    TODO: Implement concrete adapter when market data source is available.
    """

    @abstractmethod
    async def get_market_data(self, company_codes: list[str]) -> dict[str, MarketData]:
        """Retrieve market data for given company codes.

        Args:
            company_codes: List of company codes to fetch data for

        Returns:
            Dictionary mapping company codes to MarketData objects
        """
        pass


class StubMarketDataRepository(MarketDataRepository):
    """Stub implementation of MarketDataRepository.

    Returns empty market data for all requests. This is a temporary
    implementation until real market data source is integrated.
    """

    async def get_market_data(self, company_codes: list[str]) -> dict[str, MarketData]:
        """Return empty market data for all companies.

        Args:
            company_codes: List of company codes (ignored)

        Returns:
            Empty dictionary
        """
        logger.warning(
            f"Market data requested for {len(company_codes)} companies "
            "but no data source is configured. Using stub implementation."
        )
        return {}


class FilterResult(BaseModel):
    """Result of applying market filters.

    Attributes:
        filtered_companies: Companies that passed the filters
        filters_applied: Dictionary indicating which filters were actually applied
        total_before_filter: Total number of companies before filtering
    """

    model_config = ConfigDict(frozen=True)

    filtered_companies: list[AggregatedCompany]
    filters_applied: dict[str, bool]
    total_before_filter: int


class MarketFilter:
    """Service for filtering companies based on market data.

    This service applies market-based filters to search results,
    with graceful degradation when market data is unavailable.
    """

    def __init__(self, market_data_repository: MarketDataRepository):
        """Initialize the market filter service.

        Args:
            market_data_repository: Repository for retrieving market data
        """
        self.market_data_repository = market_data_repository

    async def apply_filters(
        self,
        companies: list[AggregatedCompany],
        filters: MarketFilters,
    ) -> FilterResult:
        """Apply market filters to company list.

        Filters companies based on market cap and volume criteria.
        If market data is unavailable, filters are skipped with logging.

        Args:
            companies: List of aggregated companies to filter
            filters: Market filters to apply

        Returns:
            FilterResult with filtered companies and metadata
        """
        # Track which filters were actually applied
        filters_applied = {
            "market_cap_filter": False,
            "volume_filter": False,
        }

        # If no filters specified, return all companies
        if filters.is_empty():
            logger.debug("No market filters specified, returning all companies")
            return FilterResult(
                filtered_companies=companies,
                filters_applied=filters_applied,
                total_before_filter=len(companies),
            )

        # Get company codes for market data lookup
        company_codes = [company.company_code for company in companies]

        # Retrieve market data
        market_data_map = await self.market_data_repository.get_market_data(
            company_codes
        )

        # If no market data available, log and return all companies
        if not market_data_map:
            self._log_filter_skip(filters)
            return FilterResult(
                filtered_companies=companies,
                filters_applied=filters_applied,
                total_before_filter=len(companies),
            )

        # Apply filters
        filtered_companies = []
        for company in companies:
            market_data = market_data_map.get(company.company_code)

            # If no market data for this company, skip it (conservative approach)
            if not market_data:
                logger.debug(
                    f"No market data available for {company.company_code}, "
                    "excluding from results"
                )
                continue

            # Check market cap filter
            if filters.max_market_cap_cny is not None:
                filters_applied["market_cap_filter"] = True
                if (
                    market_data.market_cap_cny is None
                    or market_data.market_cap_cny > filters.max_market_cap_cny
                ):
                    continue

            # Check volume filter
            if filters.min_5day_avg_volume is not None:
                filters_applied["volume_filter"] = True
                if (
                    market_data.avg_volume_5day is None
                    or market_data.avg_volume_5day < filters.min_5day_avg_volume
                ):
                    continue

            # Company passed all filters
            filtered_companies.append(company)

        logger.info(
            f"Market filters applied: {len(companies)} companies reduced to "
            f"{len(filtered_companies)} after filtering"
        )

        return FilterResult(
            filtered_companies=filtered_companies,
            filters_applied=filters_applied,
            total_before_filter=len(companies),
        )

    def _log_filter_skip(self, filters: MarketFilters) -> None:
        """Log warning when filters are requested but cannot be applied.

        Args:
            filters: The filters that were requested
        """
        filter_desc = []
        if filters.max_market_cap_cny is not None:
            filter_desc.append(f"max_market_cap={filters.max_market_cap_cny}")
        if filters.min_5day_avg_volume is not None:
            filter_desc.append(f"min_volume={filters.min_5day_avg_volume}")

        logger.warning(
            f"Market filters requested ({', '.join(filter_desc)}) but no market "
            "data available. Filters not applied."
        )
