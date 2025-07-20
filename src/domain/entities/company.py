"""Company-related domain entities."""

from pydantic import BaseModel, Field


class Shareholder(BaseModel):
    """Shareholder information model."""

    name: str = Field(..., description="股东名称")
    holding_percentage: float = Field(..., ge=0, le=100, description="持股比例(%)")


class CompanyBasicInfo(BaseModel):
    """Company basic information model."""

    company_name_full: str = Field(..., description="公司全称")
    company_name_short: str = Field(..., description="公司简称")
    company_code: str = Field(..., description="股票代码")
    exchange: str = Field(..., description="交易所")
    top_shareholders: list[Shareholder] = Field(..., description="前十大股东列表")


class Timeline(BaseModel):
    """Timeline information for business concepts."""

    established: str | None = Field(None, description="成立/建立时间")
    recent_event: str | None = Field(None, description="最近事件描述")


class Metrics(BaseModel):
    """Business metrics model."""

    revenue: float | None = Field(None, description="营收(元)")
    revenue_growth_rate: float | None = Field(None, description="营收增长率(%)")
    market_share: float | None = Field(None, description="市场份额(%)")
    gross_margin: float | None = Field(None, description="毛利率(%)")
    capacity: float | None = Field(None, description="产能")
    sales_volume: float | None = Field(None, description="销量")


class Relations(BaseModel):
    """Business relations model."""

    customers: list[str] = Field(default_factory=list, description="客户列表")
    partners: list[str] = Field(default_factory=list, description="合作伙伴列表")
    subsidiaries_or_investees: list[str] = Field(
        default_factory=list, description="子公司或被投资公司列表"
    )


class BusinessConcept(BaseModel):
    """Business concept model for detailed business information."""

    concept_name: str = Field(..., description="业务概念名称")
    concept_category: str = Field(
        ..., description="业务概念分类", pattern="^(核心业务|新兴业务|战略布局)$"
    )
    description: str = Field(..., description="业务描述")
    importance_score: float = Field(..., ge=0, le=1, description="重要性评分(0-1)")
    development_stage: str = Field(
        ..., description="发展阶段", pattern="^(成熟期|成长期|探索期|并购整合期)$"
    )
    timeline: Timeline = Field(..., description="时间线信息")
    metrics: Metrics | None = Field(None, description="业务指标")
    relations: Relations = Field(..., description="业务关系")
    source_sentences: list[str] = Field(
        ..., min_length=1, max_length=3, description="原文引用句子(1-3句)"
    )


class AnnualReportExtraction(BaseModel):
    """Complete annual report extraction model."""

    company_name_full: str = Field(..., description="公司全称")
    company_name_short: str = Field(..., description="公司简称")
    company_code: str = Field(..., description="股票代码")
    exchange: str = Field(..., description="交易所")
    top_shareholders: list[Shareholder] = Field(..., description="前十大股东列表")
    business_concepts: list[BusinessConcept] = Field(..., description="业务概念列表")
