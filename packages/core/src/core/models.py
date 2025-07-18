"""
Pydantic 2.0 data models for the enterprise concept retrieval system.

These models serve as the "contracts" between different modules in the monorepo,
following contract-driven development principles. All models use Pydantic 2.0+ API.
"""

from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .logging_config import get_logger

logger = get_logger(__name__)


def utc_now() -> datetime:
    """Get current UTC timestamp with timezone awareness."""
    return datetime.now(UTC)


class Company(BaseModel):
    """
    Company master data model representing companies in the system.

    Maps to the 'companies' table in PostgreSQL.
    """

    company_code: str = Field(
        ...,
        max_length=10,
        description="公司股票代码作为唯一主键 (e.g., '000001')",
    )
    company_name_full: str = Field(
        ...,
        max_length=255,
        description="公司完整官方名称 (unique)",
    )
    company_name_short: str | None = Field(
        None,
        max_length=100,
        description="公司简称",
    )
    exchange: str | None = Field(
        None,
        max_length=50,
        description="上市交易所",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="记录创建时间",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="记录最后更新时间",
    )

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return dt.isoformat() if dt else None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_code": "000001",
                "company_name_full": "平安银行股份有限公司",
                "company_name_short": "平安银行",
                "exchange": "深圳证券交易所",
            }
        },
    )


class SourceDocument(BaseModel):
    """
    Source document extraction archive model.

    Stores raw LLM extraction results from annual reports and research reports.
    Maps to the 'source_documents' table in PostgreSQL.
    """

    doc_id: UUID = Field(
        default_factory=uuid4,
        description="文档提取记录唯一ID",
    )
    company_code: str = Field(
        ...,
        max_length=10,
        description="关联到companies表的公司代码",
    )
    doc_type: Literal["annual_report", "research_report"] = Field(
        ...,
        description="文档类型",
    )
    doc_date: date = Field(
        ...,
        description="文档发布日期",
    )
    report_title: str = Field(
        ...,
        description="研报或年报标题",
    )
    raw_llm_output: dict[str, Any] = Field(
        ...,
        description="存储从LLM返回的完整JSON (JSONB in PostgreSQL)",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="记录归档时间",
    )

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return dt.isoformat() if dt else None

    @field_serializer("doc_date")
    def serialize_date(self, d: date | None) -> str | None:
        """Serialize date to ISO format."""
        return d.isoformat() if d else None

    @field_serializer("doc_id")
    def serialize_uuid(self, uuid: UUID | None) -> str | None:
        """Serialize UUID to string."""
        return str(uuid) if uuid else None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_code": "000001",
                "doc_type": "annual_report",
                "doc_date": "2023-12-31",
                "report_title": "2023年年度报告",
                "raw_llm_output": {
                    "concepts": ["零售银行", "公司银行"],
                    "metrics": {"revenue": 100000000},
                },
            }
        },
    )


class BusinessConcept(BaseModel):
    """
    Business concept master data model with vector embeddings.

    Stores business concepts extracted from documents with their embeddings
    for vector similarity search. Maps to the 'business_concepts_master' table.
    """

    concept_id: UUID = Field(
        default_factory=uuid4,
        description="业务概念唯一ID",
    )
    company_code: str = Field(
        ...,
        max_length=10,
        description="关联到companies表的公司代码",
    )
    concept_name: str = Field(
        ...,
        max_length=255,
        description="业务概念通用名称",
    )
    embedding: list[float] = Field(
        ...,
        min_length=2560,
        max_length=2560,
        description="由Qwen Embedding模型生成的向量 (VECTOR(2560) in PostgreSQL)",
    )
    concept_details: dict[str, Any] | None = Field(
        None,
        description="存储概念所有其他详细信息 (description, category, metrics等)",
    )
    last_updated_from_doc_id: UUID = Field(
        ...,
        description="指向source_documents表追溯最新信息来源",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="该概念最后更新时间",
    )

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimension(cls, v: list[float]) -> list[float]:
        """Ensure embedding has exactly 2560 dimensions."""
        if len(v) != 2560:
            raise ValueError("Embedding must have exactly 2560 dimensions")
        return v

    @field_serializer("updated_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """Serialize datetime to ISO format."""
        return dt.isoformat() if dt else None

    @field_serializer("concept_id", "last_updated_from_doc_id")
    def serialize_uuid(self, uuid: UUID | None) -> str | None:
        """Serialize UUID to string."""
        return str(uuid) if uuid else None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_code": "000001",
                "concept_name": "零售银行业务",
                "embedding": [0.1] * 2560,  # 2560-dimensional vector
                "concept_details": {
                    "description": "包括个人存贷款、信用卡等业务",
                    "category": "主营业务",
                    "revenue_percentage": 0.35,
                },
                "last_updated_from_doc_id": "123e4567-e89b-12d3-a456-426614174000",
            }
        },
    )
