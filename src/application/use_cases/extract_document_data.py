"""Extract document data use case."""

import asyncio
import time
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

from src.application.ports.llm_service import LLMServicePort
from src.application.ports.source_document_repository import (
    SourceDocumentRepositoryPort,
)
from src.domain.entities import (
    AnnualReportExtraction,
    DocumentType,
    ExtractionMetadata,
    ExtractionResult,
    ResearchReportExtraction,
)
from src.infrastructure.document_processing import DocumentLoader, ProcessedDocument
from src.shared.exceptions import DocumentProcessingError, LLMServiceError

logger = structlog.get_logger(__name__)


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

    def __init__(
        self,
        llm_service: LLMServicePort,
        archive_repository: SourceDocumentRepositoryPort | None = None,
    ):
        """Initialize use case.

        Args:
            llm_service: LLM service implementation.
            archive_repository: Optional repository for archiving extraction results.
        """
        self.llm_service = llm_service
        self.document_loader = DocumentLoader()
        self.state = ProcessingState()
        self.archive_use_case = None

        # Import here to avoid circular dependency
        from src.application.use_cases.archive_extraction_result import (
            ArchiveExtractionResultUseCase,
        )

        if archive_repository:
            self.archive_use_case = ArchiveExtractionResultUseCase(archive_repository)

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
                doc_type = self._detect_document_type(document.content, str(file_path))

            # Step 3: Extract data with LLM
            self.state.update(
                ProcessingStatus.EXTRACTING,
                "正在调用LLM进行数据提取（预计需要2-3分钟）...",
                30.0,
            )

            extraction_data, extraction_metadata = await self._extract_data(
                doc_type, document.content, company_info
            )

            # Step 3.5: Archive extraction result if archiving is enabled
            if self.archive_use_case:
                self.state.update(
                    ProcessingStatus.EXTRACTING, "正在归档原始数据...", 80.0
                )

                # Prepare raw LLM output for archiving
                raw_llm_output = self._prepare_raw_output(
                    extraction_data, extraction_metadata, doc_type
                )

                # Prepare metadata for archiving
                archive_metadata = self._prepare_archive_metadata(
                    document, doc_type, company_info, file_path, extraction_data
                )

                try:
                    archive_result = await self.archive_use_case.execute(
                        raw_llm_output=raw_llm_output,
                        metadata=archive_metadata,
                    )

                    # Check if it was skipped (indicated by the warning log)
                    if "skipping_research_report_no_company" in str(archive_result):
                        logger.info(
                            "archiving_skipped_no_company",
                            company_code=company_info.get("company_code"),
                            doc_type=doc_type.value,
                            reason=(
                                "Company not found, research report extraction "
                                "continues without archiving"
                            ),
                        )
                except Exception as e:
                    # Log error but don't fail the extraction
                    logger.error(
                        "archiving_failed",
                        error=str(e),
                        company_code=company_info.get("company_code"),
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
            raise DocumentProcessingError(f"Failed to load document: {str(e)}") from e

    def _detect_document_type(self, content: str, file_path: str) -> DocumentType:
        """Detect document type from content."""
        return self.llm_service.detect_document_type(content, file_path)

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

    def get_progress_info(self) -> dict[str, Any]:
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

    def _prepare_raw_output(
        self,
        extraction_data: AnnualReportExtraction | ResearchReportExtraction,
        extraction_metadata: ExtractionMetadata,
        doc_type: DocumentType,
    ) -> dict[str, Any]:
        """Prepare raw LLM output for archiving.

        Args:
            extraction_data: The extracted data entity
            extraction_metadata: The extraction metadata
            doc_type: The document type

        Returns:
            Dictionary representing the raw LLM output
        """
        # Convert entities to dict for archiving
        # Use model_dump with mode='json' to handle datetime serialization
        raw_output = {
            "document_type": doc_type.value,
            "extraction_data": extraction_data.model_dump(mode="json"),
            "extraction_metadata": extraction_metadata.model_dump(mode="json"),
            "status": "success",
            "timestamp": extraction_metadata.extraction_timestamp.isoformat(),
        }

        return raw_output

    def _prepare_archive_metadata(
        self,
        document: ProcessedDocument,
        doc_type: DocumentType,
        company_info: dict[str, str],
        file_path: str | Path,
        extraction_data: AnnualReportExtraction | ResearchReportExtraction,
    ) -> dict[str, Any]:
        """Prepare metadata for archiving.

        Args:
            document: The processed document
            doc_type: The document type
            company_info: Company information from filename parsing
            file_path: Original file path
            extraction_data: Extracted data from LLM containing company_code

        Returns:
            Dictionary with archive metadata
        """
        # Extract date from filename or use today
        import re
        from datetime import date as dt

        doc_date = dt.today()
        file_name = Path(file_path).name

        # Try to extract date from filename (e.g., 2024 or 20240120)
        date_match = re.search(r"(\d{8}|\d{4})", file_name)
        if date_match:
            date_str = date_match.group(1)
            if len(date_str) == 4:
                # Year only, assume end of year
                doc_date = dt(int(date_str), 12, 31)
            else:
                # Full date YYYYMMDD
                doc_date = dt(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))

        # Build report title
        company_name = company_info.get("company_name", "")
        if doc_type == DocumentType.ANNUAL_REPORT:
            report_title = f"{company_name}{doc_date.year}年年度报告"
        else:
            report_title = f"{company_name}研究报告"

        # Get company_code from extraction_data (extracted by LLM)
        company_code = (
            extraction_data.company_code
            if hasattr(extraction_data, "company_code")
            else ""
        )

        return {
            "company_code": company_code,
            "doc_type": doc_type.value,
            "doc_date": doc_date,
            "report_title": report_title,
            "file_path": str(file_path),
            "file_hash": document.metadata.file_hash,
            "original_content": document.content,  # Add the original document content
        }
