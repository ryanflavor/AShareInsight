"""
Search API endpoints for finding similar companies.

This module implements the search functionality following contract-driven
development principles with strict input/output validation.
"""

from fastapi import APIRouter, Query

from src.interfaces.api.v1.schemas.search import (
    CompanyResult,
    MatchedConcept,
    QueryCompany,
    SearchMetadata,
    SearchSimilarCompaniesRequest,
    SearchSimilarCompaniesResponse,
)

router = APIRouter()


@router.post(
    "/similar-companies",
    response_model=SearchSimilarCompaniesResponse,
    summary="Search for similar companies",
    description=(
        "Find companies similar to a given query company based on "
        "business concepts and market characteristics."
    ),
)
async def search_similar_companies(
    request: SearchSimilarCompaniesRequest,
    include_justification: bool = Query(
        False,
        description="Whether to include detailed justification for each match",
    ),
) -> SearchSimilarCompaniesResponse:
    """
    Search for companies similar to the query identifier.

    This endpoint accepts a company name or stock code and returns
    a list of similar companies ranked by relevance.

    Args:
        request: Search request with query identifier and filters
        include_justification: Whether to include detailed justifications

    Returns:
        SearchSimilarCompaniesResponse: List of similar companies with metadata
    """
    # Mock implementation for now - will be replaced with actual search logic
    # in future stories when domain layer is implemented

    mock_results = [
        CompanyResult(
            company_name="宁德时代新能源科技股份有限公司",
            company_code="300750",
            relevance_score=0.92,
            matched_concepts=[
                MatchedConcept(
                    name="新能源汽车产业链",
                    similarity_score=0.95,
                ),
                MatchedConcept(
                    name="动力电池制造",
                    similarity_score=0.88,
                ),
            ],
            justification=(
                {
                    "summary": "Both companies are key players in the EV supply chain",
                    "supporting_evidence": [
                        "Leading battery technology development",
                        "Major supplier to electric vehicle manufacturers",
                        "Strong R&D investment in energy storage",
                    ],
                }
                if include_justification
                else None
            ),
        ),
        CompanyResult(
            company_name="理想汽车有限公司",
            company_code="002015",
            relevance_score=0.85,
            matched_concepts=[
                MatchedConcept(
                    name="新能源汽车制造",
                    similarity_score=0.90,
                ),
                MatchedConcept(
                    name="智能驾驶技术",
                    similarity_score=0.82,
                ),
            ],
            justification=(
                {
                    "summary": "Direct competitor in the electric vehicle market",
                    "supporting_evidence": [
                        "Focus on electric and hybrid vehicle production",
                        "Investment in autonomous driving technology",
                    ],
                }
                if include_justification
                else None
            ),
        ),
    ]

    # Apply top_k limit
    mock_results = mock_results[: request.top_k]

    return SearchSimilarCompaniesResponse(
        query_company=QueryCompany(
            name="比亚迪股份有限公司",
            code="002594",
        ),
        metadata=SearchMetadata(
            total_results_before_limit=len(mock_results) + 10,  # Mock higher total
            filters_applied={
                "market_cap_filter": bool(
                    request.market_filters and request.market_filters.max_market_cap_cny
                ),
                "volume_filter": bool(
                    request.market_filters
                    and request.market_filters.min_5day_avg_volume
                ),
            },
        ),
        results=mock_results,
    )
