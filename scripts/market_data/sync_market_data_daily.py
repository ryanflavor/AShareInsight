#!/usr/bin/env python3
"""Daily market data synchronization script.

This script is designed to be run daily (preferably after market close at 15:30)
to sync the latest A-share market data from akshare.

Can be used with cron:
30 15 * * 1-5 /path/to/python /path/to/sync_market_data_daily.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

from src.domain.services.market_data_sync_service import MarketDataSyncService
from src.infrastructure.market_data.akshare_adapter import AkshareMarketDataAdapter
from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository,
)
from src.shared.utils.logger import get_logger
from src.shared.utils.timezone import now_china

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# Sync status file for monitoring
SYNC_STATUS_FILE = Path(__file__).parent / ".market_data_sync_status.json"


async def sync_market_data_daily(force: bool = False):
    """Perform daily market data synchronization.

    Args:
        force: Force sync even if not a trading day
    """
    sync_start = now_china()
    db_pool = None
    redis_client = None

    try:
        # Database connection settings
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "database": os.getenv("DB_NAME", "ashare_insight"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
        }

        # Redis connection settings
        redis_config = {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379")),
            "password": os.getenv("REDIS_PASSWORD"),
            "decode_responses": False,  # We handle encoding/decoding manually
        }

        # Create connections
        logger.info("Connecting to database and cache...")
        db_pool = await asyncpg.create_pool(**db_config, min_size=2, max_size=10)

        # Connect to Redis if available
        try:
            redis_client = await redis.from_url(
                f"redis://{redis_config['host']}:{redis_config['port']}",
                password=redis_config.get("password"),
                decode_responses=redis_config["decode_responses"],
            )
            await redis_client.ping()
            logger.info("Connected to Redis cache")
        except Exception as e:
            logger.warning(f"Redis not available, proceeding without cache: {e}")
            redis_client = None

        # Initialize components
        adapter = AkshareMarketDataAdapter()
        repository = MarketDataRepository(db_pool, redis_client)
        sync_service = MarketDataSyncService(adapter, repository)

        # Check sync status
        logger.info("Checking sync status...")
        status = await sync_service.get_sync_status()

        logger.info(f"Sync status: {json.dumps(status, default=str, indent=2)}")

        # Force sync if requested
        if force:
            logger.info("Force sync requested, overriding trading day check")

        # Perform sync
        logger.info("Starting market data synchronization...")
        sync_result = await sync_service.sync_daily_market_data()

        # Log results
        logger.info(f"Sync result: {json.dumps(sync_result, default=str, indent=2)}")

        # Calculate sync duration
        sync_duration = (now_china() - sync_start).total_seconds()
        sync_result["duration_seconds"] = sync_duration

        # Save sync status for monitoring
        await save_sync_status(sync_result)

        # Send notification if sync failed
        if sync_result["status"] == "failed":
            logger.error(
                f"Market data sync failed after {sync_result['attempts']} attempts: "
                f"{sync_result['error']}"
            )
            # In production, send alert notification here
            return 1

        return 0

    except Exception as e:
        logger.error(f"Unexpected error during sync: {str(e)}")
        # Save error status
        await save_sync_status(
            {
                "status": "error",
                "error": str(e),
                "sync_timestamp": sync_start,
                "duration_seconds": (now_china() - sync_start).total_seconds(),
            }
        )
        return 1
    finally:
        # Clean up connections
        if db_pool:
            await db_pool.close()
        if redis_client:
            await redis_client.close()


async def save_sync_status(status: dict):
    """Save sync status to file for monitoring.

    Args:
        status: Sync status dictionary
    """
    try:
        # Read existing status history
        history = []
        if SYNC_STATUS_FILE.exists():
            with open(SYNC_STATUS_FILE) as f:
                data = json.load(f)
                history = data.get("history", [])

        # Add new status
        history.append(status)

        # Keep only last 30 days of history
        if len(history) > 30:
            history = history[-30:]

        # Save updated status
        with open(SYNC_STATUS_FILE, "w") as f:
            json.dump(
                {
                    "last_sync": status,
                    "history": history,
                },
                f,
                default=str,
                indent=2,
            )

        logger.info(f"Sync status saved to {SYNC_STATUS_FILE}")

    except Exception as e:
        logger.error(f"Failed to save sync status: {e}")


def check_last_sync_status():
    """Check and display last sync status."""
    if not SYNC_STATUS_FILE.exists():
        print("No sync history found.")
        return

    try:
        with open(SYNC_STATUS_FILE) as f:
            data = json.load(f)
            last_sync = data.get("last_sync", {})

            print("Last sync status:")
            print(f"  Timestamp: {last_sync.get('sync_timestamp', 'Unknown')}")
            print(f"  Status: {last_sync.get('status', 'Unknown')}")
            print(f"  Records: {last_sync.get('records_saved', 0)}")
            print(f"  Duration: {last_sync.get('duration_seconds', 0):.2f}s")

            if last_sync.get("error"):
                print(f"  Error: {last_sync['error']}")

    except Exception as e:
        print(f"Error reading sync status: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Daily market data synchronization from akshare"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force sync even if not a trading day",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check last sync status and exit",
    )
    args = parser.parse_args()

    if args.status:
        check_last_sync_status()
    else:
        # Run sync
        exit_code = asyncio.run(sync_market_data_daily(force=args.force))
        sys.exit(exit_code)
