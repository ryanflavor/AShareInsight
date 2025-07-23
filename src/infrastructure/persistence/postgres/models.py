"""SQLAlchemy models for PostgreSQL database.

This module defines the ORM models that map to database tables.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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


class BusinessConceptMasterModel(Base):
    """ORM model for business_concepts_master table."""

    __tablename__ = "business_concepts_master"

    concept_id = Column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    company_code = Column(
        String(10),
        ForeignKey("companies.company_code", name="fk_business_concepts_company_code"),
        nullable=False,
    )
    concept_name = Column(String(255), nullable=False)
    concept_category = Column(String(50), nullable=False)
    importance_score = Column(Numeric(3, 2), nullable=False)
    development_stage = Column(String(50), nullable=True)
    # Using pgvector's Vector type with dimensions=2560 (halfvec precision)
    # Note: halfvec uses half-precision floats to save 50% storage space
    from pgvector.sqlalchemy import Vector

    embedding = Column(Vector(2560), nullable=True)
    concept_details = Column(JSONB, nullable=False)
    last_updated_from_doc_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("source_documents.doc_id", name="fk_business_concepts_doc_id"),
        nullable=True,
    )
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "concept_category IN ('核心业务', '新兴业务', '战略布局')",
            name="check_concept_category",
        ),
        CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="check_importance_score",
        ),
        UniqueConstraint(
            "company_code", "concept_name", name="uq_company_concept_name"
        ),
        Index("idx_company_code", "company_code"),
        Index("idx_importance_score", "importance_score"),
    )

    def to_domain_entity(self, business_concept_master_class):
        """Convert ORM model to domain entity.

        Args:
            business_concept_master_class: The BusinessConceptMaster domain class

        Returns:
            BusinessConceptMaster domain entity
        """
        from decimal import Decimal

        import numpy as np

        # Convert pgvector embedding to bytes for domain entity
        embedding_bytes = None
        if self.embedding is not None:
            # Convert pgvector to numpy array then to bytes
            embedding_array = np.array(self.embedding, dtype=np.float32)
            embedding_bytes = embedding_array.tobytes()

        return business_concept_master_class(
            concept_id=self.concept_id,
            company_code=self.company_code,
            concept_name=self.concept_name,
            concept_category=self.concept_category,
            importance_score=Decimal(str(self.importance_score)),
            development_stage=self.development_stage,
            embedding=embedding_bytes,
            concept_details=self.concept_details,
            last_updated_from_doc_id=self.last_updated_from_doc_id,
            version=self.version,
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain_entity(cls, entity):
        """Create ORM model from domain entity.

        Args:
            entity: BusinessConceptMaster domain entity

        Returns:
            BusinessConceptMasterModel instance
        """
        import numpy as np

        # Check if concept_id is a zero UUID (new concept that needs DB generation)
        zero_uuid = UUID("00000000-0000-0000-0000-000000000000")

        # Convert bytes embedding to list[float] for pgvector
        embedding_list = None
        if entity.embedding is not None:
            # Convert bytes to numpy array then to list
            embedding_array = np.frombuffer(entity.embedding, dtype=np.float32)
            embedding_list = embedding_array.tolist()

        kwargs = {
            "company_code": entity.company_code,
            "concept_name": entity.concept_name,
            "concept_category": entity.concept_category,
            "importance_score": entity.importance_score,
            "development_stage": entity.development_stage,
            "embedding": embedding_list,
            "concept_details": entity.concept_details,
            "last_updated_from_doc_id": entity.last_updated_from_doc_id,
            "version": entity.version,
            "is_active": entity.is_active,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

        # Only include concept_id if it's not a zero UUID
        if entity.concept_id != zero_uuid:
            kwargs["concept_id"] = entity.concept_id

        return cls(**kwargs)
