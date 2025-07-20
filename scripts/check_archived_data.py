#!/usr/bin/env python
"""Check if extraction results have been archived to the database."""

import asyncio
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.shared.config.settings import Settings


async def check_archived_data():
    """Check source_documents table for archived extraction results."""
    settings = Settings()

    try:
        # Connect to database
        conn_str = (
            f"postgresql://{settings.postgres_user}:"
            f"{settings.postgres_password}@"
            f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        )

        async with await psycopg.AsyncConnection.connect(
            conn_str, row_factory=dict_row
        ) as conn:
            async with conn.cursor() as cur:
                # Check if source_documents table exists
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'source_documents'
                    );
                """)
                table_exists = (await cur.fetchone())["exists"]

                if not table_exists:
                    print("❌ source_documents table does not exist!")
                    print("   Run: uv run alembic upgrade head")
                    return

                print("✅ source_documents table exists")

                # Count total documents
                await cur.execute("SELECT COUNT(*) as count FROM source_documents")
                total_count = (await cur.fetchone())["count"]
                print(f"\n📊 Total archived documents: {total_count}")

                if total_count == 0:
                    print("\n❌ No documents have been archived to the database yet!")
                    print(
                        "   The extraction results exist as JSON files but haven't been stored in the database."
                    )
                    print("\n   To archive existing extractions, run:")
                    print(
                        "   uv run python src/interfaces/cli/extract_document.py <file> --output <output>"
                    )
                    return

                # Get breakdown by document type
                await cur.execute("""
                    SELECT doc_type, COUNT(*) as count 
                    FROM source_documents 
                    GROUP BY doc_type
                    ORDER BY doc_type
                """)

                print("\n📁 Documents by type:")
                for row in await cur.fetchall():
                    print(f"   - {row['doc_type']}: {row['count']}")

                # Get breakdown by company
                await cur.execute("""
                    SELECT company_code, COUNT(*) as count 
                    FROM source_documents 
                    GROUP BY company_code
                    ORDER BY count DESC
                    LIMIT 10
                """)

                print("\n🏢 Top companies by document count:")
                for row in await cur.fetchall():
                    print(f"   - {row['company_code']}: {row['count']}")

                # Get recent documents
                await cur.execute("""
                    SELECT doc_id, company_code, doc_type, report_title, created_at
                    FROM source_documents 
                    ORDER BY created_at DESC
                    LIMIT 5
                """)

                print("\n📅 Recent archived documents:")
                for row in await cur.fetchall():
                    print(
                        f"   - {row['company_code']} ({row['doc_type']}): {row['report_title'] or 'No title'}"
                    )
                    print(f"     ID: {row['doc_id']}, Created: {row['created_at']}")

    except psycopg.OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        print("   Make sure the database is running: docker-compose up -d")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_archived_data())
