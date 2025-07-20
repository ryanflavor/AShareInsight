"""Unit tests for unified document loader."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.document_processing.base import (
    ProcessedDocument,
)
from src.infrastructure.document_processing.loader import DocumentLoader
from src.infrastructure.document_processing.text_loader import (
    MarkdownDocumentLoader,
    TextDocumentLoader,
)
from src.shared.exceptions import DocumentProcessingError


class TestDocumentLoader:
    """Test cases for DocumentLoader."""

    @pytest.fixture
    def loader(self):
        """Create a document loader."""
        return DocumentLoader()

    @pytest.fixture
    def txt_file(self, tmp_path):
        """Create a test txt file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Text content", encoding="utf-8")
        return test_file

    @pytest.fixture
    def md_file(self, tmp_path):
        """Create a test markdown file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Markdown content", encoding="utf-8")
        return test_file

    def test_initialization(self, loader):
        """Test loader initialization."""
        assert loader.encoding == "utf-8"
        assert len(loader._loaders) == 2
        assert isinstance(loader._loaders[0], TextDocumentLoader)
        assert isinstance(loader._loaders[1], MarkdownDocumentLoader)

    def test_initialization_with_encoding(self):
        """Test loader initialization with custom encoding."""
        loader = DocumentLoader(encoding="gbk")
        assert loader.encoding == "gbk"
        assert all(l.encoding == "gbk" for l in loader._loaders)

    def test_load_txt_file(self, loader, txt_file):
        """Test loading a text file."""
        doc = loader.load(txt_file)
        assert isinstance(doc, ProcessedDocument)
        assert doc.content == "Text content"
        assert doc.metadata.file_extension == ".txt"

    def test_load_md_file(self, loader, md_file):
        """Test loading a markdown file."""
        doc = loader.load(md_file)
        assert isinstance(doc, ProcessedDocument)
        assert doc.content == "# Markdown content"
        assert doc.metadata.file_extension == ".md"

    def test_load_string_path(self, loader, txt_file):
        """Test loading with string path."""
        doc = loader.load(str(txt_file))
        assert doc.content == "Text content"

    def test_load_unsupported_file(self, loader, tmp_path):
        """Test error with unsupported file type."""
        unsupported_file = tmp_path / "test.doc"
        unsupported_file.write_text("content")

        with pytest.raises(DocumentProcessingError) as exc_info:
            loader.load(unsupported_file)
        assert "No loader available for file type: .doc" in str(exc_info.value)

    def test_find_loader(self, loader):
        """Test finding appropriate loader."""
        txt_loader = loader._find_loader(Path("test.txt"))
        assert isinstance(txt_loader, TextDocumentLoader)

        md_loader = loader._find_loader(Path("test.md"))
        assert isinstance(md_loader, MarkdownDocumentLoader)

        none_loader = loader._find_loader(Path("test.pdf"))
        assert none_loader is None

    def test_get_supported_extensions(self, loader):
        """Test getting all supported extensions."""
        extensions = loader.get_supported_extensions()

        assert ".txt" in extensions
        assert ".text" in extensions
        assert ".md" in extensions
        assert ".markdown" in extensions
        assert ".mdown" in extensions
        assert ".mkd" in extensions
        assert len(extensions) == 6

    def test_load_with_company_info_defaults(self, loader, txt_file):
        """Test loading with company info extraction."""
        doc, company_info = loader.load_with_company_info(txt_file)

        assert doc.content == "Text content"
        assert company_info["company_name"] == "test"  # From filename
        assert company_info["document_type"] == "未知文档类型"

    def test_load_with_company_info_annual_report(self, loader, tmp_path):
        """Test company info extraction for annual report."""
        # Test various annual report naming patterns
        test_cases = [
            ("开山股份_2024年年度报告.txt", "开山股份", "年度报告"),
            ("测试公司_年报.txt", "测试公司", "年度报告"),
            ("company_annual_report.txt", "company", "年度报告"),
        ]

        for filename, expected_company, expected_type in test_cases:
            test_file = tmp_path / filename
            test_file.write_text("content")

            doc, company_info = loader.load_with_company_info(test_file)
            assert company_info["company_name"] == expected_company
            assert company_info["document_type"] == expected_type

    def test_load_with_company_info_research_report(self, loader, tmp_path):
        """Test company info extraction for research report."""
        test_cases = [
            ("公司A_深度研究报告.txt", "公司A", "研究报告"),
            ("投资公司_研报.txt", "投资公司", "研究报告"),
            ("research_report_company.txt", "research", "研究报告"),
        ]

        for filename, expected_company, expected_type in test_cases:
            test_file = tmp_path / filename
            test_file.write_text("content")

            doc, company_info = loader.load_with_company_info(test_file)
            assert company_info["company_name"] == expected_company
            assert company_info["document_type"] == expected_type

    def test_load_with_company_info_overrides(self, loader, txt_file):
        """Test company info with overrides."""
        doc, company_info = loader.load_with_company_info(
            txt_file,
            company_name="Override Company",
            document_type="Custom Report",
        )

        assert company_info["company_name"] == "Override Company"
        assert company_info["document_type"] == "Custom Report"

    def test_load_with_company_info_no_underscore(self, loader, tmp_path):
        """Test company info extraction without underscore in filename."""
        test_file = tmp_path / "companyreport.txt"
        test_file.write_text("content")

        doc, company_info = loader.load_with_company_info(test_file)
        assert company_info["company_name"] == "companyreport"
        assert company_info["document_type"] == "未知文档类型"

    def test_load_with_company_info_empty_parts(self, loader, tmp_path):
        """Test company info with empty filename parts."""
        test_file = tmp_path / "_.txt"
        test_file.write_text("content")

        doc, company_info = loader.load_with_company_info(test_file)
        # Should handle empty parts gracefully - empty string becomes "未知公司"
        assert company_info["company_name"] == "未知公司"
        assert company_info["document_type"] == "未知文档类型"

    def test_load_with_company_info_partial_override(self, loader, tmp_path):
        """Test partial override of company info."""
        test_file = tmp_path / "测试公司_年报.txt"
        test_file.write_text("content")

        # Override only company name
        doc, company_info = loader.load_with_company_info(
            test_file,
            company_name="新公司名",
        )
        assert company_info["company_name"] == "新公司名"
        assert company_info["document_type"] == "年度报告"  # Auto-detected

        # Override only document type
        doc, company_info = loader.load_with_company_info(
            test_file,
            document_type="季度报告",
        )
        assert company_info["company_name"] == "测试公司"  # From filename
        assert company_info["document_type"] == "季度报告"

    def test_load_error_propagation(self, loader, tmp_path):
        """Test that loader errors are properly propagated."""
        # Create a file that will fail during loading
        bad_file = tmp_path / "bad.txt"

        with patch.object(
            TextDocumentLoader,
            "load",
            side_effect=DocumentProcessingError("Load failed"),
        ):
            with pytest.raises(DocumentProcessingError) as exc_info:
                loader.load(bad_file)
            assert "Load failed" in str(exc_info.value)

    def test_multiple_loaders_priority(self, loader):
        """Test that loaders are checked in order."""
        # Text loader is first, so it should be found first
        path = Path("test.txt")
        found_loader = loader._find_loader(path)
        assert found_loader is loader._loaders[0]
        assert isinstance(found_loader, TextDocumentLoader)

        # Markdown loader is second
        path = Path("test.md")
        found_loader = loader._find_loader(path)
        assert found_loader is loader._loaders[1]
        assert isinstance(found_loader, MarkdownDocumentLoader)
