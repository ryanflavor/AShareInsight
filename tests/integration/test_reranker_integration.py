"""Integration tests for reranker functionality."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.application.ports.reranker_port import RerankRequest
from src.application.use_cases import SearchSimilarCompaniesUseCase
from src.domain.value_objects import Document
from src.infrastructure.llm.qwen import QwenServiceAdapter, QwenServiceConfig
from src.infrastructure.monitoring import get_metrics
from src.infrastructure.persistence.postgres import PostgresVectorStoreRepository


@pytest.fixture
def test_documents():
    """Create test documents with varying similarity scores."""
    return [
        Document(
            concept_id=uuid4(),
            company_code=f"00000{i}",
            company_name=f"Company {i}",
            concept_name=f"Concept {i}",
            concept_category="Technology",
            importance_score=0.8 - i * 0.05,
            similarity_score=0.9 - i * 0.05,
        )
        for i in range(10)
    ]


@pytest.fixture
def mock_vector_store(test_documents):
    """Create a mock vector store repository."""
    mock = AsyncMock(spec=PostgresVectorStoreRepository)

    async def mock_search(query):
        # Respect top_k parameter
        return test_documents[: query.top_k] if query.top_k else test_documents

    mock.search_similar_concepts.side_effect = mock_search
    return mock


@pytest.fixture
def mock_http_response():
    """Create a mock HTTP response for reranking."""
    return {
        "success": True,
        "data": {
            "results": [
                {"original_index": 9, "score": 0.95},  # Highest score
                {"original_index": 1, "score": 0.90},
                {"original_index": 3, "score": 0.85},
                {"original_index": 7, "score": 0.80},
                {"original_index": 0, "score": 0.75},
                {"original_index": 5, "score": 0.70},
                {"original_index": 2, "score": 0.65},
                {"original_index": 6, "score": 0.60},
                {"original_index": 4, "score": 0.55},
                {"original_index": 8, "score": 0.50},
            ]
        },
    }


class TestRerankerIntegration:
    """Integration tests for reranker with search pipeline."""

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_complete_search_pipeline_with_reranker(
        self, mock_post, mock_vector_store, test_documents
    ):
        """Test complete search pipeline including reranking."""
        # Mock HTTP response for 5 documents
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "results": [
                    {"original_index": 4, "score": 0.95},
                    {"original_index": 1, "score": 0.90},
                    {"original_index": 3, "score": 0.85},
                    {"original_index": 0, "score": 0.80},
                    {"original_index": 2, "score": 0.75},
                ]
            },
        }
        mock_post.return_value = mock_response

        # Create reranker config
        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        # Create reranker and use case
        async with QwenServiceAdapter(config) as reranker:
            use_case = SearchSimilarCompaniesUseCase(
                vector_store=mock_vector_store, reranker=reranker
            )

            # Execute search
            results = await use_case.execute(
                target_identifier="TEST001",
                text_to_embed="cloud computing services",
                top_k=5,
                similarity_threshold=0.5,
            )

        # Verify results
        assert len(results) == 5  # top_k=5
        # Document at index 4 should be first (highest rerank score 0.95)
        assert results[0].company_code == "000004"
        # Document at index 1 should be second (rerank score 0.9)
        assert results[1].company_code == "000001"

        # Verify HTTP call was made
        assert mock_post.call_count >= 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_reranker_performance_tracking(self, mock_post, test_documents):
        """Test that reranker performance is properly tracked."""
        # Mock HTTP response for 5 documents
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "results": [
                    {"original_index": 4, "score": 0.95},
                    {"original_index": 1, "score": 0.90},
                    {"original_index": 3, "score": 0.85},
                ]
            },
        }
        mock_post.return_value = mock_response

        # Reset metrics
        metrics = get_metrics()
        initial_reranks = metrics.total_reranks

        # Create reranker
        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        async with QwenServiceAdapter(config) as reranker:
            # Create request
            request = RerankRequest(
                query="test query",
                documents=test_documents[:5],
                top_k=3,
            )

            # Execute reranking
            response = await reranker.rerank_documents(request)

        # Verify response
        assert len(response.results) == 3  # top_k=3
        assert response.processing_time_ms > 0

        # Verify metrics were updated
        metrics = get_metrics()
        assert metrics.total_reranks == initial_reranks + 1
        assert metrics.total_documents_reranked >= 5

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_reranker_batch_processing(self, mock_post, test_documents):
        """Test that reranker handles batches correctly."""

        # Mock different responses for different batch sizes
        def side_effect(*args, **kwargs):
            mock_response = AsyncMock()
            mock_response.status_code = 200
            # Return results based on input size
            data = kwargs.get("json", {})
            num_docs = len(data.get("documents", []))
            mock_response.json.return_value = {
                "success": True,
                "data": {
                    "results": [
                        {"original_index": i, "score": max(0.1, 0.9 - i * 0.01)}
                        for i in range(num_docs)
                    ]
                },
            }
            return mock_response

        mock_post.side_effect = side_effect

        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        async with QwenServiceAdapter(config) as reranker:
            # Test with large document set
            large_docs = test_documents * 5  # 50 documents
            request = RerankRequest(
                query="test query",
                documents=large_docs,
                top_k=10,
            )

            response = await reranker.rerank_documents(request)

        # Verify results
        assert len(response.results) == 10
        # Verify HTTP call was made
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_reranker_error_handling(
        self, mock_post, mock_vector_store, test_documents
    ):
        """Test graceful degradation when reranker fails."""
        # Mock HTTP error
        mock_post.side_effect = httpx.HTTPError("Connection failed")

        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        async with QwenServiceAdapter(config) as reranker:
            use_case = SearchSimilarCompaniesUseCase(
                vector_store=mock_vector_store, reranker=reranker
            )

            # Execute search - should fall back to original order
            results = await use_case.execute(
                target_identifier="TEST001",
                text_to_embed="cloud computing services",
                top_k=5,
                similarity_threshold=0.5,
            )

        # Verify results use original similarity scores
        assert len(results) == 5
        # Documents should be in original order (by similarity score)
        assert results[0].company_code == "000000"
        assert results[1].company_code == "000001"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_concurrent_rerank_requests(self, mock_post, test_documents):
        """Test handling concurrent rerank requests."""
        # Mock HTTP response for 3 documents
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "results": [
                    {"original_index": 2, "score": 0.95},
                    {"original_index": 0, "score": 0.90},
                    {"original_index": 1, "score": 0.85},
                ]
            },
        }
        mock_post.return_value = mock_response

        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        # Create multiple rerankers for concurrent requests
        async def run_rerank(reranker, documents):
            request = RerankRequest(
                query="test query",
                documents=documents,
                top_k=5,
            )
            return await reranker.rerank_documents(request)

        # Execute concurrent requests
        tasks = []
        rerankers = []
        for i in range(3):
            reranker = QwenServiceAdapter(config)
            await reranker.__aenter__()
            rerankers.append(reranker)

            task = asyncio.create_task(
                run_rerank(reranker, test_documents[i * 3 : (i + 1) * 3])
            )
            tasks.append(task)

        # Wait for all tasks
        results = await asyncio.gather(*tasks)

        # Clean up rerankers
        for reranker in rerankers:
            await reranker.__aexit__(None, None, None)

        # Verify all requests completed
        assert len(results) == 3
        for result in results:
            assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_health_check(self, mock_get):
        """Test reranker health check."""
        # Mock healthy response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy"}
        mock_get.return_value = mock_response

        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        async with QwenServiceAdapter(config) as reranker:
            is_ready = await reranker.is_ready()

        assert is_ready is True
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post")
    async def test_reranker_with_empty_documents(self, mock_post):
        """Test reranker with empty document list."""
        config = QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

        async with QwenServiceAdapter(config) as reranker:
            request = RerankRequest(
                query="test query",
                documents=[],
                top_k=5,
            )

            response = await reranker.rerank_documents(request)

        # Should return empty results without calling service
        assert len(response.results) == 0
        assert mock_post.call_count == 0
