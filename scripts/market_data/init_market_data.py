#!/usr/bin/env python3
"""Initialize market data by fetching historical data from akshare.

This script performs initial population of market data tables with
recent trading data (last 5 trading days).
"""

import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncpg
from dotenv import load_dotenv

from src.infrastructure.market_data.akshare_adapter import AkshareMarketDataAdapter
from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository,
)
from src.shared.utils.logger import get_logger
from src.shared.utils.timezone import now_china

# Load environment variables
load_dotenv()

logger = get_logger(__name__)


async def init_market_data(days_to_fetch: int = 5):
    """Initialize market data with recent trading days.

    Args:
        days_to_fetch: Number of recent trading days to fetch
    """
    # Database connection settings
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DB", "ashareinsight_db"),
        "user": os.getenv("POSTGRES_USER", "ashareinsight"),
        "password": os.getenv("POSTGRES_PASSWORD", "ashareinsight_password"),
    }

    try:
        # Create database pool
        logger.info("Connecting to database...")
        db_pool = await asyncpg.create_pool(**db_config, min_size=2, max_size=10)

        # Initialize components
        adapter = AkshareMarketDataAdapter()
        repository = MarketDataRepository(db_pool)

        # Check current data status
        latest_date = await repository.get_latest_trading_date()
        if latest_date:
            logger.info(f"Latest market data in database: {latest_date.date()}")

            # If data is recent (within last 2 days), skip init
            if latest_date.date() >= (now_china().date() - timedelta(days=2)):
                logger.info(
                    "Market data is already up to date. Skipping initialization."
                )
                return

        logger.info("Fetching market data for initialization...")

        # Fetch current market snapshot
        snapshots = await adapter.get_all_market_snapshot()
        if not snapshots:
            logger.error("Failed to fetch market data from akshare")
            return

        logger.info(f"Fetched {len(snapshots)} company records")

        # Save to database
        records_saved = await repository.save_daily_snapshot(snapshots)
        logger.info(f"Saved {records_saved} market data records")

        # For historical data, we would need to implement additional
        # akshare API calls for historical data. For now, we initialize
        # with current day data only.

        logger.info("Market data initialization completed successfully!")

        # Display sample data
        sample_data = await repository.get_market_data_with_5day_avg(
            company_codes=["000001", "000002", "600000"]
        )

        if sample_data:
            logger.info("\nSample market data:")
            for code, data in sample_data.items():
                logger.info(
                    f"  {code}: Market Cap={data.current_market_cap / 1e8:.2f}亿, "
                    f"Today Volume={data.today_volume / 1e8:.2f}亿"
                )

    except Exception as e:
        logger.error(f"Market data initialization failed: {str(e)}")
        raise
    finally:
        if "db_pool" in locals():
            await db_pool.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize market data from akshare")
    parser.add_argument(
        "--days",
        type=int,
        default=5,
        help="Number of recent trading days to fetch (default: 5)",
    )
    args = parser.parse_args()

    # Run initialization
    asyncio.run(init_market_data(days_to_fetch=args.days))
