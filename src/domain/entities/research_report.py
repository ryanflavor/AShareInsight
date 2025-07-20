"""Research report domain entities matching prompt_b.md structure."""

from pydantic import BaseModel, Field

from .company import BusinessConcept


class ProfitForecast(BaseModel):
    """Profit forecast item."""

    year: int = Field(..., description="预测年份")
    metric: str = Field(..., description="指标名称")
    value: str | float = Field(..., description="指标值")
    yoy_growth: str | float | None = Field(None, description="同比增长")


class ValuationItem(BaseModel):
    """Valuation metric item."""

    year: int = Field(..., description="年份")
    metric: str = Field(..., description="估值指标名称")
    value: float = Field(..., description="估值指标值")


class BusinessConceptWithBrands(BusinessConcept):
    """Business concept with key products/brands for research reports."""

    key_products_or_brands: list[str] = Field(
        default_factory=list, description="具体的品牌或产品型号列表"
    )


class ResearchReportExtraction(BaseModel):
    """Research report extraction model matching prompt_b.md."""

    company_name_short: str = Field(..., description="公司简称")
    company_code: str = Field(..., description="股票代码")
    report_title: str = Field(..., description="研报标题")
    investment_rating: str = Field(..., description="投资评级")
    core_thesis: str = Field(..., description="核心投资逻辑", max_length=200)

    profit_forecast: list[ProfitForecast] = Field(..., description="盈利预测列表")

    valuation: list[ValuationItem] = Field(..., description="估值指标列表")

    comparable_companies: list[str] = Field(
        default_factory=list, description="可比公司列表"
    )

    risk_factors: list[str] = Field(default_factory=list, description="风险因素列表")

    business_concepts: list[BusinessConceptWithBrands] = Field(
        ..., description="业务概念列表"
    )
