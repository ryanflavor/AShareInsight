"""
Integration tests for database operations with our core models.

These tests verify database connectivity, CRUD operations, and
proper integration with Pydantic models.
"""

import os
from datetime import datetime

import pytest
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from packages.core.src.core.database import DatabaseOperations
from packages.core.src.core.models import BusinessConcept, Company, SourceDocument


@pytest.fixture
def test_db_url():
    """Get test database URL from environment or use default."""
    return os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://postgres:test123@localhost:5432/ashareinsight",
    )


@pytest.fixture
def db_ops(test_db_url):
    """Create DatabaseOperations instance for testing."""
    db = DatabaseOperations(test_db_url)
    # Clean up test data before each test
    db.execute_query("DELETE FROM business_concepts_master")
    db.execute_query("DELETE FROM source_documents")
    db.execute_query("DELETE FROM companies")
    yield db
    # Clean up after test
    db.close()


class TestCompanyOperations:
    """Test database operations for Company model."""

    def test_create_company(self, db_ops):
        """Test creating a new company."""
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
            company_name_short="平安银行",
            exchange="深圳证券交易所",
        )

        created = db_ops.create_company(company)
        assert created.company_code == "000001"
        assert created.company_name_full == "平安银行股份有限公司"
        assert isinstance(created.created_at, datetime)

    def test_create_duplicate_company_fails(self, db_ops):
        """Test that creating duplicate company raises error."""
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )

        db_ops.create_company(company)

        # Try to create duplicate
        with pytest.raises(UniqueViolation):
            db_ops.create_company(company)

    def test_get_company_by_code(self, db_ops):
        """Test retrieving company by code."""
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
            company_name_short="平安银行",
        )
        db_ops.create_company(company)

        retrieved = db_ops.get_company_by_code("000001")
        assert retrieved is not None
        assert retrieved.company_code == "000001"
        assert retrieved.company_name_full == "平安银行股份有限公司"

    def test_get_nonexistent_company_returns_none(self, db_ops):
        """Test retrieving non-existent company returns None."""
        result = db_ops.get_company_by_code("999999")
        assert result is None

    def test_update_company(self, db_ops):
        """Test updating company information."""
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        # Update exchange information
        updated = db_ops.update_company(
            "000001", company_name_short="平安银行", exchange="深圳证券交易所"
        )

        assert updated.exchange == "深圳证券交易所"
        assert updated.company_name_short == "平安银行"
        assert updated.updated_at > company.created_at

    def test_list_companies(self, db_ops):
        """Test listing all companies."""
        companies = [
            Company(company_code="000001", company_name_full="平安银行股份有限公司"),
            Company(company_code="000002", company_name_full="万科企业股份有限公司"),
            Company(company_code="600036", company_name_full="招商银行股份有限公司"),
        ]

        for company in companies:
            db_ops.create_company(company)

        all_companies = db_ops.list_companies()
        assert len(all_companies) == 3
        assert all(
            c.company_code in ["000001", "000002", "600036"] for c in all_companies
        )


