#!/usr/bin/env python3
"""
Fix missing original_content in database by reading from source files.
"""

import asyncio
import sys
from pathlib import Path

import structlog
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import SourceDocumentModel

logger = structlog.get_logger()


async def fix_missing_original_content():
    """Update missing original_content fields."""

    async with get_session() as session:
        # Find records with missing original_content
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.original_content.is_(None),
            SourceDocumentModel.doc_type == "annual_report",
            SourceDocumentModel.file_path.isnot(None),
        )

        result = await session.execute(stmt)
        records = result.scalars().all()

        logger.info(f"Found {len(records)} records with missing original_content")

        updated = 0
        failed = 0

        for record in records:
            file_path = Path(record.file_path)

            if file_path.exists():
                try:
                    # Read original content
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    # Update record
                    record.original_content = content
                    logger.info(
                        f"Updated original_content for {record.company_code}: {file_path.name}"
                    )
                    updated += 1

                except Exception as e:
                    logger.error(f"Failed to read {file_path}: {e}")
                    failed += 1
            else:
                logger.warning(f"File not found: {file_path}")
                failed += 1

        # Commit changes
        if updated > 0:
            await session.commit()
            logger.info(f"Successfully updated {updated} records")

        if failed > 0:
            logger.warning(f"Failed to update {failed} records")

        # Show final status
        result = await session.execute(
            text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN original_content IS NOT NULL THEN 1 END) as with_content,
                COUNT(CASE WHEN original_content IS NULL THEN 1 END) as without_content
            FROM source_documents
            WHERE doc_type = 'annual_report'
        """)
        )

        row = result.first()
        print("\nFinal Status:")
        print(f"  Total annual reports: {row.total}")
        print(f"  With original_content: {row.with_content}")
        print(f"  Without original_content: {row.without_content}")


if __name__ == "__main__":
    asyncio.run(fix_missing_original_content())
