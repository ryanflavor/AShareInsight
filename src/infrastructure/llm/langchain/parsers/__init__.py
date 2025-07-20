"""LangChain output parsers for document extraction."""

from src.domain.entities import (
    AnnualReportExtraction,
    ResearchReportExtraction,
)

from .base import BaseOutputParser, MarkdownExtractor
from .document_parsers import AnnualReportParser, ResearchReportParser
from .enhanced_parser import EnhancedOutputParser, ParsingMetrics


def get_annual_report_parser() -> EnhancedOutputParser[AnnualReportExtraction]:
    """Get an enhanced parser for annual report extraction.

    Returns:
        Configured parser for annual reports.
    """
    return EnhancedOutputParser(
        AnnualReportExtraction, parser_name="AnnualReportParser"
    )


def get_research_report_parser() -> EnhancedOutputParser[ResearchReportExtraction]:
    """Get an enhanced parser for research report extraction.

    Returns:
        Configured parser for research reports.
    """
    return EnhancedOutputParser(
        ResearchReportExtraction, parser_name="ResearchReportParser"
    )


__all__ = [
    "BaseOutputParser",
    "MarkdownExtractor",
    "AnnualReportParser",
    "ResearchReportParser",
    "EnhancedOutputParser",
    "ParsingMetrics",
    "get_annual_report_parser",
    "get_research_report_parser",
]
