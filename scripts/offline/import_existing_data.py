#!/usr/bin/env python3
"""
Import existing extracted JSON data into the database for Story 1.3 validation.

This script reads the already-extracted JSON files from Story 1.2 and archives them
into the source_documents table without re-running LLM extraction.
"""

import asyncio
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import structlog

from src.application.use_cases.archive_extraction_result import (
    ArchiveExtractionResultUseCase,
)
from src.infrastructure.persistence.postgres.connection import get_session
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)

logger = structlog.get_logger(__name__)


def extract_year_from_filename(filename: str) -> str:
    """Extract year from filename, defaulting to current year if not found.

    Args:
        filename: The filename to extract year from

    Returns:
        Year as string (e.g. "2024")
    """
    # Try to find 4-digit year patterns that look like actual years
    # Look for years in common patterns: _2024_, 2024年, 20240115
    year_patterns = [
        r"_(\d{4})_",  # _2024_
        r"(\d{4})年",  # 2024年
        r"(\d{4})(?:\d{4})",  # 20240115 (year + date)
        r"[^0-9](\d{4})[^0-9]",  # any 4-digit year surrounded by non-digits
    ]

    for pattern in year_patterns:
        year_match = re.search(pattern, filename)
        if year_match:
            year = year_match.group(1)
            # Validate year is reasonable (between 2020 and current year + 1)
            current_year = date.today().year
            if 2020 <= int(year) <= current_year + 1:
                return year

    # Fallback: try any 4-digit number that could be a year
    all_years = re.findall(r"(\d{4})", filename)
    for year in all_years:
        current_year = date.today().year
        if 2020 <= int(year) <= current_year + 1:
            return year

    # Default to current year if no valid year found
    return str(date.today().year)


async def import_extracted_file(
    file_path: Path, repository: PostgresSourceDocumentRepository
):
    """Import a single extracted JSON file into the database.

    Args:
        file_path: Path to the extracted JSON file
        repository: Repository instance for database operations
    """
    logger.info("importing_file", file=str(file_path))

    try:
        # Read the extracted JSON data
        with open(file_path, encoding="utf-8") as f:
            extracted_data = json.load(f)

        # The extracted data IS the raw LLM output for Story 1.3
        raw_llm_output = extracted_data

        # Extract metadata from the JSON structure
        doc_type = extracted_data.get("document_type", "annual_report")
        extraction_data = extracted_data.get("extraction_data", {})

        # Determine source file based on naming pattern
        # Extract year from filename dynamically
        year = extract_year_from_filename(file_path.name)

        if doc_type == "annual_report":
            source_pattern = file_path.stem.replace("_extracted", "")
            source_file = Path(f"data/annual_reports/{year}") / f"{source_pattern}.md"
        else:
            source_pattern = file_path.stem.replace("_extracted", "")
            source_file = (
                Path(f"data/research_reports/{year}") / f"{source_pattern}.txt"
            )

        # Build metadata for archiving
        # For research reports, use report_title if available
        if doc_type == "research_report":
            report_title = extraction_data.get(
                "report_title",
                extraction_data.get("company_name_short", "Unknown") + "研究报告",
            )
        else:
            report_title = (
                extraction_data.get("company_name_full", "Unknown")
                + f"{year}年年度报告"
            )

        metadata = {
            "company_code": extraction_data.get("company_code", "000000"),
            "doc_type": doc_type,
            "doc_date": f"{year}-12-31"
            if doc_type == "annual_report"
            else f"{year}-01-01",
            "report_title": report_title,
            "file_path": str(source_file),
            "file_hash": hashlib.sha256(
                json.dumps(raw_llm_output, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest(),
        }

        # Use the archive use case to store the data
        archive_use_case = ArchiveExtractionResultUseCase(repository)
        doc_id = await archive_use_case.execute(
            raw_llm_output=raw_llm_output, metadata=metadata
        )

        logger.info(
            "import_success",
            file=str(file_path),
            doc_id=str(doc_id),
            company_code=metadata["company_code"],
        )
        return True

    except Exception as e:
        logger.error("import_failed", file=str(file_path), error=str(e), exc_info=True)
        return False


async def main():
    """Import all extracted JSON files into the database."""
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

    # Find all extracted JSON files
    data_dir = Path("data/extracted")
    annual_reports = list((data_dir / "annual_reports").glob("*_extracted.json"))
    research_reports = list((data_dir / "research_reports").glob("*_extracted.json"))

    all_files = annual_reports + research_reports
    logger.info(
        "found_files",
        annual_reports=len(annual_reports),
        research_reports=len(research_reports),
        total=len(all_files),
    )

    if not all_files:
        logger.warning("no_files_found")
        return

    # Process all files
    success_count = 0
    fail_count = 0

    # Process each file in its own transaction
    for file_path in all_files:
        async with get_session() as session:
            repository = PostgresSourceDocumentRepository(session)
            success = await import_extracted_file(file_path, repository)
            if success:
                success_count += 1
            else:
                fail_count += 1

    # Report results
    logger.info(
        "import_complete",
        total=len(all_files),
        success=success_count,
        failed=fail_count,
    )


if __name__ == "__main__":
    asyncio.run(main())