class TestSourceDocumentOperations:
    """Test database operations for SourceDocument model."""

    def test_create_source_document(self, db_ops):
        """Test creating a new source document."""
        # First create a company
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        # Create source document
        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="2023年年度报告",
            raw_llm_output={"concepts": ["零售银行", "公司银行"]},
        )

        created = db_ops.create_source_document(doc)
        assert created.doc_id is not None
        assert created.company_code == "000001"
        assert created.raw_llm_output == {"concepts": ["零售银行", "公司银行"]}

    def test_create_document_with_invalid_company_fails(self, db_ops):
        """Test that creating document with invalid company code fails."""
        doc = SourceDocument(
            company_code="999999",  # Non-existent company
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test Report",
            raw_llm_output={},
        )

        with pytest.raises(ForeignKeyViolation):
            db_ops.create_source_document(doc)

    def test_get_document_by_id(self, db_ops):
        """Test retrieving document by ID."""
        # Setup
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="2023年年度报告",
            raw_llm_output={"test": "data"},
        )
        created = db_ops.create_source_document(doc)

        # Test retrieval
        retrieved = db_ops.get_source_document_by_id(created.doc_id)
        assert retrieved is not None
        assert retrieved.doc_id == created.doc_id
        assert retrieved.report_title == "2023年年度报告"

    def test_list_documents_by_company(self, db_ops):
        """Test listing documents for a specific company."""
        # Setup company
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        # Create multiple documents
        for i in range(3):
            doc = SourceDocument(
                company_code="000001",
                doc_type="annual_report" if i % 2 == 0 else "research_report",
                doc_date=datetime.now().date(),
                report_title=f"Report {i}",
                raw_llm_output={},
            )
            db_ops.create_source_document(doc)

        # Test listing
        docs = db_ops.list_documents_by_company("000001")
        assert len(docs) == 3
        assert all(d.company_code == "000001" for d in docs)

    @pytest.mark.skip(reason="query_documents_by_jsonb not implemented yet")
    def test_query_documents_by_jsonb(self, db_ops):
        """Test querying documents by JSONB content."""
        # Setup
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        # Create documents with different JSONB content
        doc1 = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Report 1",
            raw_llm_output={"category": "banking", "concepts": ["retail"]},
        )
        doc2 = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Report 2",
            raw_llm_output={"category": "insurance", "concepts": ["life"]},
        )

        db_ops.create_source_document(doc1)
        db_ops.create_source_document(doc2)

        # Query by JSONB field
        banking_docs = db_ops.query_documents_by_jsonb({"category": "banking"})
        assert len(banking_docs) == 1
        assert banking_docs[0].report_title == "Report 1"


