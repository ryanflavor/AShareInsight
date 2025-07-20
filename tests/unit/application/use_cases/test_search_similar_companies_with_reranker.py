"""Unit tests for search similar companies use case with reranker."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.application.ports.reranker_port import RerankResponse, RerankResult
from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.domain.value_objects import Document
from src.shared.exceptions import CompanyNotFoundError, SearchServiceError


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    return AsyncMock()


@pytest.fixture
def mock_reranker():
    """Create a mock reranker."""
    return AsyncMock()


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    return [
        Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="Company A",
            concept_name="E-commerce",
            concept_category="Retail",
            importance_score=0.8,
            similarity_score=0.85,
        ),
        Document(
            concept_id=uuid4(),
            company_code="000002",
            company_name="Company B",
            concept_name="Cloud Services",
            concept_category="Technology",
            importance_score=0.7,
            similarity_score=0.82,
        ),
        Document(
            concept_id=uuid4(),
            company_code="000003",
            company_name="Company C",
            concept_name="Digital Payment",
            concept_category="Fintech",
            importance_score=0.9,
            similarity_score=0.80,
        ),
    ]


class TestSearchSimilarCompaniesWithReranker:
    """Test cases for search use case with reranker integration."""

    @pytest.mark.asyncio
    async def test_search_without_reranker(self, mock_vector_store, sample_documents):
        """Test search when reranker is not provided."""
        # Setup mock
        mock_vector_store.search_similar_concepts.return_value = sample_documents

        # Create use case without reranker
        use_case = SearchSimilarCompaniesUseCase(vector_store=mock_vector_store)

        # Execute search
        results = await use_case.execute(
            target_identifier="TEST001",
            top_k=10,
            similarity_threshold=0.7,
        )

        # Verify
        assert len(results) == 3
        assert results == sample_documents  # Original order maintained
        mock_vector_store.search_similar_concepts.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_reranker_success(
        self, mock_vector_store, mock_reranker, sample_documents
    ):
        """Test successful search with reranking."""
        # Setup vector store mock
        mock_vector_store.search_similar_concepts.return_value = sample_documents

        # Setup reranker mock - reorder documents (C, A, B)
        reranked_results = [
            RerankResult(
                document=sample_documents[2],  # Company C
                rerank_score=0.95,
                original_score=0.80,
            ),
            RerankResult(
                document=sample_documents[0],  # Company A
                rerank_score=0.88,
                original_score=0.85,
            ),
            RerankResult(
                document=sample_documents[1],  # Company B
                rerank_score=0.75,
                original_score=0.82,
            ),
        ]
        mock_reranker.rerank_documents.return_value = RerankResponse(
            results=reranked_results,
            processing_time_ms=50.0,
            total_documents=3,
        )

        # Create use case with reranker
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store, reranker=mock_reranker
        )

        # Execute search
        results = await use_case.execute(
            target_identifier="TEST001",
            text_to_embed="cloud computing services",
            top_k=10,
            similarity_threshold=0.7,
        )

        # Verify reranking occurred
        assert len(results) == 3
        assert results[0].company_code == "000003"  # Company C first
        assert results[1].company_code == "000001"  # Company A second
        assert results[2].company_code == "000002"  # Company B third

        # Verify calls
        mock_vector_store.search_similar_concepts.assert_called_once()
        mock_reranker.rerank_documents.assert_called_once()

        # Verify rerank request
        rerank_request = mock_reranker.rerank_documents.call_args[0][0]
        assert rerank_request.query == "cloud computing services"
        assert len(rerank_request.documents) == 3
        assert rerank_request.top_k == 10

    @pytest.mark.asyncio
    async def test_search_with_reranker_failure_graceful_degradation(
        self, mock_vector_store, mock_reranker, sample_documents
    ):
        """Test graceful degradation when reranker fails."""
        # Setup vector store mock
        mock_vector_store.search_similar_concepts.return_value = sample_documents

        # Setup reranker to fail
        mock_reranker.rerank_documents.side_effect = RuntimeError("Reranker crashed")

        # Create use case with reranker
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store, reranker=mock_reranker
        )

        # Execute search
        results = await use_case.execute(
            target_identifier="TEST001",
            top_k=10,
            similarity_threshold=0.7,
        )

        # Verify original results are returned
        assert len(results) == 3
        assert results == sample_documents  # Original order maintained
        mock_reranker.rerank_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_empty_results(self, mock_vector_store, mock_reranker):
        """Test search with empty results doesn't call reranker."""
        # Setup vector store to return empty list
        mock_vector_store.search_similar_concepts.return_value = []

        # Create use case with reranker
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store, reranker=mock_reranker
        )

        # Execute search
        results = await use_case.execute(
            target_identifier="TEST001",
            top_k=10,
            similarity_threshold=0.7,
        )

        # Verify
        assert results == []
        mock_vector_store.search_similar_concepts.assert_called_once()
        # Reranker should not be called for empty results
        mock_reranker.rerank_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_with_reranker_respects_top_k(
        self, mock_vector_store, mock_reranker, sample_documents
    ):
        """Test that top_k parameter is passed to reranker."""
        # Setup mocks
        mock_vector_store.search_similar_concepts.return_value = sample_documents

        # Reranker returns only 2 documents (respecting top_k)
        reranked_results = [
            RerankResult(
                document=sample_documents[2],
                rerank_score=0.95,
                original_score=0.80,
            ),
            RerankResult(
                document=sample_documents[0],
                rerank_score=0.88,
                original_score=0.85,
            ),
        ]
        mock_reranker.rerank_documents.return_value = RerankResponse(
            results=reranked_results,
            processing_time_ms=30.0,
            total_documents=3,
        )

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store, reranker=mock_reranker
        )

        # Execute with top_k=2
        results = await use_case.execute(
            target_identifier="TEST001",
            top_k=2,
            similarity_threshold=0.7,
        )

        # Verify
        assert len(results) == 2
        rerank_request = mock_reranker.rerank_documents.call_args[0][0]
        assert rerank_request.top_k == 2

    @pytest.mark.asyncio
    async def test_search_company_not_found(self, mock_vector_store, mock_reranker):
        """Test handling of company not found error."""
        # Setup vector store to raise CompanyNotFoundError
        mock_vector_store.search_similar_concepts.side_effect = CompanyNotFoundError(
            "UNKNOWN"
        )

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store, reranker=mock_reranker
        )

        # Verify exception is propagated
        with pytest.raises(CompanyNotFoundError):
            await use_case.execute(target_identifier="UNKNOWN")

        # Reranker should not be called
        mock_reranker.rerank_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_service_error(self, mock_vector_store, mock_reranker):
        """Test handling of general search errors."""
        # Setup vector store to raise exception
        mock_vector_store.search_similar_concepts.side_effect = Exception(
            "Database connection failed"
        )

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store, reranker=mock_reranker
        )

        # Verify exception is wrapped in SearchServiceError
        with pytest.raises(SearchServiceError) as exc_info:
            await use_case.execute(target_identifier="TEST001")

        assert "search_similar_companies" in str(exc_info.value)
        assert "Database connection failed" in str(exc_info.value)
