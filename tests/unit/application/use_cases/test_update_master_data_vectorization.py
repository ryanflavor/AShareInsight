"""Unit tests for UpdateMasterDataUseCase with vectorization integration."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.use_cases.update_master_data import UpdateMasterDataUseCase
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.domain.entities.extraction import DocumentType
from src.domain.entities.source_document import SourceDocument


class TestUpdateMasterDataWithVectorization:
    """Test cases for UpdateMasterDataUseCase with vectorization."""

    @pytest.fixture
    def mock_source_doc_repo(self):
        """Create a mock source document repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_business_concept_repo(self):
        """Create a mock business concept repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_data_fusion_service(self):
        """Create a mock data fusion service."""
        return MagicMock()

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = AsyncMock()
        service.get_embedding_dimension = AsyncMock(return_value=2560)
        service.embed_texts = AsyncMock(return_value=[[0.1] * 2560])
        return service

    @pytest.fixture
    def mock_vectorization_service(self):
        """Create mock vectorization service."""
        service = MagicMock()
        service.prepare_text_for_embedding = MagicMock(return_value="Test text")
        return service

    @pytest.fixture
    def use_case_with_vectorization(
        self,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        mock_embedding_service,
        mock_vectorization_service,
    ):
        """Create UpdateMasterDataUseCase instance with vectorization enabled."""
        return UpdateMasterDataUseCase(
            source_document_repo=mock_source_doc_repo,
            business_concept_repo=mock_business_concept_repo,
            data_fusion_service=mock_data_fusion_service,
            embedding_service=mock_embedding_service,
            vectorization_service=mock_vectorization_service,
            batch_size=2,
            enable_async_vectorization=True,
        )

    @pytest.fixture
    def sample_source_document(self):
        """Create a sample source document with business concepts."""
        return SourceDocument(
            doc_id=uuid4(),
            company_code="000001",
            doc_type=DocumentType.ANNUAL_REPORT,
            doc_date=date(2024, 1, 1),
            report_title="2024年年度报告",
            file_path="/data/reports/000001_2024.pdf",
            file_hash="a" * 64,
            raw_llm_output={
                "extraction_data": {
                    "company_name_full": "测试科技股份有限公司",
                    "company_code": "000001",
                    "business_concepts": [
                        {
                            "concept_name": "人工智能",
                            "concept_category": "核心业务",
                            "description": "AI技术研发与应用",
                            "importance_score": 0.9,
                            "development_stage": "成长期",
                            "timeline": {"established": "2020-01-01"},
                            "metrics": {"revenue": 1000000000},
                            "relations": {"customers": ["客户A"]},
                            "source_sentences": ["原文1"],
                        },
                        {
                            "concept_name": "云计算",
                            "concept_category": "新兴业务",
                            "description": "云计算平台服务",
                            "importance_score": 0.7,
                            "development_stage": "探索期",
                            "timeline": {"established": "2023-01-01"},
                            "relations": {"partners": ["合作伙伴X"]},
                            "source_sentences": ["原文2"],
                        },
                    ],
                }
            },
            extraction_metadata={},
            original_content=None,
            processing_status="completed",
            error_message=None,
            created_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_execute_with_vectorization_triggered(
        self,
        use_case_with_vectorization,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        sample_source_document,
    ):
        """Test execution with async vectorization triggered."""
        doc_id = sample_source_document.doc_id

        # Setup mocks
        mock_source_doc_repo.find_by_id.return_value = sample_source_document
        mock_business_concept_repo.find_by_company_and_name.return_value = None

        # Mock created concepts
        created_concepts = []
        for i in range(2):
            concept = BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name=f"concept_{i}",
                concept_category="核心业务",
                importance_score=Decimal("0.5"),
                development_stage="成长期",
                concept_details={},
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            created_concepts.append(concept)

        mock_data_fusion_service.create_from_new_concept.side_effect = created_concepts
        mock_business_concept_repo.save.side_effect = created_concepts

        # Mock vectorization
        mock_business_concept_repo.find_concepts_needing_embeddings.return_value = (
            created_concepts
        )

        # Execute with patched asyncio.create_task
        with patch("asyncio.create_task") as mock_create_task:
            result = await use_case_with_vectorization.execute(doc_id)

            # Verify vectorization was triggered
            assert result["concepts_created"] == 2
            assert result["concepts_needing_vectorization"] == 2
            assert result["vectorization_triggered"] is True
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_vectorization_not_triggered_no_changes(
        self,
        use_case_with_vectorization,
        mock_source_doc_repo,
        sample_source_document,
    ):
        """Test vectorization not triggered when no concepts are created/updated."""
        doc_id = sample_source_document.doc_id
        sample_source_document.raw_llm_output["extraction_data"][
            "business_concepts"
        ] = []
        mock_source_doc_repo.find_by_id.return_value = sample_source_document

        with patch("asyncio.create_task") as mock_create_task:
            result = await use_case_with_vectorization.execute(doc_id)

            assert result["concepts_created"] == 0
            assert result["concepts_needing_vectorization"] == 0
            assert result["vectorization_triggered"] is False
            mock_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_vectorization_disabled(
        self,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        mock_embedding_service,
        mock_vectorization_service,
        sample_source_document,
    ):
        """Test execution with vectorization disabled."""
        # Create use case with vectorization disabled
        use_case = UpdateMasterDataUseCase(
            source_document_repo=mock_source_doc_repo,
            business_concept_repo=mock_business_concept_repo,
            data_fusion_service=mock_data_fusion_service,
            embedding_service=mock_embedding_service,
            vectorization_service=mock_vectorization_service,
            batch_size=2,
            enable_async_vectorization=False,  # Disabled
        )

        doc_id = sample_source_document.doc_id
        mock_source_doc_repo.find_by_id.return_value = sample_source_document
        mock_business_concept_repo.find_by_company_and_name.return_value = None

        # Mock created concepts
        created_concept = MagicMock()
        mock_data_fusion_service.create_from_new_concept.return_value = created_concept
        mock_business_concept_repo.save.return_value = created_concept

        with patch("asyncio.create_task") as mock_create_task:
            result = await use_case.execute(doc_id)

            # Vectorization should not be triggered
            assert result["vectorization_triggered"] is False
            mock_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_vectorization_success(
        self,
        use_case_with_vectorization,
        mock_business_concept_repo,
        mock_embedding_service,
        mock_vectorization_service,
    ):
        """Test async vectorization runs successfully."""
        company_code = "000001"

        # Mock concepts needing embeddings
        concepts = [
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code=company_code,
                concept_name="Test Concept",
                concept_category="核心业务",
                importance_score=Decimal("0.8"),
                development_stage="成长期",
                concept_details={"description": "Test description"},
                version=1,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        ]

        mock_business_concept_repo.find_concepts_needing_embeddings.return_value = (
            concepts
        )
        mock_vectorization_service.prepare_text_for_embedding.return_value = "Test text"
        mock_embedding_service.embed_texts.return_value = [[0.1] * 2560]

        # Run async vectorization
        await use_case_with_vectorization._run_async_vectorization(company_code)

        # Verify embedding update was called
        mock_business_concept_repo.batch_update_embeddings.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_vectorization_error_handling(
        self,
        use_case_with_vectorization,
        mock_business_concept_repo,
    ):
        """Test async vectorization handles errors gracefully."""
        company_code = "000001"

        # Mock error
        mock_business_concept_repo.find_concepts_needing_embeddings.side_effect = (
            Exception("Database error")
        )

        # Should not raise, just log error
        await use_case_with_vectorization._run_async_vectorization(company_code)

        # Verify it tried to find concepts
        mock_business_concept_repo.find_concepts_needing_embeddings.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_mixed_with_vectorization(
        self,
        use_case_with_vectorization,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        sample_source_document,
    ):
        """Test execution with mix of created and updated concepts triggers vectorization."""
        doc_id = sample_source_document.doc_id

        # Setup mocks
        mock_source_doc_repo.find_by_id.return_value = sample_source_document

        # First concept exists, second is new
        existing_concept = BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="人工智能",
            concept_category="核心业务",
            importance_score=Decimal("0.8"),
            development_stage="成长期",
            concept_details={},
            version=2,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        mock_business_concept_repo.find_by_company_and_name.side_effect = [
            existing_concept,  # First concept exists
            None,  # Second is new
        ]

        # Mock fusion for existing
        updated_concept = MagicMock()
        updated_concept.concept_id = existing_concept.concept_id
        updated_concept.version = 3
        mock_data_fusion_service.merge_business_concepts.return_value = updated_concept

        # Mock creation for new one
        new_concept = MagicMock()
        mock_data_fusion_service.create_from_new_concept.return_value = new_concept
        mock_business_concept_repo.save.return_value = new_concept

        # Execute with patched asyncio.create_task
        with patch("asyncio.create_task") as mock_create_task:
            result = await use_case_with_vectorization.execute(doc_id)

            # Verify results
            assert result["concepts_created"] == 1
            assert result["concepts_updated"] == 1
            assert result["concepts_needing_vectorization"] == 2
            assert result["vectorization_triggered"] is True
            mock_create_task.assert_called_once()
