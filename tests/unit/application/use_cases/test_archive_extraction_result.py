"""Unit tests for ArchiveExtractionResultUseCase."""

from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from src.application.use_cases.archive_extraction_result import (
    ArchiveExtractionResultUseCase,
)
from src.domain.entities.extraction import DocumentType as DocType
from src.domain.entities.source_document import SourceDocument, SourceDocumentMetadata


@pytest.fixture
def mock_repository():
    """Create a mock source document repository."""
    repository = AsyncMock()
    repository.exists = AsyncMock(return_value=False)
    repository.save = AsyncMock(return_value=uuid4())
    repository.find_by_file_hash = AsyncMock(return_value=None)
    return repository


@pytest.fixture
def archive_use_case(mock_repository):
    """Create an ArchiveExtractionResultUseCase instance with mock repository."""
    return ArchiveExtractionResultUseCase(repository=mock_repository)


@pytest.fixture
def sample_raw_llm_output():
    """Sample raw LLM output for testing."""
    return {
        "document_type": "annual_report",
        "extraction_data": {
            "company_code": "300257",
            "company_name_full": "开山集团股份有限公司",
            "company_name_short": "开山股份",
            "top_shareholders": [],
            "business_concepts": [],
        },
        "extraction_metadata": {
            "model": "gemini-2.5-pro",
            "prompt_version": "1.0",
            "processing_time_seconds": 95.3,
        },
        "status": "success",
        "timestamp": "2025-07-20T17:30:45",
    }


@pytest.fixture
def sample_metadata():
    """Sample metadata dictionary for testing."""
    return {
        "company_code": "300257",
        "doc_type": "annual_report",
        "doc_date": "2024-12-31",
        "report_title": "开山集团股份有限公司2024年年度报告",
        "file_path": "data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
        "file_hash": "a" * 64,
    }


@pytest.fixture
def sample_metadata_object():
    """Sample SourceDocumentMetadata object for testing."""
    return SourceDocumentMetadata(
        company_code="300257",
        doc_type=DocType.ANNUAL_REPORT,
        doc_date=date(2024, 12, 31),
        report_title="开山集团股份有限公司2024年年度报告",
        file_path="data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
        file_hash="a" * 64,
    )


