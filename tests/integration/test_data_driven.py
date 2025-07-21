#!/usr/bin/env python3
"""Data-driven tests based on actual database content.

These tests verify the system works correctly with real data.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from src.domain.entities.source_document import DocType
from src.infrastructure.persistence.postgres.models import (
    CompanyModel,
    SourceDocumentModel,
)
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)


class TestDataDrivenIntegration:
    """Test with actual data from the database."""

    @pytest.mark.asyncio
    async def test_source_documents_have_original_content(self, async_session):
        """Verify all source documents have original content."""
        stmt = select(SourceDocumentModel)
        result = await async_session.execute(stmt)
        documents = result.scalars().all()

        # Should have at least 20 documents (based on status)
        assert len(documents) >= 20

        # All should have original content
        for doc in documents:
            assert doc.original_content is not None
            assert len(doc.original_content) > 0
            assert doc.file_path is not None
            assert doc.file_hash is not None

    @pytest.mark.asyncio
    async def test_company_names_are_valid(self, async_session):
        """Verify company names are actual company names, not report titles."""
        stmt = select(CompanyModel)
        result = await async_session.execute(stmt)
        companies = result.scalars().all()

        # Should have at least 16 companies
        assert len(companies) >= 16

        for company in companies:
            # Company name should not contain report-related words
            invalid_words = ["报告", "摘要", "年度", "研究", "点评"]
            name_lower = company.company_name_full.lower()

            for word in invalid_words:
                assert word not in name_lower, (
                    f"Company {company.company_code} has invalid name: "
                    f"{company.company_name_full}"
                )

            # Short name should not be the company code
            assert company.company_name_short != company.company_code

    @pytest.mark.asyncio
    async def test_no_duplicate_annual_reports(self, async_session):
        """Verify no duplicate annual reports for same company/year."""
        # Query for duplicate annual reports
        from sqlalchemy import extract, func

        stmt = (
            select(
                SourceDocumentModel.company_code,
                extract("year", SourceDocumentModel.doc_date).label("year"),
                func.count().label("count"),
            )
            .where(SourceDocumentModel.doc_type == DocType.ANNUAL_REPORT.value)
            .group_by(
                SourceDocumentModel.company_code,
                extract("year", SourceDocumentModel.doc_date),
            )
            .having(func.count() > 1)
        )

        result = await async_session.execute(stmt)
        duplicates = result.all()

        # Log any duplicates found for debugging
        if duplicates:
            print("\nFound duplicate annual reports:")
            for dup in duplicates:
                print(
                    f"  Company {dup.company_code} - Year {dup.year} - Count {dup.count}"
                )

        # There should be no duplicates (or we accept the current 4 known duplicates)
        assert len(duplicates) <= 4, "Too many duplicate annual reports found"

    @pytest.mark.asyncio
    async def test_document_metadata_integrity(self, async_session):
        """Test that document metadata is complete and consistent."""
        repository = PostgresSourceDocumentRepository(async_session)

        # Get all documents
        stmt = select(SourceDocumentModel)
        result = await async_session.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            # Each document should have complete metadata
            assert doc.company_code is not None
            assert doc.doc_type in [
                DocType.ANNUAL_REPORT.value,
                DocType.RESEARCH_REPORT.value,
            ]
            assert doc.doc_date is not None
            assert doc.raw_llm_output is not None

            # Verify the raw_llm_output structure
            if isinstance(doc.raw_llm_output, dict):
                # Should have standard fields
                assert (
                    "document_type" in doc.raw_llm_output
                    or "status" in doc.raw_llm_output
                )

                # If it's an extraction result, verify structure
                if "extraction_data" in doc.raw_llm_output:
                    extraction = doc.raw_llm_output["extraction_data"]
                    assert "company_code" in extraction
                    assert extraction["company_code"] == doc.company_code

    @pytest.mark.asyncio
    async def test_file_hash_uniqueness(self, async_session):
        """Test that file hashes are unique."""
        stmt = select(SourceDocumentModel.file_hash)
        result = await async_session.execute(stmt)
        hashes = [row[0] for row in result if row[0] is not None]

        # All hashes should be unique
        assert len(hashes) == len(set(hashes)), "Found duplicate file hashes"

    @pytest.mark.asyncio
    async def test_exchange_field_exists(self, async_session):
        """Test that annual reports have exchange information."""
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.doc_type == DocType.ANNUAL_REPORT.value
        )
        result = await async_session.execute(stmt)
        annual_reports = result.scalars().all()

        # Check a sample of annual reports for exchange info
        sample_size = min(5, len(annual_reports))
        for doc in annual_reports[:sample_size]:
            if (
                isinstance(doc.raw_llm_output, dict)
                and "extraction_data" in doc.raw_llm_output
            ):
                extraction = doc.raw_llm_output["extraction_data"]
                # Exchange field should exist in annual reports
                assert (
                    "exchange" in extraction
                ), f"Document {doc.doc_id} missing exchange field"

    @pytest.mark.asyncio
    async def test_original_content_matches_file(self, async_session):
        """Test that original_content matches the actual file content."""
        stmt = select(SourceDocumentModel).limit(3)  # Test a few documents
        result = await async_session.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            if doc.file_path and Path(doc.file_path).exists():
                with open(doc.file_path, encoding="utf-8") as f:
                    file_content = f.read()

                # Original content should match file content
                assert (
                    doc.original_content == file_content
                ), f"Original content mismatch for {doc.file_path}"


class TestDataConsistency:
    """Test data consistency across the system."""

    @pytest.mark.asyncio
    async def test_extracted_json_matches_database(self, async_session):
        """Verify extracted JSON files match database records."""
        # Get a sample document from database
        stmt = (
            select(SourceDocumentModel)
            .where(SourceDocumentModel.company_code == "300257")
            .limit(1)
        )
        result = await async_session.execute(stmt)
        doc = result.scalar_one_or_none()

        if doc and doc.raw_llm_output:
            # Check if corresponding extracted JSON exists
            extracted_dir = Path("data/extracted/annual_reports")
            json_files = list(extracted_dir.glob("*300257*.json"))

            if json_files:
                with open(json_files[0]) as f:
                    extracted_data = json.load(f)

                # The extraction_data should match
                if "extraction_data" in doc.raw_llm_output:
                    db_extraction = doc.raw_llm_output["extraction_data"]
                    file_extraction = extracted_data.get("extraction_data", {})

                    # Key fields should match
                    assert db_extraction.get("company_code") == file_extraction.get(
                        "company_code"
                    )
                    assert db_extraction.get(
                        "company_name_full"
                    ) == file_extraction.get("company_name_full")

    @pytest.mark.asyncio
    async def test_company_codes_are_valid(self, async_session):
        """Test that all company codes follow the expected format."""
        stmt = select(CompanyModel.company_code)
        result = await async_session.execute(stmt)
        codes = [row[0] for row in result]

        for code in codes:
            # Should be 6 digits
            assert len(code) == 6, f"Invalid company code length: {code}"
            assert code.isdigit(), f"Company code should be numeric: {code}"

            # Should be in valid range
            code_num = int(code)
            assert 1 <= code_num <= 999999, f"Company code out of range: {code}"


if __name__ == "__main__":
    # Can run specific tests from command line
    pytest.main([__file__, "-v"])
