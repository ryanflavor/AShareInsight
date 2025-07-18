"""
Integration tests for Qwen embedding service.

This module tests the integration between AShareInsight and the Qwen embedding service.
"""

import sys
from pathlib import Path

# Add core package to path
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "packages" / "core" / "src")
)

# Ensure pytest can find the async plugin
pytest_plugins = ["pytest_asyncio"]


import numpy as np
import pytest
from core.config import get_settings
from core.embedding_service import QwenEmbeddingService, get_embedding_service
from core.logging_config import get_logger, setup_logging

logger = get_logger(__name__)


def test_health_check():
    """Test the health check endpoint of Qwen service."""
    service = get_embedding_service()
    health = service.health_check()

    assert "status" in health, "Health check response should contain 'status' field"
    assert health["status"] == "healthy", f"Qwen service is not healthy: {health}"


def test_single_embedding():
    """Test generating a single embedding."""

    service = get_embedding_service()
    test_text = "平安银行的零售银行业务包括个人存贷款、信用卡、财富管理等服务"

    try:
        embedding = service.generate_single_embedding(test_text)

        # Verify embedding properties
        assert isinstance(embedding, list), "Embedding should be a list"
        assert len(embedding) == 2560, f"Expected 2560 dimensions, got {len(embedding)}"
        assert all(isinstance(x, float) for x in embedding), (
            "All values should be floats"
        )

        # Check if normalized (L2 norm should be close to 1)
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 0.01, f"Embedding not normalized, norm={norm}"

        # Test passed, assertions above would have failed otherwise
        logger.info(f"Generated single embedding with {len(embedding)} dimensions")
        logger.info(f"Sample values: {embedding[:5]}...")
        logger.info(f"L2 norm: {norm:.6f}")

    except Exception as e:
        pytest.fail(f"Single embedding test failed: {e}")


def test_batch_embeddings():
    """Test generating batch embeddings."""

    service = get_embedding_service()
    test_texts = [
        "平安银行是中国领先的股份制商业银行",
        "公司银行业务包括对公存贷款、贸易融资、供应链金融等",
        "零售银行业务是平安银行的核心业务板块",
        "金融科技创新推动银行数字化转型",
    ]

    try:
        embeddings = service.generate_embeddings(test_texts)

        # Verify embeddings properties
        assert isinstance(embeddings, list), "Embeddings should be a list"
        assert len(embeddings) == len(test_texts), (
            f"Expected {len(test_texts)} embeddings, got {len(embeddings)}"
        )

        for i, embedding in enumerate(embeddings):
            assert len(embedding) == 2560, f"Embedding {i} has wrong dimensions"
            norm = np.linalg.norm(embedding)
            assert abs(norm - 1.0) < 0.01, f"Embedding {i} not normalized"

        # Test passed, assertions above would have failed otherwise
        logger.info(f"Generated {len(embeddings)} embeddings successfully")
        logger.info("All embeddings have correct dimensions and normalization")

    except Exception as e:
        pytest.fail(f"Batch embedding test failed: {e}")


def test_similarity_search():
    """Test semantic similarity using embeddings."""

    service = get_embedding_service()

    # Test documents with known semantic relationships
    documents = [
        "平安银行的零售银行业务包括个人存贷款和信用卡服务",
        "零售银行是平安银行的主要收入来源之一",
        "公司银行业务服务大中型企业客户",
        "金融科技创新是银行数字化转型的关键",
        "平安银行在零售转型方面取得显著成效",
    ]

    query = "平安银行零售业务发展情况"

    try:
        # Generate embeddings
        doc_embeddings = service.generate_embeddings(documents)
        query_embedding = service.generate_single_embedding(query)

        # Calculate cosine similarities
        similarities = []
        for i, doc_emb in enumerate(doc_embeddings):
            # Cosine similarity (since embeddings are normalized, just dot product)
            similarity = np.dot(query_embedding, doc_emb)
            similarities.append((i, similarity, documents[i]))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        logger.info(f"Query: '{query}'")
        logger.info("Top similar documents:")
        for idx, sim, doc in similarities[:3]:
            logger.info(f"{idx + 1}. (score: {sim:.4f}) {doc[:50]}...")

        # Verify that retail-related documents have higher scores
        top_indices = [x[0] for x in similarities[:3]]
        retail_indices = [0, 1, 4]  # Indices of retail-related documents
        overlap = len(set(top_indices) & set(retail_indices))

        assert overlap >= 2, "Semantic similarity not working well"
        logger.info(f"Semantic similarity test passed (overlap: {overlap}/3)")

    except Exception as e:
        pytest.fail(f"Similarity search test failed: {e}")


@pytest.mark.asyncio
async def test_async_embeddings():
    """Test async embedding generation."""
    service = QwenEmbeddingService()
    test_texts = ["异步测试文本1", "异步测试文本2", "异步测试文本3"]

    embeddings = await service.generate_embeddings_async(test_texts)

    assert len(embeddings) == len(test_texts), (
        "Number of embeddings should match input texts"
    )
    for embedding in embeddings:
        assert len(embedding) == 2560, "Each embedding should have 2560 dimensions"

    logger.info(f"Generated {len(embeddings)} embeddings asynchronously")


def test_service_stats():
    """Test getting service statistics."""
    service = get_embedding_service()
    stats = service.get_stats()

    assert "error" not in stats, f"Failed to get stats: {stats}"
    # Log the stats for debugging
    logger.info("Retrieved service statistics:")
    for key, value in stats.items():
        logger.info(f"{key}: {value}")


def test_configuration():
    """Test configuration loading."""
    settings = get_settings()

    assert settings.embedding_service.embedding_dimension == 2560, (
        "Embedding dimension should be 2560"
    )

    # Log configuration for debugging
    logger.info("Configuration loaded:")
    logger.info(f"Database: {settings.database.connection_string}")
    logger.info(f"Embedding service: {settings.embedding_service.base_url}")
    logger.info(
        f"Embedding dimension: {settings.embedding_service.embedding_dimension}"
    )


# Set up module-level logging
setup_logging(level="INFO")
