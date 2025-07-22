"""
Port interface for embedding service.

This module defines the abstract interface for text embedding services,
following the hexagonal architecture pattern.
"""

from abc import ABC, abstractmethod

import numpy as np
from pydantic import BaseModel


class EmbeddingRequest(BaseModel):
    """Request model for embedding generation."""

    text: str
    metadata: dict | None = None


class EmbeddingResult(BaseModel):
    """Result model for embedding generation."""

    text: str
    embedding: list[float]
    dimension: int
    metadata: dict | None = None

    model_config = {"arbitrary_types_allowed": True}


class EmbeddingServicePort(ABC):
    """Abstract interface for text embedding services.

    This port defines the contract that any embedding service implementation
    must fulfill. It abstracts away the specific embedding model implementation
    details from the application layer.
    """

    @abstractmethod
    async def embed_texts(
        self, texts: list[str], batch_size: int = 50
    ) -> list[np.ndarray]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts to process per batch (default: 50).

        Returns:
            List of embedding vectors as numpy arrays.
            The order of embeddings corresponds to the order of input texts.

        Raises:
            EmbeddingServiceError: If embedding generation fails.
        """
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed.

        Returns:
            Embedding vector as a numpy array.

        Raises:
            EmbeddingServiceError: If embedding generation fails.
        """
        pass

    @abstractmethod
    async def embed_texts_with_metadata(
        self, requests: list[EmbeddingRequest], batch_size: int = 50
    ) -> list[EmbeddingResult]:
        """Generate embeddings with associated metadata.

        Args:
            requests: List of embedding requests with text and metadata.
            batch_size: Number of texts to process per batch (default: 50).

        Returns:
            List of embedding results with vectors and metadata.

        Raises:
            EmbeddingServiceError: If embedding generation fails.
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this service.

        Returns:
            The dimension (number of components) of embedding vectors.
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the name of the embedding model.

        Returns:
            The model name (e.g., "Qwen3-Embedding-4B").
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the embedding service is healthy and ready.

        Returns:
            True if service is healthy, False otherwise.
        """
        pass
