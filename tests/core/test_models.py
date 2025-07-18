"""
Unit tests for Pydantic 2.0 data models.

Tests follow TDD principles and verify all model validations,
type hints, and business logic constraints.
"""

import json
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from packages.core.src.core.models import (
    BusinessConcept,
    Company,
    SourceDocument,
)


class TestCompanyModel:
    """Test suite for Company Pydantic model."""

    def test_create_valid_company(self):
        """Test creating a valid company instance."""
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
            company_name_short="平安银行",
            exchange="深圳证券交易所",
        )

        assert company.company_code == "000001"
        assert company.company_name_full == "平安银行股份有限公司"
        assert company.company_name_short == "平安银行"
        assert company.exchange == "深圳证券交易所"
        assert isinstance(company.created_at, datetime)
        assert isinstance(company.updated_at, datetime)

    def test_company_code_validation(self):
        """Test company code validation constraints."""
        # Test too long company code
        with pytest.raises(ValidationError) as exc_info:
            Company(
                company_code="12345678901",  # 11 chars, exceeds limit
                company_name_full="Test Company Ltd.",
            )
        assert "String should have at most 10 characters" in str(exc_info.value)

    def test_company_required_fields(self):
        """Test that required fields are enforced."""
        with pytest.raises(ValidationError) as exc_info:
            Company(company_code="000001")  # Missing company_name_full
        assert "Field required" in str(exc_info.value)

    def test_company_timestamps_auto_generated(self):
        """Test that timestamps are automatically generated."""
        company = Company(
            company_code="000001",
            company_name_full="Test Company Ltd.",
        )
        assert company.created_at is not None
        assert company.updated_at is not None
        assert company.created_at <= company.updated_at

    def test_company_model_json_serialization(self):
        """Test JSON serialization of Company model."""
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
            company_name_short="平安银行",
            exchange="深圳证券交易所",
        )
        json_str = company.model_dump_json()
        data = json.loads(json_str)

        assert data["company_code"] == "000001"
        assert data["company_name_full"] == "平安银行股份有限公司"
        assert "created_at" in data
        assert "updated_at" in data


class TestSourceDocumentModel:
    """Test suite for SourceDocument Pydantic model."""

    def test_create_valid_source_document(self):
        """Test creating a valid source document instance."""
        doc_id = uuid4()
        raw_output = {
            "concepts": ["concept1", "concept2"],
            "metrics": {"revenue": 1000000},
        }

        doc = SourceDocument(
            doc_id=doc_id,
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="2023年年度报告",
            raw_llm_output=raw_output,
        )

        assert doc.doc_id == doc_id
        assert doc.company_code == "000001"
        assert doc.doc_type == "annual_report"
        assert doc.raw_llm_output == raw_output
        assert isinstance(doc.created_at, datetime)

    def test_source_document_jsonb_validation(self):
        """Test JSONB field accepts complex nested structures."""
        complex_json = {
            "extracted_concepts": [
                {
                    "name": "零售银行业务",
                    "description": "个人金融服务",
                    "metrics": {
                        "revenue": 50000000,
                        "growth_rate": 0.15,
                    },
                    "sub_concepts": ["信用卡", "个人贷款", "存款"],
                }
            ],
            "metadata": {
                "extraction_timestamp": datetime.now().isoformat(),
                "model_version": "gemini-2.5-pro",
                "confidence_score": 0.95,
            },
        }

        doc = SourceDocument(
            doc_id=uuid4(),
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test Report",
            raw_llm_output=complex_json,
        )

        assert doc.raw_llm_output == complex_json

    def test_source_document_doc_type_validation(self):
        """Test document type validation."""
        valid_types = ["annual_report", "research_report"]

        for doc_type in valid_types:
            doc = SourceDocument(
                doc_id=uuid4(),
                company_code="000001",
                doc_type=doc_type,
                doc_date=datetime.now().date(),
                report_title="Test Report",
                raw_llm_output={},
            )
            assert doc.doc_type == doc_type

    def test_source_document_invalid_doc_type(self):
        """Test invalid document type raises error."""
        with pytest.raises(ValidationError) as exc_info:
            SourceDocument(
                doc_id=uuid4(),
                company_code="000001",
                doc_type="invalid_type",
                doc_date=datetime.now().date(),
                report_title="Test Report",
                raw_llm_output={},
            )
        assert "Input should be 'annual_report' or 'research_report'" in str(
            exc_info.value
        )

    def test_source_document_uuid_generation(self):
        """Test UUID can be auto-generated if not provided."""
        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test Report",
            raw_llm_output={},
        )
        assert isinstance(doc.doc_id, UUID)


