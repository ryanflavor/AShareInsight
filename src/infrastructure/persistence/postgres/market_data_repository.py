"""PostgreSQL market data repository implementation."""

import json
from datetime import datetime, timedelta
from decimal import Decimal

import redis
from asyncpg import Pool
from pydantic import BaseModel, Field

from src.infrastructure.market_data.akshare_adapter import MarketSnapshot
from src.shared.utils.logger import get_logger
from src.shared.utils.timezone import now_china

logger = get_logger(__name__)


class MarketDataWithAverage(BaseModel):
    """Market data with 5-day average volume."""

    company_code: str = Field(..., description="Stock code")
    current_market_cap: Decimal = Field(..., description="Current market cap in CNY")
    current_circulating_cap: Decimal = Field(
        ..., description="Current circulating market cap in CNY"
    )
    today_volume: Decimal = Field(..., description="Today's turnover amount in CNY")
    avg_5day_volume: Decimal = Field(
        ..., description="5-day average turnover amount in CNY"
    )
    last_updated: datetime = Field(..., description="Last update timestamp")


class MarketDataRepository:
    """Repository for market data persistence and retrieval."""

    def __init__(self, db_pool: Pool, redis_client: redis.Redis | None = None):
        """Initialize repository with database pool and optional Redis cache.

        Args:
            db_pool: AsyncPG connection pool
            redis_client: Redis client for caching (optional)
        """
        self.db_pool = db_pool
        self.redis_client = redis_client
        self.cache_ttl = 3600  # 1 hour cache TTL

    async def save_daily_snapshot(self, snapshots: list[MarketSnapshot]) -> int:
        """Save daily market data snapshots.

        Args:
            snapshots: List of market snapshots to save

        Returns:
            Number of records saved

        Raises:
            Exception: If database operation fails
        """
        if not snapshots:
            logger.warning("No snapshots to save")
            return 0

        try:
            async with self.db_pool.acquire() as conn:
                # First, get existing company codes
                existing_codes = await conn.fetch("SELECT company_code FROM companies")
                existing_codes_set = {row["company_code"] for row in existing_codes}

                # Filter snapshots to only include existing companies
                valid_snapshots = [
                    s for s in snapshots if s.company_code in existing_codes_set
                ]

                logger.info(
                    f"Filtered {len(snapshots)} snapshots to {len(valid_snapshots)} "
                    f"valid companies"
                )

                if not valid_snapshots:
                    logger.warning("No valid snapshots to save after filtering")
                    return 0

                # Prepare data for bulk insert
                values = [
                    (
                        s.company_code,
                        s.trading_date.date(),
                        s.total_market_cap,
                        s.circulating_market_cap,
                        s.turnover_amount,
                    )
                    for s in valid_snapshots
                ]

                # Use COPY for efficient bulk insert
                result = await conn.executemany(
                    """
                    INSERT INTO market_data_daily 
                    (company_code, trading_date, total_market_cap, 
                     circulating_market_cap, turnover_amount)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (company_code, trading_date) 
                    DO UPDATE SET
                        total_market_cap = EXCLUDED.total_market_cap,
                        circulating_market_cap = EXCLUDED.circulating_market_cap,
                        turnover_amount = EXCLUDED.turnover_amount,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    values,
                )

                # Extract number of affected rows
                affected_rows = int(result.split()[-1]) if result else len(values)

                # Invalidate cache after update
                if self.redis_client:
                    await self._invalidate_cache()

                logger.info(f"Saved {affected_rows} market data records")
                return affected_rows

        except Exception as e:
            logger.error(f"Failed to save market snapshots: {str(e)}")
            raise

    async def get_market_data_with_5day_avg(
        self, company_codes: list[str] | None = None
    ) -> dict[str, MarketDataWithAverage]:
        """Get current market data with 5-day average volume.

        Args:
            company_codes: Optional list of company codes to filter

        Returns:
            Dictionary mapping company code to market data with averages
        """
        # Try cache first
        cache_key = self._get_cache_key(company_codes)
        if self.redis_client:
            cached_data = await self._get_from_cache(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for market data: {len(cached_data)} companies")
                return cached_data

        try:
            async with self.db_pool.acquire() as conn:
                # Build query
                query = "SELECT * FROM market_data_current"
                params = []

                if company_codes:
                    placeholders = [f"${i + 1}" for i in range(len(company_codes))]
                    query += f" WHERE company_code IN ({', '.join(placeholders)})"
                    params = company_codes

                # Execute query
                rows = await conn.fetch(query, *params)

                # Convert to dictionary
                result = {}
                for row in rows:
                    market_data = MarketDataWithAverage(
                        company_code=row["company_code"],
                        current_market_cap=Decimal(str(row["current_market_cap"])),
                        current_circulating_cap=Decimal(
                            str(row["current_circulating_cap"])
                        ),
                        today_volume=Decimal(str(row["today_volume"])),
                        avg_5day_volume=Decimal(str(row["avg_5day_volume"])),
                        last_updated=row["last_updated"],
                    )
                    result[row["company_code"]] = market_data

                # Cache the result
                if self.redis_client and result:
                    await self._set_cache(cache_key, result)

                logger.info(f"Retrieved market data for {len(result)} companies")
                return result

        except Exception as e:
            logger.error(f"Failed to retrieve market data: {str(e)}")
            return {}

    async def cleanup_old_data(self, days_to_keep: int = 30) -> int:
        """Clean up market data older than specified days.

        Args:
            days_to_keep: Number of days of data to retain

        Returns:
            Number of records deleted
        """
        try:
            cutoff_date = now_china().date() - timedelta(days=days_to_keep)

            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM market_data_daily WHERE trading_date < $1",
                    cutoff_date,
                )

                deleted_count = int(result.split()[-1]) if result else 0
                logger.info(f"Cleaned up {deleted_count} old market data records")
                return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old data: {str(e)}")
            return 0

    async def get_latest_trading_date(self) -> datetime | None:
        """Get the latest trading date in the database.

        Returns:
            Latest trading date or None if no data exists
        """
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT MAX(trading_date) as max_date FROM market_data_daily"
                )
                if row and row["max_date"]:
                    return datetime.combine(row["max_date"], datetime.min.time())
                return None

        except Exception as e:
            logger.error(f"Failed to get latest trading date: {str(e)}")
            return None

    def _get_cache_key(self, company_codes: list[str] | None = None) -> str:
        """Generate cache key for market data.

        Args:
            company_codes: Optional list of company codes

        Returns:
            Cache key string
        """
        if company_codes:
            codes_hash = hash(tuple(sorted(company_codes)))
            return f"market_data:filtered:{codes_hash}"
        return "market_data:all"

    async def _get_from_cache(
        self, cache_key: str
    ) -> dict[str, MarketDataWithAverage] | None:
        """Get data from Redis cache.

        Args:
            cache_key: Cache key

        Returns:
            Cached data or None if not found
        """
        try:
            data = await self.redis_client.get(cache_key)
            if data:
                # Deserialize JSON data
                json_data = json.loads(data)
                result = {}
                for code, market_data in json_data.items():
                    # Convert string decimals back to Decimal
                    market_data["current_market_cap"] = Decimal(
                        market_data["current_market_cap"]
                    )
                    market_data["current_circulating_cap"] = Decimal(
                        market_data["current_circulating_cap"]
                    )
                    market_data["today_volume"] = Decimal(market_data["today_volume"])
                    market_data["avg_5day_volume"] = Decimal(
                        market_data["avg_5day_volume"]
                    )
                    market_data["last_updated"] = datetime.fromisoformat(
                        market_data["last_updated"]
                    )
                    result[code] = MarketDataWithAverage(**market_data)
                return result
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {str(e)}")
        return None

    async def _set_cache(
        self, cache_key: str, data: dict[str, MarketDataWithAverage]
    ) -> None:
        """Set data in Redis cache.

        Args:
            cache_key: Cache key
            data: Data to cache
        """
        try:
            # Serialize data to JSON
            json_data = {}
            for code, market_data in data.items():
                json_data[code] = {
                    "company_code": market_data.company_code,
                    "current_market_cap": str(market_data.current_market_cap),
                    "current_circulating_cap": str(market_data.current_circulating_cap),
                    "today_volume": str(market_data.today_volume),
                    "avg_5day_volume": str(market_data.avg_5day_volume),
                    "last_updated": market_data.last_updated.isoformat(),
                }

            await self.redis_client.setex(
                cache_key, self.cache_ttl, json.dumps(json_data)
            )
        except Exception as e:
            logger.warning(f"Cache set failed: {str(e)}")

    async def _invalidate_cache(self) -> None:
        """Invalidate all market data cache entries."""
        try:
            # Use pattern to delete all market data cache keys
            pattern = "market_data:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis_client.scan(
                    cursor, match=pattern, count=100
                )
                if keys:
                    await self.redis_client.delete(*keys)
                if cursor == 0:
                    break
            logger.debug("Invalidated market data cache")
        except Exception as e:
            logger.warning(f"Cache invalidation failed: {str(e)}")
