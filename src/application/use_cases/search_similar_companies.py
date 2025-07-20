"""Search similar companies use case.

This module implements the business logic for searching similar companies
based on business concepts, following the hexagonal architecture pattern.
"""

import logging

from src.application.ports import RerankerPort, VectorStorePort
from src.application.ports.reranker_port import RerankRequest
from src.domain.services import SimilarityCalculator
from src.domain.value_objects import BusinessConceptQuery, Document
from src.shared.exceptions import CompanyNotFoundError, SearchServiceError

logger = logging.getLogger(__name__)


class SearchSimilarCompaniesUseCase:
    """Use case for searching similar companies based on business concepts.

    This use case coordinates the search process by:
    1. Accepting search parameters
    2. Delegating to the vector store for similarity search
    3. Returning formatted results
    """

    def __init__(
        self, vector_store: VectorStorePort, reranker: RerankerPort | None = None
    ):
        """Initialize the use case with required dependencies.

        Args:
            vector_store: Port interface for vector store operations
            reranker: Optional port interface for document reranking
        """
        self._vector_store = vector_store
        self._reranker = reranker
        self._similarity_calculator = SimilarityCalculator()

    async def execute(
        self,
        target_identifier: str,
        text_to_embed: str | None = None,
        top_k: int = 50,
        similarity_threshold: float = 0.7,
    ) -> list[Document]:
        """Execute the similar companies search.

        Args:
            target_identifier: Company code or name to search for
            text_to_embed: Optional text for additional search context
            top_k: Number of top results to return (1-100)
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of Document objects representing similar companies

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

                    # Prepare rerank request
                    rerank_request = RerankRequest(
                        query=text_to_embed or target_identifier,
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

            logger.info(
                f"Final ranking completed, returning {len(final_documents)} documents"
            )

            return final_documents

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
