"""
Unit tests for VectorizationService async methods.
"""

from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from src.application.ports.embedding_service_port import (
    EmbeddingRequest,
    EmbeddingResult,
)
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.domain.services.vectorization_service import VectorizationService


class TestVectorizationServiceAsync:
    """Test cases for VectorizationService async methods."""

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        service = Mock()
        service.get_embedding_dimension.return_value = 3
        service.get_model_name.return_value = "mock-model"
        service.embed_text = AsyncMock(return_value=np.array([0.1, 0.2, 0.3]))
        service.embed_texts = AsyncMock(
            return_value=[np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]
        )
        service.embed_texts_with_metadata = AsyncMock(
            return_value=[
                EmbeddingResult(
                    text="concept1: description1",
                    embedding=[0.1, 0.2, 0.3],
                    dimension=3,
                    metadata={"concept_id": "1"},
                ),
                EmbeddingResult(
                    text="concept2: description2",
                    embedding=[0.4, 0.5, 0.6],
                    dimension=3,
                    metadata={"concept_id": "2"},
                ),
            ]
        )
        return service

    @pytest.fixture
    def vectorization_service(self, mock_embedding_service):
        """Create a vectorization service instance."""
        return VectorizationService(
            embedding_service=mock_embedding_service, max_text_length=100
        )

    @pytest.fixture
    def sample_concept(self):
        """Create a sample business concept."""
        from datetime import UTC, datetime
        from decimal import Decimal
        from uuid import uuid4

        return BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="TEST01",
            concept_name="测试概念",
            concept_category="核心业务",
            importance_score=Decimal("0.8"),
            development_stage="成熟期",
            concept_details={
                "description": "这是一个测试概念的描述",
                "source": "test_source",
            },
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_vectorize_business_concept(
        self, vectorization_service, sample_concept
    ):
        """Test single concept vectorization."""
        embedding, text = await vectorization_service.vectorize_business_concept(
            sample_concept
        )

        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (3,)
        assert text == "测试概念: 这是一个测试概念的描述"
        np.testing.assert_array_equal(embedding, np.array([0.1, 0.2, 0.3]))

    @pytest.mark.asyncio
    async def test_vectorize_business_concept_empty_text(
        self, vectorization_service, mock_embedding_service
    ):
        """Test vectorization with empty text."""
        from datetime import UTC, datetime
        from decimal import Decimal
        from uuid import uuid4

        concept = BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="TEST01",
            concept_name="",
            concept_category="核心业务",
            importance_score=Decimal("0.5"),
            concept_details={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        embedding, text = await vectorization_service.vectorize_business_concept(
            concept
        )

        assert text == ""
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape == (3,)
        assert np.all(embedding == 0)
        mock_embedding_service.embed_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_vectorize_business_concepts_batch(
        self, vectorization_service, mock_embedding_service
    ):
        """Test batch concept vectorization."""
        from datetime import UTC, datetime
        from decimal import Decimal
        from uuid import uuid4

        concepts = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="TEST01",
                concept_name="concept1",
                concept_category="核心业务",
                importance_score=Decimal("0.7"),
                concept_details={"description": "description1"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="TEST02",
                concept_name="concept2",
                concept_category="新兴业务",
                importance_score=Decimal("0.6"),
                concept_details={"description": "description2"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ]

        results = await vectorization_service.vectorize_business_concepts_batch(
            concepts, batch_size=10
        )

        assert len(results) == 2

        # Check first result
        concept1, embedding1, text1 = results[0]
        assert concept1.concept_name == "concept1"
        assert text1 == "concept1: description1"
        np.testing.assert_array_equal(embedding1, np.array([0.1, 0.2, 0.3]))

        # Check second result
        concept2, embedding2, text2 = results[1]
        assert concept2.concept_name == "concept2"
        assert text2 == "concept2: description2"
        np.testing.assert_array_equal(embedding2, np.array([0.4, 0.5, 0.6]))

    @pytest.mark.asyncio
    async def test_vectorize_business_concepts_batch_empty(self, vectorization_service):
        """Test batch vectorization with empty list."""
        results = await vectorization_service.vectorize_business_concepts_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_vectorize_with_metadata(
        self, vectorization_service, mock_embedding_service
    ):
        """Test vectorization with metadata tracking."""
        from datetime import UTC, datetime
        from decimal import Decimal
        from uuid import uuid4

        concept1_id = uuid4()
        concept2_id = uuid4()

        concepts = [
            BusinessConceptMaster(
                concept_id=concept1_id,
                company_code="TEST01",
                concept_name="concept1",
                concept_category="核心业务",
                importance_score=Decimal("0.7"),
                concept_details={"description": "description1", "source": "source1"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            BusinessConceptMaster(
                concept_id=concept2_id,
                company_code="TEST02",
                concept_name="concept2",
                concept_category="新兴业务",
                importance_score=Decimal("0.6"),
                concept_details={"description": "description2", "source": "source2"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        ]

        results = await vectorization_service.vectorize_with_metadata(concepts)

        assert len(results) == 2
        assert all(isinstance(r, EmbeddingResult) for r in results)

        # Verify that embed_texts_with_metadata was called with correct requests
        call_args = mock_embedding_service.embed_texts_with_metadata.call_args
        requests = call_args[0][0]
        assert len(requests) == 2
        assert all(isinstance(r, EmbeddingRequest) for r in requests)
        assert requests[0].metadata["concept_id"] == str(concept1_id)
        assert requests[1].metadata["concept_id"] == str(concept2_id)

    @pytest.mark.asyncio
    async def test_vectorize_error_handling(
        self, vectorization_service, sample_concept, mock_embedding_service
    ):
        """Test error handling during vectorization."""
        mock_embedding_service.embed_text.side_effect = Exception("Embedding failed")

        with pytest.raises(Exception) as exc_info:
            await vectorization_service.vectorize_business_concept(sample_concept)

        assert "Embedding failed" in str(exc_info.value)

    def test_get_embedding_info(self, vectorization_service):
        """Test getting embedding service information."""
        info = vectorization_service.get_embedding_info()

        assert info["model_name"] == "mock-model"
        assert info["embedding_dimension"] == 3
        assert info["max_text_length"] == 100
