"""Gemini LLM adapter implementing LLMServicePort with OpenTelemetry integration."""

import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.application.ports.llm_service import LLMServicePort
from src.domain.entities.company import AnnualReportExtraction
from src.domain.entities.research_report import ResearchReportExtraction
from src.infrastructure.llm.langchain.gemini_adapter import GeminiAdapter
from src.infrastructure.llm.langchain.parsers import (
    AnnualReportParser,
    ResearchReportParser,
)
from src.infrastructure.llm.langchain.prompts import (
    AnnualReportPromptV1,
    ResearchReportPromptV1,
)
from src.infrastructure.monitoring import LLMMetrics, add_span_attributes, trace_span
from src.shared.config.settings import Settings
from src.shared.exceptions import LLMServiceError, ValidationError

logger = structlog.get_logger(__name__)


class GeminiLLMAdapter(LLMServicePort):
    """Gemini LLM adapter with monitoring integration."""

    def __init__(self, settings: Settings):
        """Initialize Gemini LLM adapter.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.gemini_adapter = GeminiAdapter()
        self.annual_report_parser = AnnualReportParser()
        self.research_report_parser = ResearchReportParser()
        self.annual_report_prompt = AnnualReportPromptV1()
        self.research_report_prompt = ResearchReportPromptV1()

    def extract_annual_report(
        self, document_content: str, metadata: dict[str, Any] | None = None
    ) -> AnnualReportExtraction:
        """Extract annual report data with OpenTelemetry tracing.

        Args:
            document_content: The document content to analyze.
            metadata: Optional metadata about the document.

        Returns:
            CompanyReport entity with extracted data.

        Raises:
            LLMServiceError: If extraction fails.
            ValidationError: If parsing/validation fails.
        """
        span_attributes = {
            "llm.operation": "extract_annual_report",
            "document.type": "annual_report",
            "document.size": len(document_content),
        }

        if metadata:
            if isinstance(metadata, dict):
                span_attributes.update(
                    {
                        "document.file_name": metadata.get("file_name", "unknown"),
                        "document.file_hash": metadata.get("file_hash", "unknown"),
                    }
                )
            else:
                span_attributes.update(
                    {
                        "document.file_name": metadata.file_name,
                        "document.file_hash": metadata.file_hash,
                    }
                )

        with trace_span("llm.extract_annual_report", span_attributes):
            start_time = time.time()
            input_tokens = 0
            output_tokens = 0

            try:
                # Get prompt template and format with document
                prompt_text = self.annual_report_prompt.format(
                    document_content=document_content,
                    company_name="未知公司",  # Default since not in metadata
                    document_type="年度报告",  # Default document type
                )

                # Create messages
                messages = [
                    SystemMessage(content="You are a financial document analyst."),
                    HumanMessage(content=prompt_text),
                ]

                # Log the prompt being used
                add_span_attributes(
                    {
                        "llm.prompt_version": self.annual_report_prompt.get_version(),
                        "llm.prompt_length": len(prompt_text),
                    }
                )

                logger.info(
                    "Calling Gemini API for annual report extraction",
                    document_size=len(document_content),
                    prompt_version=self.annual_report_prompt.get_version(),
                )

                # Call LLM
                result = self.gemini_adapter.invoke(messages)

                # Extract token usage from result if available
                if hasattr(result, "llm_output") and result.llm_output:
                    token_usage = result.llm_output.get("token_usage", {})
                    input_tokens = token_usage.get("prompt_tokens", 0)
                    output_tokens = token_usage.get("completion_tokens", 0)

                # Get response content from ChatResult/AIMessage
                if isinstance(result, str):
                    response_content = result
                elif hasattr(result, "content"):
                    response_content = result.content
                elif hasattr(result, "generations") and result.generations:
                    response_content = result.generations[0][0].text
                else:
                    response_content = str(result)

                # Parse response with retry logic
                logger.debug(
                    "Parsing LLM response",
                    response_length=len(response_content),
                )
                company_report = self.annual_report_parser.parse_with_retry(
                    response_content
                )

                # Record metrics
                duration = time.time() - start_time
                LLMMetrics.record_llm_call(
                    model=self.gemini_adapter.config.model_name,
                    prompt_version=self.annual_report_prompt.get_version(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_seconds=duration,
                    success=True,
                )

                logger.info(
                    "Annual report extraction completed",
                    company_name=company_report.company_name_full,
                    duration_seconds=duration,
                )

                return company_report

            except Exception as e:
                duration = time.time() - start_time
                LLMMetrics.record_llm_call(
                    model=self.gemini_adapter.config.model_name,
                    prompt_version=self.annual_report_prompt.get_version(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_seconds=duration,
                    success=False,
                    error=str(e),
                )

                logger.error(
                    "Annual report extraction failed",
                    error=str(e),
                    duration_seconds=duration,
                )

                if isinstance(e, (LLMServiceError, ValidationError)):
                    raise
                raise LLMServiceError(f"Failed to extract annual report: {str(e)}")

    def extract_research_report(
        self, document_content: str, metadata: dict[str, Any] | None = None
    ) -> ResearchReportExtraction:
        """Extract research report data with OpenTelemetry tracing.

        Args:
            document_content: The document content to analyze.
            metadata: Optional metadata about the document.

        Returns:
            ResearchReport entity with extracted data.

        Raises:
            LLMServiceError: If extraction fails.
            ValidationError: If parsing/validation fails.
        """
        span_attributes = {
            "llm.operation": "extract_research_report",
            "document.type": "research_report",
            "document.size": len(document_content),
        }

        if metadata:
            if isinstance(metadata, dict):
                span_attributes.update(
                    {
                        "document.file_name": metadata.get("file_name", "unknown"),
                        "document.file_hash": metadata.get("file_hash", "unknown"),
                    }
                )
            else:
                span_attributes.update(
                    {
                        "document.file_name": metadata.file_name,
                        "document.file_hash": metadata.file_hash,
                    }
                )

        with trace_span("llm.extract_research_report", span_attributes):
            start_time = time.time()
            input_tokens = 0
            output_tokens = 0

            try:
                # Get prompt template and format with document
                prompt_text = self.research_report_prompt.format(
                    document_content=document_content,
                    report_title="研究报告",  # Default since not in metadata
                )

                # Create messages
                messages = [
                    SystemMessage(content="You are a financial research analyst."),
                    HumanMessage(content=prompt_text),
                ]

                # Log the prompt being used
                add_span_attributes(
                    {
                        "llm.prompt_version": self.research_report_prompt.get_version(),
                        "llm.prompt_length": len(prompt_text),
                    }
                )

                logger.info(
                    "Calling Gemini API for research report extraction",
                    document_size=len(document_content),
                    prompt_version=self.research_report_prompt.get_version(),
                )

                # Call LLM
                result = self.gemini_adapter.invoke(messages)

                # Extract token usage from result if available
                if hasattr(result, "llm_output") and result.llm_output:
                    token_usage = result.llm_output.get("token_usage", {})
                    input_tokens = token_usage.get("prompt_tokens", 0)
                    output_tokens = token_usage.get("completion_tokens", 0)

                # Get response content from ChatResult/AIMessage
                if isinstance(result, str):
                    response_content = result
                elif hasattr(result, "content"):
                    response_content = result.content
                elif hasattr(result, "generations") and result.generations:
                    response_content = result.generations[0][0].text
                else:
                    response_content = str(result)

                # Parse response with retry logic
                logger.debug(
                    "Parsing LLM response",
                    response_length=len(response_content),
                )
                research_report = self.research_report_parser.parse_with_retry(
                    response_content
                )

                # Record metrics
                duration = time.time() - start_time
                LLMMetrics.record_llm_call(
                    model=self.gemini_adapter.config.model_name,
                    prompt_version=self.research_report_prompt.get_version(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_seconds=duration,
                    success=True,
                )

                logger.info(
                    "Research report extraction completed",
                    report_title=research_report.report_title,
                    duration_seconds=duration,
                )

                return research_report

            except Exception as e:
                duration = time.time() - start_time
                LLMMetrics.record_llm_call(
                    model=self.gemini_adapter.config.model_name,
                    prompt_version=self.research_report_prompt.get_version(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_seconds=duration,
                    success=False,
                    error=str(e),
                )

                logger.error(
                    "Research report extraction failed",
                    error=str(e),
                    duration_seconds=duration,
                )

                if isinstance(e, (LLMServiceError, ValidationError)):
                    raise
                raise LLMServiceError(f"Failed to extract research report: {str(e)}")

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the current model configuration.

        Returns:
            Dictionary with model configuration details.
        """
        model_info = self.gemini_adapter.get_model_info()
        return {
            "adapter": "gemini",
            "name": model_info.get("model_name", "unknown"),
            "prompt_version": self.annual_report_prompt.get_version(),
            "model_info": model_info,
            "annual_report_prompt_version": self.annual_report_prompt.get_version(),
            "research_report_prompt_version": self.research_report_prompt.get_version(),
        }

    def detect_document_type(self, content: str) -> str:
        """Detect the type of document from its content.

        Args:
            content: Document content to analyze.

        Returns:
            Detected document type ('annual_report' or 'research_report').
        """
        # Simple heuristic-based detection
        content_lower = content.lower()

        # Keywords for annual reports
        annual_keywords = [
            "年度报告",
            "年报",
            "annual report",
            "财务报表",
            "审计报告",
            "股东大会",
            "董事会报告",
        ]

        # Keywords for research reports
        research_keywords = [
            "投资评级",
            "买入",
            "增持",
            "持有",
            "卖出",
            "目标价",
            "估值",
            "研究报告",
            "分析师",
            "证券研究",
        ]

        # Count keyword occurrences
        annual_score = sum(1 for keyword in annual_keywords if keyword in content_lower)
        research_score = sum(
            1 for keyword in research_keywords if keyword in content_lower
        )

        # Default to annual report if unclear
        return "research_report" if research_score > annual_score else "annual_report"
