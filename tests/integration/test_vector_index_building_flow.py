"""Integration tests for the complete vector index building flow."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from src.application.use_cases.build_vector_index import BuildVectorIndexUseCase
from src.application.use_cases.update_master_data import UpdateMasterDataUseCase
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.domain.entities.extraction import DocumentType
from src.domain.entities.source_document import SourceDocument
from src.domain.services.data_fusion_service import DataFusionService
from src.domain.services.vectorization_service import VectorizationService


class TestVectorIndexBuildingFlow:
    """Integration tests for vector index building flow."""

    @pytest.fixture
    def mock_repositories(self):
        """Create mock repositories."""
        return {
            "source_doc_repo": AsyncMock(),
            "business_concept_repo": AsyncMock(),
        }

    @pytest.fixture
    def mock_services(self):
        """Create mock services."""
        return {
            "data_fusion_service": MagicMock(spec=DataFusionService),
            "embedding_service": AsyncMock(),
            "vectorization_service": MagicMock(spec=VectorizationService),
        }

    @pytest.fixture
    def sample_source_document(self):
        """Create a sample source document."""
        return SourceDocument(
            doc_id=uuid4(),
            company_code="000001",
            doc_type=DocumentType.ANNUAL_REPORT,
            doc_date=datetime.now().date(),
            report_title="2024年年度报告",
            file_path="/data/reports/000001_2024.pdf",
            file_hash="a" * 64,
            raw_llm_output={
                "extraction_data": {
                    "company_name_full": "测试科技股份有限公司",
                    "company_code": "000001",
                    "business_concepts": [
                        {
                            "concept_name": "人工智能芯片",
                            "concept_category": "核心业务",
                            "description": "自主研发的高性能AI推理芯片",
                            "importance_score": 0.9,
                            "development_stage": "成长期",
                            "timeline": {"established": "2020-01-01"},
                            "metrics": {"revenue": 1000000000},
                            "relations": {"customers": ["客户A", "客户B"]},
                            "source_sentences": ["原文1", "原文2"],
                        },
                        {
                            "concept_name": "智能驾驶系统",
                            "concept_category": "新兴业务",
                            "description": "基于AI的自动驾驶解决方案",
                            "importance_score": 0.8,
                            "development_stage": "探索期",
                            "timeline": {"established": "2023-01-01"},
                            "relations": {"partners": ["合作伙伴X"]},
                            "source_sentences": ["原文3"],
                        },
                    ],
                }
            },
            extraction_metadata={"model": "test-model", "version": "1.0"},
            processing_status="completed",
            created_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_full_flow_from_document_to_vectors(
        self, mock_repositories, mock_services, sample_source_document
    ):
        """Test the complete flow from document processing to vector generation."""
        # Setup mocks
        mock_repositories["source_doc_repo"].find_by_id.return_value = (
            sample_source_document
        )
        mock_repositories[
            "business_concept_repo"
        ].find_by_company_and_name.return_value = None

        # Mock created concepts
        created_concepts = []
        for i, concept_data in enumerate(
            sample_source_document.raw_llm_output["extraction_data"][
                "business_concepts"
            ]
        ):
            concept = BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=concept_data["concept_name"],
                concept_category=concept_data["concept_category"],
                importance_score=Decimal(str(concept_data["importance_score"])),
                development_stage=concept_data["development_stage"],
                embedding=None,
                concept_details={
                    "description": concept_data["description"],
                    "timeline": concept_data["timeline"],
                    "relations": concept_data["relations"],
                },
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            created_concepts.append(concept)

        mock_services["data_fusion_service"].create_from_new_concept.side_effect = (
            created_concepts
        )
        mock_repositories["business_concept_repo"].save.side_effect = created_concepts

        # Mock embedding service
        # get_embedding_dimension is a regular method, not async
        mock_services["embedding_service"].get_embedding_dimension = MagicMock(
            return_value=2560
        )
        mock_services["embedding_service"].embed_texts.return_value = [
            np.array([0.1] * 2560),  # Embedding for first concept
            np.array([0.2] * 2560),  # Embedding for second concept
        ]

        # Mock vectorization service
        mock_services[
            "vectorization_service"
        ].prepare_text_for_embedding.side_effect = [
            "人工智能芯片: 自主研发的高性能AI推理芯片",
            "智能驾驶系统: 基于AI的自动驾驶解决方案",
        ]

        # Create use cases
        update_use_case = UpdateMasterDataUseCase(
            source_document_repo=mock_repositories["source_doc_repo"],
            business_concept_repo=mock_repositories["business_concept_repo"],
            data_fusion_service=mock_services["data_fusion_service"],
            embedding_service=mock_services["embedding_service"],
            vectorization_service=mock_services["vectorization_service"],
            batch_size=10,
            enable_async_vectorization=False,  # Disable async for testing
        )

        # Execute document processing
        result = await update_use_case.execute(sample_source_document.doc_id)

        # Verify document processing results
        assert result["concepts_created"] == 2
        assert result["concepts_updated"] == 0
        assert result["concepts_needing_vectorization"] == 2

        # Now simulate vector building
        mock_repositories[
            "business_concept_repo"
        ].find_concepts_needing_embeddings.return_value = created_concepts

        vector_use_case = BuildVectorIndexUseCase(
            repository=mock_repositories["business_concept_repo"],
            embedding_service=mock_services["embedding_service"],
            vectorization_service=mock_services["vectorization_service"],
            batch_size=10,
        )

        # Execute vector building
        vector_result = await vector_use_case.execute()

        # Verify vector building results
        assert vector_result["total_concepts"] == 2
        assert vector_result["processed"] == 2
        assert vector_result["succeeded"] == 2
        assert vector_result["failed"] == 0

        # Verify embeddings were updated
        mock_repositories[
            "business_concept_repo"
        ].batch_update_embeddings.assert_called_once()
        update_data = mock_repositories[
            "business_concept_repo"
        ].batch_update_embeddings.call_args[0][0]
        assert len(update_data) == 2
        assert len(update_data[0][1]) == 2560  # First embedding
        assert len(update_data[1][1]) == 2560  # Second embedding

    @pytest.mark.asyncio
    async def test_async_vectorization_integration(
        self, mock_repositories, mock_services, sample_source_document
    ):
        """Test async vectorization triggered after document processing."""
        # Setup mocks
        mock_repositories["source_doc_repo"].find_by_id.return_value = (
            sample_source_document
        )
        mock_repositories[
            "business_concept_repo"
        ].find_by_company_and_name.return_value = None

        # Mock concept creation
        created_concept = MagicMock()
        created_concept.concept_id = uuid4()
        mock_services["data_fusion_service"].create_from_new_concept.return_value = (
            created_concept
        )
        mock_repositories["business_concept_repo"].save.return_value = created_concept

        # Mock for async vectorization
        mock_repositories[
            "business_concept_repo"
        ].find_concepts_needing_embeddings.return_value = [created_concept]
        mock_services["embedding_service"].get_embedding_dimension = MagicMock(
            return_value=2560
        )
        mock_services["embedding_service"].embed_texts.return_value = [
            np.array([0.1] * 2560)
        ]
        mock_services[
            "vectorization_service"
        ].prepare_text_for_embedding.return_value = "Test text"

        # Create use case with async vectorization enabled
        update_use_case = UpdateMasterDataUseCase(
            source_document_repo=mock_repositories["source_doc_repo"],
            business_concept_repo=mock_repositories["business_concept_repo"],
            data_fusion_service=mock_services["data_fusion_service"],
            embedding_service=mock_services["embedding_service"],
            vectorization_service=mock_services["vectorization_service"],
            batch_size=10,
            enable_async_vectorization=True,
        )

        # Execute with mocked asyncio.create_task
        with patch("asyncio.create_task") as mock_create_task:
            result = await update_use_case.execute(sample_source_document.doc_id)

            # Verify async vectorization was triggered
            assert result["vectorization_triggered"] is True
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_vector_dimension_validation(self, mock_repositories, mock_services):
        """Test that vector dimensions are properly validated."""
        # Create concepts needing embeddings
        concepts = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="Test Concept",
                concept_category="核心业务",
                importance_score=Decimal("0.8"),
                development_stage="成长期",
                embedding=None,
                concept_details={"description": "Test description"},
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        ]

        mock_repositories[
            "business_concept_repo"
        ].find_concepts_needing_embeddings.return_value = concepts

        # Mock embedding service to return wrong dimension
        mock_services["embedding_service"].get_embedding_dimension = MagicMock(
            return_value=2560
        )
        mock_services["embedding_service"].embed_texts.return_value = [
            np.array([0.1] * 1000)
        ]  # Wrong dimension!

        mock_services[
            "vectorization_service"
        ].prepare_text_for_embedding.return_value = "Test text"

        # Create use case
        vector_use_case = BuildVectorIndexUseCase(
            repository=mock_repositories["business_concept_repo"],
            embedding_service=mock_services["embedding_service"],
            vectorization_service=mock_services["vectorization_service"],
            batch_size=10,
        )

        # Execute and expect dimension mismatch to be caught
        result = await vector_use_case.execute()

        assert result["failed"] == 1
        assert result["succeeded"] == 0
        assert any("dimension mismatch" in error for error in result["errors"])

    @pytest.mark.asyncio
    async def test_incremental_vector_update(self, mock_repositories, mock_services):
        """Test incremental vector updates for existing concepts."""
        # Create a mix of concepts with and without embeddings
        concepts_with_embeddings = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=f"Existing Concept {i}",
                concept_category="核心业务",
                importance_score=Decimal("0.8"),
                development_stage="成长期",
                embedding=None,  # Skip embedding field - vectors are stored in DB
                concept_details={"description": f"Description {i}"},
                version=2,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(2)
        ]

        concepts_without_embeddings = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=f"New Concept {i}",
                concept_category="新兴业务",
                importance_score=Decimal("0.7"),
                development_stage="探索期",
                embedding=None,  # Needs embedding
                concept_details={"description": f"New Description {i}"},
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(3)
        ]

        # Mock repository to return only concepts without embeddings
        mock_repositories[
            "business_concept_repo"
        ].find_concepts_needing_embeddings.return_value = concepts_without_embeddings

        # Mock services
        mock_services["embedding_service"].get_embedding_dimension = MagicMock(
            return_value=2560
        )
        mock_services["embedding_service"].embed_texts.return_value = [
            np.array([0.2] * 2560),
            np.array([0.3] * 2560),
            np.array([0.4] * 2560),
        ]
        mock_services[
            "vectorization_service"
        ].prepare_text_for_embedding.return_value = "Test text"

        # Create use case
        vector_use_case = BuildVectorIndexUseCase(
            repository=mock_repositories["business_concept_repo"],
            embedding_service=mock_services["embedding_service"],
            vectorization_service=mock_services["vectorization_service"],
            batch_size=2,  # Small batch to test batching
        )

        # Execute
        result = await vector_use_case.execute()

        # Verify only new concepts were processed
        assert result["total_concepts"] == 3
        assert result["processed"] == 3
        assert result["succeeded"] == 3

        # Verify batching worked (3 concepts with batch size 2 = 2 batches)
        assert mock_services["embedding_service"].embed_texts.call_count == 2

    @pytest.mark.asyncio
    async def test_error_recovery_in_batch_processing(
        self, mock_repositories, mock_services
    ):
        """Test error recovery when some concepts in a batch fail."""
        # Create concepts
        concepts = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=f"Concept {i}",
                concept_category="核心业务",
                importance_score=Decimal("0.8"),
                development_stage="成长期",
                embedding=None,
                concept_details={"description": f"Description {i}"},
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(4)
        ]

        mock_repositories[
            "business_concept_repo"
        ].find_concepts_needing_embeddings.return_value = concepts

        # Mock services - fail on second batch
        mock_services["embedding_service"].get_embedding_dimension = MagicMock(
            return_value=2560
        )
        mock_services["embedding_service"].embed_texts.side_effect = [
            [np.array([0.1] * 2560), np.array([0.2] * 2560)],  # First batch succeeds
            Exception("Embedding service error"),  # Second batch fails
        ]
        mock_services[
            "vectorization_service"
        ].prepare_text_for_embedding.return_value = "Test text"

        # Create use case
        vector_use_case = BuildVectorIndexUseCase(
            repository=mock_repositories["business_concept_repo"],
            embedding_service=mock_services["embedding_service"],
            vectorization_service=mock_services["vectorization_service"],
            batch_size=2,
        )

        # Execute
        result = await vector_use_case.execute()

        # Verify partial success
        assert result["total_concepts"] == 4
        assert result["processed"] == 2  # First batch only
        assert result["succeeded"] == 2
        assert result["failed"] == 2  # Second batch failed
        assert len(result["errors"]) > 0
