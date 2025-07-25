#!/usr/bin/env python3
"""Set database timezone to Asia/Shanghai permanently.

This script changes the database's default timezone setting.
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


async def set_permanent_timezone():
    """Set database timezone permanently."""
    # Connect to database
    conn = await asyncpg.connect(settings.database.database_url)

    try:
        print("=== Setting Database Timezone to Asia/Shanghai ===")
        print(f"Current time: {now_china()}")

        # Check current database timezone
        current_tz = await conn.fetchval("""
            SELECT current_setting('TIMEZONE');
        """)
        print(f"\nCurrent database timezone: {current_tz}")

        # Set database timezone permanently
        print("\nSetting database timezone to Asia/Shanghai...")
        await conn.execute("""
            ALTER DATABASE ashareinsight_db SET timezone TO 'Asia/Shanghai';
        """)

        print("✓ Database timezone setting updated!")
        print(
            "\nNote: You need to reconnect to the database for this change to take effect."
        )
        print("New connections will use Asia/Shanghai timezone by default.")

        # Test with new connection
        print("\nTesting with new connection...")
        conn2 = await asyncpg.connect(settings.database.database_url)
        try:
            new_tz = await conn2.fetchval("SHOW timezone;")
            print(f"New connection timezone: {new_tz}")

            # Test timestamp display
            result = await conn2.fetchrow("""
                SELECT 
                    NOW() as current_time,
                    NOW()::text as current_time_text
            """)
            print(f"Current time: {result['current_time']}")
            print(f"Current time (text): {result['current_time_text']}")

        finally:
            await conn2.close()

        return True

    except Exception as e:
        print(f"\n✗ Failed to set timezone: {e}")
        return False

    finally:
        await conn.close()


async def main():
    """Main function."""
    load_dotenv()

    print("This will permanently change the database timezone to Asia/Shanghai.")
    print("All new connections will use this timezone by default.")

    if "--yes" not in sys.argv:
        response = input("\nProceed? (yes/no): ")
        if response.lower() != "yes":
            print("Cancelled.")
            return False

    return await set_permanent_timezone()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
