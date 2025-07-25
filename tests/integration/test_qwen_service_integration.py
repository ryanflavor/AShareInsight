"""Test integration with running Qwen Service."""

import asyncio

# Configure logging
import logging
from decimal import Decimal
from uuid import uuid4

import pytest
import structlog

from src.application.ports.reranker_port import RerankRequest
from src.domain.value_objects.document import Document
from src.infrastructure.llm.qwen.qwen_rerank_adapter import (
    QwenRerankAdapter,
    QwenRerankConfig,
)

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger(__name__)


@pytest.mark.asyncio
async def test_qwen_rerank():
    """Test the Qwen Service integration."""

    # Create test documents
    source_concept_id = uuid4()  # Common source concept
    test_documents = [
        Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="阿里巴巴集团",
            concept_name="电子商务平台",
            concept_category="科技",
            importance_score=Decimal("0.9"),
            similarity_score=0.85,
            source_concept_id=source_concept_id,
        ),
        Document(
            concept_id=uuid4(),
            company_code="000002",
            company_name="腾讯控股",
            concept_name="社交媒体平台",
            concept_category="科技",
            importance_score=Decimal("0.85"),
            similarity_score=0.82,
            source_concept_id=source_concept_id,
        ),
        Document(
            concept_id=uuid4(),
            company_code="000003",
            company_name="京东集团",
            concept_name="电商物流服务",
            concept_category="电商",
            importance_score=Decimal("0.8"),
            similarity_score=0.80,
            source_concept_id=source_concept_id,
        ),
        Document(
            concept_id=uuid4(),
            company_code="000004",
            company_name="美团",
            concept_name="本地生活服务",
            concept_category="服务",
            importance_score=Decimal("0.75"),
            similarity_score=0.78,
            source_concept_id=source_concept_id,
        ),
    ]

    # Create adapter config
    config = QwenRerankConfig(
        service_url="http://localhost:9547", timeout_seconds=10.0, max_retries=2
    )

    # Test the adapter
    try:
        async with QwenRerankAdapter(config) as adapter:
            logger.info("Connected to Qwen Service")

            # Check if service is ready
            is_ready = await adapter.is_ready()
            logger.info(f"Service ready: {is_ready}")

            if not is_ready:
                logger.error("Service is not ready!")
                return

            # Create rerank request
            request = RerankRequest(
                query="电商平台运营模式", documents=test_documents, top_k=3
            )

            logger.info(
                f"Sending rerank request with {len(request.documents)} documents"
            )

            # Execute reranking
            response = await adapter.rerank_documents(request)

            logger.info(f"Reranking completed in {response.processing_time_ms:.2f}ms")
            logger.info(f"Returned {len(response.results)} documents")

            # Display results
            logger.info("\nReranked results:")
            for i, result in enumerate(response.results):
                logger.info(
                    f"{i + 1}. {result.document.company_name} - "
                    f"{result.document.concept_name} "
                    f"(rerank: {result.rerank_score:.3f}, "
                    f"original: {result.original_score:.3f})"
                )

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_qwen_rerank())
