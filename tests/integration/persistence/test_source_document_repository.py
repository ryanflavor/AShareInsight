"""Integration tests for PostgresSourceDocumentRepository."""

from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domain.entities.extraction import DocumentType as DocType
from src.domain.entities.source_document import SourceDocument
from src.infrastructure.persistence.postgres.models import Base, CompanyModel
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine."""
    # Use SQLite for testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine):
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def repository(test_session):
    """Create a repository instance with test session."""
    return PostgresSourceDocumentRepository(test_session)


@pytest_asyncio.fixture
async def sample_company(test_session):
    """Create a sample company in the database."""
    company = CompanyModel(
        company_code="300257",
        company_name="开山集团股份有限公司",
        exchange="深圳证券交易所",
    )
    test_session.add(company)
    await test_session.commit()
    return company


@pytest.fixture
def sample_document():
    """Create a sample SourceDocument for testing."""
    return SourceDocument(
        company_code="300257",
        doc_type=DocType.ANNUAL_REPORT,
        doc_date=date(2024, 12, 31),
        report_title="开山集团股份有限公司2024年年度报告",
        file_path="data/annual_reports/2024/300257_开山股份_2024_annual_report.md",
        file_hash="a" * 64,
        raw_llm_output={
            "status": "success",
            "data": {"company_code": "300257", "test": "value"},
        },
        extraction_metadata={
            "model": "gemini-2.5-pro",
            "processing_time_seconds": 95.3,
        },
        processing_status="completed",
    )


class TestPostgresSourceDocumentRepository:
    """Integration tests for PostgresSourceDocumentRepository."""

    @pytest.mark.asyncio
    async def test_save_new_document_with_existing_company(
        self, repository, sample_company, sample_document
    ):
        """Test saving a new document when company already exists."""
        doc_id = await repository.save(sample_document)

        assert doc_id is not None
        assert isinstance(doc_id, type(uuid4()))

        # Verify document was saved
        saved_doc = await repository.find_by_id(doc_id)
        assert saved_doc is not None
        assert saved_doc.company_code == "300257"
        assert saved_doc.doc_type == DocType.ANNUAL_REPORT
        assert saved_doc.raw_llm_output["status"] == "success"

    @pytest.mark.asyncio
    async def test_save_new_document_creates_company(
        self, repository, test_session, sample_document
    ):
        """Test saving a document creates company if it doesn't exist."""
        # Verify company doesn't exist
        stmt = select(CompanyModel).where(CompanyModel.company_code == "300257")
        result = await test_session.execute(stmt)
        assert result.scalar_one_or_none() is None

        # Save document
        doc_id = await repository.save(sample_document)

        # Verify company was created
        result = await test_session.execute(stmt)
        company = result.scalar_one_or_none()
        assert company is not None
        assert company.company_code == "300257"
        assert company.company_name == "开山集团股份有限公司"

    @pytest.mark.asyncio
    async def test_save_duplicate_file_hash_raises_error(
        self, repository, sample_company, sample_document
    ):
        """Test that saving duplicate file_hash raises IntegrityError."""
        # Save first document
        await repository.save(sample_document)

        # Try to save another document with same file_hash
        duplicate_doc = SourceDocument(
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=date(2024, 12, 31),
            file_hash="a" * 64,  # Same hash
            raw_llm_output={"data": "different"},
        )

        with pytest.raises(IntegrityError) as excinfo:
            await repository.save(duplicate_doc)

        assert "already exists" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_find_by_id_existing(
        self, repository, sample_company, sample_document
    ):
        """Test finding an existing document by ID."""
        doc_id = await repository.save(sample_document)

        found_doc = await repository.find_by_id(doc_id)

        assert found_doc is not None
        assert found_doc.doc_id == doc_id
        assert found_doc.company_code == "300257"
        assert found_doc.file_hash == "a" * 64

    @pytest.mark.asyncio
    async def test_find_by_id_not_found(self, repository):
        """Test finding a non-existent document by ID."""
        non_existent_id = uuid4()

        found_doc = await repository.find_by_id(non_existent_id)

        assert found_doc is None

    @pytest.mark.asyncio
    async def test_find_by_file_hash(self, repository, sample_company, sample_document):
        """Test finding document by file hash."""
        await repository.save(sample_document)

        found_doc = await repository.find_by_file_hash("a" * 64)

        assert found_doc is not None
        assert found_doc.file_hash == "a" * 64
        assert found_doc.company_code == "300257"

    @pytest.mark.asyncio
    async def test_find_by_company_and_date_range(
        self, repository, sample_company, test_session
    ):
        """Test finding documents by company and date range."""
        # Create multiple documents
        docs = [
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                file_hash="a" * 64,
                raw_llm_output={"data": "2024"},
            ),
            SourceDocument(
                company_code="300257",
                doc_type=DocType.RESEARCH_REPORT,
                doc_date=date(2024, 6, 30),
                file_hash="b" * 64,
                raw_llm_output={"data": "Q2"},
            ),
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2023, 12, 31),
                file_hash="c" * 64,
                raw_llm_output={"data": "2023"},
            ),
        ]

        for doc in docs:
            await repository.save(doc)

        # Test various queries
        # All documents for company
        results = await repository.find_by_company_and_date_range("300257")
        assert len(results) == 3

        # Filter by date range
        results = await repository.find_by_company_and_date_range(
            "300257",
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        assert len(results) == 2

        # Filter by document type
        results = await repository.find_by_company_and_date_range(
            "300257",
            doc_type="annual_report",
        )
        assert len(results) == 2
        assert all(r.doc_type == DocType.ANNUAL_REPORT for r in results)

        # Combined filters
        results = await repository.find_by_company_and_date_range(
            "300257",
            start_date="2024-01-01",
            doc_type="research_report",
        )
        assert len(results) == 1
        assert results[0].doc_date == date(2024, 6, 30)

    @pytest.mark.asyncio
    async def test_update_status(self, repository, sample_company, sample_document):
        """Test updating document processing status."""
        doc_id = await repository.save(sample_document)

        # Update status to failed
        updated = await repository.update_status(doc_id, "failed", "Test error message")

        assert updated is True

        # Verify update
        doc = await repository.find_by_id(doc_id)
        assert doc.processing_status == "failed"
        assert doc.error_message == "Test error message"

    @pytest.mark.asyncio
    async def test_update_status_not_found(self, repository):
        """Test updating status of non-existent document."""
        non_existent_id = uuid4()

        updated = await repository.update_status(non_existent_id, "failed")

        assert updated is False

    @pytest.mark.asyncio
    async def test_get_statistics(self, repository, sample_company):
        """Test getting repository statistics."""
        # Create documents with different types and statuses
        docs = [
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2024, 12, 31),
                file_hash="a" * 64,
                raw_llm_output={"data": "test"},
                processing_status="completed",
            ),
            SourceDocument(
                company_code="300257",
                doc_type=DocType.RESEARCH_REPORT,
                doc_date=date(2024, 1, 15),
                file_hash="b" * 64,
                raw_llm_output={"data": "test"},
                processing_status="completed",
            ),
            SourceDocument(
                company_code="300257",
                doc_type=DocType.ANNUAL_REPORT,
                doc_date=date(2023, 12, 31),
                file_hash="c" * 64,
                raw_llm_output={"data": "test"},
                processing_status="failed",
                error_message="Test error",
            ),
        ]

        for doc in docs:
            await repository.save(doc)

        stats = await repository.get_statistics()

        assert stats["total_documents"] == 3
        assert stats["documents_by_type"]["annual_report"] == 2
        assert stats["documents_by_type"]["research_report"] == 1
        assert stats["documents_by_status"]["completed"] == 2
        assert stats["documents_by_status"]["failed"] == 1
        assert stats["latest_document_date"] == "2024-12-31"

    @pytest.mark.asyncio
    async def test_exists_with_existing_hash(
        self, repository, sample_company, sample_document
    ):
        """Test exists method with existing file hash."""
        await repository.save(sample_document)

        exists = await repository.exists("a" * 64)

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_with_non_existing_hash(self, repository):
        """Test exists method with non-existing file hash."""
        exists = await repository.exists("z" * 64)

        assert exists is False

    @pytest.mark.asyncio
    async def test_save_with_null_optional_fields(self, repository, sample_company):
        """Test saving document with null optional fields."""
        doc = SourceDocument(
            company_code="300257",
            doc_type=DocType.ANNUAL_REPORT,
            doc_date=date(2024, 12, 31),
            raw_llm_output={"minimal": "data"},
            # All optional fields are None
        )

        doc_id = await repository.save(doc)

        saved_doc = await repository.find_by_id(doc_id)
        assert saved_doc is not None
        assert saved_doc.report_title is None
        assert saved_doc.file_path is None
        assert saved_doc.file_hash is None
        assert saved_doc.extraction_metadata is None
        assert saved_doc.error_message is None
