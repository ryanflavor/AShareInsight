"""Source Document entity for archiving LLM extraction results.

This module defines the SourceDocument entity that represents raw LLM extraction
results stored in the database for traceability and retraining purposes.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from .extraction import DocumentType as DocType


class SourceDocument(BaseModel):
    """Represents an archived source document with its LLM extraction result.

    This entity stores the complete raw output from LLM extraction along with
    metadata for future reference, auditing, and model retraining.
    """

    doc_id: UUID | None = Field(None, description="Unique document identifier")
    company_code: str = Field(
        ...,
        max_length=10,
        description="Stock code of the company (e.g., '300257')",
        examples=["300257", "002747"],
    )
    doc_type: DocType = Field(
        ..., description="Type of document: annual_report or research_report"
    )
    doc_date: date = Field(
        ..., description="Document date (e.g., report period end date)"
    )
    report_title: str | None = Field(
        None,
        description="Full report title",
        examples=["开山集团股份有限公司2024年年度报告"],
    )
    file_path: str | None = Field(
        None,
        description="Original file path",
        examples=["data/annual_reports/2024/300257_开山股份_2024_annual_report.md"],
    )
    file_hash: str | None = Field(
        None,
        max_length=64,
        description="SHA-256 hash of the file for deduplication",
    )
    raw_llm_output: dict[str, Any] = Field(
        ...,
        description="Complete raw JSON response from LLM, stored as-is",
    )
    extraction_metadata: dict[str, Any] | None = Field(
        None,
        description="Metadata about the extraction process",
        examples=[
            {
                "model": "gemini-2.5-pro-preview-06-05",
                "prompt_version": "1.0",
                "extraction_time": "2025-07-20T17:30:45",
                "token_usage": {
                    "prompt_tokens": 15234,
                    "completion_tokens": 3456,
                    "total_tokens": 18690,
                },
                "processing_time_seconds": 95.3,
            }
        ],
    )
    processing_status: str = Field(
        "completed",
        max_length=20,
        description="Processing status",
        examples=["completed", "failed", "processing"],
    )
    error_message: str | None = Field(
        None, description="Error message if processing failed"
    )
    created_at: datetime | None = Field(
        None, description="Timestamp when the record was created"
    )

    @field_validator("company_code")
    @classmethod
    def validate_company_code(cls, v: str) -> str:
        """Validate company code format."""
        if not v or len(v) > 10:
            raise ValueError("Company code must be between 1 and 10 characters")
        return v.strip()

    @field_validator("file_hash")
    @classmethod
    def validate_file_hash(cls, v: str | None) -> str | None:
        """Validate SHA-256 hash format."""
        if v is not None:
            v = v.strip().lower()
            if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
                raise ValueError(
                    "File hash must be a valid SHA-256 hash (64 hex chars)"
                )
        return v

    @field_validator("raw_llm_output")
    @classmethod
    def validate_raw_llm_output(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Ensure raw_llm_output is not empty."""
        if not v:
            raise ValueError("raw_llm_output cannot be empty")
        return v

    model_config = {
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None,
            date: lambda v: v.isoformat() if v else None,
        }
    }


class SourceDocumentMetadata(BaseModel):
    """Metadata for source document archiving."""

    company_code: str = Field(..., max_length=10, description="Stock code")
    doc_type: DocType = Field(..., description="Document type")
    doc_date: date = Field(..., description="Document date")
    report_title: str | None = Field(None, description="Report title")
    file_path: str | None = Field(None, description="File path")
    file_hash: str | None = Field(None, max_length=64, description="File SHA-256 hash")

    @classmethod
    def from_extraction_result(
        cls,
        extraction_data: dict[str, Any],
        document_metadata: dict[str, Any],
        document_type: str,
    ) -> "SourceDocumentMetadata":
        """Create metadata from Story 1.2 extraction result.

        Args:
            extraction_data: The extraction_data section from extraction result
            document_metadata: The document_metadata section from extraction result
            document_type: The document type (annual_report or research_report)

        Returns:
            SourceDocumentMetadata instance
        """
        # Generate report title
        company_name = extraction_data.get("company_name_full", "")
        doc_date_str = document_metadata.get("doc_date", "")

        if document_type == "annual_report":
            report_title = f"{company_name}2024年年度报告"
        else:
            report_title = document_metadata.get(
                "report_title", f"{company_name}研究报告"
            )

        return cls(
            company_code=extraction_data.get("company_code", ""),
            doc_type=DocType(document_type),
            doc_date=date.fromisoformat(doc_date_str) if doc_date_str else date.today(),
            report_title=report_title,
            file_path=document_metadata.get("file_path"),
            file_hash=document_metadata.get("file_hash"),
        )
