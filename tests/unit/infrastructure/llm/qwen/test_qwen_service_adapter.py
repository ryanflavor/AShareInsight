"""Unit tests for QwenServiceAdapter."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.application.ports.reranker_port import RerankRequest
from src.domain.value_objects.document import Document
from src.infrastructure.llm.qwen.qwen_service_adapter import (
    QwenServiceAdapter,
    QwenServiceConfig,
)
from src.shared.exceptions import ModelInferenceError, ModelLoadError


@asynccontextmanager
async def mock_track_performance_context(*args, **kwargs):
    """Mock context manager for track_rerank_performance."""
    yield


class TestQwenServiceAdapter:
    """Unit tests for Qwen Service HTTP adapter."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return QwenServiceConfig(
            service_url="http://localhost:9547",
            timeout_seconds=5.0,
            max_retries=2,
        )

    @pytest.fixture
    def test_documents(self):
        """Create test documents."""
        return [
            Document(
                concept_id=uuid4(),
                company_code=f"00000{i}",
                company_name=f"Company {i}",
                concept_name=f"Concept {i}",
                concept_category="Technology",
                importance_score=0.8,
                similarity_score=0.85 - i * 0.05,
            )
            for i in range(3)
        ]

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_adapter_initialization(self, config):
        """Test adapter initialization."""
        adapter = QwenServiceAdapter(config)
        assert adapter.config == config
        assert adapter._is_ready is False

    @pytest.mark.asyncio
    async def test_health_check_success(self, config, mock_http_client):
        """Test successful health check."""
        # Mock successful health response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_http_client.get.return_value = mock_response

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client

        # Check health
        await adapter._check_service_health()

        assert adapter._is_ready is True
        mock_http_client.get.assert_called_once_with("/health")

    @pytest.mark.asyncio
    async def test_health_check_failure(self, config, mock_http_client):
        """Test failed health check."""
        # Mock failed health response
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_http_client.get.return_value = mock_response

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client

        # Check health should raise error
        with pytest.raises(ModelLoadError) as exc_info:
            await adapter._check_service_health()

        assert "unhealthy" in str(exc_info.value).lower()
        assert adapter._is_ready is False

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, config, mock_http_client):
        """Test health check with connection error."""
        # Mock connection error
        mock_http_client.get.side_effect = httpx.RequestError("Connection refused")

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client

        # Check health should raise error
        with pytest.raises(ModelLoadError) as exc_info:
            await adapter._check_service_health()

        assert "Failed to connect" in str(exc_info.value)
        assert adapter._is_ready is False

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_rerank_documents_success(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test successful document reranking."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # Mock successful rerank response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        # Properly mock the json() method to return a value, not a coroutine
        mock_response.json = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "results": [
                        {"original_index": 2, "score": 0.95},
                        {"original_index": 0, "score": 0.90},
                        {"original_index": 1, "score": 0.85},
                    ]
                },
            }
        )
        mock_http_client.post.return_value = mock_response

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        # Create request
        request = RerankRequest(
            query="test query",
            documents=test_documents,
            top_k=2,
        )

        # Execute reranking
        response = await adapter.rerank_documents(request)

        # Verify results
        assert len(response.results) == 2  # top_k=2
        assert response.results[0].document.company_code == "000002"  # highest score
        assert response.results[0].rerank_score == 0.95
        assert response.results[1].document.company_code == "000000"  # second highest
        assert response.results[1].rerank_score == 0.90
        assert response.processing_time_ms > 0

        # Verify HTTP call
        mock_http_client.post.assert_called_once()
        call_args = mock_http_client.post.call_args
        assert call_args[0][0] == "/rerank"
        assert "query" in call_args[1]["json"]
        assert "documents" in call_args[1]["json"]

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_rerank_with_empty_documents(
        self, mock_track_performance, config, mock_http_client
    ):
        """Test reranking with empty document list."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        # Create request with empty documents
        request = RerankRequest(
            query="test query",
            documents=[],
            top_k=5,
        )

        # Execute reranking
        response = await adapter.rerank_documents(request)

        # Should return empty results without calling service
        assert len(response.results) == 0
        assert response.processing_time_ms > 0
        mock_http_client.post.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_rerank_service_not_ready(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test reranking when service is not ready."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # Mock health check to succeed
        mock_health_response = AsyncMock()
        mock_health_response.status_code = 200
        mock_http_client.get.return_value = mock_health_response

        # Mock rerank response
        mock_rerank_response = AsyncMock()
        mock_rerank_response.status_code = 200
        mock_rerank_response.json = AsyncMock(
            return_value={
                "success": True,
                "data": {"results": [{"original_index": 0, "score": 0.9}]},
            }
        )
        mock_http_client.post.return_value = mock_rerank_response

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        # Service not ready initially
        adapter._is_ready = False

        request = RerankRequest(
            query="test query",
            documents=test_documents[:1],
            top_k=1,
        )

        # Should check health first, then rerank
        response = await adapter.rerank_documents(request)

        assert len(response.results) == 1
        mock_http_client.get.assert_called_once_with("/health")

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_rerank_http_error(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test reranking with HTTP error."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # Mock HTTP error
        mock_http_client.post.side_effect = httpx.HTTPError("Server error")

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        request = RerankRequest(
            query="test query",
            documents=test_documents,
            top_k=2,
        )

        # Should raise ModelInferenceError
        with pytest.raises(ModelInferenceError) as exc_info:
            await adapter.rerank_documents(request)

        assert "Unexpected error during reranking" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_rerank_invalid_response(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test reranking with invalid response format."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # Mock invalid response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(return_value={"invalid": "response"})
        mock_http_client.post.return_value = mock_response

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        request = RerankRequest(
            query="test query",
            documents=test_documents,
            top_k=2,
        )

        # Should raise ModelInferenceError
        with pytest.raises(ModelInferenceError) as exc_info:
            await adapter.rerank_documents(request)

        assert "Invalid response" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_rerank_out_of_bounds_index(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test reranking with out of bounds index in response."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # Mock response with invalid index
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = AsyncMock(
            return_value={
                "success": True,
                "data": {
                    "results": [
                        {"original_index": 0, "score": 0.9},
                        {"original_index": 10, "score": 0.8},  # Out of bounds
                    ]
                },
            }
        )
        mock_http_client.post.return_value = mock_response

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        request = RerankRequest(
            query="test query",
            documents=test_documents,  # Only 3 documents
            top_k=2,
        )

        # Should raise ModelInferenceError
        with pytest.raises(ModelInferenceError) as exc_info:
            await adapter.rerank_documents(request)

        assert "Invalid document index" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_is_ready_check(self, config, mock_http_client):
        """Test is_ready method."""
        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client

        # Initially not ready
        assert await adapter.is_ready() is False

        # Set ready state
        adapter._is_ready = True
        assert await adapter.is_ready() is True

        # Test with health check failure
        adapter._is_ready = False
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_http_client.get.return_value = mock_response

        # Should return False on health check failure
        assert await adapter.is_ready() is False

    @pytest.mark.asyncio
    async def test_close_method(self, config, mock_http_client):
        """Test close method."""
        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client

        await adapter.close()

        mock_http_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, config):
        """Test async context manager."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Mock health check
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response

            async with QwenServiceAdapter(config) as adapter:
                assert adapter.client is mock_client

            # Should close client on exit
            mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_retry_mechanism(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test retry mechanism on transient failures."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # First call fails, second succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status_code = 500

        mock_response_success = AsyncMock()
        mock_response_success.status_code = 200
        mock_response_success.json = AsyncMock(
            return_value={
                "success": True,
                "data": {"results": [{"original_index": 0, "score": 0.9}]},
            }
        )

        mock_http_client.post.side_effect = [
            mock_response_fail,
            mock_response_success,
        ]

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        request = RerankRequest(
            query="test query",
            documents=test_documents[:1],
            top_k=1,
        )

        # Should succeed after retry
        response = await adapter.rerank_documents(request)

        assert len(response.results) == 1
        assert mock_http_client.post.call_count == 2  # One failure, one success

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.qwen.qwen_service_adapter.track_rerank_performance")
    async def test_document_to_text_conversion(
        self, mock_track_performance, config, mock_http_client, test_documents
    ):
        """Test document to text conversion for reranking."""
        # Mock the performance tracking context manager
        mock_track_performance.return_value = mock_track_performance_context()
        # Capture the actual request sent
        captured_request = None

        async def capture_request(*args, **kwargs):
            nonlocal captured_request
            captured_request = kwargs.get("json", {})
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = AsyncMock(
                return_value={
                    "success": True,
                    "data": {"results": [{"original_index": 0, "score": 0.9}]},
                }
            )
            return mock_response

        mock_http_client.post.side_effect = capture_request

        adapter = QwenServiceAdapter(config)
        adapter.client = mock_http_client
        adapter._is_ready = True

        request = RerankRequest(
            query="test query",
            documents=test_documents[:1],
            top_k=1,
        )

        await adapter.rerank_documents(request)

        # Verify document was converted to text with Chinese labels
        assert captured_request is not None
        assert "documents" in captured_request
        assert len(captured_request["documents"]) == 1
        doc_text = captured_request["documents"][0]
        assert "公司名称: Company 0" in doc_text
        assert "股票代码: 000000" in doc_text
        assert "业务概念: Concept 0" in doc_text
        assert "概念类别: Technology" in doc_text
        assert "重要性: 0.80" in doc_text
