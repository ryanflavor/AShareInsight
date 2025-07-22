"""
Unit tests for EmbeddingServicePort interface.
"""

from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from src.application.ports.embedding_service_port import (
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingServicePort,
)


class TestEmbeddingRequest:
    """Test cases for EmbeddingRequest model."""

    def test_create_with_text_only(self):
        """Test creating request with text only."""
        request = EmbeddingRequest(text="sample text")
        assert request.text == "sample text"
        assert request.metadata is None

    def test_create_with_metadata(self):
        """Test creating request with metadata."""
        metadata = {"id": "123", "source": "test"}
        request = EmbeddingRequest(text="sample text", metadata=metadata)
        assert request.text == "sample text"
        assert request.metadata == metadata


class TestEmbeddingResult:
    """Test cases for EmbeddingResult model."""

    def test_create_result(self):
        """Test creating embedding result."""
        embedding = [0.1, 0.2, 0.3]
        result = EmbeddingResult(
            text="sample text", embedding=embedding, dimension=3, metadata={"id": "123"}
        )
        assert result.text == "sample text"
        assert result.embedding == embedding
        assert result.dimension == 3
        assert result.metadata == {"id": "123"}

    def test_create_result_without_metadata(self):
        """Test creating result without metadata."""
        result = EmbeddingResult(text="sample text", embedding=[0.1, 0.2], dimension=2)
        assert result.metadata is None


class TestEmbeddingServicePort:
    """Test cases for EmbeddingServicePort interface."""

    def test_abstract_interface_cannot_be_instantiated(self):
        """Test that the abstract port interface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            EmbeddingServicePort()

    def test_concrete_implementation_must_implement_all_methods(self):
        """Test that concrete implementations must implement all abstract methods."""

        class IncompleteImplementation(EmbeddingServicePort):
            async def embed_texts(
                self, texts: list[str], batch_size: int = 50
            ) -> list[np.ndarray]:
                return [np.array([0.1, 0.2]) for _ in texts]

        with pytest.raises(TypeError):
            IncompleteImplementation()

    @pytest.mark.asyncio
    async def test_mock_implementation_follows_interface(self):
        """Test that a mock implementation can follow the interface correctly."""
        mock_service = Mock(spec=EmbeddingServicePort)

        # Configure mock behavior for async methods
        mock_service.embed_texts = AsyncMock(
            return_value=[np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]
        )
        mock_service.embed_text = AsyncMock(return_value=np.array([0.1, 0.2, 0.3]))
        mock_service.embed_texts_with_metadata = AsyncMock(
            return_value=[
                EmbeddingResult(
                    text="text1",
                    embedding=[0.1, 0.2, 0.3],
                    dimension=3,
                    metadata={"id": "1"},
                ),
                EmbeddingResult(
                    text="text2",
                    embedding=[0.4, 0.5, 0.6],
                    dimension=3,
                    metadata={"id": "2"},
                ),
            ]
        )
        mock_service.get_embedding_dimension.return_value = 3
        mock_service.get_model_name.return_value = "mock-model"
        mock_service.health_check = AsyncMock(return_value=True)

        # Test embed_texts
        result = await mock_service.embed_texts(["text1", "text2"])
        assert len(result) == 2
        assert isinstance(result[0], np.ndarray)
        assert result[0].shape == (3,)

        # Test embed_text
        result = await mock_service.embed_text("single text")
        assert isinstance(result, np.ndarray)
        assert result.shape == (3,)

        # Test embed_texts_with_metadata
        requests = [
            EmbeddingRequest(text="text1", metadata={"id": "1"}),
            EmbeddingRequest(text="text2", metadata={"id": "2"}),
        ]
        results = await mock_service.embed_texts_with_metadata(requests)
        assert len(results) == 2
        assert results[0].text == "text1"
        assert results[0].dimension == 3

        # Test get_embedding_dimension
        dimension = mock_service.get_embedding_dimension()
        assert dimension == 3

        # Test get_model_name
        model_name = mock_service.get_model_name()
        assert model_name == "mock-model"

        # Test health_check
        health = await mock_service.health_check()
        assert health is True
