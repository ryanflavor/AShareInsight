"""
Search API endpoints for finding similar companies.

This module implements the search functionality following contract-driven
development principles with strict input/output validation.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.domain.value_objects import Document
from src.interfaces.api.dependencies import get_search_similar_companies_use_case
from src.interfaces.api.v1.schemas.search import (
    CompanyResult,
    Justification,
    MatchedConcept,
    QueryCompany,
    SearchMetadata,
    SearchSimilarCompaniesRequest,
    SearchSimilarCompaniesResponse,
)
from src.shared.exceptions import CompanyNotFoundError, SearchServiceError

logger = logging.getLogger(__name__)
router = APIRouter()


def _convert_documents_to_response(
    documents: list[Document],
    query_identifier: str,
    include_justification: bool,
    filters_applied: dict,
) -> SearchSimilarCompaniesResponse:
    """Convert domain Documents to API response format.

    Args:
        documents: List of Document objects from the use case
        query_identifier: Original query identifier
        include_justification: Whether to include justifications
        filters_applied: Dictionary of applied filters

    Returns:
        SearchSimilarCompaniesResponse formatted for API
    """
    # Group documents by company to aggregate concepts
    company_results = {}

    for doc in documents:
        if doc.company_code not in company_results:
            company_results[doc.company_code] = {
                "company_name": doc.company_name,
                "company_code": doc.company_code,
                "concepts": [],
                "max_score": doc.similarity_score,
            }

        company_results[doc.company_code]["concepts"].append(
            {"name": doc.concept_name, "similarity_score": doc.similarity_score}
        )

        # Keep the highest score for the company
        if doc.similarity_score > company_results[doc.company_code]["max_score"]:
            company_results[doc.company_code]["max_score"] = doc.similarity_score

    # Convert to CompanyResult objects
    results = []
    for company_code, data in company_results.items():
        matched_concepts = [
            MatchedConcept(
                name=concept["name"], similarity_score=concept["similarity_score"]
            )
            for concept in sorted(
                data["concepts"], key=lambda x: x["similarity_score"], reverse=True
            )[:5]  # Limit to top 5 concepts per company
        ]

        company_result = CompanyResult(
            company_name=data["company_name"],
            company_code=company_code,
            relevance_score=data["max_score"],
            matched_concepts=matched_concepts,
            justification=(
                Justification(
                    summary=f"Matched {len(data['concepts'])} business concepts",
                    supporting_evidence=[
                        f"{c.name} (score: {c.similarity_score:.2f})"
                        for c in matched_concepts[:3]
                    ],
                )
                if include_justification
                else None
            ),
        )
        results.append(company_result)

    # Sort by relevance score
    results.sort(key=lambda x: x.relevance_score, reverse=True)

    # Extract query company info from first document if available
    query_company = QueryCompany(
        name=query_identifier,  # Will be replaced with actual name once found
        code=query_identifier if len(query_identifier) <= 10 else None,
    )

    return SearchSimilarCompaniesResponse(
        query_company=query_company,
        metadata=SearchMetadata(
            total_results_before_limit=len(results), filters_applied=filters_applied
        ),
        results=results,
    )


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
    use_case: SearchSimilarCompaniesUseCase = Depends(
        get_search_similar_companies_use_case
    ),
) -> SearchSimilarCompaniesResponse:
    """
    Search for companies similar to the query identifier.

    This endpoint accepts a company name or stock code and returns
    a list of similar companies ranked by relevance.

    Args:
        request: Search request with query identifier and filters
        include_justification: Whether to include detailed justifications
        use_case: Injected search use case

    Returns:
        SearchSimilarCompaniesResponse: List of similar companies with metadata

    Raises:
        HTTPException: 404 if company not found, 500 for other errors
    """
    try:
        # Log the search request
        logger.info(f"Searching similar companies for: {request.query_identifier}")

        # Execute search through use case
        documents = await use_case.execute(
            target_identifier=request.query_identifier,
            text_to_embed=None,  # Not implemented in this story
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
        )

        # Determine which filters were applied
        filters_applied = {
            "similarity_threshold": request.similarity_threshold != 0.7,
            "market_cap_filter": bool(
                request.market_filters and request.market_filters.max_market_cap_cny
            ),
            "volume_filter": bool(
                request.market_filters and request.market_filters.min_5day_avg_volume
            ),
        }

        # Convert documents to response format
        response = _convert_documents_to_response(
            documents=documents,
            query_identifier=request.query_identifier,
            include_justification=include_justification,
            filters_applied=filters_applied,
        )

        logger.info(
            f"Found {len(response.results)} similar companies for "
            f"{request.query_identifier}"
        )

        return response

    except CompanyNotFoundError as e:
        logger.warning(f"Company not found: {e}")
        raise HTTPException(
            status_code=404, detail=f"Company '{request.query_identifier}' not found"
        ) from e

    except SearchServiceError as e:
        logger.error(f"Search service error: {e}")
        raise HTTPException(
            status_code=500, detail="Search service temporarily unavailable"
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error in search endpoint: {e}")
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred"
        ) from e
