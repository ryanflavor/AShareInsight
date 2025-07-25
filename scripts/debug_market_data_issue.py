#!/usr/bin/env python3
"""Debug why market filter returns 0 results."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal

import asyncpg
from dotenv import load_dotenv

from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository
from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository as PostgresMarketDataRepo,
)
from src.infrastructure.persistence.postgres.market_data_repository_adapter import (
    PostgresMarketDataRepositoryAdapter,
)

# Load environment variables
load_dotenv()


async def debug_market_data():
    """Debug market data issue."""
    import os

    # Database connection settings
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DB", "ashareinsight_db"),
        "user": os.getenv("POSTGRES_USER", "ashareinsight"),
        "password": os.getenv("POSTGRES_PASSWORD", "ashareinsight_password"),
    }

    # Create database pool
    db_pool = await asyncpg.create_pool(**db_config, min_size=2, max_size=10)

    try:
        # First, find similar companies for 002240
        vector_store = PostgresVectorStoreRepository()

        from src.domain.value_objects import BusinessConceptQuery

        query = BusinessConceptQuery(
            target_identifier="新光光电", top_k=100, similarity_threshold=0.5
        )

        print("=== Step 1: Vector Search Results ===")
        documents = await vector_store.search_similar_concepts(query)

        # Get unique company codes
        company_codes = list(set(doc.company_code for doc in documents))
        print(f"\nFound {len(documents)} documents from {len(company_codes)} companies")
        print(f"Company codes: {company_codes[:10]}...")  # Show first 10

        # Check which companies have market data
        print("\n=== Step 2: Market Data Check ===")
        postgres_repo = PostgresMarketDataRepo(db_pool)
        market_repo = PostgresMarketDataRepositoryAdapter(postgres_repo)

        market_data = await market_repo.get_market_data(company_codes)
        print(
            f"\nMarket data found for {len(market_data)} out of {len(company_codes)} companies"
        )

        # Show sample market data
        print("\n=== Sample Market Data ===")
        for i, (code, data) in enumerate(market_data.items()):
            if i >= 5:  # Show first 5
                break
            print(
                f"{code}: Market Cap={float(data.market_cap_cny) / 1e8:.2f}亿, "
                f"Volume={float(data.avg_volume_5day) / 1e8:.2f}亿"
            )

        # Check filtering
        print("\n=== Step 3: Filter Application ===")
        max_cap = Decimal("8500000000")  # 85亿
        max_vol = Decimal("200000000")  # 2亿

        filtered_count = 0
        for code, data in market_data.items():
            if data.market_cap_cny <= max_cap and data.avg_volume_5day <= max_vol:
                filtered_count += 1
                if filtered_count <= 5:  # Show first 5 that pass
                    print(
                        f"✅ {code}: Cap={float(data.market_cap_cny) / 1e8:.2f}亿, "
                        f"Vol={float(data.avg_volume_5day) / 1e8:.2f}亿"
                    )

        print(f"\n{filtered_count} companies pass the filters")

        # Check company codes mismatch
        print("\n=== Step 4: Company Code Analysis ===")
        missing_codes = set(company_codes) - set(market_data.keys())
        if missing_codes:
            print(f"Companies without market data: {list(missing_codes)[:10]}...")

            # Check if these exist in market_data_daily
            async with db_pool.acquire() as conn:
                result = await conn.fetch(
                    """
                    SELECT DISTINCT company_code 
                    FROM market_data_daily
                    WHERE company_code = ANY($1)
                    """,
                    list(missing_codes)[:10],
                )
                codes_in_market_table = [r["company_code"] for r in result]
                print(
                    f"Of these, {len(codes_in_market_table)} exist in market_data_daily: {codes_in_market_table}"
                )

    finally:
        await vector_store.close()
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(debug_market_data())
