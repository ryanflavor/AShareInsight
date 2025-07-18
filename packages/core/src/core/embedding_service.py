"""
Embedding service client for Qwen integration.

This module provides a client for interacting with the Qwen embedding service
to generate high-quality text embeddings for business concepts.
"""

import asyncio
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .logging_config import get_logger

logger = get_logger(__name__)


class EmbeddingRequest(BaseModel):
    """Request model for embedding generation."""

    texts: list[str] = Field(..., description="List of texts to embed")
    normalize: bool = Field(True, description="Whether to normalize embeddings")
    batch_size: int | None = Field(None, description="Optional batch size override")


class EmbeddingResponse(BaseModel):
    """Response model for embedding generation."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    stats: dict[str, Any] | None = None


class QwenEmbeddingService:
    """
    Client for Qwen embedding service.

    This service generates 2560-dimensional embeddings using the Qwen3-Embedding-4B model.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9547",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the embedding service client.

        Args:
            base_url: Base URL of the Qwen service
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout, trust_env=False
        )  # Ignore proxy for local service
        self._async_client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    def __del__(self):
        """Cleanup HTTP clients."""
        if hasattr(self, "_client"):
            self._client.close()
        if hasattr(self, "_async_client"):
            asyncio.create_task(self._async_client.aclose())

    def generate_embeddings(
        self, texts: list[str], normalize: bool = True, batch_size: int | None = None
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed
            normalize: Whether to normalize the embeddings
            batch_size: Optional batch size for processing

        Returns:
            List of 2560-dimensional embedding vectors

        Raises:
            Exception: If embedding generation fails
        """
        request = EmbeddingRequest(
            texts=texts, normalize=normalize, batch_size=batch_size
        )

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()

                response = self._client.post(
                    f"{self.base_url}/embed",
                    json=request.model_dump(),
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

                result = EmbeddingResponse(**response.json())

                if not result.success:
                    raise Exception(f"Embedding generation failed: {result.error}")

                embeddings = result.data["embeddings"]
                dimensions = result.data["dimensions"]

                # Verify dimensions
                if dimensions != 2560:
                    raise ValueError(
                        f"Expected 2560-dimensional embeddings, got {dimensions}"
                    )

                elapsed_time = time.time() - start_time
                logger.info(
                    f"Generated {len(embeddings)} embeddings in {elapsed_time:.2f}s",
                    extra={
                        "text_count": len(texts),
                        "dimensions": dimensions,
                        "processing_time": elapsed_time,
                    },
                )

                return embeddings

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2**attempt)  # Exponential backoff

            except Exception as e:
                logger.error(
                    f"Error generating embeddings on attempt {attempt + 1}: {e}"
                )
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2**attempt)

    async def generate_embeddings_async(
        self, texts: list[str], normalize: bool = True, batch_size: int | None = None
    ) -> list[list[float]]:
        """
        Generate embeddings asynchronously.

        Args:
            texts: List of texts to embed
            normalize: Whether to normalize the embeddings
            batch_size: Optional batch size for processing

        Returns:
            List of 2560-dimensional embedding vectors
        """
        request = EmbeddingRequest(
            texts=texts, normalize=normalize, batch_size=batch_size
        )

        for attempt in range(self.max_retries):
            try:
                start_time = time.time()

                response = await self._async_client.post(
                    f"{self.base_url}/embed",
                    json=request.model_dump(),
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

                result = EmbeddingResponse(**response.json())

                if not result.success:
                    raise Exception(f"Embedding generation failed: {result.error}")

                embeddings = result.data["embeddings"]
                dimensions = result.data["dimensions"]

                if dimensions != 2560:
                    raise ValueError(
                        f"Expected 2560-dimensional embeddings, got {dimensions}"
                    )

                elapsed_time = time.time() - start_time
                logger.info(
                    f"Generated {len(embeddings)} embeddings asynchronously in {elapsed_time:.2f}s"
                )

                return embeddings

            except Exception as e:
                logger.error(f"Error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)

    def generate_single_embedding(
        self, text: str, normalize: bool = True
    ) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            normalize: Whether to normalize the embedding

        Returns:
            2560-dimensional embedding vector
        """
        embeddings = self.generate_embeddings([text], normalize=normalize)
        return embeddings[0]

    def health_check(self) -> dict[str, Any]:
        """
        Check the health status of the Qwen service.

        Returns:
            Health status information
        """
        try:
            response = self._client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def get_stats(self) -> dict[str, Any]:
        """
        Get service statistics.

        Returns:
            Service statistics
        """
        try:
            response = self._client.get(f"{self.base_url}/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}


# Singleton instance for convenience
_embedding_service: QwenEmbeddingService | None = None


def get_embedding_service(
    base_url: str = "http://localhost:9547",
    timeout: float = 30.0,
    max_retries: int = 3,
) -> QwenEmbeddingService:
    """
    Get or create a singleton embedding service instance.

    Args:
        base_url: Base URL of the Qwen service
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts

    Returns:
        QwenEmbeddingService instance
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = QwenEmbeddingService(
            base_url=base_url, timeout=timeout, max_retries=max_retries
        )
    return _embedding_service
