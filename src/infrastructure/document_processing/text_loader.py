"""Text and Markdown document loaders."""

from pathlib import Path

from src.shared.exceptions import DocumentProcessingError

from .base import BaseDocumentLoader


class TextDocumentLoader(BaseDocumentLoader):
    """Loader for plain text documents."""

    SUPPORTED_EXTENSIONS = {".txt", ".text"}

    def can_load(self, file_path: Path) -> bool:
        """Check if this is a text file."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def load_content(self, file_path: Path) -> str:
        """Load text file content."""
        try:
            with open(file_path, encoding=self.encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encodings
            for encoding in ["gbk", "gb2312", "gb18030", "big5"]:
                try:
                    with open(file_path, encoding=encoding) as f:
                        content = f.read()
                        self.encoding = encoding  # Update for metadata
                        return content
                except UnicodeDecodeError:
                    continue
            raise DocumentProcessingError(
                f"Failed to decode file {file_path} with any supported encoding"
            )
        except Exception as e:
            raise DocumentProcessingError(
                f"Failed to read text file {file_path}: {str(e)}"
            )


class MarkdownDocumentLoader(BaseDocumentLoader):
    """Loader for Markdown documents."""

    SUPPORTED_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}

    def can_load(self, file_path: Path) -> bool:
        """Check if this is a markdown file."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def load_content(self, file_path: Path) -> str:
        """Load markdown file content."""
        try:
            with open(file_path, encoding=self.encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encodings
            for encoding in ["gbk", "gb2312", "gb18030", "big5"]:
                try:
                    with open(file_path, encoding=encoding) as f:
                        content = f.read()
                        self.encoding = encoding  # Update for metadata
                        return content
                except UnicodeDecodeError:
                    continue
            raise DocumentProcessingError(
                f"Failed to decode file {file_path} with any supported encoding"
            )
        except Exception as e:
            raise DocumentProcessingError(
                f"Failed to read markdown file {file_path}: {str(e)}"
            )
