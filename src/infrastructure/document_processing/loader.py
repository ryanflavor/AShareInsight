"""Unified document loader with automatic format detection."""

from pathlib import Path

from src.shared.exceptions import DocumentProcessingError

from .base import BaseDocumentLoader, ProcessedDocument
from .text_loader import MarkdownDocumentLoader, TextDocumentLoader


class DocumentLoader:
    """Main document loader that automatically selects the appropriate loader."""

    def __init__(self, encoding: str = "utf-8"):
        """Initialize document loader.

        Args:
            encoding: Default encoding for reading files.
        """
        self.encoding = encoding
        self._loaders = [
            TextDocumentLoader(encoding),
            MarkdownDocumentLoader(encoding),
        ]

    def load(self, file_path: str | Path) -> ProcessedDocument:
        """Load a document automatically detecting its type.

        Args:
            file_path: Path to the document.

        Returns:
            ProcessedDocument with content and metadata.

        Raises:
            DocumentProcessingError: If no loader can handle the file.
        """
        path = Path(file_path) if isinstance(file_path, str) else file_path

        # Find appropriate loader
        loader = self._find_loader(path)
        if not loader:
            raise DocumentProcessingError(
                f"No loader available for file type: {path.suffix}"
            )

        return loader.load(path)

    def load_with_company_info(
        self,
        file_path: str | Path,
        company_name: str | None = None,
        document_type: str | None = None,
    ) -> tuple[ProcessedDocument, dict[str, str]]:
        """Load document and extract company info from filename if not provided.

        Args:
            file_path: Path to the document.
            company_name: Optional company name override.
            document_type: Optional document type override.

        Returns:
            Tuple of (ProcessedDocument, company_info_dict).
        """
        doc = self.load(file_path)

        # Extract info from filename if not provided
        file_name = Path(file_path).stem  # Remove extension

        if not company_name:
            # Try to extract company name from filename
            # Common patterns: "公司名_年报", "公司名_2024年年度报告"
            parts = file_name.split("_")
            if parts:
                company_name = parts[0]

        if not document_type:
            # Try to detect document type
            if any(keyword in file_name for keyword in ["年报", "年度报告", "annual"]):
                document_type = "年度报告"
            elif any(
                keyword in file_name for keyword in ["研报", "研究报告", "research"]
            ):
                document_type = "研究报告"
            else:
                document_type = "未知文档类型"

        company_info = {
            "company_name": company_name or "未知公司",
            "document_type": document_type,
        }

        return doc, company_info

    def _find_loader(self, file_path: Path) -> BaseDocumentLoader | None:
        """Find appropriate loader for the file.

        Args:
            file_path: Path to the file.

        Returns:
            Loader instance or None if no loader can handle the file.
        """
        for loader in self._loaders:
            if loader.can_load(file_path):
                return loader
        return None

    def get_supported_extensions(self) -> set[str]:
        """Get all supported file extensions.

        Returns:
            Set of supported extensions.
        """
        extensions = set()
        for loader in self._loaders:
            if hasattr(loader, "SUPPORTED_EXTENSIONS"):
                extensions.update(loader.SUPPORTED_EXTENSIONS)
        return extensions
