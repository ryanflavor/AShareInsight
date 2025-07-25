"""Integration tests for market data synchronization."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from src.domain.services.market_data_sync_service import MarketDataSyncService
from src.infrastructure.market_data.akshare_adapter import (
    AkshareMarketDataAdapter,
    MarketSnapshot,
)
from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository,
)
from src.shared.utils.timezone import now_china


@pytest.mark.integration
class TestMarketDataSyncIntegration:
    """Integration tests for market data sync workflow."""

    @pytest.fixture
    async def db_pool(self):
        """Create test database connection pool."""
        # This would connect to a test database in real integration tests
        pool = AsyncMock(spec=asyncpg.Pool)
        yield pool
        # Cleanup would happen here

    @pytest.fixture
    def market_adapter(self):
        """Create market data adapter."""
        return AkshareMarketDataAdapter(max_retries=2, retry_delay=0.1)

    @pytest.fixture
    def market_repository(self, db_pool):
        """Create market data repository."""
        return MarketDataRepository(db_pool, redis_client=None)

    @pytest.fixture
    def sync_service(self, market_adapter, market_repository):
        """Create sync service."""
        return MarketDataSyncService(market_adapter, market_repository, max_retries=2)

    @pytest.mark.asyncio
    async def test_full_sync_workflow(
        self, sync_service, market_adapter, market_repository, db_pool
    ):
        """Test complete market data sync workflow."""
        # Mock market data
        mock_snapshots = [
            MarketSnapshot(
                company_code="000001",
                company_name="Test Company 1",
                total_market_cap=Decimal("50e8"),
                circulating_market_cap=Decimal("45e8"),
                turnover_amount=Decimal("1e8"),
                trading_date=now_china(),
            ),
            MarketSnapshot(
                company_code="000002",
                company_name="Test Company 2",
                total_market_cap=Decimal("80e8"),
                circulating_market_cap=Decimal("75e8"),
                turnover_amount=Decimal("2e8"),
                trading_date=now_china(),
            ),
        ]

        # Mock adapter response
        with patch.object(
            market_adapter, "get_all_market_snapshot", return_value=mock_snapshots
        ) as mock_fetch:
            # Mock repository methods
            with (
                patch.object(
                    market_repository, "get_latest_trading_date", return_value=None
                ) as mock_latest,
                patch.object(
                    market_repository, "save_daily_snapshot", return_value=2
                ) as mock_save,
                patch.object(
                    market_repository, "cleanup_old_data", return_value=0
                ) as mock_cleanup,
            ):
                # Mock trading day check
                with patch.object(sync_service, "_is_trading_day", return_value=True):
                    # Execute sync
                    result = await sync_service.sync_daily_market_data()

                    # Verify result
                    assert result["status"] == "success"
                    assert result["records_saved"] == 2
                    assert result["attempts"] == 1

                    # Verify method calls
                    mock_fetch.assert_called_once()
                    mock_save.assert_called_once_with(mock_snapshots)
                    mock_cleanup.assert_called_once_with(days_to_keep=30)

    @pytest.mark.asyncio
    async def test_sync_skip_non_trading_day(self, sync_service):
        """Test sync skips non-trading days."""
        # Mock as non-trading day
        with patch.object(sync_service, "_is_trading_day", return_value=False):
            result = await sync_service.sync_daily_market_data()

            assert result["status"] == "skipped"
            assert result["error"] == "Not a trading day"

    @pytest.mark.asyncio
    async def test_sync_already_synced(self, sync_service, market_repository):
        """Test sync skips when data already exists."""
        # Mock latest date as today
        with (
            patch.object(
                market_repository,
                "get_latest_trading_date",
                return_value=now_china(),
            ),
            patch.object(sync_service, "_is_trading_day", return_value=True),
        ):
            result = await sync_service.sync_daily_market_data()

            assert result["status"] == "already_synced"

    @pytest.mark.asyncio
    async def test_sync_with_retries(
        self, sync_service, market_adapter, market_repository
    ):
        """Test sync retry logic on failure."""
        # First attempt fails, second succeeds
        mock_snapshots = [
            MarketSnapshot(
                company_code="000001",
                company_name="Test Company",
                total_market_cap=Decimal("50e8"),
                circulating_market_cap=Decimal("45e8"),
                turnover_amount=Decimal("1e8"),
                trading_date=now_china(),
            )
        ]

        with (
            patch.object(
                market_adapter,
                "get_all_market_snapshot",
                side_effect=[Exception("Network error"), mock_snapshots],
            ),
            patch.object(
                market_repository, "get_latest_trading_date", return_value=None
            ),
            patch.object(market_repository, "save_daily_snapshot", return_value=1),
            patch.object(market_repository, "cleanup_old_data", return_value=0),
            patch.object(sync_service, "_is_trading_day", return_value=True),
            patch("asyncio.sleep"),
        ):  # Skip actual sleep
            result = await sync_service.sync_daily_market_data()

            assert result["status"] == "success"
            assert result["attempts"] == 2

    @pytest.mark.asyncio
    async def test_sync_all_retries_fail(
        self, sync_service, market_adapter, market_repository
    ):
        """Test sync failure after all retries."""
        with (
            patch.object(
                market_adapter,
                "get_all_market_snapshot",
                side_effect=Exception("Persistent error"),
            ),
            patch.object(
                market_repository, "get_latest_trading_date", return_value=None
            ),
            patch.object(sync_service, "_is_trading_day", return_value=True),
            patch("asyncio.sleep"),
        ):
            result = await sync_service.sync_daily_market_data()

            assert result["status"] == "failed"
            assert result["attempts"] == sync_service.max_retries
            assert "Persistent error" in result["error"]

    def test_is_trading_day(self, sync_service):
        """Test trading day logic."""
        # Weekend should not be trading day
        saturday = datetime(2024, 1, 6).date()  # Saturday
        sunday = datetime(2024, 1, 7).date()  # Sunday
        assert not sync_service._is_trading_day(saturday)
        assert not sync_service._is_trading_day(sunday)

        # Regular weekday (assuming not holiday)
        monday = datetime(2024, 1, 8).date()  # Monday
        with patch("chinese_calendar.is_holiday", return_value=False):
            # Mock current time as after market close
            with patch(
                "src.domain.services.market_data_sync_service.datetime"
            ) as mock_dt:
                mock_dt.now.return_value = datetime(2024, 1, 8, 16, 0)  # 4 PM
                mock_dt.now().date.return_value = monday
                assert sync_service._is_trading_day(monday)
