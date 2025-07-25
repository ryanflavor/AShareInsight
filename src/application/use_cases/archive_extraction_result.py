"""Use case for archiving LLM extraction results.

This module implements the business logic for archiving raw LLM extraction results
to ensure traceability and enable future model retraining.
"""

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

import structlog
from opentelemetry import trace
from sqlalchemy.exc import IntegrityError, OperationalError

from src.application.ports.source_document_repository import (
    SourceDocumentRepositoryPort,
)
from src.application.use_cases.update_master_data import UpdateMasterDataUseCase
from src.domain.entities.source_document import SourceDocument, SourceDocumentMetadata

logger = structlog.get_logger(__name__)


class ArchiveExtractionResultUseCase:
    """Use case for archiving LLM extraction results to the database."""

    def __init__(
        self,
        repository: SourceDocumentRepositoryPort,
        update_master_data_use_case: UpdateMasterDataUseCase | None = None,
    ):
        """Initialize the use case with repository dependency.

        Args:
            repository: The source document repository implementation
            update_master_data_use_case: Optional use case for updating master data
        """
        self.repository = repository
        self.update_master_data_use_case = update_master_data_use_case

    async def execute(
        self,
        raw_llm_output: dict[str, Any],
        metadata: dict[str, Any] | SourceDocumentMetadata,
    ) -> UUID:
        """Archive the raw LLM extraction result.

        Args:
            raw_llm_output: Complete raw JSON response from LLM
            metadata: Document metadata containing company_code, doc_type, etc.

        Returns:
            UUID: The ID of the archived document

        Raises:
            ValueError: If required metadata fields are missing
            IntegrityError: If document already exists (duplicate hash)
            OperationalError: If database operation fails
        """
        import time

        start_time = time.time()

        # Get trace ID from current OpenTelemetry span
        current_span = trace.get_current_span()
        if current_span.is_recording():
            trace_id = format(current_span.get_span_context().trace_id, "032x")
        else:
            trace_id = "no_active_trace"

        logger.info(
            "archiving_extraction_result",
            trace_id=trace_id,
            company_code=(
                metadata.get("company_code")
                if isinstance(metadata, dict)
                else metadata.company_code
            ),
        )

        try:
            # Convert metadata to SourceDocumentMetadata if needed
            if isinstance(metadata, dict):
                doc_metadata = self._dict_to_metadata(metadata)
            else:
                doc_metadata = metadata

            # File hash MUST be provided from the file content
            # Do NOT calculate hash from LLM output to avoid inconsistencies
            if not doc_metadata.file_hash:
                raise ValueError(
                    "file_hash must be provided in metadata. "
                    "Hash should be calculated from file content, not LLM output."
                )

            # Check if document already exists
            if await self.repository.exists(doc_metadata.file_hash):
                existing = await self.repository.find_by_file_hash(
                    doc_metadata.file_hash
                )

                # Record metrics for already existing document
                from src.infrastructure.monitoring.archive_metrics import ArchiveMetrics

                duration = time.time() - start_time
                ArchiveMetrics.record_archive_operation(
                    operation="save",
                    company_code=doc_metadata.company_code,
                    doc_type=doc_metadata.doc_type.value,
                    doc_id=str(existing.doc_id) if existing else None,
                    file_hash=doc_metadata.file_hash,
                    raw_data_size=len(json.dumps(raw_llm_output)),
                    duration_seconds=duration,
                    success=True,
                    already_exists=True,
                )

                logger.info(
                    "document_already_archived",
                    trace_id=trace_id,
                    doc_id=str(existing.doc_id) if existing else None,
                    file_hash=doc_metadata.file_hash,
                    company_code=doc_metadata.company_code,
                )
                if not existing or not existing.doc_id:
                    raise ValueError("Invalid existing document state")
                return existing.doc_id

            # Create SourceDocument entity
            source_document = SourceDocument(
                doc_id=None,  # Will be assigned by database
                company_code=doc_metadata.company_code,
                doc_type=doc_metadata.doc_type,
                doc_date=doc_metadata.doc_date,
                report_title=doc_metadata.report_title,
                file_path=doc_metadata.file_path,
                file_hash=doc_metadata.file_hash,
                raw_llm_output=raw_llm_output,
                extraction_metadata=self._build_extraction_metadata(raw_llm_output),
                original_content=(
                    getattr(doc_metadata, "original_content", None)
                    if hasattr(doc_metadata, "original_content")
                    else (
                        metadata.get("original_content")
                        if isinstance(metadata, dict)
                        else None
                    )
                ),
                processing_status="completed",
                error_message=None,
                created_at=None,  # Will be set by database
            )

            # Save to repository with retry logic
            doc_id = await self._save_with_retry(source_document)

            # Record metrics
            import time

            from src.infrastructure.monitoring.archive_metrics import ArchiveMetrics

            duration = time.time() - start_time if "start_time" in locals() else 0.0

            ArchiveMetrics.record_archive_operation(
                operation="save",
                company_code=doc_metadata.company_code,
                doc_type=doc_metadata.doc_type.value,
                doc_id=str(doc_id),
                file_hash=doc_metadata.file_hash,
                raw_data_size=len(json.dumps(raw_llm_output)),
                duration_seconds=duration,
                success=True,
                already_exists=False,
            )

            logger.info(
                "extraction_result_archived",
                trace_id=trace_id,
                doc_id=str(doc_id),
                company_code=doc_metadata.company_code,
                doc_type=doc_metadata.doc_type.value,
                file_hash=doc_metadata.file_hash,
                raw_output_size=len(json.dumps(raw_llm_output)),
            )

            # Trigger master data fusion if use case is available
            if self.update_master_data_use_case:
                try:
                    logger.info(
                        "triggering_master_data_fusion",
                        trace_id=trace_id,
                        doc_id=str(doc_id),
                        company_code=doc_metadata.company_code,
                    )

                    fusion_stats = await self.update_master_data_use_case.execute(
                        doc_id
                    )

                    logger.info(
                        "master_data_fusion_completed",
                        trace_id=trace_id,
                        doc_id=str(doc_id),
                        **fusion_stats,
                    )
                except Exception as e:
                    # Log fusion error but don't fail the archival
                    logger.error(
                        "master_data_fusion_failed",
                        trace_id=trace_id,
                        doc_id=str(doc_id),
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Fusion failures should not affect archival success

            return doc_id

        except IntegrityError as e:
            logger.error(
                "archive_integrity_error",
                trace_id=trace_id,
                error=str(e),
                company_code=(
                    doc_metadata.company_code
                    if "doc_metadata" in locals()
                    else (
                        metadata.get("company_code", "unknown")
                        if isinstance(metadata, dict)
                        else getattr(metadata, "company_code", "unknown")
                    )
                ),
            )
            raise
        except OperationalError as e:
            logger.error(
                "archive_database_error",
                trace_id=trace_id,
                error=str(e),
                company_code=(
                    doc_metadata.company_code
                    if "doc_metadata" in locals()
                    else (
                        metadata.get("company_code", "unknown")
                        if isinstance(metadata, dict)
                        else getattr(metadata, "company_code", "unknown")
                    )
                ),
            )
            raise
        except ValueError as e:
            # Check if it's a company not found error for research reports
            if (
                "not found in database" in str(e)
                and "research report" in str(e).lower()
            ):
                logger.warning(
                    "skipping_research_report_no_company",
                    trace_id=trace_id,
                    company_code=(
                        doc_metadata.company_code
                        if "doc_metadata" in locals()
                        else (
                            metadata.get("company_code", "unknown")
                            if isinstance(metadata, dict)
                            else getattr(metadata, "company_code", "unknown")
                        )
                    ),
                    reason=(
                        "Company not found in database, "
                        "skipping research report archival"
                    ),
                )
                # Return a special UUID to indicate skipped
                from uuid import uuid4

                return (
                    uuid4()
                )  # Return a dummy UUID to indicate success without archiving
            else:
                # Re-raise other ValueError exceptions
                raise
        except Exception as e:
            logger.error(
                "archive_unexpected_error",
                trace_id=trace_id,
                error=str(e),
                error_type=type(e).__name__,
                company_code=(
                    doc_metadata.company_code
                    if "doc_metadata" in locals()
                    else (
                        metadata.get("company_code", "unknown")
                        if isinstance(metadata, dict)
                        else getattr(metadata, "company_code", "unknown")
                    )
                ),
            )
            raise

    async def _save_with_retry(
        self, document: SourceDocument, max_retries: int = 3
    ) -> UUID:
        """Save document with exponential backoff retry.

        Args:
            document: The source document to save
            max_retries: Maximum number of retry attempts

        Returns:
            UUID: The saved document ID

        Raises:
            OperationalError: If all retries fail
        """
        for attempt in range(max_retries):
            try:
                return await self.repository.save(document)
            except OperationalError as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    "archive_save_retry",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    wait_time=wait_time,
                    error=str(e),
                )
                await asyncio.sleep(wait_time)

        # This should never be reached due to the raise in the loop
        raise OperationalError(
            "Failed to save document after all retries",
            params=None,
            orig=Exception("All retries exhausted"),
        )

    def _dict_to_metadata(self, metadata: dict[str, Any]) -> SourceDocumentMetadata:
        """Convert dictionary metadata to SourceDocumentMetadata.

        Args:
            metadata: Dictionary containing metadata fields

        Returns:
            SourceDocumentMetadata instance

        Raises:
            ValueError: If required fields are missing
        """
        required_fields = ["company_code", "doc_type", "doc_date"]
        missing_fields = [f for f in required_fields if f not in metadata]

        if missing_fields:
            raise ValueError(f"Missing required metadata fields: {missing_fields}")

        # Handle different date formats
        from datetime import date

        doc_date = metadata["doc_date"]
        if isinstance(doc_date, str):
            try:
                doc_date = date.fromisoformat(doc_date)
            except ValueError as e:
                raise ValueError(f"Invalid date format: {doc_date}") from e
        elif not isinstance(doc_date, date):
            raise ValueError(f"Invalid doc_date type: {type(doc_date)}")

        # Import here to avoid circular dependency
        from src.domain.entities.extraction import DocumentType as DocType

        return SourceDocumentMetadata(
            company_code=metadata["company_code"],
            doc_type=DocType(metadata["doc_type"]),
            doc_date=doc_date,
            report_title=metadata.get("report_title"),
            file_path=metadata.get("file_path"),
            file_hash=metadata.get("file_hash"),
            original_content=metadata.get("original_content"),
        )

    def _calculate_hash(self, data: dict[str, Any]) -> str:
        """Calculate SHA-256 hash of the data.

        Args:
            data: Dictionary to hash

        Returns:
            str: Hexadecimal SHA-256 hash
        """
        # Ensure consistent JSON serialization
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _build_extraction_metadata(self, raw_output: dict[str, Any]) -> dict[str, Any]:
        """Build extraction metadata from raw LLM output.

        Args:
            raw_output: Raw LLM output containing metadata

        Returns:
            Dictionary with extraction metadata
        """
        # Extract metadata if it exists in the raw output
        if "extraction_metadata" in raw_output:
            return dict(raw_output["extraction_metadata"])

        # Build basic metadata from available information
        metadata = {}

        if "model_version" in raw_output:
            metadata["model_version"] = raw_output["model_version"]

        if "processing_time_seconds" in raw_output:
            metadata["processing_time_seconds"] = raw_output["processing_time_seconds"]

        if "timestamp" in raw_output:
            metadata["extraction_time"] = raw_output["timestamp"]

        # Add token usage if available
        for key in ["token_usage", "usage", "tokens"]:
            if key in raw_output:
                metadata["token_usage"] = raw_output[key]
                break

        return metadata
