"""Market data filtering service for company search results.

This module provides domain services for filtering search results based
on market data such as market capitalization and trading volume.
"""

from abc import ABC, abstractmethod
from decimal import Decimal

import structlog
from pydantic import BaseModel, ConfigDict, Field

from src.domain.services.company_aggregator import AggregatedCompany
from src.shared.config.market_filter_config import MarketFilterConfig

logger = structlog.get_logger(__name__)


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


class ScoredCompany(BaseModel):
    """Company with market-based scoring.

    Attributes:
        company: The aggregated company data
        market_cap_score: Market cap tier score (S)
        volume_score: Volume tier score (V)
        relevance_coefficient: Relevance coefficient (X)
        l_score: Combined score L = X * (S + V)
    """

    model_config = ConfigDict(frozen=True)

    company: AggregatedCompany
    market_cap_score: float = Field(..., description="Market cap tier score (S)")
    volume_score: float = Field(..., description="Volume tier score (V)")
    relevance_coefficient: float = Field(..., description="Relevance coefficient (X)")
    l_score: float = Field(..., description="Combined score L = X * (S + V)")


class MarketFilters(BaseModel):
    """Market data filters for search results.

    Attributes:
        max_market_cap_cny: Maximum market cap in CNY
        max_avg_volume_5day: Maximum 5-day average volume in CNY
    """

    model_config = ConfigDict(frozen=True)

    max_market_cap_cny: Decimal | None = Field(None, gt=0)
    max_avg_volume_5day: Decimal | None = Field(None, gt=0)

    def is_empty(self) -> bool:
        """Check if all filters are None (no filtering needed).

        Returns:
            True if no filters are specified
        """
        return self.max_market_cap_cny is None and self.max_avg_volume_5day is None


class MarketDataRepository(ABC):
    """Abstract repository for market data.

    This interface defines methods for retrieving market data.
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


class FilterResult(BaseModel):
    """Result of applying market filters with scoring.

    Attributes:
        scored_companies: Companies with scores, sorted by L value
        filters_applied: Dictionary indicating which filters were actually applied
        total_before_filter: Total number of companies before filtering
        filter_config: Configuration used for filtering
    """

    model_config = ConfigDict(frozen=True)

    scored_companies: list[ScoredCompany]
    filters_applied: dict[str, bool]
    total_before_filter: int
    filter_config: dict[str, float]


class MarketFilter:
    """Service for filtering and scoring companies based on market data.

    This service applies market-based filters and advanced scoring to search results,
    with graceful degradation when market data is unavailable.
    """

    def __init__(
        self,
        market_data_repository: MarketDataRepository,
        config: MarketFilterConfig | None = None,
    ):
        """Initialize the market filter service.

        Args:
            market_data_repository: Repository for retrieving market data
            config: Market filter configuration (uses defaults if not provided)
        """
        self.market_data_repository = market_data_repository
        self.config = config or MarketFilterConfig()

    async def apply_filters(
        self,
        companies: list[AggregatedCompany],
        filters: MarketFilters | None = None,
    ) -> FilterResult:
        """Apply market filters and scoring to company list.

        Filters companies based on market cap and volume criteria,
        then applies the advanced scoring algorithm L = X * (S + V).

        Args:
            companies: List of aggregated companies to filter
            filters: Optional market filters (uses config defaults if not provided)

        Returns:
            FilterResult with scored and filtered companies
        """
        # Use config defaults if no filters provided
        if filters is None:
            filters = MarketFilters(
                max_market_cap_cny=Decimal(str(self.config.max_market_cap)),
                max_avg_volume_5day=Decimal(str(self.config.max_avg_volume_5d)),
            )

        # Track which filters were actually applied
        filters_applied = {
            "market_cap_filter": False,
            "volume_filter": False,
            "advanced_scoring": False,
        }

        # Get company codes for market data lookup
        company_codes = [company.company_code for company in companies]

        # Retrieve market data
        market_data_map = await self.market_data_repository.get_market_data(
            company_codes
        )

        # If no market data available, return companies without scoring
        if not market_data_map:
            logger.warning(
                f"No market data available for {len(companies)} companies. "
                "Returning without market filtering or scoring."
            )
            # Create scored companies with default scores
            scored_companies = [
                ScoredCompany(
                    company=company,
                    market_cap_score=0.0,
                    volume_score=0.0,
                    relevance_coefficient=company.relevance_score,
                    l_score=0.0,
                )
                for company in companies
            ]
            return FilterResult(
                scored_companies=scored_companies,
                filters_applied=filters_applied,
                total_before_filter=len(companies),
                filter_config={
                    "max_market_cap": float(filters.max_market_cap_cny or 0),
                    "max_avg_volume_5d": float(filters.max_avg_volume_5day or 0),
                },
            )

        # Apply filters and scoring
        scored_companies = []
        for company in companies:
            market_data = market_data_map.get(company.company_code)

            # If no market data for this company, skip it
            if not market_data:
                logger.debug(
                    f"No market data available for {company.company_code}, "
                    "excluding from results"
                )
                continue

            # Apply market cap filter
            if filters.max_market_cap_cny is not None:
                filters_applied["market_cap_filter"] = True
                if (
                    market_data.market_cap_cny is None
                    or market_data.market_cap_cny > filters.max_market_cap_cny
                ):
                    continue

            # Apply volume filter
            if filters.max_avg_volume_5day is not None:
                filters_applied["volume_filter"] = True
                if (
                    market_data.avg_volume_5day is None
                    or market_data.avg_volume_5day > filters.max_avg_volume_5day
                ):
                    continue

            # Calculate scores
            filters_applied["advanced_scoring"] = True

            # Get relevance coefficient (X)
            relevance_coefficient = self.config.get_relevance_coefficient(
                company.relevance_score
            )

            # Get market cap score (S)
            market_cap_score = self.config.get_market_cap_score(
                float(market_data.market_cap_cny or 0)
            )

            # Get volume score (V)
            volume_score = self.config.get_volume_score(
                float(market_data.avg_volume_5day or 0)
            )

            # Calculate L score: L = X * (S + V)
            l_score = relevance_coefficient * (market_cap_score + volume_score)

            scored_company = ScoredCompany(
                company=company,
                market_cap_score=market_cap_score,
                volume_score=volume_score,
                relevance_coefficient=relevance_coefficient,
                l_score=l_score,
            )
            scored_companies.append(scored_company)

        # Sort by L score descending
        scored_companies.sort(key=lambda x: x.l_score, reverse=True)

        logger.info(
            f"Market filters and scoring applied: {len(companies)} companies "
            f"reduced to {len(scored_companies)} after filtering"
        )

        return FilterResult(
            scored_companies=scored_companies,
            filters_applied=filters_applied,
            total_before_filter=len(companies),
            filter_config={
                "max_market_cap": float(filters.max_market_cap_cny or 0),
                "max_avg_volume_5d": float(filters.max_avg_volume_5day or 0),
            },
        )
