#!/usr/bin/env python3
"""Validation script for Story 2.3 - Qwen Rerank Service Integration."""

import asyncio
import logging
import sys
from pathlib import Path

import structlog

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.ports.reranker_port import RerankRequest
from src.domain.value_objects.document import Document
from src.infrastructure.llm.qwen.qwen_rerank_adapter import (
    QwenRerankAdapter,
    QwenRerankConfig,
)
from src.shared.config.settings import Settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = structlog.get_logger(__name__)


async def test_reranker_health_check():
    """Test 1: Verify reranker service health check."""
    logger.info("Test 1: Testing reranker service health check...")

    settings = Settings()
    config = QwenRerankConfig(
        service_url=settings.reranker.reranker_service_url,
        timeout_seconds=settings.reranker.reranker_timeout_seconds,
        max_retries=settings.reranker.reranker_max_retries,
        retry_backoff=settings.reranker.reranker_retry_backoff,
    )

    adapter = QwenRerankAdapter(config)

    try:
        is_ready = await adapter.is_ready()
        if is_ready:
            logger.info("✅ Test 1 PASSED: Reranker service is ready")
            return True
        else:
            logger.error("❌ Test 1 FAILED: Reranker service is not ready")
            return False
    except Exception as e:
        logger.error(f"❌ Test 1 FAILED with error: {e}")
        return False
    finally:
        await adapter.close()


async def test_rerank_empty_documents():
    """Test 2: Test reranking with empty document list."""
    logger.info("Test 2: Testing reranking with empty document list...")

    settings = Settings()
    config = QwenRerankConfig(
        service_url=settings.reranker.reranker_service_url,
        timeout_seconds=settings.reranker.reranker_timeout_seconds,
        max_retries=settings.reranker.reranker_max_retries,
        retry_backoff=settings.reranker.reranker_retry_backoff,
    )

    adapter = QwenRerankAdapter(config)

    try:
        request = RerankRequest(query="测试查询", documents=[], top_k=None)

        response = await adapter.rerank_documents(request)

        if (
            response.results == []
            and response.total_documents == 0
            and response.processing_time_ms >= 0
        ):
            logger.info("✅ Test 2 PASSED: Empty document list handled correctly")
            return True
        else:
            logger.error("❌ Test 2 FAILED: Unexpected response for empty documents")
            return False
    except Exception as e:
        logger.error(f"❌ Test 2 FAILED with error: {e}")
        return False
    finally:
        await adapter.close()


async def test_rerank_documents():
    """Test 3: Test actual document reranking."""
    logger.info("Test 3: Testing actual document reranking...")

    settings = Settings()
    config = QwenRerankConfig(
        service_url=settings.reranker.reranker_service_url,
        timeout_seconds=settings.reranker.reranker_timeout_seconds,
        max_retries=settings.reranker.reranker_max_retries,
        retry_backoff=settings.reranker.reranker_retry_backoff,
    )

    # Create sample documents
    from decimal import Decimal
    from uuid import uuid4

    documents = [
        Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="平安银行",
            concept_name="银行业务",
            concept_category="金融",
            importance_score=Decimal("0.95"),
            similarity_score=0.75,
        ),
        Document(
            concept_id=uuid4(),
            company_code="600036",
            company_name="招商银行",
            concept_name="银行业务",
            concept_category="金融",
            importance_score=Decimal("0.98"),
            similarity_score=0.85,
        ),
        Document(
            concept_id=uuid4(),
            company_code="601318",
            company_name="中国平安",
            concept_name="保险业务",
            concept_category="金融",
            importance_score=Decimal("0.99"),
            similarity_score=0.70,
        ),
    ]

    adapter = QwenRerankAdapter(config)

    try:
        request = RerankRequest(query="银行股票投资", documents=documents, top_k=2)

        response = await adapter.rerank_documents(request)

        # Validate response structure
        if not response.results:
            logger.error("❌ Test 3 FAILED: No results returned")
            return False

        if len(response.results) > 2:
            logger.error(
                f"❌ Test 3 FAILED: Expected max 2 results, got {len(response.results)}"
            )
            return False

        # Check that results have rerank scores
        for result in response.results:
            if not (0 <= result.rerank_score <= 1):
                logger.error(
                    f"❌ Test 3 FAILED: Invalid rerank score {result.rerank_score}"
                )
                return False

            if result.original_score != result.document.similarity_score:
                logger.error("❌ Test 3 FAILED: Original score mismatch")
                return False

        # Log results
        logger.info("Reranked results:")
        for i, result in enumerate(response.results):
            logger.info(
                f"  {i + 1}. {result.document.company_name} "
                f"(original: {result.original_score:.3f}, "
                f"rerank: {result.rerank_score:.3f})"
            )

        logger.info(f"Processing time: {response.processing_time_ms:.2f}ms")
        logger.info("✅ Test 3 PASSED: Document reranking successful")
        return True

    except Exception as e:
        logger.error(f"❌ Test 3 FAILED with error: {e}")
        return False
    finally:
        await adapter.close()


async def test_rerank_with_top_k():
    """Test 4: Test reranking with top_k parameter."""
    logger.info("Test 4: Testing reranking with top_k parameter...")

    settings = Settings()
    config = QwenRerankConfig(
        service_url=settings.reranker.reranker_service_url,
        timeout_seconds=settings.reranker.reranker_timeout_seconds,
        max_retries=settings.reranker.reranker_max_retries,
        retry_backoff=settings.reranker.reranker_retry_backoff,
    )

    # Create more documents
    from decimal import Decimal
    from uuid import uuid4

    documents = []
    for i in range(10):
        documents.append(
            Document(
                concept_id=uuid4(),
                company_code=f"{i:06d}",
                company_name=f"测试公司{i}",
                concept_name="银行业务" if i % 2 == 0 else "保险业务",
                concept_category="金融",
                importance_score=Decimal(str(0.8 + (i * 0.02))),
                similarity_score=0.9 - (i * 0.05),
            )
        )

    adapter = QwenRerankAdapter(config)

    try:
        request = RerankRequest(query="银行业务发展", documents=documents, top_k=3)

        response = await adapter.rerank_documents(request)

        if len(response.results) != 3:
            logger.error(
                f"❌ Test 4 FAILED: Expected 3 results, got {len(response.results)}"
            )
            return False

        # Check that results are ordered by rerank score
        prev_score = float("inf")
        for result in response.results:
            if result.rerank_score > prev_score:
                logger.error("❌ Test 4 FAILED: Results not properly ordered")
                return False
            prev_score = result.rerank_score

        logger.info("✅ Test 4 PASSED: top_k parameter working correctly")
        return True

    except Exception as e:
        logger.error(f"❌ Test 4 FAILED with error: {e}")
        return False
    finally:
        await adapter.close()


async def main():
    """Run all validation tests."""
    logger.info("=== Starting Story 2.3 Validation ===")
    logger.info("Story: Rerank模型集成与精排")
    logger.info("")

    tests = [
        ("Health Check", test_reranker_health_check),
        ("Empty Documents", test_rerank_empty_documents),
        ("Document Reranking", test_rerank_documents),
        ("Top-K Parameter", test_rerank_with_top_k),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} Test ---")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    logger.info("\n=== Test Summary ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 Story 2.3 validation SUCCESSFUL!")
        return 0
    else:
        logger.error("\n❌ Story 2.3 validation FAILED!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
