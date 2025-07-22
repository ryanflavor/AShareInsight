"""Document-specific parsers for annual and research reports."""

from __future__ import annotations

from src.domain.entities import (
    AnnualReportExtraction,
    ResearchReportExtraction,
)

from .enhanced_parser import EnhancedOutputParser


class AnnualReportParser(EnhancedOutputParser[AnnualReportExtraction]):
    """Parser for annual report extractions."""

    def __init__(self):
        """Initialize annual report parser."""
        super().__init__(AnnualReportExtraction, parser_name="AnnualReportParser")

    def get_format_instructions(self) -> str:
        """Get format instructions for annual report extraction."""
        return (
            "输出必须是有效的JSON格式，可以直接被JSON解析器解析。\n"
            "所有数值类型字段（如holding_percentage, importance_score等）"
            "必须是数字，不能是字符串。\n"
            "如果某个字段没有找到对应信息，使用null而不是空字符串。\n"
            "source_sentences必须是原文的准确引用，不能改写或总结。"
        )


class ResearchReportParser(EnhancedOutputParser[ResearchReportExtraction]):
    """Parser for research report extractions."""

    def __init__(self):
        """Initialize research report parser."""
        super().__init__(ResearchReportExtraction, parser_name="ResearchReportParser")

    def get_format_instructions(self) -> str:
        """Get format instructions for research report extraction."""
        return (
            "输出必须是有效的JSON格式。\n"
            "所有数值字段必须是数字类型。\n"
            "如果某个字段没有找到信息，使用null。\n"
            "source_sentences必须是原文准确引用。"
        )
