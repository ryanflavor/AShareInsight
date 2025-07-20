"""Extract document data use case."""

import asyncio
import time
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from src.application.ports.llm_service import LLMServicePort
from src.domain.entities import (
    AnnualReportExtraction,
    DocumentType,
    ExtractionMetadata,
    ExtractionResult,
    ResearchReportExtraction,
)
from src.infrastructure.document_processing import DocumentLoader, ProcessedDocument
from src.shared.exceptions import DocumentProcessingError, LLMServiceError


class ProcessingStatus(str, Enum):
    """Status of document processing."""

    PENDING = "pending"
    LOADING = "loading"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingState(BaseModel):
    """Current state of document processing."""

    status: ProcessingStatus = ProcessingStatus.PENDING
    current_step: str = "初始化"
    progress_percentage: float = 0.0
    start_time: float | None = None
    error_message: str | None = None

    def update(self, status: ProcessingStatus, step: str, progress: float) -> None:
        """Update processing state."""
        self.status = status
        self.current_step = step
        self.progress_percentage = progress


class ExtractDocumentDataUseCase:
    """Use case for extracting data from documents."""

    def __init__(self, llm_service: LLMServicePort):
        """Initialize use case.

        Args:
            llm_service: LLM service implementation.
        """
        self.llm_service = llm_service
        self.document_loader = DocumentLoader()
        self.state = ProcessingState()

    async def execute(
        self,
        file_path: str | Path,
        company_name: str | None = None,
        document_type_override: str | None = None,
    ) -> ExtractionResult:
        """Execute the document extraction process.

        Args:
            file_path: Path to the document file.
            company_name: Optional company name override.
            document_type_override: Optional document type override.

        Returns:
            Complete extraction result with metadata.

        Raises:
            DocumentProcessingError: If document loading fails.
            LLMServiceError: If extraction fails.
        """
        self.state = ProcessingState()
        self.state.start_time = time.time()

        try:
            # Step 1: Load document
            self.state.update(ProcessingStatus.LOADING, "正在加载文档...", 10.0)

            document, company_info = await self._load_document(
                file_path, company_name, document_type_override
            )

            # Step 2: Detect document type
            self.state.update(ProcessingStatus.LOADING, "正在检测文档类型...", 20.0)

            # Use override if provided, otherwise detect
            if document_type_override:
                doc_type = DocumentType(document_type_override)
            else:
                doc_type = self._detect_document_type(document.content)

            # Step 3: Extract data with LLM
            self.state.update(
                ProcessingStatus.EXTRACTING,
                "正在调用LLM进行数据提取（预计需要2-3分钟）...",
                30.0,
            )

            extraction_data, extraction_metadata = await self._extract_data(
                doc_type, document.content, company_info
            )

            # Step 4: Create final result
            self.state.update(ProcessingStatus.COMPLETED, "提取完成", 100.0)

            processing_time = time.time() - self.state.start_time
            extraction_metadata.processing_time_seconds = processing_time
            extraction_metadata.file_hash = document.metadata.file_hash

            result = ExtractionResult(
                document_type=doc_type,
                extraction_data=extraction_data,
                extraction_metadata=extraction_metadata,
                raw_llm_response="",  # Will be set by the LLM service
            )

            return result

        except Exception as e:
            self.state.update(ProcessingStatus.FAILED, f"处理失败: {str(e)}", 0.0)
            self.state.error_message = str(e)
            raise

    async def _load_document(
        self,
        file_path: str | Path,
        company_name: str | None,
        document_type_override: str | None,
    ) -> tuple[ProcessedDocument, dict[str, str]]:
        """Load document with company information."""
        try:
            document, company_info = self.document_loader.load_with_company_info(
                file_path, company_name, document_type_override
            )
            return document, company_info
        except Exception as e:
            raise DocumentProcessingError(f"Failed to load document: {str(e)}")

    def _detect_document_type(self, content: str) -> DocumentType:
        """Detect document type from content."""
        return self.llm_service.detect_document_type(content)

    async def _extract_data(
        self, doc_type: DocumentType, content: str, company_info: dict[str, str]
    ) -> tuple[AnnualReportExtraction | ResearchReportExtraction, ExtractionMetadata]:
        """Extract data using appropriate LLM service method."""
        start_time = time.time()

        if doc_type == DocumentType.ANNUAL_REPORT:
            # Note: extract_annual_report only takes content and optional metadata
            extraction = await asyncio.to_thread(
                self.llm_service.extract_annual_report,
                content,
                {
                    "company_name": company_info["company_name"],
                    "document_type": company_info["document_type"],
                },
            )
        elif doc_type == DocumentType.RESEARCH_REPORT:
            extraction = await asyncio.to_thread(
                self.llm_service.extract_research_report, content
            )
        else:
            raise LLMServiceError(f"Unsupported document type: {doc_type}")

        # Create metadata
        processing_time = time.time() - start_time
        metadata = ExtractionMetadata(
            model_version=self.llm_service.get_model_info()["name"],
            prompt_version=self.llm_service.get_model_info()["prompt_version"],
            processing_time_seconds=processing_time,
            token_usage={
                "input_tokens": 0,  # Would need to get from LLM service
                "output_tokens": 0,
                "total_tokens": 0,
            },
            file_hash="",  # Set by caller
        )

        return extraction, metadata

    def get_current_state(self) -> ProcessingState:
        """Get current processing state.

        Returns:
            Current processing state with progress information.
        """
        return self.state

    def get_progress_info(self) -> dict[str, any]:
        """Get user-friendly progress information.

        Returns:
            Progress information for display to user.
        """
        elapsed_time = 0.0
        if self.state.start_time:
            elapsed_time = time.time() - self.state.start_time

        estimated_total_time = 180.0  # 3 minutes for LLM processing
        estimated_remaining = max(0, estimated_total_time - elapsed_time)

        return {
            "status": self.state.status.value,
            "current_step": self.state.current_step,
            "progress_percentage": self.state.progress_percentage,
            "elapsed_time_seconds": elapsed_time,
            "estimated_remaining_seconds": estimated_remaining,
            "error_message": self.state.error_message,
        }
