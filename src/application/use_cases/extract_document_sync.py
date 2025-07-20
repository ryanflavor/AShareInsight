"""Synchronous document extraction use case for CLI."""

import time
import uuid
from typing import Any

import structlog

from src.application.ports.llm_service import LLMServicePort
from src.domain.entities.extraction import DocumentExtractionResult
from src.infrastructure.monitoring import LLMMetrics, trace_span
from src.shared.config.settings import Settings
from src.shared.exceptions import LLMServiceError, ValidationError

logger = structlog.get_logger()


class ExtractDocumentDataUseCase:
    """Synchronous use case for extracting data from documents."""

    def __init__(self, llm_service: LLMServicePort, settings: Settings):
        """Initialize the use case.

        Args:
            llm_service: LLM service implementation.
            settings: Application settings.
        """
        self.llm_service = llm_service
        self.settings = settings

    def execute(
        self,
        document_content: str,
        document_type: str,
        document_metadata: dict[str, Any] | None = None,
    ) -> DocumentExtractionResult:
        """Execute document extraction synchronously.

        Args:
            document_content: Content of the document to extract.
            document_type: Type of document (annual_report or research_report).
            document_metadata: Optional metadata about the document.

        Returns:
            DocumentExtractionResult with extracted data or error information.
        """
        span_attributes = {
            "usecase.operation": "extract_document",
            "document.type": document_type,
            "document.size": len(document_content),
        }

        if document_metadata:
            if isinstance(document_metadata, dict):
                span_attributes.update(
                    {
                        "document.file_name": document_metadata.get(
                            "file_name", "unknown"
                        ),
                        "document.file_hash": document_metadata.get(
                            "file_hash", "unknown"
                        ),
                    }
                )
            else:
                span_attributes.update(
                    {
                        "document.file_name": getattr(
                            document_metadata, "file_name", "unknown"
                        ),
                        "document.file_hash": getattr(
                            document_metadata, "file_hash", "unknown"
                        ),
                    }
                )

        with trace_span("usecase.extract_document", span_attributes):
            document_id = str(uuid.uuid4())
            start_time = time.time()

            try:
                # Call appropriate extraction method based on document type
                if document_type == "annual_report":
                    extracted_data = self.llm_service.extract_annual_report(
                        document_content, document_metadata
                    )
                elif document_type == "research_report":
                    extracted_data = self.llm_service.extract_research_report(
                        document_content, document_metadata
                    )
                else:
                    raise ValueError(f"Unsupported document type: {document_type}")

                # Get model info
                model_info = self.llm_service.get_model_info()

                # Calculate processing time
                processing_time = time.time() - start_time

                # Create successful result
                result = DocumentExtractionResult(
                    document_id=document_id,
                    status="success",
                    document_type=document_type,
                    extracted_data=extracted_data,
                    processing_time_seconds=processing_time,
                    model_version=model_info.get("model_info", {}).get("model_name"),
                    prompt_version=(
                        model_info.get("annual_report_prompt_version")
                        if document_type == "annual_report"
                        else model_info.get("research_report_prompt_version")
                    ),
                    # Token usage will be populated by the LLM service
                    token_usage=None,
                )

                # Record document processing metrics
                LLMMetrics.record_document_processing(
                    document_type=document_type,
                    document_size=len(document_content),
                    processing_time=processing_time,
                    success=True,
                )

                return result

            except (LLMServiceError, ValidationError) as e:
                # Handle expected errors
                processing_time = time.time() - start_time

                result = DocumentExtractionResult(
                    document_id=document_id,
                    status="failed",
                    document_type=document_type,
                    error=str(e),
                    processing_time_seconds=processing_time,
                )

                # Record failure metrics
                LLMMetrics.record_document_processing(
                    document_type=document_type,
                    document_size=len(document_content),
                    processing_time=processing_time,
                    success=False,
                    error=str(e),
                )

                return result

            except Exception as e:
                # Handle unexpected errors
                processing_time = time.time() - start_time

                # Log the full traceback for debugging
                import traceback

                logger.error(
                    "Unexpected error in extract_document_sync",
                    error=str(e),
                    traceback=traceback.format_exc(),
                )

                result = DocumentExtractionResult(
                    document_id=document_id,
                    status="failed",
                    document_type=document_type,
                    error=f"Unexpected error: {str(e)}",
                    processing_time_seconds=processing_time,
                )

                # Record failure metrics
                LLMMetrics.record_document_processing(
                    document_type=document_type,
                    document_size=len(document_content),
                    processing_time=processing_time,
                    success=False,
                    error=str(e),
                )

                return result
