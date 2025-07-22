"""Unit tests for Qwen embedding adapter."""

from unittest.mock import AsyncMock, patch

import aiohttp
import numpy as np
import pytest

from src.application.ports.embedding_service_port import (
    EmbeddingRequest,
    EmbeddingResult,
)
from src.infrastructure.llm.qwen.qwen_embedding_adapter import (
    QwenEmbeddingAdapter,
    QwenEmbeddingConfig,
)
from src.shared.exceptions.infrastructure_exceptions import ExternalServiceError


class TestQwenEmbeddingConfig:
    """Test cases for QwenEmbeddingConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        # QwenEmbeddingConfig now requires all fields
        config = QwenEmbeddingConfig(
            base_url="http://localhost:9547",
            model_name="Qwen3-Embedding-4B",
            timeout=300,
            max_batch_size=50,
            normalize=True,
            max_retries=3,
            retry_wait_min=1,
            retry_wait_max=10,
            embedding_dimension=2560,
        )
        assert config.base_url == "http://localhost:9547"
        assert config.timeout == 300
        assert config.max_batch_size == 50
        assert config.normalize is True
        assert config.max_retries == 3
        assert config.retry_wait_min == 1
        assert config.retry_wait_max == 10
        assert config.embedding_dimension == 2560

    def test_custom_config(self):
        """Test custom configuration values."""
        config = QwenEmbeddingConfig(
            base_url="http://custom:8080",
            model_name="Custom-Model",
            timeout=60,
            max_batch_size=100,
            normalize=False,
            max_retries=5,
            retry_wait_min=2,
            retry_wait_max=20,
            embedding_dimension=1024,
        )
        assert config.base_url == "http://custom:8080"
        assert config.model_name == "Custom-Model"
        assert config.timeout == 60
        assert config.max_batch_size == 100
        assert config.normalize is False
        assert config.embedding_dimension == 1024


class TestQwenEmbeddingAdapter:
    """Test cases for QwenEmbeddingAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create a Qwen embedding adapter instance."""
        config = QwenEmbeddingConfig(
            base_url="http://localhost:9547",
            model_name="Qwen3-Embedding-4B",
            timeout=300,
            max_batch_size=50,
            normalize=True,
            max_retries=3,
            retry_wait_min=1,
            retry_wait_max=10,
            embedding_dimension=2560,
        )
        return QwenEmbeddingAdapter(config)

    @pytest.fixture
    def mock_response(self):
        """Create a mock successful response."""
        return {
            "success": True,
            "data": {"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], "dimensions": 3},
        }

    @pytest.mark.asyncio
    async def test_embed_text_success(self, adapter, mock_response):
        """Test successful single text embedding."""
        mock_response["data"]["embeddings"] = [[0.1, 0.2, 0.3]]

        with patch.object(
            adapter, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await adapter.embed_text("test text")

            assert isinstance(result, np.ndarray)
            assert result.shape == (3,)
            np.testing.assert_array_equal(result, np.array([0.1, 0.2, 0.3]))
            mock_request.assert_called_once_with(
                "/embed", {"texts": ["test text"], "normalize": True}
            )

    @pytest.mark.asyncio
    async def test_embed_texts_success(self, adapter, mock_response):
        """Test successful batch text embedding."""
        with patch.object(
            adapter, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            texts = ["text1", "text2"]
            results = await adapter.embed_texts(texts)

            assert len(results) == 2
            assert all(isinstance(r, np.ndarray) for r in results)
            assert all(r.shape == (3,) for r in results)
            np.testing.assert_array_equal(results[0], np.array([0.1, 0.2, 0.3]))
            np.testing.assert_array_equal(results[1], np.array([0.4, 0.5, 0.6]))

    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self, adapter):
        """Test embedding empty text list."""
        result = await adapter.embed_texts([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_texts_batch_processing(self, adapter):
        """Test batch processing with texts exceeding max_batch_size."""
        adapter.config.max_batch_size = 2
        texts = ["text1", "text2", "text3", "text4", "text5"]

        mock_responses = [
            {
                "success": True,
                "data": {"embeddings": [[0.1, 0.2], [0.3, 0.4]], "dimensions": 2},
            },
            {
                "success": True,
                "data": {"embeddings": [[0.5, 0.6], [0.7, 0.8]], "dimensions": 2},
            },
            {"success": True, "data": {"embeddings": [[0.9, 1.0]], "dimensions": 2}},
        ]

        with patch.object(
            adapter, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = mock_responses

            results = await adapter.embed_texts(texts)

            assert len(results) == 5
            assert mock_request.call_count == 3

    @pytest.mark.asyncio
    async def test_embed_texts_with_metadata(self, adapter):
        """Test embedding with metadata."""
        requests = [
            EmbeddingRequest(text="text1", metadata={"id": "1", "type": "doc"}),
            EmbeddingRequest(text="text2", metadata={"id": "2", "type": "query"}),
        ]

        mock_response = {
            "success": True,
            "data": {"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], "dimensions": 3},
        }

        with patch.object(
            adapter, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            results = await adapter.embed_texts_with_metadata(requests)

            assert len(results) == 2
            assert all(isinstance(r, EmbeddingResult) for r in results)

            assert results[0].text == "text1"
            assert results[0].embedding == [0.1, 0.2, 0.3]
            assert results[0].dimension == 3
            assert results[0].metadata == {"id": "1", "type": "doc"}

            assert results[1].text == "text2"
            assert results[1].embedding == [0.4, 0.5, 0.6]
            assert results[1].dimension == 3
            assert results[1].metadata == {"id": "2", "type": "query"}

    @pytest.mark.asyncio
    async def test_error_handling(self, adapter):
        """Test error handling for failed requests."""
        with patch.object(
            adapter, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = {
                "success": False,
                "detail": "Service unavailable",
            }

            with pytest.raises(ExternalServiceError) as exc_info:
                await adapter.embed_text("test")

            assert "Qwen embedding failed: Service unavailable" in str(exc_info.value)

    def test_get_embedding_dimension(self, adapter):
        """Test getting embedding dimension."""
        # Default dimension
        assert adapter.get_embedding_dimension() == 2560

        # After setting dimension
        adapter._embedding_dimension = 3
        assert adapter.get_embedding_dimension() == 3

    def test_get_model_name(self, adapter):
        """Test getting model name."""
        assert adapter.get_model_name() == "Qwen3-Embedding-4B"

    @pytest.mark.asyncio
    async def test_health_check_success(self, adapter):
        """Test successful health check."""
        with patch.object(adapter, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = np.array([0.1, 0.2, 0.3])

            result = await adapter.health_check()
            assert result is True
            mock_embed.assert_called_once_with("health check")

    @pytest.mark.asyncio
    async def test_health_check_failure(self, adapter):
        """Test failed health check."""
        with patch.object(adapter, "embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = Exception("Service unavailable")

            result = await adapter.health_check()
            assert result is False

    @pytest.mark.asyncio
    async def test_session_management(self, adapter):
        """Test aiohttp session management."""
        # Session should be None initially
        assert adapter._session is None

        # Session should be created on first use
        session = await adapter._ensure_session()
        assert isinstance(session, aiohttp.ClientSession)
        assert adapter._session is session

        # Same session should be returned
        session2 = await adapter._ensure_session()
        assert session2 is session

        # Close session
        await adapter.close()
        assert adapter._session is None

    @pytest.mark.asyncio
    async def test_performance_logging(self, adapter, mock_response, capsys):
        """Test that performance metrics are logged."""
        with patch.object(
            adapter, "_make_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            await adapter.embed_texts(["text1", "text2"])

            captured = capsys.readouterr()
            # Check for the actual log output format
            assert "batch_embedded" in captured.out
            assert "batch_size=2" in captured.out
            assert "texts_per_second" in captured.out
