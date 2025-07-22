"""Unit tests for BuildVectorIndexUseCase."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.application.use_cases.build_vector_index import BuildVectorIndexUseCase
from src.domain.entities.business_concept_master import BusinessConceptMaster


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    return AsyncMock()


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    service = AsyncMock()
    service.get_embedding_dimension = MagicMock(return_value=2560)
    return service


@pytest.fixture
def mock_vectorization_service():
    """Create a mock vectorization service."""
    return MagicMock()


@pytest.fixture
def use_case(mock_repository, mock_embedding_service, mock_vectorization_service):
    """Create use case instance with mocked dependencies."""
    return BuildVectorIndexUseCase(
        repository=mock_repository,
        embedding_service=mock_embedding_service,
        vectorization_service=mock_vectorization_service,
        batch_size=2,  # Small batch size for testing
    )


@pytest.fixture
def sample_concepts():
    """Create sample business concepts for testing."""
    return [
        BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="AI 芯片",
            concept_category="核心业务",
            importance_score=Decimal("0.9"),
            development_stage="commercialization",
            embedding=None,
            concept_details={
                "description": "公司自主研发的高性能AI推理芯片",
                "market_position": "领先",
            },
            last_updated_from_doc_id=uuid4(),
            version=1,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="智能座舱",
            concept_category="新兴业务",
            importance_score=Decimal("0.8"),
            development_stage="development",
            embedding=None,
            concept_details={
                "description": "基于自研操作系统的智能座舱解决方案",
                "target_market": "新能源汽车",
            },
            last_updated_from_doc_id=uuid4(),
            version=1,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
    ]


class TestBuildVectorIndexUseCase:
    """Test cases for BuildVectorIndexUseCase."""

    @pytest.mark.asyncio
    async def test_execute_no_concepts(self, use_case, mock_repository):
        """Test execution when no concepts need vectorization."""
        mock_repository.find_concepts_needing_embeddings.return_value = []

        result = await use_case.execute()

        assert result["total_concepts"] == 0
        assert result["processed"] == 0
        assert result["succeeded"] == 0
        assert result["failed"] == 0
        mock_repository.find_concepts_needing_embeddings.assert_called_once_with(
            limit=None
        )

    @pytest.mark.asyncio
    async def test_execute_successful_vectorization(
        self,
        use_case,
        mock_repository,
        mock_embedding_service,
        mock_vectorization_service,
        sample_concepts,
    ):
        """Test successful vectorization of concepts."""
        mock_repository.find_concepts_needing_embeddings.return_value = sample_concepts
        mock_vectorization_service.prepare_text_for_embedding.side_effect = [
            "AI 芯片: 公司自主研发的高性能AI推理芯片",
            "智能座舱: 基于自研操作系统的智能座舱解决方案",
        ]
        mock_embedding_service.embed_texts.return_value = [
            [0.1] * 2560,  # Mock embedding for concept 1
            [0.2] * 2560,  # Mock embedding for concept 2
        ]

        result = await use_case.execute()

        assert result["total_concepts"] == 2
        assert result["processed"] == 2
        assert result["succeeded"] == 2
        assert result["failed"] == 0
        assert result["skipped"] == 0
        assert len(result["errors"]) == 0

        # Verify embedding service was called
        mock_embedding_service.embed_texts.assert_called_once()

        # Verify repository update was called
        mock_repository.batch_update_embeddings.assert_called_once()
        update_data = mock_repository.batch_update_embeddings.call_args[0][0]
        assert len(update_data) == 2
        assert update_data[0][0] == sample_concepts[0].concept_id
        assert update_data[1][0] == sample_concepts[1].concept_id

    @pytest.mark.asyncio
    async def test_execute_with_limit(self, use_case, mock_repository, sample_concepts):
        """Test execution with limit parameter."""
        mock_repository.find_concepts_needing_embeddings.return_value = [
            sample_concepts[0]
        ]
        mock_vectorization_service = use_case.vectorization_service
        mock_vectorization_service.prepare_text_for_embedding.return_value = "Test text"
        use_case.embedding_service.embed_texts.return_value = [[0.1] * 2560]

        result = await use_case.execute(limit=1)

        assert result["total_concepts"] == 1
        assert result["processed"] == 1
        mock_repository.find_concepts_needing_embeddings.assert_called_once_with(
            limit=1
        )

    @pytest.mark.asyncio
    async def test_execute_rebuild_all_with_company(
        self, use_case, mock_repository, sample_concepts
    ):
        """Test rebuild all for specific company."""
        mock_repository.find_all_by_company.return_value = sample_concepts
        mock_vectorization_service = use_case.vectorization_service
        mock_vectorization_service.prepare_text_for_embedding.return_value = "Test text"
        use_case.embedding_service.embed_texts.return_value = [
            [0.1] * 2560,
            [0.2] * 2560,
        ]

        result = await use_case.execute(rebuild_all=True, company_code="000001")

        assert result["total_concepts"] == 2
        assert result["processed"] == 2
        mock_repository.find_all_by_company.assert_called_once_with("000001")

    @pytest.mark.asyncio
    async def test_execute_empty_text_after_preparation(
        self,
        use_case,
        mock_repository,
        mock_vectorization_service,
        sample_concepts,
    ):
        """Test handling of empty text after preparation."""
        mock_repository.find_concepts_needing_embeddings.return_value = [
            sample_concepts[0]
        ]
        mock_vectorization_service.prepare_text_for_embedding.return_value = ""

        result = await use_case.execute()

        assert result["total_concepts"] == 1
        assert result["processed"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_execute_embedding_generation_failure(
        self,
        use_case,
        mock_repository,
        mock_embedding_service,
        mock_vectorization_service,
        sample_concepts,
    ):
        """Test handling of embedding generation failure."""
        mock_repository.find_concepts_needing_embeddings.return_value = sample_concepts
        mock_vectorization_service.prepare_text_for_embedding.return_value = "Test text"
        mock_embedding_service.embed_texts.side_effect = Exception(
            "Embedding service error"
        )

        result = await use_case.execute()

        assert result["total_concepts"] == 2
        assert result["processed"] == 0
        assert result["failed"] == 2
        assert "Batch embedding failed: Embedding service error" in result["errors"]

    @pytest.mark.asyncio
    async def test_execute_dimension_mismatch(
        self,
        use_case,
        mock_repository,
        mock_embedding_service,
        mock_vectorization_service,
        sample_concepts,
    ):
        """Test handling of embedding dimension mismatch."""
        mock_repository.find_concepts_needing_embeddings.return_value = [
            sample_concepts[0]
        ]
        mock_vectorization_service.prepare_text_for_embedding.return_value = "Test text"
        # Return wrong dimension embedding
        mock_embedding_service.embed_texts.return_value = [[0.1] * 1000]

        result = await use_case.execute()

        assert result["total_concepts"] == 1
        assert result["failed"] == 1
        assert any("dimension mismatch" in error for error in result["errors"])

    @pytest.mark.asyncio
    async def test_get_vectorization_status_with_company(
        self, use_case, mock_repository, sample_concepts
    ):
        """Test getting vectorization status for specific company."""
        # One concept has embedding, one doesn't
        sample_concepts[0].embedding = [0.1] * 2560
        mock_repository.find_all_by_company.return_value = sample_concepts

        status = await use_case.get_vectorization_status(company_code="000001")

        assert status["total_concepts"] == 2
        assert status["concepts_with_embeddings"] == 1
        assert status["concepts_needing_embeddings"] == 1
        assert status["embedding_dimension"] == 2560
        assert status["company_code"] == "000001"
        assert "timestamp" in status

    @pytest.mark.asyncio
    async def test_get_vectorization_status_without_company(
        self, use_case, mock_repository, sample_concepts
    ):
        """Test getting vectorization status without company filter."""
        mock_repository.find_concepts_needing_embeddings.return_value = sample_concepts

        status = await use_case.get_vectorization_status()

        assert status["total_concepts"] == "unknown"
        assert status["concepts_with_embeddings"] == "unknown"
        assert status["concepts_needing_embeddings"] == 2
        assert status["embedding_dimension"] == 2560
        assert "timestamp" in status

    @pytest.mark.asyncio
    async def test_get_vectorization_status_error(self, use_case, mock_repository):
        """Test error handling in get vectorization status."""
        mock_repository.find_concepts_needing_embeddings.side_effect = Exception(
            "Database error"
        )

        status = await use_case.get_vectorization_status()

        assert "error" in status
        assert status["error"] == "Database error"
        assert "timestamp" in status

    @pytest.mark.asyncio
    async def test_batch_processing(
        self,
        use_case,
        mock_repository,
        mock_embedding_service,
        mock_vectorization_service,
    ):
        """Test batch processing with multiple batches."""
        # Create 5 concepts to test batching with batch_size=2
        concepts = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=f"Concept {i}",
                concept_category="核心业务",
                importance_score=Decimal("0.9"),
                development_stage="commercialization",
                embedding=None,
                concept_details={"description": f"Description {i}"},
                last_updated_from_doc_id=uuid4(),
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(5)
        ]

        mock_repository.find_concepts_needing_embeddings.return_value = concepts
        mock_vectorization_service.prepare_text_for_embedding.return_value = "Test text"
        mock_embedding_service.embed_texts.return_value = [[0.1] * 2560] * 2

        result = await use_case.execute()

        # Should process in 3 batches: 2, 2, 1
        assert result["total_concepts"] == 5
        assert result["processed"] == 5
        assert result["succeeded"] == 5

        # Verify embedding service was called 3 times (for 3 batches)
        assert mock_embedding_service.embed_texts.call_count == 3
