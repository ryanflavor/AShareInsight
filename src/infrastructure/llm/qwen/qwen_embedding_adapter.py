"""
Qwen Embedding model adapter implementation.

This module provides the concrete implementation of EmbeddingServicePort
using the locally deployed Qwen3-Embedding-4B model.
"""

import time
from typing import Any

import aiohttp
import numpy as np
import structlog
from pydantic import BaseModel, ConfigDict
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from src.application.ports.embedding_service_port import (
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingServicePort,
)
from src.infrastructure.monitoring.vectorization_metrics import VectorizationMetrics
from src.shared.config.settings import QwenEmbeddingSettings
from src.shared.exceptions.infrastructure_exceptions import ExternalServiceError

logger = structlog.get_logger(__name__)


class QwenEmbeddingConfig(BaseModel):
    """Configuration for Qwen embedding service."""

    model_config = ConfigDict(extra="forbid")

    base_url: str
    timeout: int
    max_batch_size: int
    normalize: bool
    max_retries: int
    retry_wait_min: int
    retry_wait_max: int
    embedding_dimension: int

    @classmethod
    def from_settings(cls, settings: QwenEmbeddingSettings) -> "QwenEmbeddingConfig":
        """Create config from settings object."""
        return cls(
            base_url=settings.qwen_base_url,
            timeout=settings.qwen_timeout,
            max_batch_size=settings.qwen_max_batch_size,
            normalize=settings.qwen_normalize,
            max_retries=settings.qwen_max_retries,
            retry_wait_min=settings.qwen_retry_wait_min,
            retry_wait_max=settings.qwen_retry_wait_max,
            embedding_dimension=settings.qwen_embedding_dimension,
        )


class QwenEmbeddingAdapter(EmbeddingServicePort):
    """Adapter for Qwen3-Embedding-4B model service.

    This adapter implements the EmbeddingServicePort interface using
    the locally deployed Qwen embedding service API.
    """

    def __init__(self, config: QwenEmbeddingConfig) -> None:
        """Initialize the Qwen embedding adapter.

        Args:
            config: Configuration for the adapter. Must be provided.
        """
        self.config = config
        self._embedding_dimension: int | None = None
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session is initialized."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _make_request(
        self, endpoint: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Make HTTP request to Qwen service with retry logic.

        Args:
            endpoint: API endpoint path
            payload: Request payload

        Returns:
            Response data

        Raises:
            ExternalServiceError: If request fails after retries
        """
        url = f"{self.config.base_url}{endpoint}"
        session = await self._ensure_session()

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(
                multiplier=1,
                min=self.config.retry_wait_min,
                max=self.config.retry_wait_max,
            ),
        ):
            with attempt:
                try:
                    async with session.post(
                        url,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                    ) as response:
                        response.raise_for_status()
                        return await response.json()
                except aiohttp.ClientError as e:
                    raise ExternalServiceError(
                        f"Failed to call Qwen service at {url}: {str(e)}"
                    ) from e

        # This line should never be reached due to retry logic, but added for mypy
        raise ExternalServiceError(f"Unexpected error in retry logic for {url}")

    async def embed_texts(
        self, texts: list[str], batch_size: int = 50
    ) -> list[np.ndarray]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.
            batch_size: Number of texts to process per batch.

        Returns:
            List of embedding vectors as numpy arrays.

        Raises:
            ExternalServiceError: If embedding generation fails.
        """
        if not texts:
            return []

        embeddings = []
        effective_batch_size = min(batch_size, self.config.max_batch_size)

        # Process in batches to respect max_batch_size
        for i in range(0, len(texts), effective_batch_size):
            batch = texts[i : i + effective_batch_size]

            start_time = time.time()

            payload = {"texts": batch, "normalize": self.config.normalize}

            # Track embedding generation with monitoring
            with VectorizationMetrics.track_embedding_generation(
                batch_size=len(batch),
                model=self.get_model_name(),
                expected_dimension=self.get_embedding_dimension(),
            ):
                response = await self._make_request("/embed", payload)

                if not response.get("success"):
                    error_msg = response.get("detail", "Unknown error")
                    VectorizationMetrics.record_model_error(
                        company_code="N/A",  # Will be provided by caller context
                        error_type="embedding_generation_failed",
                        error_message=error_msg,
                    )
                    raise ExternalServiceError(f"Qwen embedding failed: {error_msg}")

                batch_embeddings = response["data"]["embeddings"]
                embeddings.extend([np.array(emb) for emb in batch_embeddings])

                # Update dimension from first successful response
                if self._embedding_dimension is None:
                    self._embedding_dimension = response["data"]["dimensions"]

                # Validate dimensions
                for j, emb in enumerate(batch_embeddings):
                    if len(emb) != self.get_embedding_dimension():
                        VectorizationMetrics.record_dimension_error(
                            company_code="N/A",
                            concept_name=f"batch_{i}_item_{j}",
                            expected=self.get_embedding_dimension(),
                            actual=len(emb),
                        )

                # Log performance metrics
                elapsed = time.time() - start_time
                if len(batch) > 0:
                    # Record batch completion metrics
                    VectorizationMetrics.record_batch_completed(
                        batch_size=len(batch),
                        successful=len(batch_embeddings),
                        failed=0,
                        duration_ms=elapsed * 1000,
                    )
                    logger.info(
                        "batch_embedded",
                        batch_size=len(batch),
                        elapsed_time=elapsed,
                        texts_per_second=len(batch) / elapsed,
                    )

        return embeddings

    async def embed_text(self, text: str) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed.

        Returns:
            Embedding vector as numpy array.

        Raises:
            ExternalServiceError: If embedding generation fails.
        """
        embeddings = await self.embed_texts([text])
        return embeddings[0] if embeddings else np.array([])

    async def embed_texts_with_metadata(
        self, requests: list[EmbeddingRequest], batch_size: int = 50
    ) -> list[EmbeddingResult]:
        """Generate embeddings with associated metadata.

        Args:
            requests: List of embedding requests with text and metadata.
            batch_size: Number of texts to process per batch.

        Returns:
            List of embedding results with vectors and metadata.

        Raises:
            ExternalServiceError: If embedding generation fails.
        """
        if not requests:
            return []

        # Extract texts for batch processing
        texts = [req.text for req in requests]
        embeddings = await self.embed_texts(texts, batch_size)

        # Combine embeddings with metadata
        results = []
        if len(requests) != len(embeddings):
            raise ValueError(
                f"Mismatch between requests ({len(requests)}) "
                f"and embeddings ({len(embeddings)})"
            )

        for req, embedding in zip(requests, embeddings, strict=False):
            results.append(
                EmbeddingResult(
                    text=req.text,
                    embedding=embedding.tolist(),
                    dimension=self.get_embedding_dimension(),
                    metadata=req.metadata,
                )
            )

        return results

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this service.

        Returns:
            The dimension of embedding vectors from config or detected from service.
        """
        return self._embedding_dimension or self.config.embedding_dimension

    def get_model_name(self) -> str:
        """Get the name of the embedding model.

        Returns:
            The model name.
        """
        return "Qwen3-Embedding-4B"

    async def health_check(self) -> bool:
        """Check if the embedding service is healthy and ready.

        Returns:
            True if service is healthy, False otherwise.
        """
        try:
            # Try to embed a simple test text
            result = await self.embed_text("health check")
            return len(result) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session:
            await self._session.close()
            self._session = None
