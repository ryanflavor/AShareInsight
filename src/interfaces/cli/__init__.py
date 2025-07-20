"""CLI interface module."""

from .batch_extract import batch_extract
from .extract_document import extract_document

__all__ = ["extract_document", "batch_extract"]
