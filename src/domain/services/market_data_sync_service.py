"""Market data synchronization service."""

import asyncio
from datetime import datetime, timedelta

import chinese_calendar as calendar

from src.infrastructure.market_data.akshare_adapter import AkshareMarketDataAdapter
from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository,
)
from src.shared.utils.logger import get_logger
from src.shared.utils.timezone import now_china

logger = get_logger(__name__)


class MarketDataSyncService:
    """Service for synchronizing market data from akshare."""

    def __init__(
        self,
        market_data_adapter: AkshareMarketDataAdapter,
        market_data_repository: MarketDataRepository,
        max_retries: int = 3,
    ):
        """Initialize sync service.

        Args:
            market_data_adapter: Akshare adapter for fetching data
            market_data_repository: Repository for persisting data
            max_retries: Maximum number of retry attempts for sync
        """
        self.adapter = market_data_adapter
        self.repository = market_data_repository
        self.max_retries = max_retries

    async def sync_daily_market_data(self) -> dict:
        """Synchronize daily market data.

        Returns:
            Dictionary with sync results including status and statistics
        """
        sync_result = {
            "status": "failed",
            "trading_date": None,
            "records_saved": 0,
            "error": None,
            "sync_timestamp": now_china(),
            "attempts": 0,
        }

        # Check if today is a trading day
        today = now_china().date()
        if not self._is_trading_day(today):
            logger.info(f"{today} is not a trading day, skipping sync")
            sync_result["status"] = "skipped"
            sync_result["error"] = "Not a trading day"
            return sync_result

        # Check if we already have data for today
        latest_date = await self.repository.get_latest_trading_date()
        if latest_date and latest_date.date() >= today:
            logger.info(f"Market data already synced for {today}")
            sync_result["status"] = "already_synced"
            sync_result["trading_date"] = today
            return sync_result

        # Perform sync with retries
        for attempt in range(self.max_retries):
            sync_result["attempts"] = attempt + 1
            try:
                logger.info(
                    f"Starting market data sync attempt {attempt + 1}/{self.max_retries}"
                )

                # Fetch market snapshots
                snapshots = await self.adapter.get_all_market_snapshot()
                if not snapshots:
                    raise Exception("No market data received from akshare")

                # Save to database
                records_saved = await self.repository.save_daily_snapshot(snapshots)

                # Clean up old data (keep last 30 days)
                await self.repository.cleanup_old_data(days_to_keep=30)

                # Update sync result
                sync_result.update(
                    {
                        "status": "success",
                        "trading_date": today,
                        "records_saved": records_saved,
                        "error": None,
                    }
                )

                logger.info(
                    f"Market data sync completed successfully. "
                    f"Saved {records_saved} records for {today}"
                )
                return sync_result

            except Exception as e:
                logger.error(f"Sync attempt {attempt + 1} failed: {str(e)}")
                sync_result["error"] = str(e)

                if attempt < self.max_retries - 1:
                    # Wait before retry with exponential backoff
                    wait_time = 2**attempt * 5  # 5s, 10s, 20s
                    logger.info(f"Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All sync attempts failed. Last error: {str(e)}")

        return sync_result

    def _is_trading_day(self, date: datetime.date) -> bool:
        """Check if a date is a trading day.

        Args:
            date: Date to check

        Returns:
            True if it's a trading day, False otherwise
        """
        # Check if it's a weekend
        if date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # Check if it's a Chinese holiday
        if calendar.is_holiday(date):
            return False

        # Additional check for market hours (market closes at 15:00)
        now = now_china()
        if date == now.date() and now.hour < 15:
            logger.info("Market is still open, sync should run after 15:00")
            return False

        return True

    async def get_sync_status(self) -> dict:
        """Get current sync status.

        Returns:
            Dictionary with sync status information
        """
        try:
            latest_date = await self.repository.get_latest_trading_date()
            today = now_china().date()
            is_trading_day = self._is_trading_day(today)

            status = {
                "latest_data_date": latest_date.date() if latest_date else None,
                "today": today,
                "is_trading_day": is_trading_day,
                "data_is_current": False,
                "next_sync_needed": None,
            }

            if latest_date:
                # Data is current if we have today's data or today is not a trading day
                if latest_date.date() >= today:
                    status["data_is_current"] = True
                elif is_trading_day:
                    status["next_sync_needed"] = today
                else:
                    # Find next trading day
                    next_day = today + timedelta(days=1)
                    while not self._is_trading_day(next_day):
                        next_day += timedelta(days=1)
                    status["next_sync_needed"] = next_day

            return status

        except Exception as e:
            logger.error(f"Failed to get sync status: {str(e)}")
            return {
                "error": str(e),
                "latest_data_date": None,
                "data_is_current": False,
            }
