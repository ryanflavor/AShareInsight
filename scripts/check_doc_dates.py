#!/usr/bin/env python3
"""Script to check doc_date values in the database."""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from src.infrastructure.persistence.postgres.models import SourceDocumentModel

# Load environment variables
load_dotenv()

# Database connection
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'ashareinsight')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'ashareinsight_password')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'ashareinsight_db')}"
)

engine = create_engine(DATABASE_URL)


def check_doc_dates():
    """Check for potentially incorrect doc_date values."""
    with Session(engine) as session:
        # Get total count
        total_count = session.query(func.count(SourceDocumentModel.doc_id)).scalar()
        print(f"\nTotal documents in database: {total_count}")

        # Get date range
        min_date = session.query(func.min(SourceDocumentModel.doc_date)).scalar()
        max_date = session.query(func.max(SourceDocumentModel.doc_date)).scalar()
        print(f"Date range: {min_date} to {max_date}")

        # Check for future dates
        today = datetime.now().date()
        future_docs = (
            session.query(SourceDocumentModel)
            .filter(SourceDocumentModel.doc_date > today)
            .all()
        )

        if future_docs:
            print(f"\n⚠️  Found {len(future_docs)} documents with future dates:")
            for doc in future_docs[:10]:  # Show first 10
                print(
                    f"  - {doc.company_code}: {doc.doc_date} ({doc.doc_type}) - {doc.report_title}"
                )

        # Check for very old dates (before 2000)
        old_date_threshold = datetime(2000, 1, 1).date()
        old_docs = (
            session.query(SourceDocumentModel)
            .filter(SourceDocumentModel.doc_date < old_date_threshold)
            .all()
        )

        if old_docs:
            print(f"\n⚠️  Found {len(old_docs)} documents with dates before 2000:")
            for doc in old_docs[:10]:  # Show first 10
                print(
                    f"  - {doc.company_code}: {doc.doc_date} ({doc.doc_type}) - {doc.report_title}"
                )

        # Check for common problematic patterns
        # Pattern 1: Default dates (1970-01-01, 1900-01-01)
        default_dates = [
            datetime(1970, 1, 1).date(),
            datetime(1900, 1, 1).date(),
        ]

        for default_date in default_dates:
            count = (
                session.query(func.count(SourceDocumentModel.doc_id))
                .filter(SourceDocumentModel.doc_date == default_date)
                .scalar()
            )
            if count > 0:
                print(f"\n⚠️  Found {count} documents with default date {default_date}")

        # Group by year to see distribution
        print("\n\nDocuments by year:")
        year_counts = (
            session.query(
                func.extract("year", SourceDocumentModel.doc_date).label("year"),
                func.count(SourceDocumentModel.doc_id).label("count"),
            )
            .group_by(func.extract("year", SourceDocumentModel.doc_date))
            .order_by("year")
            .all()
        )

        for year, count in year_counts:
            print(f"  {int(year)}: {count} documents")

        # Show sample of recent documents
        print("\n\nSample of recent documents:")
        recent_docs = (
            session.query(SourceDocumentModel)
            .order_by(SourceDocumentModel.doc_date.desc())
            .limit(10)
            .all()
        )

        for doc in recent_docs:
            print(
                f"  - {doc.company_code}: {doc.doc_date} ({doc.doc_type}) - {doc.report_title}"
            )

        # Check for dates that don't match expected patterns in file names
        print("\n\nChecking for date mismatches in file paths:")
        all_docs = (
            session.query(SourceDocumentModel)
            .filter(SourceDocumentModel.file_path.isnot(None))
            .limit(100)
            .all()
        )

        mismatches = []
        for doc in all_docs:
            if doc.file_path:
                # Extract potential dates from file path
                import re

                date_patterns = [
                    r"(\d{4})年",  # Chinese year format
                    r"(\d{8})",  # YYYYMMDD format
                    r"(\d{4})[_-](\d{1,2})[_-](\d{1,2})",  # YYYY-MM-DD or YYYY_MM_DD
                ]

                found_date = None
                for pattern in date_patterns:
                    match = re.search(pattern, doc.file_path)
                    if match:
                        if pattern == r"(\d{4})年":
                            year = int(match.group(1))
                            # For annual reports, assume end of year
                            found_date = f"{year}-12-31"
                        elif pattern == r"(\d{8})":
                            date_str = match.group(1)
                            try:
                                found_date = (
                                    f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                                )
                            except:
                                continue
                        break

                if found_date and str(doc.doc_date) != found_date:
                    mismatches.append(
                        {
                            "doc_id": doc.doc_id,
                            "company_code": doc.company_code,
                            "db_date": doc.doc_date,
                            "file_date": found_date,
                            "file_path": doc.file_path,
                        }
                    )

        if mismatches:
            print(f"Found {len(mismatches)} potential date mismatches:")
            for m in mismatches[:10]:  # Show first 10
                print(
                    f"  - {m['company_code']}: DB={m['db_date']}, File suggests={m['file_date']}"
                )
                print(f"    File: {m['file_path']}")


if __name__ == "__main__":
    check_doc_dates()
