"""SQLAlchemy models for PostgreSQL database.

This module defines the ORM models that map to database tables.
"""

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base: Any = declarative_base()


class CompanyModel(Base):
    """ORM model for companies table."""

    __tablename__ = "companies"

    company_code = Column(String(10), primary_key=True)
    company_name_full = Column(String(255), nullable=False)
    company_name_short = Column(String(100), nullable=True)
    exchange = Column(String(50), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SourceDocumentModel(Base):
    """ORM model for source_documents table."""

    __tablename__ = "source_documents"

    doc_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    company_code = Column(
        String(10),
        ForeignKey("companies.company_code", name="fk_source_documents_company_code"),
        nullable=False,
    )
    doc_type = Column(String(50), nullable=False)
    doc_date = Column(Date, nullable=False)
    report_title = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)
    file_hash = Column(String(64), nullable=True)
    raw_llm_output = Column(JSONB, nullable=False)
    extraction_metadata = Column(JSONB, nullable=True)
    original_content = Column(Text, nullable=True)
    processing_status = Column(String(20), server_default="completed", nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('annual_report', 'research_report')",
            name="check_doc_type",
        ),
        UniqueConstraint("file_hash", name="uq_source_documents_file_hash"),
        Index("idx_company_date", "company_code", "doc_date"),
        Index("idx_doc_type", "doc_type"),
        Index("idx_processing_status", "processing_status"),
    )

    def to_domain_entity(self, source_document_class):
        """Convert ORM model to domain entity.

        Args:
            source_document_class: The SourceDocument domain class

        Returns:
            SourceDocument domain entity
        """
        return source_document_class(
            doc_id=self.doc_id,
            company_code=self.company_code,
            doc_type=self.doc_type,
            doc_date=self.doc_date,
            report_title=self.report_title,
            file_path=self.file_path,
            file_hash=self.file_hash,
            raw_llm_output=self.raw_llm_output,
            extraction_metadata=self.extraction_metadata,
            original_content=self.original_content,
            processing_status=self.processing_status,
            error_message=self.error_message,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain_entity(cls, entity):
        """Create ORM model from domain entity.

        Args:
            entity: SourceDocument domain entity

        Returns:
            SourceDocumentModel instance
        """
        return cls(
            doc_id=entity.doc_id,
            company_code=entity.company_code,
            doc_type=entity.doc_type.value,
            doc_date=entity.doc_date,
            report_title=entity.report_title,
            file_path=entity.file_path,
            file_hash=entity.file_hash,
            raw_llm_output=entity.raw_llm_output,
            extraction_metadata=entity.extraction_metadata,
            original_content=entity.original_content,
            processing_status=entity.processing_status,
            error_message=entity.error_message,
            created_at=entity.created_at,
        )
