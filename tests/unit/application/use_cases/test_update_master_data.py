"""Unit tests for UpdateMasterDataUseCase."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.application.use_cases.update_master_data import UpdateMasterDataUseCase
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.domain.entities.extraction import DocumentType
from src.domain.entities.source_document import SourceDocument
from src.shared.exceptions.business_exceptions import OptimisticLockError


class TestUpdateMasterDataUseCase:
    """Test cases for UpdateMasterDataUseCase."""

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
    def use_case(
        self, mock_source_doc_repo, mock_business_concept_repo, mock_data_fusion_service
    ):
        """Create an UpdateMasterDataUseCase instance with mocks."""
        return UpdateMasterDataUseCase(
            source_document_repo=mock_source_doc_repo,
            business_concept_repo=mock_business_concept_repo,
            data_fusion_service=mock_data_fusion_service,
            batch_size=2,  # Small batch size for testing
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
            file_hash="a" * 64,  # Valid SHA-256 hash (64 hex chars)
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
                        {
                            "concept_name": "物联网",
                            "concept_category": "战略布局",
                            "description": "物联网解决方案",
                            "importance_score": 0.5,
                            "development_stage": "探索期",
                            "timeline": {"established": "2024-01-01"},
                            "relations": {},
                            "source_sentences": ["原文3"],
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
    async def test_execute_success_all_new_concepts(
        self,
        use_case,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        sample_source_document,
    ):
        """Test successful execution with all new concepts."""
        doc_id = sample_source_document.doc_id

        # Setup mocks
        mock_source_doc_repo.find_by_id.return_value = sample_source_document
        mock_business_concept_repo.find_by_company_and_name.return_value = (
            None  # All new
        )

        # Mock created concepts
        created_concepts = []
        for i in range(3):
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

        # Execute
        result = await use_case.execute(doc_id)

        # Verify
        assert result["concepts_created"] == 3
        assert result["concepts_updated"] == 0
        assert result["concepts_skipped"] == 0
        assert result["total_concepts"] == 3
        assert result["processing_time_ms"] >= 0  # Can be 0 for very fast operations

        # Verify repository calls
        mock_source_doc_repo.find_by_id.assert_called_once_with(doc_id)
        assert mock_business_concept_repo.find_by_company_and_name.call_count == 3
        assert mock_business_concept_repo.save.call_count == 3
        assert mock_data_fusion_service.create_from_new_concept.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_success_mixed_new_and_existing(
        self,
        use_case,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        sample_source_document,
    ):
        """Test successful execution with mix of new and existing concepts."""
        doc_id = sample_source_document.doc_id

        # Setup mocks
        mock_source_doc_repo.find_by_id.return_value = sample_source_document

        # First concept exists, others are new
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
            None,  # Third is new
        ]

        # Mock fusion for existing
        updated_concept = MagicMock()
        updated_concept.concept_id = existing_concept.concept_id
        updated_concept.version = 3
        mock_data_fusion_service.merge_business_concepts.return_value = updated_concept

        # Mock creation for new ones
        new_concepts = [MagicMock() for _ in range(2)]
        mock_data_fusion_service.create_from_new_concept.side_effect = new_concepts
        mock_business_concept_repo.save.side_effect = new_concepts

        # Execute
        result = await use_case.execute(doc_id)

        # Verify
        assert result["concepts_created"] == 2
        assert result["concepts_updated"] == 1
        assert result["concepts_skipped"] == 0
        assert result["total_concepts"] == 3

        # Verify fusion was called for existing
        assert mock_data_fusion_service.merge_business_concepts.call_count == 1
        assert mock_business_concept_repo.update.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_optimistic_lock_retry(
        self,
        use_case,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        sample_source_document,
    ):
        """Test handling of optimistic lock errors with retry."""
        doc_id = sample_source_document.doc_id

        # Setup document with one concept
        sample_source_document.raw_llm_output["extraction_data"][
            "business_concepts"
        ] = [
            sample_source_document.raw_llm_output["extraction_data"][
                "business_concepts"
            ][0]
        ]
        mock_source_doc_repo.find_by_id.return_value = sample_source_document

        # Existing concept
        existing_concept = MagicMock()
        mock_business_concept_repo.find_by_company_and_name.return_value = (
            existing_concept
        )

        # First update fails with OptimisticLockError, second succeeds
        mock_business_concept_repo.update.side_effect = [
            OptimisticLockError("Version conflict"),
            None,
        ]

        updated_concept = MagicMock()
        mock_data_fusion_service.merge_business_concepts.return_value = updated_concept

        # Execute
        result = await use_case.execute(doc_id)

        # Verify retry happened
        assert result["concepts_updated"] == 1
        assert result["concepts_skipped"] == 0
        assert mock_business_concept_repo.update.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_document_not_found(self, use_case, mock_source_doc_repo):
        """Test handling when source document not found."""
        doc_id = uuid4()
        mock_source_doc_repo.find_by_id.return_value = None

        with pytest.raises(ValueError, match=f"Source document {doc_id} not found"):
            await use_case.execute(doc_id)

    @pytest.mark.asyncio
    async def test_execute_no_business_concepts(
        self, use_case, mock_source_doc_repo, sample_source_document
    ):
        """Test handling when document has no business concepts."""
        doc_id = sample_source_document.doc_id
        sample_source_document.raw_llm_output["extraction_data"][
            "business_concepts"
        ] = []
        mock_source_doc_repo.find_by_id.return_value = sample_source_document

        result = await use_case.execute(doc_id)

        assert result["concepts_created"] == 0
        assert result["concepts_updated"] == 0
        assert result["concepts_skipped"] == 0
        assert result["total_concepts"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_parse_errors(
        self,
        use_case,
        mock_source_doc_repo,
        mock_business_concept_repo,
        sample_source_document,
    ):
        """Test handling of malformed business concept data."""
        doc_id = sample_source_document.doc_id

        # Add invalid concept data
        sample_source_document.raw_llm_output["extraction_data"][
            "business_concepts"
        ] = [
            {
                "concept_name": "Valid Concept",
                "concept_category": "核心业务",
                "description": "Valid description",
                "importance_score": 0.5,
                "development_stage": "成长期",
                "timeline": {"established": "2020-01-01"},
                "relations": {"customers": []},
                "source_sentences": ["原文"],
            },
            {
                # Missing required fields
                "concept_name": "Invalid Concept",
                # Missing concept_category and other required fields
            },
        ]

        mock_source_doc_repo.find_by_id.return_value = sample_source_document
        mock_business_concept_repo.find_by_company_and_name.return_value = None

        # Mock successful creation for valid concept
        created_concept = MagicMock()
        mock_business_concept_repo.save.return_value = created_concept

        # Execute
        result = await use_case.execute(doc_id)

        # Should process valid concept, skip invalid one
        assert result["total_concepts"] == 1  # Only valid concepts counted
        assert result["concepts_created"] == 1
        assert result["concepts_skipped"] == 0  # Parse errors not counted in skipped

    @pytest.mark.asyncio
    async def test_execute_with_batch_processing(
        self,
        use_case,
        mock_source_doc_repo,
        mock_business_concept_repo,
        mock_data_fusion_service,
        sample_source_document,
    ):
        """Test batch processing with delay between batches."""
        doc_id = sample_source_document.doc_id

        # Use existing 3 concepts with batch size of 2
        mock_source_doc_repo.find_by_id.return_value = sample_source_document
        mock_business_concept_repo.find_by_company_and_name.return_value = None

        # Mock creations
        created_concepts = [MagicMock() for _ in range(3)]
        mock_data_fusion_service.create_from_new_concept.side_effect = created_concepts
        mock_business_concept_repo.save.side_effect = created_concepts

        # Execute and verify batch processing
        with patch("asyncio.sleep") as mock_sleep:
            result = await use_case.execute(doc_id)

            # Should have one sleep call between batches (batch 1: 2 items, batch 2: 1 item)
            mock_sleep.assert_called_once_with(0.1)

        assert result["concepts_created"] == 3
        assert result["total_concepts"] == 3
