"""Unit tests for DataFusionService."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.domain.entities.company import (
    BusinessConcept,
    Metrics,
    Relations,
    Timeline,
)
from src.domain.services.data_fusion_service import DataFusionService


class TestDataFusionService:
    """Test cases for DataFusionService."""

    @pytest.fixture
    def data_fusion_service(self):
        """Create a DataFusionService instance."""
        return DataFusionService()

    @pytest.fixture
    def existing_business_concept_master(self):
        """Create an existing BusinessConceptMaster for testing."""
        return BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="人工智能芯片",
            concept_category="核心业务",
            importance_score=Decimal("0.85"),
            development_stage="成长期",
            embedding=None,
            concept_details={
                "description": "公司的人工智能芯片业务",
                "metrics": {
                    "revenue": 500000000.0,
                    "revenue_growth_rate": 30.0,
                    "market_share": 15.0,
                },
                "timeline": {
                    "established": "2020-01-01",
                    "recent_event": "2023年推出第二代AI芯片",
                },
                "relations": {
                    "customers": ["客户1", "客户2"],
                    "partners": ["合作伙伴A"],
                    "subsidiaries_or_investees": [],
                },
                "source_sentences": ["原文1", "原文2"],
            },
            last_updated_from_doc_id=uuid4(),
            version=2,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.fixture
    def new_business_concept(self):
        """Create a new BusinessConcept for testing."""
        return BusinessConcept(
            concept_name="人工智能芯片",
            concept_category="核心业务",
            description="公司的人工智能芯片业务，专注于边缘计算和云端推理",
            importance_score=0.92,
            development_stage="成熟期",
            timeline=Timeline(
                established="2020-01-01",
                recent_event="2024年Q1发布第三代AI芯片，性能提升50%",
            ),
            metrics=Metrics(
                revenue=800000000.0,
                revenue_growth_rate=60.0,
                market_share=20.0,
                gross_margin=45.0,
            ),
            relations=Relations(
                customers=["客户2", "客户3", "客户4"],
                partners=["合作伙伴A", "合作伙伴B"],
                subsidiaries_or_investees=["AI芯片研发中心"],
            ),
            source_sentences=["原文3", "原文4", "原文5"],
        )

    def test_merge_business_concepts(
        self,
        data_fusion_service,
        existing_business_concept_master,
        new_business_concept,
    ):
        """Test merging business concepts with all fusion rules."""
        doc_id = uuid4()

        # Perform merge
        result = data_fusion_service.merge_business_concepts(
            existing_business_concept_master, new_business_concept, doc_id
        )

        # Verify time-sensitive fields are overwritten
        assert result.importance_score == Decimal("0.92")
        assert result.development_stage == "成熟期"
        assert result.concept_details["metrics"]["revenue"] == 800000000.0
        assert result.concept_details["metrics"]["revenue_growth_rate"] == 60.0
        assert result.concept_details["metrics"]["market_share"] == 20.0
        assert result.concept_details["metrics"]["gross_margin"] == 45.0
        assert (
            result.concept_details["timeline"]["recent_event"]
            == "2024年Q1发布第三代AI芯片，性能提升50%"
        )

        # Verify cumulative fields are merged (union)
        relations = result.concept_details["relations"]
        assert set(relations["customers"]) == {"客户1", "客户2", "客户3", "客户4"}
        assert set(relations["partners"]) == {"合作伙伴A", "合作伙伴B"}
        assert set(relations["subsidiaries_or_investees"]) == {"AI芯片研发中心"}

        # Verify description is updated (longer version)
        assert (
            result.concept_details["description"]
            == "公司的人工智能芯片业务，专注于边缘计算和云端推理"
        )

        # Verify source sentences are merged
        assert set(result.concept_details["source_sentences"]) == {
            "原文1",
            "原文2",
            "原文3",
            "原文4",
            "原文5",
        }

        # Verify metadata
        assert result.last_updated_from_doc_id == doc_id
        assert result.version == 3  # Incremented from 2

    def test_create_from_new_concept(self, data_fusion_service, new_business_concept):
        """Test creating a new BusinessConceptMaster from a BusinessConcept."""
        company_code = "000002"
        doc_id = uuid4()

        result = data_fusion_service.create_from_new_concept(
            new_business_concept, company_code, doc_id
        )

        # Verify basic fields
        assert result.company_code == company_code
        assert result.concept_name == "人工智能芯片"
        assert result.concept_category == "核心业务"
        assert result.importance_score == Decimal("0.92")
        assert result.development_stage == "成熟期"
        assert result.last_updated_from_doc_id == doc_id
        assert result.version == 1
        assert result.is_active is True

        # Verify concept_details structure
        details = result.concept_details
        assert (
            details["description"] == "公司的人工智能芯片业务，专注于边缘计算和云端推理"
        )
        assert details["metrics"]["revenue"] == 800000000.0
        assert (
            details["timeline"]["recent_event"]
            == "2024年Q1发布第三代AI芯片，性能提升50%"
        )
        assert details["relations"]["customers"] == ["客户2", "客户3", "客户4"]
        assert details["source_sentences"] == ["原文3", "原文4", "原文5"]

    def test_create_from_concept_without_metrics(self, data_fusion_service):
        """Test creating from a concept without metrics."""
        concept = BusinessConcept(
            concept_name="区块链技术",
            concept_category="新兴业务",
            description="探索区块链在供应链金融中的应用",
            importance_score=0.3,
            development_stage="探索期",
            timeline=Timeline(established="2023-06-01"),
            metrics=None,  # No metrics
            relations=Relations(),
            source_sentences=["区块链探索项目启动"],
        )

        result = data_fusion_service.create_from_new_concept(concept, "000003", uuid4())

        assert result.concept_details["metrics"] == {}
        assert result.importance_score == Decimal("0.3")

    def test_get_updated_fields(self, data_fusion_service):
        """Test the _get_updated_fields method."""
        # Test with all fields populated
        new_data = {
            "importance_score": 0.9,
            "development_stage": "成熟期",
            "metrics": {"revenue": 1000000},
            "timeline": {"established": "2020-01-01"},
            "relations": {"customers": ["客户A"]},
            "description": "详细描述",
            "source_sentences": ["引用1"],
        }

        fields = data_fusion_service._get_updated_fields(new_data)
        assert set(fields) == {
            "importance_score",
            "development_stage",
            "metrics",
            "timeline",
            "relations",
            "description",
            "source_sentences",
        }

        # Test with empty values
        new_data = {
            "importance_score": None,
            "development_stage": "",
            "metrics": {},
            "timeline": {"established": None, "recent_event": None},
            "relations": {"customers": [], "partners": []},
            "description": "",
            "source_sentences": [],
        }

        fields = data_fusion_service._get_updated_fields(new_data)
        assert fields == []  # No fields should be considered updated

    def test_merge_with_empty_existing_relations(
        self, data_fusion_service, new_business_concept
    ):
        """Test merging when existing concept has no relations."""
        existing = BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="测试概念",
            concept_category="核心业务",
            importance_score=Decimal("0.5"),
            development_stage="探索期",
            embedding=None,
            concept_details={
                "description": "测试",
                # No relations key
            },
            version=1,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        doc_id = uuid4()
        result = data_fusion_service.merge_business_concepts(
            existing, new_business_concept, doc_id
        )

        # Should create relations from new concept
        assert "relations" in result.concept_details
        relations = result.concept_details["relations"]
        assert set(relations["customers"]) == {"客户2", "客户3", "客户4"}
        assert set(relations["partners"]) == {"合作伙伴A", "合作伙伴B"}
