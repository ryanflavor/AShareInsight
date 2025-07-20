"""Unit tests for SourceDocument entity."""

from datetime import date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.entities.extraction import DocumentType as DocType
from src.domain.entities.source_document import SourceDocument, SourceDocumentMetadata


class TestSourceDocument:
    """Test cases for SourceDocument entity."""

    def test_create_valid_source_document(self):
        """Test creating a valid SourceDocument."""
        doc_id = uuid4()
        doc_date = date(2024, 12, 31)
        created_at = datetime.now()

        doc = SourceDocument(
            doc_id=doc_id,
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=doc_date,
            report_title="开山集团股份有限公司2024年年度报告",
            file_path="data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
            file_hash="a" * 64,  # Valid SHA-256 hash
            raw_llm_output={"status": "success", "data": {"test": "value"}},
            extraction_metadata={"model": "gemini-2.5-pro", "tokens": 1000},
            processing_status="completed",
            created_at=created_at,
        )

        assert doc.doc_id == doc_id
        assert doc.company_code == "300257"
        assert doc.doc_type == DocType.ANNUAL_REPORT
        assert doc.doc_date == doc_date
        assert doc.report_title == "开山集团股份有限公司2024年年度报告"
        assert doc.file_hash == "a" * 64
        assert doc.raw_llm_output["status"] == "success"
        assert doc.processing_status == "completed"
        assert doc.error_message is None
        assert doc.created_at == created_at

    def test_create_minimal_source_document(self):
        """Test creating a SourceDocument with minimal required fields."""
        doc = SourceDocument(
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=date(2024, 12, 31),
            raw_llm_output={"data": "test"},
        )

        assert doc.doc_id is None
        assert doc.company_code == "300257"
        assert doc.doc_type == DocType.ANNUAL_REPORT
        assert doc.report_title is None
        assert doc.file_path is None
        assert doc.file_hash is None
        assert doc.processing_status == "completed"
        assert doc.extraction_metadata is None

    def test_invalid_company_code_too_long(self):
        """Test that company code longer than 10 chars raises validation error."""
        with pytest.raises(ValidationError) as excinfo:
            SourceDocument(
                company_code="12345678901",  # 11 chars, too long
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                raw_llm_output={"data": "test"},
            )

        assert "String should have at most 10 characters" in str(excinfo.value)

    def test_invalid_company_code_empty(self):
        """Test that empty company code raises validation error."""
        with pytest.raises(ValidationError) as excinfo:
            SourceDocument(
                company_code="",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                raw_llm_output={"data": "test"},
            )

        assert "Company code must be between 1 and 10 characters" in str(excinfo.value)

    def test_invalid_file_hash_format(self):
        """Test that invalid SHA-256 hash format raises validation error."""
        with pytest.raises(ValidationError) as excinfo:
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                file_hash="invalid_hash",  # Not 64 hex chars
                raw_llm_output={"data": "test"},
            )

        assert "File hash must be a valid SHA-256 hash" in str(excinfo.value)

    def test_invalid_file_hash_wrong_length(self):
        """Test that hash with wrong length raises validation error."""
        with pytest.raises(ValidationError) as excinfo:
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                file_hash="a" * 63,  # 63 chars instead of 64
                raw_llm_output={"data": "test"},
            )

        assert "File hash must be a valid SHA-256 hash" in str(excinfo.value)

    def test_invalid_file_hash_non_hex(self):
        """Test that hash with non-hex characters raises validation error."""
        with pytest.raises(ValidationError) as excinfo:
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                file_hash="g" * 64,  # 'g' is not a hex char
                raw_llm_output={"data": "test"},
            )

        assert "File hash must be a valid SHA-256 hash" in str(excinfo.value)

    def test_empty_raw_llm_output(self):
        """Test that empty raw_llm_output raises validation error."""
        with pytest.raises(ValidationError) as excinfo:
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                raw_llm_output={},
            )

        assert "raw_llm_output cannot be empty" in str(excinfo.value)

    def test_file_hash_normalization(self):
        """Test that file hash is normalized to lowercase."""
        doc = SourceDocument(
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=date(2024, 12, 31),
            file_hash="ABCDEF" + "0" * 58,  # Mixed case
            raw_llm_output={"data": "test"},
        )

        assert doc.file_hash == "abcdef" + "0" * 58  # Should be lowercase

    def test_json_serialization(self):
        """Test JSON serialization of SourceDocument."""
        doc_id = uuid4()
        doc_date = date(2024, 12, 31)
        created_at = datetime.now()

        doc = SourceDocument(
            doc_id=doc_id,
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=doc_date,
            created_at=created_at,
            raw_llm_output={"data": "test"},
        )

        json_data = doc.model_dump(mode="json")

        assert json_data["doc_id"] == str(doc_id)
        assert json_data["doc_date"] == doc_date.isoformat()
        assert json_data["created_at"] == created_at.isoformat()
        assert json_data["doc_type"] == "annual_report"


