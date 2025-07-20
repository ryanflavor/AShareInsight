"""Unit tests for text and markdown document loaders."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.document_processing.text_loader import (
    MarkdownDocumentLoader,
    TextDocumentLoader,
)
from src.shared.exceptions import DocumentProcessingError


class TestTextDocumentLoader:
    """Test cases for TextDocumentLoader."""

    @pytest.fixture
    def loader(self):
        """Create a text document loader."""
        return TextDocumentLoader()

    @pytest.fixture
    def text_file(self, tmp_path):
        """Create a test text file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test text content", encoding="utf-8")
        return test_file

    def test_supported_extensions(self):
        """Test supported file extensions."""
        assert TextDocumentLoader.SUPPORTED_EXTENSIONS == {".txt", ".text"}

    def test_can_load(self, loader):
        """Test can_load method for various file types."""
        assert loader.can_load(Path("document.txt"))
        assert loader.can_load(Path("document.TXT"))  # Case insensitive
        assert loader.can_load(Path("document.text"))
        assert loader.can_load(Path("document.TEXT"))

        assert not loader.can_load(Path("document.md"))
        assert not loader.can_load(Path("document.doc"))
        assert not loader.can_load(Path("document"))

    def test_load_content_success(self, loader, text_file):
        """Test successful content loading."""
        content = loader.load_content(text_file)
        assert content == "Test text content"

    def test_load_content_utf8(self, loader, tmp_path):
        """Test loading UTF-8 encoded content with special characters."""
        test_file = tmp_path / "utf8.txt"
        test_content = "UTF-8 content: 你好世界 🌍"
        test_file.write_text(test_content, encoding="utf-8")

        content = loader.load_content(test_file)
        assert content == test_content
        assert loader.encoding == "utf-8"

    def test_load_content_gbk(self, loader, tmp_path):
        """Test loading GBK encoded content."""
        test_file = tmp_path / "gbk.txt"
        test_content = "中文内容测试"
        test_file.write_text(test_content, encoding="gbk")

        content = loader.load_content(test_file)
        assert content == test_content
        assert loader.encoding == "gbk"

    def test_load_content_gb2312(self, loader, tmp_path):
        """Test loading GB2312 encoded content."""
        test_file = tmp_path / "gb2312.txt"
        test_content = "简体中文"
        test_file.write_text(test_content, encoding="gb2312")

        content = loader.load_content(test_file)
        assert content == test_content
        # Python often decodes gb2312 as gbk (superset)
        assert loader.encoding in ["gb2312", "gbk"]

    def test_load_content_encoding_fallback(self, loader, tmp_path):
        """Test encoding fallback mechanism."""
        test_file = tmp_path / "encoded.txt"

        # Create a file with specific encoding
        test_content = "测试内容"
        test_file.write_text(test_content, encoding="gb18030")

        # Reset loader encoding to utf-8
        loader.encoding = "utf-8"

        # Should fall back to gbk or gb18030
        content = loader.load_content(test_file)
        assert content == test_content
        # Python often decodes gb18030 as gbk
        assert loader.encoding in ["gbk", "gb18030"]

    def test_load_content_unsupported_encoding(self, loader, tmp_path):
        """Test error with unsupported encoding."""
        test_file = tmp_path / "bad_encoding.txt"

        # Write binary data that's not valid in any encoding
        test_file.write_bytes(b"\xff\xfe\xff\xfe")

        with pytest.raises(DocumentProcessingError) as exc_info:
            loader.load_content(test_file)
        assert "Failed to decode file" in str(exc_info.value)
        assert "with any supported encoding" in str(exc_info.value)

    def test_load_content_file_not_found(self, loader):
        """Test error when file doesn't exist."""
        with pytest.raises(DocumentProcessingError) as exc_info:
            loader.load_content(Path("/non/existent/file.txt"))
        assert "Failed to read text file" in str(exc_info.value)

    def test_load_content_permission_error(self, loader, tmp_path):
        """Test error with permission issues."""
        test_file = tmp_path / "no_access.txt"
        test_file.write_text("content")

        with patch("builtins.open", side_effect=PermissionError("No access")):
            with pytest.raises(DocumentProcessingError) as exc_info:
                loader.load_content(test_file)
            assert "Failed to read text file" in str(exc_info.value)
            assert "No access" in str(exc_info.value)

    def test_full_document_load(self, loader, text_file):
        """Test loading complete document with metadata."""
        doc = loader.load(text_file)

        assert doc.content == "Test text content"
        assert doc.metadata.file_name == "test.txt"
        assert doc.metadata.file_extension == ".txt"
        assert doc.metadata.encoding == "utf-8"