class TestBusinessConceptModel:
    """Test suite for BusinessConcept Pydantic model."""

    def test_create_valid_business_concept(self):
        """Test creating a valid business concept instance."""
        concept_id = uuid4()
        doc_id = uuid4()
        embedding = [0.1] * 2560  # 2560-dimensional vector
        concept_details = {
            "description": "零售银行业务包括个人存贷款、信用卡等",
            "category": "主营业务",
            "metrics": {
                "revenue": 50000000,
                "percentage": 0.35,
            },
        }

        concept = BusinessConcept(
            concept_id=concept_id,
            company_code="000001",
            concept_name="零售银行业务",
            embedding=embedding,
            concept_details=concept_details,
            last_updated_from_doc_id=doc_id,
        )

        assert concept.concept_id == concept_id
        assert concept.company_code == "000001"
        assert concept.concept_name == "零售银行业务"
        assert len(concept.embedding) == 2560
        assert concept.concept_details == concept_details
        assert concept.last_updated_from_doc_id == doc_id
        assert isinstance(concept.updated_at, datetime)

    def test_business_concept_embedding_dimension(self):
        """Test embedding must be exactly 2560 dimensions."""
        # Test with wrong dimension
        with pytest.raises(ValidationError) as exc_info:
            BusinessConcept(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="Test Concept",
                embedding=[0.1] * 512,  # Wrong dimension
                concept_details={},
                last_updated_from_doc_id=uuid4(),
            )
        assert "List should have at least 2560 items" in str(exc_info.value)

    def test_business_concept_embedding_type(self):
        """Test embedding must contain float values."""
        with pytest.raises(ValidationError) as exc_info:
            BusinessConcept(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="Test Concept",
                embedding=["not", "a", "float"] + [0.1] * 2557,  # Invalid types
                concept_details={},
                last_updated_from_doc_id=uuid4(),
            )
        assert "Input should be a valid number" in str(exc_info.value)

    def test_business_concept_name_validation(self):
        """Test concept name length validation."""
        # Test maximum length (255 chars)
        long_name = "A" * 255
        concept = BusinessConcept(
            concept_id=uuid4(),
            company_code="000001",
            concept_name=long_name,
            embedding=[0.1] * 2560,
            concept_details={},
            last_updated_from_doc_id=uuid4(),
        )
        assert concept.concept_name == long_name

        # Test exceeding maximum length
        with pytest.raises(ValidationError) as exc_info:
            BusinessConcept(
                concept_id=uuid4(),
                company_code="000001",
                concept_name="A" * 256,  # Too long
                embedding=[0.1] * 2560,
                concept_details={},
                last_updated_from_doc_id=uuid4(),
            )
        assert "String should have at most 255 characters" in str(exc_info.value)

    def test_business_concept_complex_details(self):
        """Test concept_details can store complex nested JSONB data."""
        complex_details = {
            "description": "详细业务描述",
            "category": "主营业务",
            "subcategories": ["零售", "对公", "投资"],
            "metrics": {
                "revenue": {
                    "amount": 50000000,
                    "currency": "CNY",
                    "year": 2023,
                },
                "growth": {
                    "yoy": 0.15,
                    "qoq": 0.03,
                },
            },
            "related_concepts": ["信贷业务", "中间业务收入"],
            "data_sources": [
                {"doc_id": str(uuid4()), "page": 45},
                {"doc_id": str(uuid4()), "page": 78},
            ],
        }

        concept = BusinessConcept(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="零售银行业务",
            embedding=[0.1] * 2560,
            concept_details=complex_details,
            last_updated_from_doc_id=uuid4(),
        )

        assert concept.concept_details == complex_details

    def test_business_concept_json_serialization(self):
        """Test JSON serialization handles all fields correctly."""
        concept = BusinessConcept(
            concept_id=uuid4(),
            company_code="000001",
            concept_name="Test Concept",
            embedding=[0.1] * 2560,
            concept_details={"test": "data"},
            last_updated_from_doc_id=uuid4(),
        )

        json_str = concept.model_dump_json()
        data = json.loads(json_str)

        assert data["company_code"] == "000001"
        assert data["concept_name"] == "Test Concept"
        assert len(data["embedding"]) == 2560
        assert data["concept_details"] == {"test": "data"}
        assert "updated_at" in data


class TestModelRelationships:
    """Test relationships and constraints between models."""

    def test_foreign_key_consistency(self):
        """Test that foreign key fields have consistent types across models."""
        company = Company(
            company_code="000001",
            company_name_full="Test Company",
        )

        doc = SourceDocument(
            company_code=company.company_code,  # Should match
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test Report",
            raw_llm_output={},
        )

        concept = BusinessConcept(
            company_code=company.company_code,  # Should match
            concept_name="Test Concept",
            embedding=[0.1] * 2560,
            concept_details={},
            last_updated_from_doc_id=doc.doc_id,  # Should match doc_id
        )

        assert doc.company_code == company.company_code
        assert concept.company_code == company.company_code
        assert concept.last_updated_from_doc_id == doc.doc_id

    def test_timestamp_fields_timezone_aware(self):
        """Test that all timestamp fields are timezone-aware."""
        company = Company(
            company_code="000001",
            company_name_full="Test Company",
        )
        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test Report",
            raw_llm_output={},
        )
        concept = BusinessConcept(
            company_code="000001",
            concept_name="Test Concept",
            embedding=[0.1] * 2560,
            concept_details={},
            last_updated_from_doc_id=uuid4(),
        )

        # Check all timestamps are timezone-aware
        assert company.created_at.tzinfo is not None
        assert company.updated_at.tzinfo is not None
        assert doc.created_at.tzinfo is not None
        assert concept.updated_at.tzinfo is not None
