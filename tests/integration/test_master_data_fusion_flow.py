"""Integration tests for the complete master data fusion flow."""

import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.archive_extraction_result import (
    ArchiveExtractionResultUseCase,
)
from src.application.use_cases.update_master_data import UpdateMasterDataUseCase
from src.domain.entities.source_document import SourceDocumentMetadata
from src.domain.services.data_fusion_service import DataFusionService
from src.infrastructure.persistence.postgres.business_concept_master_repository import (
    PostgresBusinessConceptMasterRepository,
)
from src.infrastructure.persistence.postgres.models import (
    CompanyModel,
)
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)


@pytest.mark.integration
class TestMasterDataFusionFlow:
    """Integration tests for master data fusion flow."""

    @pytest_asyncio.fixture
    async def db_session(self):
        """Create a test database session."""
        # Use in-memory SQLite for testing
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from src.infrastructure.persistence.postgres.models import Base

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
        )

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session() as session:
            yield session
            await session.rollback()

        await engine.dispose()

    @pytest_asyncio.fixture
    async def setup_test_company(self, db_session: AsyncSession):
        """Create a test company in the database."""
        company = CompanyModel(
            company_code="TEST001",
            company_name_full="测试科技股份有限公司",
            company_name_short="测试科技",
            exchange="深交所",
        )
        db_session.add(company)
        await db_session.commit()
        return company

    @pytest.fixture
    def sample_llm_output_v1(self):
        """Sample LLM output for first document."""
        return {
            "extraction_data": {
                "company_name_full": "测试科技股份有限公司",
                "company_code": "TEST001",
                "business_concepts": [
                    {
                        "concept_name": "人工智能平台",
                        "concept_category": "核心业务",
                        "description": "AI平台服务",
                        "importance_score": 0.85,
                        "development_stage": "成长期",
                        "timeline": {
                            "established": "2020-01-01",
                            "recent_event": "2023年推出AI平台2.0",
                        },
                        "metrics": {
                            "revenue": 500000000.0,
                            "revenue_growth_rate": 25.0,
                            "market_share": 10.0,
                        },
                        "relations": {
                            "customers": ["客户A", "客户B"],
                            "partners": ["合作伙伴1"],
                            "subsidiaries_or_investees": [],
                        },
                        "source_sentences": ["原文引用1", "原文引用2"],
                    },
                    {
                        "concept_name": "云计算服务",
                        "concept_category": "新兴业务",
                        "description": "云服务",
                        "importance_score": 0.6,
                        "development_stage": "探索期",
                        "timeline": {"established": "2023-01-01"},
                        "relations": {"customers": ["客户C"]},
                        "source_sentences": ["原文引用3"],
                    },
                ],
            }
        }

    @pytest.fixture
    def sample_llm_output_v2(self):
        """Sample LLM output for second document with updates."""
        return {
            "extraction_data": {
                "company_name_full": "测试科技股份有限公司",
                "company_code": "TEST001",
                "business_concepts": [
                    {
                        "concept_name": "人工智能平台",  # Same concept, updated data
                        "concept_category": "核心业务",
                        "description": "AI平台服务，提供机器学习、深度学习、NLP等全栈AI能力",
                        "importance_score": 0.92,  # Increased
                        "development_stage": "成熟期",  # Advanced
                        "timeline": {
                            "established": "2020-01-01",
                            "recent_event": "2024年Q1推出AI平台3.0，接入大模型",
                        },
                        "metrics": {
                            "revenue": 800000000.0,  # Increased
                            "revenue_growth_rate": 60.0,  # Increased
                            "market_share": 15.0,  # Increased
                            "gross_margin": 65.0,  # New metric
                        },
                        "relations": {
                            "customers": ["客户B", "客户D", "客户E"],  # Updated
                            "partners": [
                                "合作伙伴1",
                                "合作伙伴2",
                                "合作伙伴3",
                            ],  # Expanded
                            "subsidiaries_or_investees": ["AI研究院"],  # New
                        },
                        "source_sentences": ["原文引用4", "原文引用5", "原文引用6"],
                    },
                    {
                        "concept_name": "物联网解决方案",  # New concept
                        "concept_category": "战略布局",
                        "description": "工业物联网整体解决方案",
                        "importance_score": 0.4,
                        "development_stage": "探索期",
                        "timeline": {"established": "2024-01-01"},
                        "relations": {"partners": ["物联网联盟"]},
                        "source_sentences": ["原文引用7"],
                    },
                ],
            }
        }

    @pytest.mark.asyncio
    async def test_complete_fusion_flow_new_company(
        self, db_session: AsyncSession, setup_test_company, sample_llm_output_v1
    ):
        """Test complete flow: archive and fusion for new company."""
        # Create repositories
        source_doc_repo = PostgresSourceDocumentRepository(db_session)
        business_concept_repo = PostgresBusinessConceptMasterRepository(db_session)

        # Create services and use cases
        data_fusion_service = DataFusionService()
        update_master_data_use_case = UpdateMasterDataUseCase(
            source_doc_repo, business_concept_repo, data_fusion_service
        )
        archive_use_case = ArchiveExtractionResultUseCase(
            source_doc_repo, update_master_data_use_case
        )

        # Archive document with fusion
        metadata = SourceDocumentMetadata(
            company_code="TEST001",
            doc_type="annual_report",
            doc_date=date(2023, 12, 31),
            report_title="2023年年度报告",
            file_path="/test/TEST001_2023.pdf",
            file_hash=f"hash_{uuid4()}",
        )

        doc_id = await archive_use_case.execute(sample_llm_output_v1, metadata)

        # Verify document was archived
        assert doc_id is not None
        source_doc = await source_doc_repo.find_by_id(doc_id)
        assert source_doc is not None
        assert source_doc.company_code == "TEST001"

        # Verify business concepts were created
        concepts = await business_concept_repo.find_all_by_company("TEST001")
        assert len(concepts) == 2

        # Verify AI platform concept
        ai_concept = next(c for c in concepts if c.concept_name == "人工智能平台")
        assert ai_concept.importance_score == Decimal("0.85")
        assert ai_concept.development_stage == "成长期"
        assert ai_concept.concept_details["metrics"]["revenue"] == 500000000.0
        assert set(ai_concept.concept_details["relations"]["customers"]) == {
            "客户A",
            "客户B",
        }

        # Verify cloud service concept
        cloud_concept = next(c for c in concepts if c.concept_name == "云计算服务")
        assert cloud_concept.importance_score == Decimal("0.6")
        assert cloud_concept.development_stage == "探索期"

    @pytest.mark.asyncio
    async def test_complete_fusion_flow_update_existing(
        self,
        db_session: AsyncSession,
        setup_test_company,
        sample_llm_output_v1,
        sample_llm_output_v2,
    ):
        """Test complete flow: archive and fusion with updates to existing concepts."""
        # Create repositories
        source_doc_repo = PostgresSourceDocumentRepository(db_session)
        business_concept_repo = PostgresBusinessConceptMasterRepository(db_session)

        # Create services and use cases
        data_fusion_service = DataFusionService()
        update_master_data_use_case = UpdateMasterDataUseCase(
            source_doc_repo, business_concept_repo, data_fusion_service
        )
        archive_use_case = ArchiveExtractionResultUseCase(
            source_doc_repo, update_master_data_use_case
        )

        # First document - create initial concepts
        metadata_v1 = SourceDocumentMetadata(
            company_code="TEST001",
            doc_type="annual_report",
            doc_date=date(2023, 12, 31),
            report_title="2023年年度报告",
            file_path="/test/TEST001_2023.pdf",
            file_hash=f"hash_v1_{uuid4()}",
        )

        doc_id_v1 = await archive_use_case.execute(sample_llm_output_v1, metadata_v1)

        # Second document - update existing and add new
        metadata_v2 = SourceDocumentMetadata(
            company_code="TEST001",
            doc_type="annual_report",
            doc_date=date(2024, 3, 31),
            report_title="2024年第一季度报告",
            file_path="/test/TEST001_2024Q1.pdf",
            file_hash=f"hash_v2_{uuid4()}",
        )

        doc_id_v2 = await archive_use_case.execute(sample_llm_output_v2, metadata_v2)

        # Verify both documents were archived
        assert doc_id_v1 is not None
        assert doc_id_v2 is not None

        # Verify business concepts
        concepts = await business_concept_repo.find_all_by_company("TEST001")
        assert len(concepts) == 3  # 2 original + 1 new

        # Verify AI platform concept was updated
        ai_concept = next(c for c in concepts if c.concept_name == "人工智能平台")
        assert ai_concept.importance_score == Decimal("0.92")  # Updated
        assert ai_concept.development_stage == "成熟期"  # Updated
        assert (
            ai_concept.concept_details["metrics"]["revenue"] == 800000000.0
        )  # Updated
        assert (
            ai_concept.concept_details["metrics"]["gross_margin"] == 65.0
        )  # New field

        # Verify relations were merged
        customers = set(ai_concept.concept_details["relations"]["customers"])
        assert customers == {"客户A", "客户B", "客户D", "客户E"}  # Union
        partners = set(ai_concept.concept_details["relations"]["partners"])
        assert partners == {"合作伙伴1", "合作伙伴2", "合作伙伴3"}  # Union

        # Verify description was updated (longer version)
        assert "全栈AI能力" in ai_concept.concept_details["description"]

        # Verify source sentences were merged
        sentences = set(ai_concept.concept_details["source_sentences"])
        assert sentences >= {
            "原文引用1",
            "原文引用2",
            "原文引用4",
            "原文引用5",
            "原文引用6",
        }

        # Verify version was incremented
        assert ai_concept.version == 2
        assert ai_concept.last_updated_from_doc_id == doc_id_v2

        # Verify cloud service concept was not updated
        cloud_concept = next(c for c in concepts if c.concept_name == "云计算服务")
        assert cloud_concept.version == 1  # Not updated
        assert cloud_concept.importance_score == Decimal("0.6")  # Original value

        # Verify new IoT concept was created
        iot_concept = next(c for c in concepts if c.concept_name == "物联网解决方案")
        assert iot_concept.importance_score == Decimal("0.4")
        assert iot_concept.concept_category == "战略布局"
        assert iot_concept.version == 1

    @pytest.mark.asyncio
    async def test_concurrent_updates_handling(
        self, db_session: AsyncSession, setup_test_company, sample_llm_output_v1
    ):
        """Test handling of concurrent updates to the same concept."""
        # Create initial concept
        source_doc_repo = PostgresSourceDocumentRepository(db_session)
        business_concept_repo = PostgresBusinessConceptMasterRepository(db_session)
        data_fusion_service = DataFusionService()

        # Create initial document
        metadata = SourceDocumentMetadata(
            company_code="TEST001",
            doc_type="annual_report",
            doc_date=date(2023, 12, 31),
            report_title="2023年年度报告",
            file_path="/test/TEST001_2023.pdf",
            file_hash=f"hash_{uuid4()}",
        )

        archive_use_case = ArchiveExtractionResultUseCase(source_doc_repo)
        doc_id = await archive_use_case.execute(sample_llm_output_v1, metadata)

        # Create initial concepts
        update_use_case = UpdateMasterDataUseCase(
            source_doc_repo, business_concept_repo, data_fusion_service
        )
        await update_use_case.execute(doc_id)

        # Simulate concurrent updates by creating two update use cases
        update_use_case1 = UpdateMasterDataUseCase(
            source_doc_repo, business_concept_repo, data_fusion_service
        )
        update_use_case2 = UpdateMasterDataUseCase(
            source_doc_repo, business_concept_repo, data_fusion_service
        )

        # Create two different updates
        sample_llm_output_update1 = {
            "extraction_data": {
                "company_code": "TEST001",
                "business_concepts": [
                    {
                        "concept_name": "人工智能平台",
                        "concept_category": "核心业务",
                        "description": "Update 1",
                        "importance_score": 0.88,
                        "development_stage": "成长期",
                        "timeline": {"established": "2020-01-01"},
                        "relations": {"customers": ["客户X"]},
                        "source_sentences": ["更新1"],
                    }
                ],
            }
        }

        sample_llm_output_update2 = {
            "extraction_data": {
                "company_code": "TEST001",
                "business_concepts": [
                    {
                        "concept_name": "人工智能平台",
                        "concept_category": "核心业务",
                        "description": "Update 2",
                        "importance_score": 0.89,
                        "development_stage": "成熟期",
                        "timeline": {"established": "2020-01-01"},
                        "relations": {"customers": ["客户Y"]},
                        "source_sentences": ["更新2"],
                    }
                ],
            }
        }

        # Archive both updates
        doc_id1 = await archive_use_case.execute(
            sample_llm_output_update1,
            SourceDocumentMetadata(
                company_code="TEST001",
                doc_type="annual_report",
                doc_date=date(2024, 1, 1),
                file_hash=f"hash_update1_{uuid4()}",
            ),
        )

        doc_id2 = await archive_use_case.execute(
            sample_llm_output_update2,
            SourceDocumentMetadata(
                company_code="TEST001",
                doc_type="annual_report",
                doc_date=date(2024, 1, 2),
                file_hash=f"hash_update2_{uuid4()}",
            ),
        )

        # Run updates concurrently
        results = await asyncio.gather(
            update_use_case1.execute(doc_id1),
            update_use_case2.execute(doc_id2),
            return_exceptions=True,
        )

        # At least one should succeed
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 1

        # Verify final state
        concepts = await business_concept_repo.find_all_by_company("TEST001")
        ai_concept = next(c for c in concepts if c.concept_name == "人工智能平台")

        # Should have customers from both updates due to union strategy
        customers = set(ai_concept.concept_details["relations"]["customers"])
        assert "客户A" in customers  # Original
        assert "客户B" in customers  # Original
        assert ("客户X" in customers) or ("客户Y" in customers)  # At least one update