class TestMarkdownDocumentLoader:
    """Test cases for MarkdownDocumentLoader."""

    @pytest.fixture
    def loader(self):
        """Create a markdown document loader."""
        return MarkdownDocumentLoader()

    @pytest.fixture
    def markdown_file(self, tmp_path):
        """Create a test markdown file."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test Markdown\n\nContent here.", encoding="utf-8")
        return test_file

    def test_supported_extensions(self):
        """Test supported file extensions."""
        assert MarkdownDocumentLoader.SUPPORTED_EXTENSIONS == {
            ".md",
            ".markdown",
            ".mdown",
            ".mkd",
        }

    def test_can_load(self, loader):
        """Test can_load method for various file types."""
        assert loader.can_load(Path("document.md"))
        assert loader.can_load(Path("document.MD"))  # Case insensitive
        assert loader.can_load(Path("document.markdown"))
        assert loader.can_load(Path("document.mdown"))
        assert loader.can_load(Path("document.mkd"))

        assert not loader.can_load(Path("document.txt"))
        assert not loader.can_load(Path("document.doc"))
        assert not loader.can_load(Path("document"))

    def test_load_content_success(self, loader, markdown_file):
        """Test successful markdown content loading."""
        content = loader.load_content(markdown_file)
        assert content == "# Test Markdown\n\nContent here."

    def test_load_markdown_with_chinese(self, loader, tmp_path):
        """Test loading markdown with Chinese characters."""
        test_file = tmp_path / "chinese.md"
        test_content = (
            "# 中文标题\n\n这是中文内容。\n\n## 子标题\n\n- 列表项1\n- 列表项2"
        )
        test_file.write_text(test_content, encoding="utf-8")

        content = loader.load_content(test_file)
        assert content == test_content

    def test_load_markdown_complex_content(self, loader, tmp_path):
        """Test loading markdown with complex formatting."""
        test_file = tmp_path / "complex.md"
        test_content = """# Main Title

## Section 1

This is a paragraph with **bold** and *italic* text.

```python
def hello():
    print("Hello, world!")
```

### Subsection

- Item 1
- Item 2
  - Nested item

> This is a quote

[Link](https://example.com)
"""
        test_file.write_text(test_content, encoding="utf-8")

        content = loader.load_content(test_file)
        assert content == test_content

    def test_load_content_encoding_fallback(self, loader, tmp_path):
        """Test encoding fallback for markdown files."""
        test_file = tmp_path / "encoded.md"
        # Use GBK instead of big5 for this test
        test_content = "# 测试标题\n\n测试内容"
        test_file.write_text(test_content, encoding="gbk")

        # Reset loader encoding
        loader.encoding = "utf-8"

        content = loader.load_content(test_file)
        assert content == test_content
        assert loader.encoding == "gbk"

    def test_load_content_io_error(self, loader):
        """Test IO error handling."""
        with patch("builtins.open", side_effect=OSError("Disk error")):
            with pytest.raises(DocumentProcessingError) as exc_info:
                loader.load_content(Path("test.md"))
            assert "Failed to read markdown file" in str(exc_info.value)
            assert "Disk error" in str(exc_info.value)

    def test_full_document_load(self, loader, markdown_file):
        """Test loading complete markdown document with metadata."""
        doc = loader.load(markdown_file)

        assert doc.content == "# Test Markdown\n\nContent here."
        assert doc.metadata.file_name == "test.md"
        assert doc.metadata.file_extension == ".md"
        assert doc.metadata.encoding == "utf-8"

    def test_markdown_empty_file(self, loader, tmp_path):
        """Test loading empty markdown file."""
        test_file = tmp_path / "empty.md"
        test_file.write_text("", encoding="utf-8")

        content = loader.load_content(test_file)
        assert content == ""

    def test_encoding_update_persists(self, loader, tmp_path):
        """Test that encoding update persists for metadata."""
        test_file = tmp_path / "persist.md"
        test_file.write_text("内容", encoding="gbk")

        # Load with automatic encoding detection
        doc = loader.load(test_file)

        assert doc.content == "内容"
        assert doc.metadata.encoding == "gbk"  # Should reflect detected encoding
