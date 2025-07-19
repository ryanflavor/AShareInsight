"""Qwen Service HTTP adapter implementation.

This module provides the concrete implementation of the RerankerPort
using the HTTP API of the running qwen_service.
"""

import asyncio
import logging
import time

import httpx
from pydantic import BaseModel, Field

from src.application.ports.reranker_port import (
    RerankerPort,
    RerankRequest,
    RerankResponse,
    RerankResult,
)
from src.infrastructure.monitoring import track_rerank_performance
from src.shared.exceptions import ModelInferenceError, ModelLoadError

logger = logging.getLogger(__name__)


class QwenServiceConfig(BaseModel):
    """Configuration for Qwen Service HTTP adapter.

    Attributes:
        service_url: Base URL of the Qwen service
        rerank_endpoint: Endpoint for reranking
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum retry attempts
    """

    service_url: str = Field(default="http://localhost:8000")
    rerank_endpoint: str = Field(default="/rerank")
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff: float = Field(default=0.5, ge=0.1, le=5.0)


class QwenServiceAdapter(RerankerPort):
    """Qwen Service HTTP adapter for document reranking.

    This adapter communicates with the qwen_service HTTP API
    for high-quality document reranking.
    """

    def __init__(self, config: QwenServiceConfig) -> None:
        """Initialize the Qwen Service adapter.

        Args:
            config: Configuration for the service adapter
        """
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=self.config.service_url, timeout=self.config.timeout_seconds
        )
        self._is_ready = False
        logger.info(
            f"Initialized Qwen Service adapter pointing to {self.config.service_url}"
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self._check_service_health()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    async def _check_service_health(self) -> None:
        """Check if the service is healthy.

        Raises:
            ModelLoadError: If service is not available
        """
        try:
            response = await self.client.get("/health")
            if response.status_code == 200:
                self._is_ready = True
                logger.info("Qwen Service is healthy and ready")
            else:
                raise ModelLoadError(
                    f"Qwen Service unhealthy: status {response.status_code}"
                )
        except httpx.RequestError as e:
            raise ModelLoadError(
                f"Failed to connect to Qwen Service at "
                f"{self.config.service_url}: {str(e)}"
            ) from e

    async def rerank_documents(self, request: RerankRequest) -> RerankResponse:
        """Rerank documents using Qwen Service HTTP API.

        Args:
            request: The reranking request

        Returns:
            RerankResponse with reranked documents

        Raises:
            ModelInferenceError: If service call fails
        """
        if not self._is_ready:
            await self._check_service_health()

        start_time = time.perf_counter()

        # Handle empty document list
        if not request.documents:
            processing_time_ms = (time.perf_counter() - start_time) * 1000
            return RerankResponse(
                results=[], processing_time_ms=processing_time_ms, total_documents=0
            )

        # Prepare request payload
        # Convert documents to text format for the service
        document_texts = []
        for doc in request.documents:
            # Build comprehensive document text with all relevant fields
            text_parts = [
                f"公司名称: {doc.company_name}",
                f"股票代码: {doc.company_code}",
                f"业务概念: {doc.concept_name}",
            ]

            if doc.concept_category:
                text_parts.append(f"概念类别: {doc.concept_category}")

            # Include importance score as it may help with relevance ranking
            text_parts.append(f"重要性: {float(doc.importance_score):.2f}")

            doc_text = " | ".join(text_parts)
            document_texts.append(doc_text)

        payload = {
            "query": request.query,
            "documents": document_texts,
            "top_k": request.top_k,
        }

        try:
            # Use performance tracking
            async with track_rerank_performance(len(request.documents)):
                # Make HTTP request with retries
                for attempt in range(self.config.max_retries + 1):
                    try:
                        response = await self.client.post(
                            self.config.rerank_endpoint, json=payload
                        )

                        if response.status_code == 200:
                            break
                        elif attempt < self.config.max_retries:
                            logger.warning(
                                f"Rerank request failed "
                                f"(attempt {attempt + 1}), retrying..."
                            )
                            await asyncio.sleep(
                                self.config.retry_backoff * (attempt + 1)
                            )  # Exponential backoff
                        else:
                            raise ModelInferenceError(
                                f"Rerank service returned status "
                                f"{response.status_code}: "
                                f"{response.text}"
                            )

                    except httpx.RequestError as e:
                        if attempt < self.config.max_retries:
                            logger.warning(
                                f"Request error (attempt {attempt + 1}): "
                                f"{e}, retrying..."
                            )
                            await asyncio.sleep(
                                self.config.retry_backoff * (attempt + 1)
                            )
                        else:
                            raise ModelInferenceError(
                                f"Failed to connect to rerank service: {str(e)}"
                            ) from e

                # Parse response
                result = await response.json()

                # Log response metadata without sensitive data
                logger.info(
                    f"Rerank response received - "
                    f"success: {result.get('success', False)}, "
                    f"result count: {len(result.get('results', []))}"
                )

                # Validate response format
                if "success" not in result:
                    raise ModelInferenceError(
                        "Invalid response format: missing 'success' field"
                    )

                if not result.get("success", False):
                    raise ModelInferenceError(
                        f"Rerank service error: {result.get('error', 'Unknown error')}"
                    )

                # Extract reranked results
                reranked_data = result.get("data", {})
                if not reranked_data:
                    raise ModelInferenceError(
                        "Invalid response format: missing 'data' field"
                    )

                reranked_docs = reranked_data.get(
                    "results", []
                )  # Changed from "reranked_documents"

                # Create results with rerank scores
                results = []
                for reranked in reranked_docs:
                    # Find original document by index
                    idx = reranked.get("original_index")  # Changed from "index"
                    if idx is None:
                        raise ModelInferenceError(
                            "Invalid response format: missing original_index"
                        )
                    if not (0 <= idx < len(request.documents)):
                        raise ModelInferenceError(
                            f"Invalid document index {idx}: "
                            f"out of range [0, {len(request.documents)})"
                        )

                    doc = request.documents[idx]
                    results.append(
                        RerankResult(
                            document=doc,
                            rerank_score=float(reranked["score"]),
                            original_score=doc.similarity_score,
                        )
                    )

                # Apply top_k if not already applied by service
                if request.top_k and len(results) > request.top_k:
                    results = results[: request.top_k]

                # Calculate processing time
                processing_time_ms = (time.perf_counter() - start_time) * 1000

                return RerankResponse(
                    results=results,
                    processing_time_ms=processing_time_ms,
                    total_documents=len(request.documents),
                )

        except ModelInferenceError:
            raise
        except Exception as e:
            raise ModelInferenceError(
                f"Unexpected error during reranking: {str(e)}"
            ) from e

    async def is_ready(self) -> bool:
        """Check if the reranker service is ready.

        Returns:
            True if service is ready, False otherwise
        """
        if not self._is_ready:
            try:
                await self._check_service_health()
            except Exception:
                return False
        return self._is_ready

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
