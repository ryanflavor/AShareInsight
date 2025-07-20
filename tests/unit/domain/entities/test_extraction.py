"""Unit tests for extraction domain entities."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.domain.entities.company import (
    AnnualReportExtraction,
    Shareholder,
)
from src.domain.entities.extraction import (
    CompanyReport,
    DocumentExtractionResult,
    DocumentType,
    ExtractionMetadata,
    ExtractionResult,
    TokenUsage,
)
from src.domain.entities.research_report import ResearchReportExtraction


class TestDocumentType:
    """Test cases for DocumentType enum."""

    def test_document_type_values(self):
        """Test document type enum values."""
        assert DocumentType.ANNUAL_REPORT.value == "annual_report"
        assert DocumentType.RESEARCH_REPORT.value == "research_report"

    def test_document_type_from_string(self):
        """Test creating document type from string."""
        assert DocumentType("annual_report") == DocumentType.ANNUAL_REPORT
        assert DocumentType("research_report") == DocumentType.RESEARCH_REPORT

    def test_invalid_document_type(self):
        """Test invalid document type raises error."""
        with pytest.raises(ValueError):
            DocumentType("invalid_type")


class TestTokenUsage:
    """Test cases for TokenUsage model."""

    def test_valid_token_usage(self):
        """Test creating valid token usage."""
        usage = TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
        )
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.total_tokens == 1500

    def test_token_usage_consistency(self):
        """Test token usage with consistent total."""
        usage = TokenUsage(
            input_tokens=2000,
            output_tokens=3000,
            total_tokens=5000,
        )
        assert usage.input_tokens + usage.output_tokens == usage.total_tokens

    def test_token_usage_zero_values(self):
        """Test token usage with zero values."""
        usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0

    def test_token_usage_required_fields(self):
        """Test all fields are required."""
        with pytest.raises(ValidationError):
            TokenUsage(input_tokens=100, output_tokens=50)  # Missing total_tokens

        with pytest.raises(ValidationError):
            TokenUsage(input_tokens=100, total_tokens=150)  # Missing output_tokens

        with pytest.raises(ValidationError):
            TokenUsage(output_tokens=50, total_tokens=150)  # Missing input_tokens


class TestExtractionMetadata:
    """Test cases for ExtractionMetadata model."""

    def test_valid_extraction_metadata(self):
        """Test creating valid extraction metadata."""
        metadata = ExtractionMetadata(
            model_version="gemini-2.5-pro",
            prompt_version="v1.0",
            processing_time_seconds=120.5,
            token_usage={"input": 1000, "output": 500, "total": 1500},
            file_hash="abc123def456",
        )

        assert metadata.model_version == "gemini-2.5-pro"
        assert metadata.prompt_version == "v1.0"
        assert metadata.processing_time_seconds == 120.5
        assert metadata.token_usage["input"] == 1000
        assert metadata.file_hash == "abc123def456"

    def test_metadata_timestamp_default(self):
        """Test that extraction timestamp has default value."""
        before = datetime.now()
        metadata = ExtractionMetadata(
            model_version="test",
            prompt_version="v1",
            processing_time_seconds=10.0,
            token_usage={},
            file_hash="test",
        )
        after = datetime.now()

        assert before <= metadata.extraction_timestamp <= after

    def test_metadata_custom_timestamp(self):
        """Test setting custom extraction timestamp."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        metadata = ExtractionMetadata(
            model_version="test",
            prompt_version="v1",
            extraction_timestamp=custom_time,
            processing_time_seconds=10.0,
            token_usage={},
            file_hash="test",
        )
        assert metadata.extraction_timestamp == custom_time

    def test_metadata_required_fields(self):
        """Test that all required fields must be provided."""
        with pytest.raises(ValidationError):
            ExtractionMetadata(
                # Missing model_version
                prompt_version="v1",
                processing_time_seconds=10.0,
                token_usage={},
                file_hash="test",
            )


class TestExtractionResult:
    """Test cases for ExtractionResult model."""

    def test_extraction_result_annual_report(self):
        """Test extraction result with annual report data."""
        annual_report = AnnualReportExtraction(
            company_name_full="Test Company Ltd.",
            company_name_short="Test Co",
            company_code="000001",
            exchange="Test Exchange",
            top_shareholders=[],
            business_concepts=[],
        )

        metadata = ExtractionMetadata(
            model_version="gemini-2.5-pro",
            prompt_version="v1.0",
            processing_time_seconds=90.0,
            token_usage={"input": 1000, "output": 500},
            file_hash="abc123",
        )

        result = ExtractionResult(
            document_type=DocumentType.ANNUAL_REPORT,
            extraction_data=annual_report,
            extraction_metadata=metadata,
            raw_llm_response='{"test": "response"}',
        )

        assert result.document_type == DocumentType.ANNUAL_REPORT
        assert result.extraction_data.company_code == "000001"
        assert result.extraction_metadata.model_version == "gemini-2.5-pro"
        assert result.raw_llm_response == '{"test": "response"}'

    def test_extraction_result_research_report(self):
        """Test extraction result with research report data."""
        research_report = ResearchReportExtraction(
            company_name_short="Test Co",
            company_code="000001",
            report_title="Test Report",
            investment_rating="买入",
            core_thesis="Test thesis",
            profit_forecast=[],
            valuation=[],
            business_concepts=[],
        )

        metadata = ExtractionMetadata(
            model_version="gemini-2.5-pro",
            prompt_version="v2.0",
            processing_time_seconds=60.0,
            token_usage={"input": 800, "output": 400},
            file_hash="def456",
        )

        result = ExtractionResult(
            document_type=DocumentType.RESEARCH_REPORT,
            extraction_data=research_report,
            extraction_metadata=metadata,
            raw_llm_response="{}",
        )

        assert result.document_type == DocumentType.RESEARCH_REPORT
        assert result.extraction_data.investment_rating == "买入"

    def test_extraction_result_use_enum_values(self):
        """Test that enum values are used in serialization."""
        annual_report = AnnualReportExtraction(
            company_name_full="Test",
            company_name_short="Test",
            company_code="000001",
            exchange="Test",
            top_shareholders=[],
            business_concepts=[],
        )

        result = ExtractionResult(
            document_type=DocumentType.ANNUAL_REPORT,
            extraction_data=annual_report,
            extraction_metadata=ExtractionMetadata(
                model_version="test",
                prompt_version="v1",
                processing_time_seconds=10.0,
                token_usage={},
                file_hash="test",
            ),
            raw_llm_response="",
        )

        data = result.model_dump()
        assert data["document_type"] == "annual_report"  # String value, not enum


