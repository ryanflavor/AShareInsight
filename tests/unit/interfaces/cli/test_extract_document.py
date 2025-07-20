"""Unit tests for extract_document CLI."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from src.domain.entities.company import AnnualReportExtraction
from src.domain.entities.extraction import (
    DocumentExtractionResult,
    TokenUsage,
)
from src.interfaces.cli.extract_document import extract_document
from src.shared.exceptions import DocumentProcessingError, LLMServiceError


@pytest.fixture
def cli_runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_settings():
    """Mock settings with required configuration."""
    with patch("src.interfaces.cli.extract_document.Settings") as mock:
        settings = MagicMock()
        mock_llm = MagicMock()
        mock_llm.gemini_api_key = "test-api-key"
        mock_llm.gemini_base_url = "https://test.api.com"
        settings.llm = mock_llm
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_document():
    """Mock document object."""
    doc = MagicMock()
    doc.content = "Test document content"
    doc.metadata = {
        "file_name": "test.txt",
        "file_size": 1000,
        "file_hash": "abc123",
    }
    return doc


@pytest.fixture
def mock_extraction_result():
    """Mock successful extraction result."""
    company_report = AnnualReportExtraction(
        company_name_full="Test Company Ltd.",
        company_name_short="Test Co",
        company_code="000001",
        exchange="Shanghai Stock Exchange",
        top_shareholders=[],
        business_concepts=[],
    )

    return DocumentExtractionResult(
        document_id="test-doc-id",
        status="success",
        document_type="annual_report",
        extracted_data=company_report,
        processing_time_seconds=5.5,
        model_version="gemini-2.5-pro",
        prompt_version="v1.0",
        token_usage=TokenUsage(
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
        ),
    )


class TestExtractDocumentCLI:
    """Test cases for extract_document CLI."""

    def test_successful_extraction(
        self, cli_runner, mock_settings, mock_document, mock_extraction_result, tmp_path
    ):
        """Test successful document extraction."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.return_value = mock_extraction_result

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            # Assertions
            assert result.exit_code == 0
            assert "Extraction completed successfully" in result.output
            assert "Test Company Ltd." in result.output
            assert "000001" in result.output

    def test_extraction_with_output_file(
        self, cli_runner, mock_settings, mock_document, mock_extraction_result, tmp_path
    ):
        """Test extraction with custom output file."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")
        output_file = tmp_path / "output.json"

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.return_value = mock_extraction_result

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [
                    str(test_file),
                    "--document-type",
                    "annual_report",
                    "-o",
                    str(output_file),
                ],
            )

            # Assertions
            assert result.exit_code == 0
            assert output_file.exists()
            assert "Result saved to:" in result.output
            assert str(output_file) in result.output

    def test_debug_mode(
        self, cli_runner, mock_settings, mock_document, mock_extraction_result, tmp_path
    ):
        """Test CLI with debug mode enabled."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
            patch("src.interfaces.cli.extract_document.logging") as mock_logging,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.return_value = mock_extraction_result

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report", "--debug"],
            )

            # Assertions
            assert result.exit_code == 0
            mock_logging.basicConfig.assert_called_once()
            args, kwargs = mock_logging.basicConfig.call_args
            assert kwargs["level"] == mock_logging.DEBUG

    def test_no_progress_mode(
        self, cli_runner, mock_settings, mock_document, mock_extraction_result, tmp_path
    ):
        """Test CLI with progress disabled."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.return_value = mock_extraction_result

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report", "--no-progress"],
            )

            # Assertions
            assert result.exit_code == 0
            # Progress indicators should not appear in output
            assert "[cyan]Loading document..." not in result.output

    def test_missing_api_key(self, cli_runner, tmp_path):
        """Test error when API key is not set."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with patch("src.interfaces.cli.extract_document.Settings") as mock_settings:
            mock_llm_settings = MagicMock()
            mock_llm_settings.gemini_api_key = None
            mock_settings.return_value.llm = mock_llm_settings

            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            assert result.exit_code == 1
            assert "GEMINI_API_KEY environment variable not set" in result.output

    def test_document_processing_error(self, cli_runner, mock_settings, tmp_path):
        """Test handling of document processing errors."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader:
            mock_loader.return_value.load.side_effect = DocumentProcessingError(
                "Failed to load document"
            )

            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            assert result.exit_code == 1
            assert "Document processing error: Failed to load document" in result.output

    def test_llm_service_error(
        self, cli_runner, mock_settings, mock_document, tmp_path
    ):
        """Test handling of LLM service errors."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.side_effect = LLMServiceError(
                "API request failed"
            )

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            assert result.exit_code == 1
            assert "LLM service error: API request failed" in result.output

    def test_validation_error(self, cli_runner, mock_settings, mock_document, tmp_path):
        """Test handling of validation errors."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.side_effect = (
                ValidationError.from_exception_data(
                    "CompanyReport",
                    [
                        {
                            "type": "missing",
                            "loc": ("company_name_full",),
                            "msg": "Field required",
                        }
                    ],
                )
            )

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            assert result.exit_code == 1
            assert "Validation error:" in result.output

    def test_extraction_failure(
        self, cli_runner, mock_settings, mock_document, tmp_path
    ):
        """Test handling of extraction failure status."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        failed_result = DocumentExtractionResult(
            document_id="test-doc-id",
            status="failed",
            document_type="annual_report",
            error="JSON parsing failed",
            raw_output="Invalid JSON response",
        )

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.return_value = failed_result

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            assert result.exit_code == 1
            assert "Extraction failed: JSON parsing failed" in result.output

    def test_keyboard_interrupt(
        self, cli_runner, mock_settings, mock_document, tmp_path
    ):
        """Test handling of keyboard interrupt."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        with (
            patch("src.interfaces.cli.extract_document.DocumentLoader") as mock_loader,
            patch("src.interfaces.cli.extract_document.GeminiLLMAdapter") as mock_llm,
            patch(
                "src.interfaces.cli.extract_document.ExtractDocumentDataUseCase"
            ) as mock_use_case,
        ):
            # Setup mocks
            mock_loader.return_value.load.return_value = mock_document
            mock_use_case.return_value.execute.side_effect = KeyboardInterrupt()

            # Run CLI
            result = cli_runner.invoke(
                extract_document,
                [str(test_file), "--document-type", "annual_report"],
            )

            assert result.exit_code == 130
            assert "Operation cancelled by user" in result.output

    def test_invalid_document_type(self, cli_runner, mock_settings, tmp_path):
        """Test error with invalid document type."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text("Test content")

        result = cli_runner.invoke(
            extract_document,
            [str(test_file), "--document-type", "invalid_type"],
        )

        assert result.exit_code == 2
        assert "Invalid value for '--document-type'" in result.output

    def test_file_not_found(self, cli_runner, mock_settings):
        """Test error when file doesn't exist."""
        result = cli_runner.invoke(
            extract_document,
            ["non_existent_file.txt", "--document-type", "annual_report"],
        )

        assert result.exit_code == 2
        assert "Path 'non_existent_file.txt' does not exist" in result.output
