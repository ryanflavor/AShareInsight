"""Unified extraction result models."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .company import AnnualReportExtraction, CompanyBasicInfo
from .research_report import ResearchReportExtraction


class DocumentType(str, Enum):
    """Supported document types."""

    ANNUAL_REPORT = "annual_report"
    RESEARCH_REPORT = "research_report"


class TokenUsage(BaseModel):
    """Token usage statistics."""

    input_tokens: int = Field(..., description="输入Token数量")
    output_tokens: int = Field(..., description="输出Token数量")
    total_tokens: int = Field(..., description="总Token数量")


class ExtractionMetadata(BaseModel):
    """Metadata about the extraction process."""

    model_version: str = Field(..., description="LLM模型版本")
    prompt_version: str = Field(..., description="提示词版本")
    extraction_timestamp: datetime = Field(
        default_factory=datetime.now, description="提取时间戳"
    )
    processing_time_seconds: float = Field(..., description="处理耗时(秒)")
    token_usage: dict[str, int] = Field(..., description="Token使用情况")
    file_hash: str = Field(..., description="源文件SHA-256哈希")


class ExtractionResult(BaseModel):
    """Unified extraction result model."""

    document_type: DocumentType = Field(..., description="文档类型")
    extraction_data: AnnualReportExtraction | ResearchReportExtraction = Field(
        ..., description="提取的数据"
    )
    extraction_metadata: ExtractionMetadata = Field(..., description="提取元数据")
    raw_llm_response: str = Field(..., description="LLM原始响应")

    model_config = {"use_enum_values": True}


class CompanyReport(CompanyBasicInfo):
    """Company report model extending CompanyBasicInfo with business concepts."""

    business_concepts: list = Field(
        default_factory=list, description="Business concepts list"
    )


class DocumentExtractionResult(BaseModel):
    """Document extraction result model for CLI/API responses."""

    document_id: str = Field(..., description="Document unique identifier")
    status: str = Field(..., description="Processing status (success/failed)")
    document_type: str = Field(..., description="Document type")
    extracted_data: AnnualReportExtraction | ResearchReportExtraction | None = Field(
        None, description="Extracted data if successful"
    )
    processing_time_seconds: float = Field(
        0.0, description="Total processing time in seconds"
    )
    model_version: str | None = Field(None, description="LLM model version used")
    prompt_version: str | None = Field(None, description="Prompt version used")
    token_usage: TokenUsage | None = Field(None, description="Token usage statistics")
    error: str | None = Field(None, description="Error message if failed")
    raw_output: str | None = Field(None, description="Raw LLM output if available")
