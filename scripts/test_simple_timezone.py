#!/usr/bin/env python3
"""Simple test to check timezone handling in PostgreSQL."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from dotenv import load_dotenv

from src.shared.config import settings
from src.shared.utils.timezone import to_china_tz


async def test_simple_timezone():
    """Test simple timezone handling."""
    # Test direct asyncpg connection
    conn = await asyncpg.connect(settings.database.database_url)

    try:
        # Set session timezone
        await conn.execute("SET TIME ZONE 'Asia/Shanghai';")

        # Check what PostgreSQL returns
        print("=== Direct asyncpg Test ===")

        # Get current timezone
        tz = await conn.fetchval("SHOW timezone;")
        print(f"Session timezone: {tz}")

        # Get a timestamp from database
        result = await conn.fetchrow("""
            SELECT 
                created_at,
                created_at::text as created_at_text,
                created_at AT TIME ZONE 'Asia/Shanghai' as created_at_china,
                to_char(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS TZ') as created_at_formatted
            FROM companies
            LIMIT 1;
        """)

        print(f"\nRaw timestamp from DB: {result['created_at']}")
        print(f"As text: {result['created_at_text']}")
        print(f"AT TIME ZONE 'Asia/Shanghai': {result['created_at_china']}")
        print(f"Formatted: {result['created_at_formatted']}")

        # Test Python conversion
        print(f"\nPython to_china_tz(): {to_china_tz(result['created_at'])}")

    finally:
        await conn.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(test_simple_timezone())
