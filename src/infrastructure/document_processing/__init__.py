"""Document processing infrastructure."""

from .base import (
    BaseDocumentLoader,
    DocumentMetadata,
    ProcessedDocument,
)
from .loader import DocumentLoader
from .text_loader import (
    MarkdownDocumentLoader,
    TextDocumentLoader,
)

__all__ = [
    # Base classes
    "BaseDocumentLoader",
    "DocumentMetadata",
    "ProcessedDocument",
    # Loaders
    "DocumentLoader",
    "TextDocumentLoader",
    "MarkdownDocumentLoader",
]
