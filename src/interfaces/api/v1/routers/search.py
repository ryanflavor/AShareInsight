"""
Search API endpoints for finding similar companies.

This module implements the search functionality following contract-driven
development principles with strict input/output validation.
"""

from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.domain.services import (
    AggregatedCompany,
    QueryCompanyParser,
)
from src.domain.services import (
    MarketFilters as DomainMarketFilters,
)
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

logger = structlog.get_logger(__name__)
router = APIRouter()


def _convert_aggregated_to_response(
    aggregated_companies: list[AggregatedCompany],
    query_identifier: str,
    include_justification: bool,
    filters_applied: dict,
    total_before_limit: int,
    query_company_info: dict[str, str] | None = None,
) -> SearchSimilarCompaniesResponse:
    """Convert aggregated companies to API response format.

    Args:
        aggregated_companies: List of AggregatedCompany objects from the use case
        query_identifier: Original query identifier
        include_justification: Whether to include justifications
        filters_applied: Dictionary of applied filters
        total_before_limit: Total companies before top_k limit

    Returns:
        SearchSimilarCompaniesResponse formatted for API
    """
    # Parse query company information
    query_parser = QueryCompanyParser()
    parsed_query = query_parser.resolve_from_results(
        query_identifier=query_identifier,
        aggregated_companies=aggregated_companies,
    )

    # Handle case where code is not a valid stock code
    # If parsed_query.code is None or doesn't match the pattern, use query_company_info
    query_code = parsed_query.code
    query_name = parsed_query.name

    # If we have query company info from the database, use it
    if query_company_info:
        query_name = (
            query_company_info.get("company_name_short")
            or query_company_info["company_name"]
        )
        query_code = query_company_info["company_code"]
    elif not query_code or not query_code.isdigit() or len(query_code) != 6:
        # Try to get code from first result if available
        if aggregated_companies:
            query_code = aggregated_companies[0].company_code
            # Also update the name to the actual company name
            query_name = (
                aggregated_companies[0].company_name_short
                or aggregated_companies[0].company_name
            )
        else:
            # Use a placeholder code if no results
            query_code = "000000"
            query_name = parsed_query.name

    query_company = QueryCompany(
        name=query_name,
        code=query_code,
    )

    # Convert to CompanyResult objects
    results = []
    for company in aggregated_companies:
        # Get top 5 concepts for this company
        top_concepts = company.matched_concepts[:5]

        matched_concepts = [
            MatchedConcept(
                name=concept.concept_name,
                similarity_score=concept.similarity_score,
            )
            for concept in top_concepts
        ]

        company_result = CompanyResult(
            company_name=company.company_name_short or company.company_name,
            company_code=company.company_code,
            relevance_score=company.relevance_score,
            matched_concepts=matched_concepts,
            justification=(
                Justification(
                    summary=(
                        f"Matched {len(company.matched_concepts)} business concepts"
                    ),
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

    return SearchSimilarCompaniesResponse(
        query_company=query_company,
        metadata=SearchMetadata(
            total_results_before_limit=total_before_limit,
            filters_applied=filters_applied,
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
    use_case: SearchSimilarCompaniesUseCase = Depends(  # noqa: B008
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

        # Convert API market filters to domain model if provided
        domain_market_filters = None
        if request.market_filters:
            domain_market_filters = DomainMarketFilters(
                max_market_cap_cny=(
                    Decimal(str(request.market_filters.max_market_cap_cny))
                    if request.market_filters.max_market_cap_cny
                    else None
                ),
                max_avg_volume_5day=(
                    Decimal(str(request.market_filters.min_5day_avg_volume))
                    if request.market_filters.min_5day_avg_volume
                    else None
                ),
            )

        # Execute search through use case
        # Note: use_case handles aggregation, filtering and limiting internally
        aggregated_companies, filters_applied_by_service = await use_case.execute(
            target_identifier=request.query_identifier,
            text_to_embed=None,  # Not implemented in this story
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            market_filters=domain_market_filters,
        )

        # If no results found, try to determine query company info
        if not aggregated_companies:
            # For no results, we still need to return a valid response
            # Use the query identifier as the company name
            query_company = QueryCompany(
                name=request.query_identifier,
                code="000000",  # Placeholder code
            )

            return SearchSimilarCompaniesResponse(
                query_company=query_company,
                metadata=SearchMetadata(
                    total_results_before_limit=0,
                    filters_applied={},
                ),
                results=[],
            )

        # Merge filter information
        filters_applied = {
            "similarity_threshold": request.similarity_threshold != 0.7,
            "market_cap_filter": filters_applied_by_service.get(
                "market_cap_filter", False
            ),
            "volume_filter": filters_applied_by_service.get("volume_filter", False),
        }

        # Include all metadata from the service
        filters_applied.update(
            {
                k: v
                for k, v in filters_applied_by_service.items()
                if k not in filters_applied
            }
        )

        # For now, we use the length of results as total_before_limit
        # In future, the use case should return this information
        total_before_limit = len(aggregated_companies)

        # Get query company info from vector store if available
        # This ensures we have accurate company information
        query_company_info = None
        try:
            from src.infrastructure.persistence.postgres import (
                PostgresVectorStoreRepository,
            )

            vector_store = PostgresVectorStoreRepository()
            pool = await vector_store._ensure_pool()
            query_company_info = await vector_store._identify_company(
                pool, request.query_identifier
            )
            await vector_store.close()
        except Exception as e:
            logger.warning(f"Failed to get query company info: {e}")

        # Convert aggregated companies to response format
        response = _convert_aggregated_to_response(
            aggregated_companies=aggregated_companies,
            query_identifier=request.query_identifier,
            include_justification=include_justification,
            filters_applied=filters_applied,
            total_before_limit=total_before_limit,
            query_company_info=query_company_info,
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
