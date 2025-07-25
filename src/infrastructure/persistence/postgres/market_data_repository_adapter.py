"""Adapter to connect domain MarketDataRepository interface with PostgreSQL implementation."""

from src.domain.services.market_filter import MarketData, MarketDataRepository
from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository as PostgresMarketDataRepository,
)


class PostgresMarketDataRepositoryAdapter(MarketDataRepository):
    """Adapter that implements domain MarketDataRepository using PostgreSQL."""

    def __init__(self, postgres_repo: PostgresMarketDataRepository):
        """Initialize adapter with PostgreSQL repository.

        Args:
            postgres_repo: PostgreSQL market data repository implementation
        """
        self.postgres_repo = postgres_repo

    async def get_market_data(self, company_codes: list[str]) -> dict[str, MarketData]:
        """Retrieve market data for given company codes.

        Args:
            company_codes: List of company codes to fetch data for

        Returns:
            Dictionary mapping company codes to MarketData objects
        """
        # Get data from PostgreSQL repository
        market_data_with_avg = await self.postgres_repo.get_market_data_with_5day_avg(
            company_codes
        )

        # Convert to domain model
        result = {}
        for code, data in market_data_with_avg.items():
            result[code] = MarketData(
                company_code=code,
                market_cap_cny=data.current_market_cap,
                avg_volume_5day=data.avg_5day_volume,
            )

        return result
