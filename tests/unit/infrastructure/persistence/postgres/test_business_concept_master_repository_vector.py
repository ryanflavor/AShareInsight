"""
Unit tests for vector-related methods in BusinessConceptMasterRepository.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.infrastructure.persistence.postgres.business_concept_master_repository import (
    PostgresBusinessConceptMasterRepository,
)
from src.infrastructure.persistence.postgres.models import BusinessConceptMasterModel


class TestBusinessConceptMasterRepositoryVector:
    """Test cases for vector-related repository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create repository instance with mock session."""
        return PostgresBusinessConceptMasterRepository(mock_session)

    @pytest.fixture
    def sample_concept(self):
        """Create a sample business concept entity."""
        return BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="智能座舱",
            concept_category="核心业务",
            importance_score=Decimal("0.95"),
            development_stage="成熟期",
            embedding=None,
            concept_details={"description": "智能座舱解决方案"},
            last_updated_from_doc_id=uuid4(),
            version=1,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.fixture
    def sample_embedding(self):
        """Create a sample embedding vector."""
        # Create a 2560-dimensional vector (simulated)
        return [0.1 * i for i in range(2560)]

    @pytest.mark.asyncio
    async def test_update_embedding_success(
        self, repository, mock_session, sample_concept, sample_embedding
    ):
        """Test successful embedding update."""
        # Setup mock
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Execute
        await repository.update_embedding(sample_concept.concept_id, sample_embedding)

        # Verify
        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args[0][0]

        # Check that it's an update statement
        assert "UPDATE" in str(call_args)
        assert "business_concepts_master" in str(call_args)

    @pytest.mark.asyncio
    async def test_update_embedding_not_found(
        self, repository, mock_session, sample_embedding
    ):
        """Test embedding update when concept not found."""
        # Setup mock
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        concept_id = uuid4()

        # Execute
        with patch(
            "src.infrastructure.persistence.postgres.business_concept_master_repository.logger"
        ) as mock_logger:
            await repository.update_embedding(concept_id, sample_embedding)

            # Verify warning was logged
            mock_logger.warning.assert_called_once_with(
                "embedding_update_failed_not_found", concept_id=str(concept_id)
            )

    @pytest.mark.asyncio
    async def test_batch_update_embeddings_empty(self, repository, mock_session):
        """Test batch update with empty list."""
        # Execute
        await repository.batch_update_embeddings([])

        # Verify no database calls
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_update_embeddings_small_batch(
        self, repository, mock_session, sample_embedding
    ):
        """Test batch update with small batch."""
        # Create test data
        embeddings = [
            (uuid4(), sample_embedding),
            (uuid4(), sample_embedding),
            (uuid4(), sample_embedding),
        ]

        # Setup mock
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Execute
        await repository.batch_update_embeddings(embeddings)

        # Verify
        assert mock_session.execute.call_count == 3
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_update_embeddings_large_batch(
        self, repository, mock_session, sample_embedding
    ):
        """Test batch update with batch larger than batch_size."""
        # Create test data (150 items, batch_size is 100)
        embeddings = [(uuid4(), sample_embedding) for _ in range(150)]

        # Setup mock
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        # Execute
        await repository.batch_update_embeddings(embeddings)

        # Verify
        assert mock_session.execute.call_count == 150
        assert mock_session.flush.call_count == 2  # Two batches

    @pytest.mark.asyncio
    async def test_find_concepts_needing_embeddings_no_limit(
        self, repository, mock_session, sample_concept
    ):
        """Test finding concepts needing embeddings without limit."""
        # Setup mock
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [
            Mock(
                spec=BusinessConceptMasterModel,
                to_domain_entity=Mock(return_value=sample_concept),
            )
        ]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Execute
        result = await repository.find_concepts_needing_embeddings()

        # Verify
        assert len(result) == 1
        assert result[0] == sample_concept
        mock_session.execute.assert_called_once()

        # Check query includes proper filters
        call_args = mock_session.execute.call_args[0][0]
        query_str = str(call_args)
        assert "embedding IS NULL" in query_str
        assert "is_active IS true" in query_str

    @pytest.mark.asyncio
    async def test_find_concepts_needing_embeddings_with_limit(
        self, repository, mock_session
    ):
        """Test finding concepts needing embeddings with limit."""
        # Setup mock
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Execute
        result = await repository.find_concepts_needing_embeddings(limit=10)

        # Verify
        assert result == []
        mock_session.execute.assert_called_once()

        # Check query includes limit
        call_args = mock_session.execute.call_args[0][0]
        query_str = str(call_args)
        assert "LIMIT" in query_str

    def test_embedding_string_format(self):
        """Test embedding string formatting."""
        embedding = [0.1, 0.2, 0.3]
        expected = "[0.1,0.2,0.3]"

        # Simulate the formatting used in the repository
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        assert embedding_str == expected
