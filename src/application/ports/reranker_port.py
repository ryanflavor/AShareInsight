"""Reranker port interface for document reranking.

This module defines the abstract interface for reranking services
that improve search result relevance through neural reranking models.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from src.domain.value_objects.document import Document


class RerankRequest(BaseModel):
    """Request model for document reranking.

    Attributes:
        query: The original search query text
        documents: List of documents to rerank
        top_k: Optional limit on number of results to return
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The search query text for reranking context",
    )
    documents: list[Document] = Field(
        ..., min_length=0, max_length=1000, description="List of documents to rerank"
    )
    top_k: int | None = Field(
        None, ge=1, le=100, description="Return only top K results after reranking"
    )


class RerankResult(BaseModel):
    """Result model for document reranking.

    Attributes:
        document: The reranked document
        rerank_score: The reranking model's relevance score
        original_score: The original similarity score
    """

    document: Document = Field(..., description="The reranked document")
    rerank_score: float = Field(
        ..., ge=0.0, le=1.0, description="Reranking model's relevance score"
    )
    original_score: float = Field(
        ..., ge=0.0, le=1.0, description="Original similarity score from vector search"
    )


class RerankResponse(BaseModel):
    """Response model for document reranking.

    Attributes:
        results: List of reranked documents with scores
        processing_time_ms: Time taken for reranking in milliseconds
        total_documents: Total number of documents processed
    """

    results: list[RerankResult] = Field(
        ..., description="Reranked documents ordered by relevance"
    )
    processing_time_ms: float = Field(
        ..., ge=0.0, description="Processing time in milliseconds"
    )
    total_documents: int = Field(
        ..., ge=0, description="Total number of documents processed"
    )


class RerankerPort(ABC):
    """Abstract port interface for document reranking services.

    This interface defines the contract for reranking services that
    take initial search results and reorder them based on more
    sophisticated relevance scoring.
    """

    @abstractmethod
    async def rerank_documents(self, request: RerankRequest) -> RerankResponse:
        """Rerank a list of documents based on query relevance.

        This method takes documents from initial vector search and
        reorders them using a neural reranking model to improve
        result relevance.

        Args:
            request: The reranking request containing query and documents

        Returns:
            RerankResponse containing reranked documents with scores

        Raises:
            ValueError: If the request is invalid
            RuntimeError: If the reranking model fails
        """
        pass

    @abstractmethod
    async def is_ready(self) -> bool:
        """Check if the reranker service is ready to process requests.

        Returns:
            True if the service is ready, False otherwise
        """
        pass