class TestArchiveExtractionResultUseCase:
    """Test cases for ArchiveExtractionResultUseCase."""

    @pytest.mark.asyncio
    async def test_successful_archive_with_dict_metadata(
        self, archive_use_case, mock_repository, sample_raw_llm_output, sample_metadata
    ):
        """Test successful archiving with dictionary metadata."""
        doc_id = uuid4()
        mock_repository.save.return_value = doc_id

        result = await archive_use_case.execute(
            raw_llm_output=sample_raw_llm_output,
            metadata=sample_metadata,
        )

        assert result == doc_id
        mock_repository.exists.assert_called_once_with("a" * 64)
        mock_repository.save.assert_called_once()

        # Verify the saved document
        saved_doc = mock_repository.save.call_args[0][0]
        assert isinstance(saved_doc, SourceDocument)
        assert saved_doc.company_code == "300257"
        assert saved_doc.doc_type == DocType.ANNUAL_REPORT
        assert saved_doc.doc_date == date(2024, 12, 31)
        assert saved_doc.raw_llm_output == sample_raw_llm_output

    @pytest.mark.asyncio
    async def test_successful_archive_with_object_metadata(
        self,
        archive_use_case,
        mock_repository,
        sample_raw_llm_output,
        sample_metadata_object,
    ):
        """Test successful archiving with SourceDocumentMetadata object."""
        doc_id = uuid4()
        mock_repository.save.return_value = doc_id

        result = await archive_use_case.execute(
            raw_llm_output=sample_raw_llm_output,
            metadata=sample_metadata_object,
        )

        assert result == doc_id
        mock_repository.exists.assert_called_once_with("a" * 64)
        mock_repository.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_already_exists(
        self, archive_use_case, mock_repository, sample_raw_llm_output, sample_metadata
    ):
        """Test archiving when document already exists."""
        existing_doc_id = uuid4()
        existing_doc = SourceDocument(
            doc_id=existing_doc_id,
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=date(2024, 12, 31),
            raw_llm_output=sample_raw_llm_output,
        )

        mock_repository.exists.return_value = True
        mock_repository.find_by_file_hash.return_value = existing_doc

        result = await archive_use_case.execute(
            raw_llm_output=sample_raw_llm_output,
            metadata=sample_metadata,
        )

        assert result == existing_doc_id
        mock_repository.exists.assert_called_once_with("a" * 64)
        mock_repository.find_by_file_hash.assert_called_once_with("a" * 64)
        mock_repository.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_file_hash_generates_hash(
        self, archive_use_case, mock_repository, sample_raw_llm_output
    ):
        """Test that missing file_hash is generated from raw output."""
        metadata = {
            "company_code": "300257",
            "doc_type": "annual_report",
            "doc_date": "2024-12-31",
        }

        doc_id = uuid4()
        mock_repository.save.return_value = doc_id

        result = await archive_use_case.execute(
            raw_llm_output=sample_raw_llm_output,
            metadata=metadata,
        )

        assert result == doc_id
        # Verify a hash was generated
        saved_doc = mock_repository.save.call_args[0][0]
        assert saved_doc.file_hash is not None
        assert len(saved_doc.file_hash) == 64

    @pytest.mark.asyncio
    async def test_missing_required_metadata_fields(
        self, archive_use_case, sample_raw_llm_output
    ):
        """Test that missing required metadata fields raises ValueError."""
        metadata = {
            "company_code": "300257",
            # Missing doc_type and doc_date
        }

        with pytest.raises(ValueError) as excinfo:
            await archive_use_case.execute(
                raw_llm_output=sample_raw_llm_output,
                metadata=metadata,
            )

        assert "Missing required metadata fields" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_integrity_error_handling(
        self, archive_use_case, mock_repository, sample_raw_llm_output, sample_metadata
    ):
        """Test handling of IntegrityError from repository."""
        mock_repository.save.side_effect = IntegrityError(
            "Duplicate key value", params=None, orig=None
        )

        with pytest.raises(IntegrityError):
            await archive_use_case.execute(
                raw_llm_output=sample_raw_llm_output,
                metadata=sample_metadata,
            )

    @pytest.mark.asyncio
    async def test_operational_error_retry(
        self, archive_use_case, mock_repository, sample_raw_llm_output, sample_metadata
    ):
        """Test retry logic for OperationalError."""
        doc_id = uuid4()
        # Fail twice, then succeed
        mock_repository.save.side_effect = [
            OperationalError("Connection lost", params=None, orig=None),
            OperationalError("Connection lost", params=None, orig=None),
            doc_id,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await archive_use_case.execute(
                raw_llm_output=sample_raw_llm_output,
                metadata=sample_metadata,
            )

        assert result == doc_id
        assert mock_repository.save.call_count == 3

    @pytest.mark.asyncio
    async def test_operational_error_max_retries_exceeded(
        self, archive_use_case, mock_repository, sample_raw_llm_output, sample_metadata
    ):
        """Test that max retries are respected for OperationalError."""
        mock_repository.save.side_effect = OperationalError(
            "Connection lost", params=None, orig=None
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(OperationalError):
                await archive_use_case.execute(
                    raw_llm_output=sample_raw_llm_output,
                    metadata=sample_metadata,
                )

        assert mock_repository.save.call_count == 3  # Max retries

    @pytest.mark.asyncio
    async def test_extraction_metadata_building(
        self, archive_use_case, mock_repository
    ):
        """Test extraction metadata is properly built from raw output."""
        raw_output = {
            "status": "success",
            "model_version": "gemini-2.5-pro",
            "processing_time_seconds": 120.5,
            "timestamp": "2025-07-20T10:00:00",
            "token_usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
        }

        metadata = {
            "company_code": "300257",
            "doc_type": "annual_report",
            "doc_date": "2024-12-31",
        }

        doc_id = uuid4()
        mock_repository.save.return_value = doc_id

        await archive_use_case.execute(
            raw_llm_output=raw_output,
            metadata=metadata,
        )

        saved_doc = mock_repository.save.call_args[0][0]
        assert saved_doc.extraction_metadata["model_version"] == "gemini-2.5-pro"
        assert saved_doc.extraction_metadata["processing_time_seconds"] == 120.5
        assert saved_doc.extraction_metadata["extraction_time"] == "2025-07-20T10:00:00"
        assert saved_doc.extraction_metadata["token_usage"]["total_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_invalid_date_format_in_metadata(
        self, archive_use_case, sample_raw_llm_output
    ):
        """Test handling of invalid date format in metadata."""
        metadata = {
            "company_code": "300257",
            "doc_type": "annual_report",
            "doc_date": "invalid-date",
        }

        with pytest.raises(ValueError):
            await archive_use_case.execute(
                raw_llm_output=sample_raw_llm_output,
                metadata=metadata,
            )

    def test_hash_calculation_consistency(self, archive_use_case):
        """Test that hash calculation is consistent."""
        data = {"test": "data", "nested": {"value": 123}}

        hash1 = archive_use_case._calculate_hash(data)
        hash2 = archive_use_case._calculate_hash(data)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_dict_to_metadata_conversion(self, archive_use_case):
        """Test conversion from dictionary to SourceDocumentMetadata."""
        metadata_dict = {
            "company_code": "300257",
            "doc_type": "research_report",
            "doc_date": date(2024, 1, 15),
            "report_title": "Investment Analysis",
            "file_path": "/path/to/file.txt",
            "file_hash": "b" * 64,
        }

        result = archive_use_case._dict_to_metadata(metadata_dict)

        assert isinstance(result, SourceDocumentMetadata)
        assert result.company_code == "300257"
        assert result.doc_type == DocType.RESEARCH_REPORT
        assert result.doc_date == date(2024, 1, 15)
        assert result.report_title == "Investment Analysis"
        assert result.file_path == "/path/to/file.txt"
        assert result.file_hash == "b" * 64
