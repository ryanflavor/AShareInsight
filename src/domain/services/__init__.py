"""Domain services for AShareInsight.

This module exports domain services that implement core business logic.
"""

from src.domain.services.company_aggregator import (
    AggregatedCompany,
    CompanyAggregator,
    CompanyConceptGroup,
)
from src.domain.services.market_filter import (
    FilterResult,
    MarketData,
    MarketDataRepository,
    MarketFilter,
    MarketFilters,
    StubMarketDataRepository,
)
from src.domain.services.query_parser import ParsedQueryCompany, QueryCompanyParser
from src.domain.services.similarity_calculator import (
    RankingWeight,
    ScoredDocument,
    SimilarityCalculator,
)

__all__ = [
    "SimilarityCalculator",
    "RankingWeight",
    "ScoredDocument",
    "CompanyAggregator",
    "AggregatedCompany",
    "CompanyConceptGroup",
    "MarketFilter",
    "MarketFilters",
    "MarketData",
    "MarketDataRepository",
    "StubMarketDataRepository",
    "FilterResult",
    "QueryCompanyParser",
    "ParsedQueryCompany",
]