class TestBusinessConceptOperations:
    """Test database operations for BusinessConcept model."""

    def test_create_business_concept(self, db_ops):
        """Test creating a new business concept."""
        # Setup company and document
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="2023年年度报告",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        # Create business concept
        concept = BusinessConcept(
            company_code="000001",
            concept_name="零售银行业务",
            embedding=[0.1] * 2560,
            concept_details={"description": "个人金融服务"},
            last_updated_from_doc_id=created_doc.doc_id,
        )

        created = db_ops.create_business_concept(concept)
        assert created.concept_id is not None
        assert created.concept_name == "零售银行业务"
        assert len(created.embedding) == 2560

    def test_vector_similarity_search(self, db_ops):
        """Test vector similarity search functionality."""
        # Setup
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        # Create concepts with different embeddings
        import numpy as np

        concepts = []
        for i in range(5):
            # Create different embeddings with varying patterns
            embedding = [0.1 + (j % 10) * 0.01 + i * 0.1 for j in range(2560)]
            # Normalize to match what the service does
            embedding = list(np.array(embedding) / np.linalg.norm(embedding))
            concept = BusinessConcept(
                company_code="000001",
                concept_name=f"Concept {i}",
                embedding=embedding,
                concept_details={},
                last_updated_from_doc_id=created_doc.doc_id,
            )
            created = db_ops.create_business_concept(concept)
            concepts.append(created)

        # Search for similar vectors - create pattern similar to Concept 1
        query_embedding = [0.2 + (j % 10) * 0.01 for j in range(2560)]
        query_embedding = list(
            np.array(query_embedding) / np.linalg.norm(query_embedding)
        )
        results = db_ops.search_concepts_by_similarity(
            query_embedding, company_code="000001", limit=3
        )

        assert len(results) == 3
        # First result should be closest to our query
        assert results[0]["concept_name"] == "Concept 1"
        assert results[0]["distance"] < results[1]["distance"]

    def test_update_concept_embedding(self, db_ops):
        """Test updating concept embedding."""
        # Setup
        company = Company(
            company_code="000001",
            company_name_full="平安银行股份有限公司",
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        concept = BusinessConcept(
            company_code="000001",
            concept_name="Test Concept",
            embedding=[0.1] * 2560,
            concept_details={},
            last_updated_from_doc_id=created_doc.doc_id,
        )
        created = db_ops.create_business_concept(concept)

        # Update embedding
        new_embedding = [0.5] * 2560
        updated = db_ops.update_concept_embedding(
            created.concept_id, new_embedding, created_doc.doc_id
        )

        assert updated.embedding == new_embedding
        assert updated.updated_at > created.updated_at

    def test_list_concepts_by_company(self, db_ops):
        """Test listing concepts for a specific company."""
        # Setup companies
        companies = [
            Company(company_code="000001", company_name_full="公司1"),
            Company(company_code="000002", company_name_full="公司2"),
        ]
        for company in companies:
            db_ops.create_company(company)

        # Create document for each company
        docs = {}
        for company in companies:
            doc = SourceDocument(
                company_code=company.company_code,
                doc_type="annual_report",
                doc_date=datetime.now().date(),
                report_title="Test",
                raw_llm_output={},
            )
            docs[company.company_code] = db_ops.create_source_document(doc)

        # Create concepts for company 000001
        for i in range(3):
            concept = BusinessConcept(
                company_code="000001",
                concept_name=f"Concept {i}",
                embedding=[0.1] * 2560,
                concept_details={},
                last_updated_from_doc_id=docs["000001"].doc_id,
            )
            db_ops.create_business_concept(concept)

        # Create one concept for company 000002
        concept = BusinessConcept(
            company_code="000002",
            concept_name="Other Concept",
            embedding=[0.2] * 2560,
            concept_details={},
            last_updated_from_doc_id=docs["000002"].doc_id,
        )
        db_ops.create_business_concept(concept)

        # Test listing
        concepts_001 = db_ops.list_concepts_by_company("000001")
        concepts_002 = db_ops.list_concepts_by_company("000002")

        assert len(concepts_001) == 3
        assert len(concepts_002) == 1
        assert all(c.company_code == "000001" for c in concepts_001)


class TestTransactionAndConstraints:
    """Test database transactions and constraints."""

    @pytest.mark.skip(reason="delete_company not implemented yet")
    def test_cascade_delete_company(self, db_ops):
        """Test that deleting a company cascades to related records."""
        # Setup
        company = Company(
            company_code="000001",
            company_name_full="Test Company",
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        concept = BusinessConcept(
            company_code="000001",
            concept_name="Test Concept",
            embedding=[0.1] * 2560,
            concept_details={},
            last_updated_from_doc_id=created_doc.doc_id,
        )
        db_ops.create_business_concept(concept)

        # Delete company
        db_ops.delete_company("000001")

        # Verify cascading deletes
        assert db_ops.get_company_by_code("000001") is None
        assert db_ops.get_source_document_by_id(created_doc.doc_id) is None
        assert len(db_ops.list_concepts_by_company("000001")) == 0

    @pytest.mark.skip(reason="delete_document not implemented yet")
    def test_prevent_document_delete_with_concepts(self, db_ops):
        """Test that documents referenced by concepts cannot be deleted."""
        # Setup
        company = Company(
            company_code="000001",
            company_name_full="Test Company",
        )
        db_ops.create_company(company)

        doc = SourceDocument(
            company_code="000001",
            doc_type="annual_report",
            doc_date=datetime.now().date(),
            report_title="Test",
            raw_llm_output={},
        )
        created_doc = db_ops.create_source_document(doc)

        concept = BusinessConcept(
            company_code="000001",
            concept_name="Test Concept",
            embedding=[0.1] * 2560,
            concept_details={},
            last_updated_from_doc_id=created_doc.doc_id,
        )
        db_ops.create_business_concept(concept)

        # Try to delete document - should fail
        with pytest.raises(ForeignKeyViolation):
            db_ops.delete_document(created_doc.doc_id)

    @pytest.mark.skip(
        reason="Transaction rollback requires architectural changes to pass connection"
    )
    def test_transaction_rollback(self, db_ops):
        """Test transaction rollback on error."""
        company = Company(
            company_code="000001",
            company_name_full="Test Company",
        )
        db_ops.create_company(company)

        # Try to create multiple documents in a transaction
        # where one will fail
        with pytest.raises(Exception):
            with db_ops.transaction():
                # This should succeed
                doc1 = SourceDocument(
                    company_code="000001",
                    doc_type="annual_report",
                    doc_date=datetime.now().date(),
                    report_title="Doc 1",
                    raw_llm_output={},
                )
                db_ops.create_source_document(doc1)

                # This should fail (invalid company)
                doc2 = SourceDocument(
                    company_code="999999",
                    doc_type="annual_report",
                    doc_date=datetime.now().date(),
                    report_title="Doc 2",
                    raw_llm_output={},
                )
                db_ops.create_source_document(doc2)

        # Verify first document was rolled back
        docs = db_ops.list_documents_by_company("000001")
        assert len(docs) == 0
