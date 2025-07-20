#!/usr/bin/env python3
"""
Verify that extracted data has been properly archived in the database.

This script checks if the real extraction results from Story 1.2 have been
successfully stored in the source_documents table as per Story 1.3 requirements.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from sqlalchemy import func, select

from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.models import SourceDocumentModel

logger = structlog.get_logger(__name__)


async def verify_archive_data():
    """Verify archived data in the database."""

    async with get_session() as session:
        # Count total documents
        count_stmt = select(func.count()).select_from(SourceDocumentModel)
        result = await session.execute(count_stmt)
        total_count = result.scalar()

        logger.info("total_documents_archived", count=total_count)

        # Get document types distribution
        type_stmt = select(
            SourceDocumentModel.doc_type,
            func.count(SourceDocumentModel.doc_id).label("count"),
        ).group_by(SourceDocumentModel.doc_type)

        result = await session.execute(type_stmt)
        type_distribution = result.all()

        for doc_type, count in type_distribution:
            logger.info("document_type_count", type=doc_type, count=count)

        # Sample some documents to verify content
        sample_stmt = select(SourceDocumentModel).limit(5)
        result = await session.execute(sample_stmt)
        samples = result.scalars().all()

        for doc in samples:
            logger.info(
                "sample_document",
                doc_id=str(doc.doc_id),
                company_code=doc.company_code,
                doc_type=doc.doc_type,
                report_title=doc.report_title,
                has_raw_output=bool(doc.raw_llm_output),
                raw_output_size=len(json.dumps(doc.raw_llm_output))
                if doc.raw_llm_output
                else 0,
            )

        # Verify specific companies from our test data
        test_companies = ["300257", "300663", "002747", "688488"]
        for company_code in test_companies:
            stmt = select(SourceDocumentModel).where(
                SourceDocumentModel.company_code == company_code
            )
            result = await session.execute(stmt)
            docs = result.scalars().all()

            if docs:
                logger.info(
                    "company_documents_found",
                    company_code=company_code,
                    count=len(docs),
                    types=[d.doc_type for d in docs],
                )
            else:
                logger.warning("company_not_found", company_code=company_code)

        return total_count


async def compare_with_source_files():
    """Compare archived data with source extracted files."""

    # Count source files
    data_dir = Path("data/extracted")
    annual_reports = list((data_dir / "annual_reports").glob("*_extracted.json"))
    research_reports = list((data_dir / "research_reports").glob("*_extracted.json"))

    total_source_files = len(annual_reports) + len(research_reports)

    logger.info(
        "source_files_count",
        annual_reports=len(annual_reports),
        research_reports=len(research_reports),
        total=total_source_files,
    )

    # Get archived count
    archived_count = await verify_archive_data()

    # Compare
    if archived_count == total_source_files:
        logger.info(
            "verification_passed", message="All extracted files have been archived"
        )
    else:
        logger.warning(
            "verification_mismatch",
            source_files=total_source_files,
            archived=archived_count,
            missing=total_source_files - archived_count,
        )


async def main():
    """Main verification process."""
    # Configure logging
    import logging

    logging.basicConfig(level=logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logger.info("Starting archive data verification")

    try:
        await compare_with_source_files()
        logger.info("Verification complete")
    except Exception as e:
        logger.error("Verification failed", error=str(e), exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
