#!/usr/bin/env python3
"""Check PostgreSQL timezone configuration.

This script connects to the database and checks the current timezone settings.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from dotenv import load_dotenv

from src.shared.config import settings


async def check_timezone():
    """Check PostgreSQL timezone configuration."""
    # Create connection
    conn = await asyncpg.connect(settings.database.database_url)

    try:
        # Check current timezone
        current_tz = await conn.fetchval("SHOW timezone;")
        print(f"Current PostgreSQL timezone: {current_tz}")

        # Check server time
        server_time = await conn.fetchval("SELECT CURRENT_TIMESTAMP;")
        print(f"Current server time: {server_time}")

        # Check server time with timezone
        server_time_tz = await conn.fetchval("SELECT NOW();")
        print(f"Current server time (NOW()): {server_time_tz}")

        # Check time in different timezones
        utc_time = await conn.fetchval("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC';")
        china_time = await conn.fetchval(
            "SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai';"
        )
        print(f"\nTime in UTC: {utc_time}")
        print(f"Time in Asia/Shanghai: {china_time}")

        # Check a sample timestamp from database
        sample_query = """
        SELECT company_code, created_at, 
               created_at AT TIME ZONE 'Asia/Shanghai' as created_at_china
        FROM companies
        LIMIT 1;
        """
        result = await conn.fetchrow(sample_query)
        if result:
            print("\nSample data from companies table:")
            print(f"Company: {result['company_code']}")
            print(f"Created at (stored): {result['created_at']}")
            print(f"Created at (China TZ): {result['created_at_china']}")

    finally:
        await conn.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(check_timezone())
