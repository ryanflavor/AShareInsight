#!/usr/bin/env python3
"""Set PostgreSQL session timezone to Asia/Shanghai.

This script updates the PostgreSQL configuration to use China timezone.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from dotenv import load_dotenv

from src.shared.config import settings
from src.shared.utils.timezone import now_china


async def set_database_timezone():
    """Set database timezone configuration."""
    # Create connection
    conn = await asyncpg.connect(settings.database.database_url)

    try:
        print("=== PostgreSQL Timezone Configuration ===")
        print(f"Current time: {now_china()}")
        print()

        # Check current timezone
        current_tz = await conn.fetchval("SHOW timezone;")
        print(f"Current database timezone: {current_tz}")

        # Set timezone to Asia/Shanghai for this session
        await conn.execute("SET TIME ZONE 'Asia/Shanghai';")
        new_tz = await conn.fetchval("SHOW timezone;")
        print(f"Session timezone set to: {new_tz}")

        # Test timestamp display
        print("\n=== Testing Timestamp Display ===")

        # Create test table
        await conn.execute("DROP TABLE IF EXISTS timezone_test;")
        await conn.execute("""
            CREATE TEMP TABLE timezone_test (
                id SERIAL PRIMARY KEY,
                test_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            );
        """)

        # Insert test data
        await conn.execute("""
            INSERT INTO timezone_test (description) VALUES
            ('Test entry created with CURRENT_TIMESTAMP'),
            ('Test entry created with NOW()');
        """)

        # Query with different timezone displays
        results = await conn.fetch("""
            SELECT 
                description,
                test_time as time_stored,
                test_time AT TIME ZONE 'UTC' as time_utc,
                test_time AT TIME ZONE 'Asia/Shanghai' as time_china,
                to_char(test_time AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS') as time_china_formatted
            FROM timezone_test;
        """)

        for row in results:
            print(f"\n{row['description']}:")
            print(f"  Stored (with TZ): {row['time_stored']}")
            print(f"  UTC display: {row['time_utc']}")
            print(f"  China display: {row['time_china']}")
            print(f"  China formatted: {row['time_china_formatted']}")

        # Check existing data
        print("\n=== Checking Existing Data ===")

        # Companies table
        company_result = await conn.fetch("""
            SELECT 
                company_code,
                created_at,
                to_char(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS') as created_at_china
            FROM companies
            LIMIT 3;
        """)

        if company_result:
            print("\nCompanies table:")
            for row in company_result:
                print(
                    f"  {row['company_code']}: {row['created_at']} -> {row['created_at_china']} (China)"
                )

        # Business concepts master table
        concept_result = await conn.fetch("""
            SELECT 
                concept_id,
                created_at,
                to_char(created_at AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS') as created_at_china
            FROM business_concepts_master
            LIMIT 3;
        """)

        if concept_result:
            print("\nBusiness concepts master table:")
            for row in concept_result:
                print(
                    f"  {row['concept_id']}: {row['created_at']} -> {row['created_at_china']} (China)"
                )

        print("\n=== Recommendations ===")
        print("1. PostgreSQL stores TIMESTAMP WITH TIME ZONE in UTC internally")
        print("2. Display conversion happens at query time based on session timezone")
        print("3. To display all times in China timezone, either:")
        print("   a) Set session timezone to 'Asia/Shanghai' (done in connection.py)")
        print("   b) Use AT TIME ZONE 'Asia/Shanghai' in queries")
        print("   c) Format with to_char() for consistent display")

    finally:
        await conn.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(set_database_timezone())
