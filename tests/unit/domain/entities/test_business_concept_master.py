"""Unit tests for BusinessConceptMaster domain entity."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domain.entities.business_concept_master import BusinessConceptMaster


class TestBusinessConceptMaster:
    """Test cases for BusinessConceptMaster entity."""

    @pytest.fixture
    def valid_business_concept_master(self):
        """Create a valid BusinessConceptMaster instance for testing."""
        return BusinessConceptMaster(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="智能制造",
            concept_category="核心业务",
            importance_score=Decimal("0.95"),
            development_stage="成熟期",
            embedding=None,
            concept_details={
                "description": "公司的智能制造业务板块",
                "metrics": {
                    "revenue": 1000000000.0,
                    "revenue_growth_rate": 15.5,
                    "market_share": 25.0,
                },
                "timeline": {
                    "established": "2018-01-01",
                    "recent_event": "2024年扩建新工厂",
                },
                "relations": {
                    "customers": ["客户A", "客户B"],
                    "partners": ["合作伙伴X"],
                    "subsidiaries_or_investees": ["子公司1"],
                },
                "source_sentences": ["原文引用1", "原文引用2"],
            },
            last_updated_from_doc_id=uuid4(),
            version=1,
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def test_create_valid_business_concept_master(self, valid_business_concept_master):
        """Test creating a valid BusinessConceptMaster instance."""
        assert valid_business_concept_master.company_code == "000001"
        assert valid_business_concept_master.concept_name == "智能制造"
        assert valid_business_concept_master.concept_category == "核心业务"
        assert valid_business_concept_master.importance_score == Decimal("0.95")
        assert valid_business_concept_master.development_stage == "成熟期"
        assert valid_business_concept_master.version == 1
        assert valid_business_concept_master.is_active is True

    def test_concept_category_validation(self):
        """Test that concept_category validation works correctly."""
        with pytest.raises(ValueError, match="concept_category must be one of"):
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="测试概念",
                concept_category="无效分类",  # Invalid category
                importance_score=Decimal("0.5"),
                development_stage="成长期",
                embedding=None,
                concept_details={},
                version=1,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    def test_importance_score_validation(self):
        """Test that importance_score validation works correctly."""
        # Test score > 1
        with pytest.raises(ValidationError):
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="测试概念",
                concept_category="核心业务",
                importance_score=Decimal("1.5"),  # Invalid score
                development_stage="成长期",
                embedding=None,
                concept_details={},
                version=1,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        # Test score < 0
        with pytest.raises(ValidationError):
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="测试概念",
                concept_category="核心业务",
                importance_score=Decimal("-0.1"),  # Invalid score
                development_stage="成长期",
                embedding=None,
                concept_details={},
                version=1,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    def test_concept_details_validation(self):
        """Test that concept_details validation works correctly."""
        with pytest.raises(ValidationError):
            BusinessConceptMaster(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="测试概念",
                concept_category="核心业务",
                importance_score=Decimal("0.5"),
                development_stage="成长期",
                embedding=None,
                concept_details="not a dict",  # Invalid type
                version=1,
                is_active=True,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    def test_update_from_fusion_time_sensitive_fields(
        self, valid_business_concept_master
    ):
        """Test updating time-sensitive fields using fusion rules."""
        doc_id = uuid4()
        new_data = {
            "importance_score": 0.98,
            "development_stage": "成长期",
            "metrics": {
                "revenue": 2000000000.0,
                "revenue_growth_rate": 25.0,
                "market_share": 30.0,
            },
            "timeline": {
                "established": "2018-01-01",
                "recent_event": "2024年Q2推出新产品线",
            },
        }

        valid_business_concept_master.update_from_fusion(new_data, doc_id)

        assert valid_business_concept_master.importance_score == Decimal("0.98")
        assert valid_business_concept_master.development_stage == "成长期"
        assert (
            valid_business_concept_master.concept_details["metrics"]["revenue"]
            == 2000000000.0
        )
        assert (
            valid_business_concept_master.concept_details["timeline"]["recent_event"]
            == "2024年Q2推出新产品线"
        )
        assert valid_business_concept_master.last_updated_from_doc_id == doc_id
        assert valid_business_concept_master.version == 2

    def test_update_from_fusion_merge_relations(self, valid_business_concept_master):
        """Test merging relations using union strategy."""
        doc_id = uuid4()
        new_data = {
            "relations": {
                "customers": ["客户B", "客户C", "客户D"],  # B is duplicate
                "partners": ["合作伙伴Y", "合作伙伴Z"],
                "subsidiaries_or_investees": ["子公司2"],
            }
        }

        valid_business_concept_master.update_from_fusion(new_data, doc_id)

        relations = valid_business_concept_master.concept_details["relations"]

        # Check customers union
        assert set(relations["customers"]) == {"客户A", "客户B", "客户C", "客户D"}

        # Check partners union
        assert set(relations["partners"]) == {"合作伙伴X", "合作伙伴Y", "合作伙伴Z"}

        # Check subsidiaries union
        assert set(relations["subsidiaries_or_investees"]) == {"子公司1", "子公司2"}

    def test_update_from_fusion_smart_merge_description(
        self, valid_business_concept_master
    ):
        """Test smart merge for description (keep longer version)."""
        doc_id = uuid4()

        # Test with shorter description - should not update
        new_data = {"description": "智能制造"}
        valid_business_concept_master.update_from_fusion(new_data, doc_id)
        assert (
            valid_business_concept_master.concept_details["description"]
            == "公司的智能制造业务板块"
        )

        # Test with longer description - should update
        longer_desc = "公司的智能制造业务板块，包括工业机器人、智能装备、工业软件等多个细分领域，是公司的核心竞争力"
        new_data = {"description": longer_desc}
        valid_business_concept_master.update_from_fusion(new_data, doc_id)
        assert (
            valid_business_concept_master.concept_details["description"] == longer_desc
        )

    def test_update_from_fusion_merge_source_sentences(
        self, valid_business_concept_master
    ):
        """Test merging source sentences with deduplication and limit."""
        doc_id = uuid4()

        # Add more sentences including duplicates
        new_sentences = ["原文引用2", "原文引用3"] + [
            f"原文引用{i}" for i in range(4, 25)
        ]
        new_data = {"source_sentences": new_sentences}

        valid_business_concept_master.update_from_fusion(new_data, doc_id)

        source_sentences = valid_business_concept_master.concept_details[
            "source_sentences"
        ]

        # Check deduplication
        assert len(source_sentences) == len(set(source_sentences))

        # Check limit of 20
        assert len(source_sentences) <= 20

        # Check that original sentences are preserved
        assert "原文引用1" in source_sentences
        assert "原文引用2" in source_sentences

    def test_json_serialization(self, valid_business_concept_master):
        """Test that the entity can be properly serialized to JSON."""
        # This should not raise any exceptions
        json_data = valid_business_concept_master.model_dump_json()
        assert isinstance(json_data, str)

        # Check that UUID and datetime are properly serialized
        assert str(valid_business_concept_master.concept_id) in json_data
        assert "created_at" in json_data