class TestSourceDocumentMetadata:
    """Test cases for SourceDocumentMetadata."""

    def test_create_valid_metadata(self):
        """Test creating valid SourceDocumentMetadata."""
        metadata = SourceDocumentMetadata(
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=date(2024, 12, 31),
            report_title="开山集团股份有限公司2024年年度报告",
            file_path="data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
            file_hash="a" * 64,
        )

        assert metadata.company_code == "300257"
        assert metadata.doc_type == DocType.ANNUAL_REPORT
        assert metadata.doc_date == date(2024, 12, 31)
        assert metadata.report_title == "开山集团股份有限公司2024年年度报告"
        assert (
            metadata.file_path
            == "data/annual_reports/2024/300257_开山股份_2024_annual_report.md"
        )
        assert metadata.file_hash == "a" * 64

    def test_from_extraction_result_annual_report(self):
        """Test creating metadata from annual report extraction result."""
        extraction_data = {
            "company_code": "300257",
            "company_name_full": "开山集团股份有限公司",
            "company_name_short": "开山股份",
        }

        document_metadata = {
            "doc_date": "2024-12-31",
            "file_path": "data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
            "file_hash": "a" * 64,
        }

        metadata = SourceDocumentMetadata.from_extraction_result(
            extraction_data=extraction_data,
            document_metadata=document_metadata,
            document_type="annual_report",
        )

        assert metadata.company_code == "300257"
        assert metadata.doc_type == DocType.ANNUAL_REPORT
        assert metadata.doc_date == date(2024, 12, 31)
        assert metadata.report_title == "开山集团股份有限公司2024年年度报告"
        assert (
            metadata.file_path
            == "data/annual_reports/2024/300257_开山股份_2024_annual_report.md"
        )
        assert metadata.file_hash == "a" * 64

    def test_from_extraction_result_research_report(self):
        """Test creating metadata from research report extraction result."""
        extraction_data = {
            "company_code": "300257",
            "company_name_full": "开山集团股份有限公司",
        }

        document_metadata = {
            "doc_date": "2024-01-15",
            "file_path": "data/research_reports/2024/300257_research.txt",
            "file_hash": "b" * 64,
            "report_title": "开山股份投资价值分析",
        }

        metadata = SourceDocumentMetadata.from_extraction_result(
            extraction_data=extraction_data,
            document_metadata=document_metadata,
            document_type="research_report",
        )

        assert metadata.company_code == "300257"
        assert metadata.doc_type == DocType.RESEARCH_REPORT
        assert metadata.doc_date == date(2024, 1, 15)
        assert metadata.report_title == "开山股份投资价值分析"
        assert metadata.file_path == "data/research_reports/2024/300257_research.txt"
        assert metadata.file_hash == "b" * 64

    def test_from_extraction_result_missing_report_title(self):
        """Test creating metadata when report title is missing."""
        extraction_data = {
            "company_code": "300257",
            "company_name_full": "开山集团股份有限公司",
        }

        document_metadata = {
            "doc_date": "2024-01-15",
            "file_path": "data/research_reports/2024/300257_research.txt",
        }

        metadata = SourceDocumentMetadata.from_extraction_result(
            extraction_data=extraction_data,
            document_metadata=document_metadata,
            document_type="research_report",
        )

        assert metadata.report_title == "开山集团股份有限公司研究报告"

    def test_from_extraction_result_default_date(self):
        """Test that missing doc_date defaults to today."""
        extraction_data = {
            "company_code": "300257",
            "company_name_full": "开山集团股份有限公司",
        }

        document_metadata = {
            "file_path": "data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
        }

        metadata = SourceDocumentMetadata.from_extraction_result(
            extraction_data=extraction_data,
            document_metadata=document_metadata,
            document_type="annual_report",
        )

        assert metadata.doc_date == date.today()