class TestCompanyReport:
    """Test cases for CompanyReport model."""

    def test_company_report_creation(self):
        """Test creating a company report."""
        report = CompanyReport(
            company_name_full="Test Company Ltd.",
            company_name_short="Test Co",
            company_code="000001",
            exchange="Test Exchange",
            top_shareholders=[
                Shareholder(name="Major Holder", holding_percentage=60.0)
            ],
            business_concepts=[
                {
                    "concept_name": "Main Business",
                    "description": "Core operations",
                }
            ],
        )

        assert report.company_name_full == "Test Company Ltd."
        assert len(report.top_shareholders) == 1
        assert len(report.business_concepts) == 1

    def test_company_report_inherits_basic_info(self):
        """Test that CompanyReport inherits from CompanyBasicInfo."""
        report = CompanyReport(
            company_name_full="Full Name",
            company_name_short="Short",
            company_code="000001",
            exchange="Exchange",
            top_shareholders=[],
        )

        # Should have all CompanyBasicInfo fields
        assert hasattr(report, "company_name_full")
        assert hasattr(report, "company_name_short")
        assert hasattr(report, "company_code")
        assert hasattr(report, "exchange")
        assert hasattr(report, "top_shareholders")
        assert hasattr(report, "business_concepts")

    def test_company_report_empty_business_concepts(self):
        """Test company report with empty business concepts."""
        report = CompanyReport(
            company_name_full="Test",
            company_name_short="Test",
            company_code="000001",
            exchange="Test",
            top_shareholders=[],
            business_concepts=[],
        )
        assert report.business_concepts == []


class TestDocumentExtractionResult:
    """Test cases for DocumentExtractionResult model."""

    def test_successful_extraction_result(self):
        """Test successful document extraction result."""
        company_report = AnnualReportExtraction(
            company_name_full="Test Company",
            company_name_short="Test",
            company_code="000001",
            exchange="Test Exchange",
            top_shareholders=[],
            business_concepts=[],
        )

        result = DocumentExtractionResult(
            document_id="doc-123",
            status="success",
            document_type="annual_report",
            extracted_data=company_report,
            processing_time_seconds=45.5,
            model_version="gemini-2.5-pro",
            prompt_version="v1.0",
            token_usage=TokenUsage(
                input_tokens=1000,
                output_tokens=500,
                total_tokens=1500,
            ),
        )

        assert result.document_id == "doc-123"
        assert result.status == "success"
        assert result.extracted_data.company_code == "000001"
        assert result.token_usage.total_tokens == 1500
        assert result.error is None
        assert result.raw_output is None

    def test_failed_extraction_result(self):
        """Test failed document extraction result."""
        result = DocumentExtractionResult(
            document_id="doc-456",
            status="failed",
            document_type="research_report",
            error="JSON parsing failed",
            raw_output="Invalid JSON response from LLM",
        )

        assert result.document_id == "doc-456"
        assert result.status == "failed"
        assert result.extracted_data is None
        assert result.error == "JSON parsing failed"
        assert result.raw_output == "Invalid JSON response from LLM"
        assert result.token_usage is None

    def test_extraction_result_defaults(self):
        """Test extraction result with default values."""
        result = DocumentExtractionResult(
            document_id="doc-789",
            status="pending",
            document_type="annual_report",
        )

        assert result.processing_time_seconds == 0.0
        assert result.model_version is None
        assert result.prompt_version is None
        assert result.token_usage is None
        assert result.error is None
        assert result.raw_output is None
        assert result.extracted_data is None

    def test_extraction_result_with_research_report(self):
        """Test extraction result with research report data."""
        research_report = ResearchReportExtraction(
            company_name_short="Test Co",
            company_code="000001",
            report_title="Investment Report",
            investment_rating="买入",
            core_thesis="Strong buy recommendation",
            profit_forecast=[],
            valuation=[],
            business_concepts=[],
        )

        result = DocumentExtractionResult(
            document_id="doc-999",
            status="success",
            document_type="research_report",
            extracted_data=research_report,
            processing_time_seconds=30.0,
        )

        assert result.extracted_data.investment_rating == "买入"
        assert isinstance(result.extracted_data, ResearchReportExtraction)

    def test_extraction_result_serialization(self):
        """Test extraction result serialization."""
        result = DocumentExtractionResult(
            document_id="doc-111",
            status="success",
            document_type="annual_report",
            processing_time_seconds=25.5,
            model_version="test-model",
            prompt_version="v1.0",
        )

        data = result.model_dump()
        assert data["document_id"] == "doc-111"
        assert data["status"] == "success"
        assert data["processing_time_seconds"] == 25.5
        assert data["model_version"] == "test-model"
        assert data["extracted_data"] is None
