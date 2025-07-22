"""Domain entities for AShareInsight."""

from .business_concept import BusinessConcept as BusinessConceptEntity
from .company import (
    AnnualReportExtraction,
    BusinessConcept,
    CompanyBasicInfo,
    Metrics,
    Relations,
    Shareholder,
    Timeline,
)
from .extraction import (
    CompanyReport,
    DocumentExtractionResult,
    DocumentType,
    ExtractionMetadata,
    ExtractionResult,
    TokenUsage,
)
from .research_report import (
    BusinessConceptWithBrands,
    ProfitForecast,
    ResearchReportExtraction,
    ValuationItem,
)

__all__ = [
    # Company entities
    "Shareholder",
    "CompanyBasicInfo",
    "Timeline",
    "Metrics",
    "Relations",
    "BusinessConcept",
    "BusinessConceptEntity",
    "AnnualReportExtraction",
    # Research report entities
    "ProfitForecast",
    "ValuationItem",
    "BusinessConceptWithBrands",
    "ResearchReportExtraction",
    # Extraction entities
    "DocumentType",
    "ExtractionMetadata",
    "ExtractionResult",
    "TokenUsage",
    "CompanyReport",
    "DocumentExtractionResult",
]
