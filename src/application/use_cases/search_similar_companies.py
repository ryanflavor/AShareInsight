"""Search similar companies use case.

This module implements the business logic for searching similar companies
based on business concepts, following the hexagonal architecture pattern.
"""

import structlog

from src.application.ports import RerankerPort, VectorStorePort
from src.application.ports.reranker_port import RerankRequest
from src.domain.services import (
    AggregatedCompany,
    CompanyAggregator,
    MarketDataRepository,
    MarketFilter,
    SimilarityCalculator,
)
from src.domain.services import (
    MarketFilters as DomainMarketFilters,
)
from src.domain.value_objects import BusinessConceptQuery
from src.shared.exceptions import CompanyNotFoundError, SearchServiceError

logger = structlog.get_logger(__name__)


class SearchSimilarCompaniesUseCase:
    """Use case for searching similar companies based on business concepts.

    This use case coordinates the search process by:
    1. Accepting search parameters
    2. Delegating to the vector store for similarity search
    3. Returning formatted results
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        reranker: RerankerPort | None = None,
        market_data_repository: MarketDataRepository | None = None,
    ):
        """Initialize the use case with required dependencies.

        Args:
            vector_store: Port interface for vector store operations
            reranker: Optional port interface for document reranking
            market_data_repository: Optional repository for market data
        """
        self._vector_store = vector_store
        self._reranker = reranker
        self._similarity_calculator = SimilarityCalculator()
        self._company_aggregator = CompanyAggregator()
        self._market_filter = (
            MarketFilter(market_data_repository) if market_data_repository else None
        )

    async def execute(
        self,
        target_identifier: str,
        text_to_embed: str | None = None,
        top_k: int = 50,
        similarity_threshold: float = 0.7,
        market_filters: DomainMarketFilters | None = None,
    ) -> tuple[list[AggregatedCompany], dict[str, any]]:
        """Execute the similar companies search.

        Args:
            target_identifier: Company code or name to search for
            text_to_embed: Optional text for additional search context
            top_k: Number of top results to return (1-200)
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            Tuple of (List of AggregatedCompany objects, filters applied dict)

        Raises:
            CompanyNotFoundError: If target company cannot be found
            SearchServiceError: If search operation fails
        """
        try:
            # Log the search request
            logger.info(
                f"Searching similar companies for: {target_identifier}, "
                f"top_k={top_k}, threshold={similarity_threshold}"
            )

            # Create query object
            query = BusinessConceptQuery(
                target_identifier=target_identifier,
                text_to_embed=text_to_embed,
                top_k=top_k,
                similarity_threshold=similarity_threshold,
            )

            # Delegate to vector store for search
            documents = await self._vector_store.search_similar_concepts(query)

            # Log initial results
            logger.info(
                f"Found {len(documents)} similar companies for {target_identifier}"
            )

            # Apply reranking if available and documents exist
            rerank_scores = None
            if self._reranker and documents:
                try:
                    logger.info(f"Applying reranking to {len(documents)} documents")

                    # Build intelligent query text if not provided
                    query_text = text_to_embed
                    if not query_text and documents:
                        # Extract company name and top concepts from the source company
                        # Find documents from the source company
                        source_docs = [
                            doc
                            for doc in documents
                            if doc.company_code == target_identifier
                        ]

                        if source_docs:
                            # Get company name from first matching document
                            company_name = source_docs[0].company_name

                            # Get top 3 unique concepts sorted by importance
                            unique_concepts = {}
                            for doc in source_docs:
                                if doc.concept_name not in unique_concepts:
                                    unique_concepts[doc.concept_name] = (
                                        doc.importance_score
                                    )

                            # Sort by importance and take top 3
                            top_concepts = sorted(
                                unique_concepts.items(),
                                key=lambda x: x[1],
                                reverse=True,
                            )[:3]
                            concept_names = [name for name, _ in top_concepts]

                            # Build structured query text
                            query_text = (
                                f"{company_name} 主营业务:{' '.join(concept_names)}"
                            )
                            logger.info(f"Built query text for reranking: {query_text}")
                        else:
                            # Fallback to identifier if no source documents found
                            query_text = target_identifier

                    # Prepare rerank request
                    rerank_request = RerankRequest(
                        query=query_text or target_identifier,
                        documents=documents,
                        top_k=top_k,
                    )

                    # Execute reranking
                    rerank_response = await self._reranker.rerank_documents(
                        rerank_request
                    )

                    # Build rerank scores mapping
                    rerank_scores = {
                        str(result.document.concept_id): result.rerank_score
                        for result in rerank_response.results
                    }

                    # Update documents with reranked order
                    documents = [result.document for result in rerank_response.results]

                    logger.info(
                        f"Reranking completed in "
                        f"{rerank_response.processing_time_ms:.2f}ms, "
                        f"returned {len(documents)} documents"
                    )

                except Exception as e:
                    # Log error but continue with original results
                    # (graceful degradation)
                    logger.error(f"Reranking failed, using original order: {e}")
                    # Keep original documents order and no rerank scores

            # Apply final ranking algorithm
            logger.info(
                f"Applying similarity calculation to {len(documents)} documents"
            )

            scored_documents = self._similarity_calculator.calculate_final_scores(
                documents=documents,
                rerank_scores=rerank_scores,
            )

            # Extract sorted documents with final scores
            final_documents = [scored.document for scored in scored_documents]

            logger.info(f"Final ranking completed, {len(final_documents)} documents")

            # Aggregate documents by company
            logger.info("Aggregating documents by company")
            aggregated_companies = self._company_aggregator.aggregate_by_company(
                documents=final_documents,
                strategy="max",  # Use highest concept score as company score
            )

            logger.info(
                f"Aggregated {len(final_documents)} documents into "
                f"{len(aggregated_companies)} companies"
            )

            # Apply market filters if provided
            filters_applied = {
                "market_cap_filter": False,
                "volume_filter": False,
                "advanced_scoring": False,
            }
            filter_config = {}

            if self._market_filter:
                logger.info("Applying market filters and scoring")
                filter_result = await self._market_filter.apply_filters(
                    companies=aggregated_companies,
                    filters=market_filters,
                )

                # Extract companies from scored results
                scored_companies = filter_result.scored_companies
                aggregated_companies = [sc.company for sc in scored_companies]

                # Update metadata
                filters_applied = filter_result.filters_applied
                filter_config = filter_result.filter_config

                logger.info(
                    f"Market filters and scoring applied: "
                    f"{filter_result.total_before_filter} companies reduced to "
                    f"{len(aggregated_companies)}"
                )

            # Apply top_k limit after filtering
            if len(aggregated_companies) > top_k:
                aggregated_companies = aggregated_companies[:top_k]
                logger.info(f"Limited results to top {top_k} companies")

            # Build comprehensive metadata
            metadata = {
                **filters_applied,
                **filter_config,
                "total_results": len(aggregated_companies),
            }

            return aggregated_companies, metadata

        except CompanyNotFoundError:
            # Re-raise company not found errors
            logger.warning(f"Company not found: {target_identifier}")
            raise

        except Exception as e:
            # Wrap other errors in SearchServiceError
            logger.error(f"Search failed for {target_identifier}: {e}")
            raise SearchServiceError(
                operation="search_similar_companies", reason=str(e)
            ) from e
