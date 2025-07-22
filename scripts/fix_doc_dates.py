#!/usr/bin/env python3
"""Script to fix incorrect doc_date values in the database."""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from sqlalchemy import create_engine
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


def fix_year_errors(session: Session, dry_run: bool = True):
    """Fix documents with incorrect year (0021, 0025, 0029)."""
    print("\n=== Fixing year errors ===")

    # Find documents with year < 1000 (clearly wrong)
    wrong_year_docs = (
        session.query(SourceDocumentModel)
        .filter(SourceDocumentModel.doc_date < datetime(1000, 1, 1).date())
        .all()
    )

    fixes = []
    for doc in wrong_year_docs:
        old_date = doc.doc_date
        year = old_date.year

        # Try to extract year from file path
        new_year = None

        if doc.file_path:
            # Look for year in file path (e.g., "data/research_reports/2024/...")
            year_match = re.search(r"/(\d{4})/", doc.file_path)
            if year_match:
                new_year = int(year_match.group(1))
            else:
                # Try to find YYYYMMDD pattern
                date_match = re.search(r"(\d{8})", doc.file_path)
                if date_match:
                    date_str = date_match.group(1)
                    new_year = int(date_str[:4])

        # If we couldn't find year from file path, use a reasonable default
        if not new_year:
            # For years < 100, assume it's 20XX
            if year < 100:
                new_year = 2000 + year
            else:
                continue  # Skip if we can't determine the correct year

        new_date = old_date.replace(year=new_year)

        fixes.append(
            {
                "doc_id": doc.doc_id,
                "company_code": doc.company_code,
                "old_date": old_date,
                "new_date": new_date,
                "report_title": doc.report_title,
                "file_path": doc.file_path,
            }
        )

        if not dry_run:
            doc.doc_date = new_date

    print(f"Found {len(fixes)} documents with year errors:")
    for fix in fixes:
        print(f"  - {fix['company_code']}: {fix['old_date']} → {fix['new_date']}")
        print(f"    {fix['report_title']}")
        if "file_path" in fix and fix["file_path"]:
            print(f"    File: {fix['file_path']}")

    if not dry_run and fixes:
        session.commit()
        print(f"\n✅ Fixed {len(fixes)} year errors")

    return fixes


def fix_date_from_filename(session: Session, dry_run: bool = True):
    """Fix dates based on filenames for research reports."""
    print("\n=== Fixing dates from filenames ===")

    # Get all documents with file paths
    docs_with_paths = (
        session.query(SourceDocumentModel)
        .filter(SourceDocumentModel.file_path.isnot(None))
        .all()
    )

    fixes = []
    date_pattern = re.compile(r"(\d{8})")  # YYYYMMDD format

    for doc in docs_with_paths:
        if not doc.file_path:
            continue

        # Extract date from filename
        match = date_pattern.search(doc.file_path)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d").date()

                # Only fix if dates are different
                if doc.doc_date != file_date:
                    fixes.append(
                        {
                            "doc_id": doc.doc_id,
                            "company_code": doc.company_code,
                            "old_date": doc.doc_date,
                            "new_date": file_date,
                            "file_path": doc.file_path,
                        }
                    )

                    if not dry_run:
                        doc.doc_date = file_date
            except ValueError:
                # Invalid date format, skip
                continue

    print(f"Found {len(fixes)} documents with filename date mismatches:")
    for fix in fixes[:10]:  # Show first 10
        print(f"  - {fix['company_code']}: {fix['old_date']} → {fix['new_date']}")
        print(f"    File: {fix['file_path']}")

    if len(fixes) > 10:
        print(f"  ... and {len(fixes) - 10} more")

    if not dry_run and fixes:
        session.commit()
        print(f"\n✅ Fixed {len(fixes)} dates from filenames")

    return fixes


def main():
    """Main function to fix doc_date issues."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix incorrect doc_date values")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be fixed without making changes (default: True)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually apply the fixes to the database"
    )
    args = parser.parse_args()

    dry_run = not args.apply

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    else:
        print("⚠️  APPLY MODE - Changes will be written to database")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

    with Session(engine) as session:
        # Fix year errors first
        year_fixes = fix_year_errors(session, dry_run)

        # Then fix dates from filenames
        filename_fixes = fix_date_from_filename(session, dry_run)

        # Summary
        print("\n=== Summary ===")
        print(f"Year errors to fix: {len(year_fixes)}")
        print(f"Filename date mismatches to fix: {len(filename_fixes)}")

        if dry_run:
            print("\nTo apply these fixes, run:")
            print("  uv run python scripts/fix_doc_dates.py --apply")


if __name__ == "__main__":
    main()
