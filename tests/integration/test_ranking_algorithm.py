"""Integration tests for the complete ranking algorithm flow.

This module tests the integration of vector search, reranking, and
final ranking calculation.
"""

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.application.ports import RerankerPort, VectorStorePort
from src.application.ports.reranker_port import (
    RerankRequest,
    RerankResponse,
    RerankResult,
)
from src.application.use_cases.search_similar_companies import (
    SearchSimilarCompaniesUseCase,
)
from src.domain.value_objects import BusinessConceptQuery, Document


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store port."""
    return AsyncMock(spec=VectorStorePort)


@pytest.fixture
def mock_reranker():
    """Create a mock reranker port."""
    return AsyncMock(spec=RerankerPort)


@pytest.fixture
def sample_search_results():
    """Create sample documents returned by vector search."""
    return [
        Document(
            concept_id=UUID("12345678-1234-5678-1234-567812345678"),
            company_code="600036",
            company_name="招商银行",
            concept_name="零售银行业务",
            concept_category="主营业务",
            importance_score=Decimal("0.85"),
            similarity_score=0.88,
            source_concept_id=UUID("87654321-4321-8765-4321-876543218765"),
        ),
        Document(
            concept_id=UUID("23456789-2345-6789-2345-678923456789"),
            company_code="000001",
            company_name="平安银行",
            concept_name="消费金融",
            concept_category="主营业务",
            importance_score=Decimal("0.75"),
            similarity_score=0.82,
            source_concept_id=UUID("87654321-4321-8765-4321-876543218765"),
        ),
        Document(
            concept_id=UUID("34567890-3456-7890-3456-789034567890"),
            company_code="601328",
            company_name="交通银行",
            concept_name="公司银行业务",
            concept_category="主营业务",
            importance_score=Decimal("0.65"),
            similarity_score=0.79,
            source_concept_id=UUID("87654321-4321-8765-4321-876543218765"),
        ),
    ]


@pytest.fixture
def sample_rerank_response(sample_search_results):
    """Create sample rerank response."""
    # Reranker changes the order and assigns new scores
    return RerankResponse(
        results=[
            RerankResult(
                document=sample_search_results[1],  # 平安银行
                rerank_score=0.92,
                original_score=sample_search_results[1].similarity_score,
            ),
            RerankResult(
                document=sample_search_results[0],  # 招商银行
                rerank_score=0.88,
                original_score=sample_search_results[0].similarity_score,
            ),
            RerankResult(
                document=sample_search_results[2],  # 交通银行
                rerank_score=0.75,
                original_score=sample_search_results[2].similarity_score,
            ),
        ],
        processing_time_ms=45.5,
        total_documents=3,
    )


class TestCompleteRankingFlow:
    """Test the complete ranking flow with all components integrated."""

    @pytest.mark.asyncio
    async def test_search_with_reranking_and_final_scoring(
        self,
        mock_vector_store,
        mock_reranker,
        sample_search_results,
        sample_rerank_response,
    ):
        """Test complete flow: vector search -> rerank -> final scoring."""
        # Setup mocks
        mock_vector_store.search_similar_concepts.return_value = sample_search_results
        mock_reranker.rerank_documents.return_value = sample_rerank_response
        mock_reranker.is_ready.return_value = True

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store,
            reranker=mock_reranker,
        )

        # Execute search
        result = await use_case.execute(
            target_identifier="建设银行",
            text_to_embed="银行零售业务",
            top_k=10,
            similarity_threshold=0.7,
        )

        # Extract results list from tuple if needed
        if isinstance(result, tuple):
            results, filter_info = result
        else:
            results = result

        # Verify vector search was called
        mock_vector_store.search_similar_concepts.assert_called_once()
        call_args = mock_vector_store.search_similar_concepts.call_args[0][0]
        assert isinstance(call_args, BusinessConceptQuery)
        assert call_args.target_identifier == "建设银行"
        assert call_args.text_to_embed == "银行零售业务"

        # Verify reranker was called
        mock_reranker.rerank_documents.assert_called_once()
        rerank_args = mock_reranker.rerank_documents.call_args[0][0]
        assert isinstance(rerank_args, RerankRequest)
        assert rerank_args.query == "银行零售业务"
        assert len(rerank_args.documents) == 3

        # Verify final results
        assert len(results) == 3

        # Check final ordering based on weighted scores
        # Default weights: 0.7 * rerank + 0.3 * importance
        # 平安银行: 0.7 * 0.92 + 0.3 * 0.75 = 0.644 + 0.225 = 0.869
        # 招商银行: 0.7 * 0.88 + 0.3 * 0.85 = 0.616 + 0.255 = 0.871
        # 交通银行: 0.7 * 0.75 + 0.3 * 0.65 = 0.525 + 0.195 = 0.72

        # So order should be: 招商银行, 平安银行, 交通银行
        assert results[0].company_code == "600036"  # 招商银行
        assert results[1].company_code == "000001"  # 平安银行
        assert results[2].company_code == "601328"  # 交通银行

    @pytest.mark.asyncio
    async def test_search_without_reranker(
        self,
        mock_vector_store,
        sample_search_results,
    ):
        """Test flow without reranker - should use importance scores only."""
        # Setup mock
        mock_vector_store.search_similar_concepts.return_value = sample_search_results

        # Create use case without reranker
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store,
            reranker=None,
        )

        # Execute search
        result = await use_case.execute(
            target_identifier="建设银行",
            top_k=10,
        )

        # Extract results list from tuple if needed
        if isinstance(result, tuple):
            results, filter_info = result
        else:
            results = result

        # Verify results are sorted by importance score
        assert len(results) == 3
        assert results[0].company_code == "600036"  # 招商银行 (0.85)
        assert results[1].company_code == "000001"  # 平安银行 (0.75)
        assert results[2].company_code == "601328"  # 交通银行 (0.65)

    @pytest.mark.asyncio
    async def test_search_with_reranker_failure(
        self,
        mock_vector_store,
        mock_reranker,
        sample_search_results,
    ):
        """Test graceful degradation when reranker fails."""
        # Setup mocks
        mock_vector_store.search_similar_concepts.return_value = sample_search_results
        mock_reranker.rerank_documents.side_effect = RuntimeError(
            "Reranker service unavailable"
        )
        mock_reranker.is_ready.return_value = True

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store,
            reranker=mock_reranker,
        )

        # Execute search - should not raise exception
        result = await use_case.execute(
            target_identifier="建设银行",
            top_k=10,
        )

        # Extract results list from tuple if needed
        if isinstance(result, tuple):
            results, filter_info = result
        else:
            results = result

        # Verify reranker was attempted
        mock_reranker.rerank_documents.assert_called_once()

        # Verify results fall back to importance score ordering
        assert len(results) == 3
        assert results[0].company_code == "600036"  # 招商银行 (0.85)
        assert results[1].company_code == "000001"  # 平安银行 (0.75)
        assert results[2].company_code == "601328"  # 交通银行 (0.65)

    @pytest.mark.asyncio
    async def test_empty_search_results(
        self,
        mock_vector_store,
        mock_reranker,
    ):
        """Test handling of empty search results."""
        # Setup mock to return empty results
        mock_vector_store.search_similar_concepts.return_value = []

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store,
            reranker=mock_reranker,
        )

        # Execute search
        result = await use_case.execute(
            target_identifier="不存在的公司",
            top_k=10,
        )

        # Extract results list from tuple if needed
        if isinstance(result, tuple):
            results, filter_info = result
        else:
            results = result

        # Verify results
        assert results == []

        # Reranker should not be called for empty results
        mock_reranker.rerank_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_rerank_results(
        self,
        mock_vector_store,
        mock_reranker,
        sample_search_results,
    ):
        """Test when reranker returns fewer documents than input."""
        # Setup mocks
        mock_vector_store.search_similar_concepts.return_value = sample_search_results

        # Reranker only returns top 2 documents
        partial_rerank_response = RerankResponse(
            results=[
                RerankResult(
                    document=sample_search_results[0],
                    rerank_score=0.95,
                    original_score=sample_search_results[0].similarity_score,
                ),
                RerankResult(
                    document=sample_search_results[1],
                    rerank_score=0.90,
                    original_score=sample_search_results[1].similarity_score,
                ),
            ],
            processing_time_ms=35.0,
            total_documents=3,
        )
        mock_reranker.rerank_documents.return_value = partial_rerank_response

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store,
            reranker=mock_reranker,
        )

        # Execute search
        result = await use_case.execute(
            target_identifier="建设银行",
            top_k=2,  # Request only top 2
        )

        # Extract results list from tuple if needed
        if isinstance(result, tuple):
            results, filter_info = result
        else:
            results = result

        # Verify only 2 results returned
        assert len(results) == 2

        # Verify ordering based on final scores
        # 招商银行: 0.7 * 0.95 + 0.3 * 0.85 = 0.665 + 0.255 = 0.92
        # 平安银行: 0.7 * 0.90 + 0.3 * 0.75 = 0.63 + 0.225 = 0.855
        assert results[0].company_code == "600036"  # 招商银行
        assert results[1].company_code == "000001"  # 平安银行

    @pytest.mark.asyncio
    async def test_consistent_source_concept_tracking(
        self,
        mock_vector_store,
        sample_search_results,
    ):
        """Test that source concept ID is preserved through the pipeline."""
        # Setup mock
        mock_vector_store.search_similar_concepts.return_value = sample_search_results

        # Create use case
        use_case = SearchSimilarCompaniesUseCase(
            vector_store=mock_vector_store,
            reranker=None,
        )

        # Execute search
        result = await use_case.execute(
            target_identifier="建设银行",
            top_k=10,
        )

        # Extract results list from tuple if needed
        if isinstance(result, tuple):
            results, filter_info = result
        else:
            results = result

        # Verify all results maintain the same source concept ID
        expected_source_id = UUID("87654321-4321-8765-4321-876543218765")
        # Check source_concept_id in the matched concepts of each aggregated company
        assert all(
            all(
                concept.source_concept_id == expected_source_id
                for concept in company.matched_concepts
            )
            for company in results
        )
