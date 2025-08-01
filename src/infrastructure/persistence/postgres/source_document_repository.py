"""PostgreSQL implementation of SourceDocumentRepositoryPort.

This module provides the concrete implementation of the SourceDocument repository
using PostgreSQL with async SQLAlchemy.
"""

from datetime import date
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.source_document_repository import (
    SourceDocumentRepositoryPort,
)
from src.domain.entities.source_document import SourceDocument
from src.infrastructure.persistence.postgres.models import (
    CompanyModel,
    SourceDocumentModel,
)

logger = structlog.get_logger(__name__)


class PostgresSourceDocumentRepository(SourceDocumentRepositoryPort):
    """PostgreSQL implementation of SourceDocument repository."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: AsyncSession instance for database operations
        """
        self.session = session

    async def save(self, document: SourceDocument) -> UUID:
        """Save a source document to the database.

        Args:
            document: The SourceDocument entity to save

        Returns:
            UUID: The generated document ID

        Raises:
            IntegrityError: If a document with the same file_hash already exists
            OperationalError: If there's a database connection issue
        """
        try:
            # Import DocumentType here to avoid circular imports
            from src.domain.entities.extraction import DocumentType

            # Check if company exists
            company_stmt = select(CompanyModel).where(
                CompanyModel.company_code == document.company_code
            )
            result = await self.session.execute(company_stmt)
            existing_company = result.scalar_one_or_none()

            # Only create/update company for annual reports
            if document.doc_type == DocumentType.ANNUAL_REPORT:
                if not existing_company:
                    # Create company record with minimal info
                    # TODO: This should be handled by a separate Company service
                    # For now, extract company name more intelligently
                    company_name_full = f"Company {document.company_code}"

                    if document.report_title:
                        # Try to extract company name from report title
                        # Remove common suffixes like "年年度报告", "研究报告", etc.
                        import re

                        cleaned_title = re.sub(
                            r"\d{4}年.*报告.*$", "", document.report_title
                        )
                        cleaned_title = re.sub(r"\(\d+\)[^\(]*$", "", cleaned_title)
                        cleaned_title = cleaned_title.strip()
                        if cleaned_title:
                            company_name_full = cleaned_title

                    # Extract additional info from raw_llm_output if available
                    company_name_short = f"待更新-{document.company_code}"
                    exchange = None

                    if document.raw_llm_output and isinstance(
                        document.raw_llm_output, dict
                    ):
                        extraction_data = document.raw_llm_output.get(
                            "extraction_data", {}
                        )
                        if extraction_data:
                            # Get company names
                            if extraction_data.get("company_name_full"):
                                company_name_full = extraction_data["company_name_full"]
                            if extraction_data.get("company_name_short"):
                                company_name_short = extraction_data[
                                    "company_name_short"
                                ]
                            # Get exchange
                            exchange = extraction_data.get("exchange")

                    company = CompanyModel(
                        company_code=document.company_code,
                        company_name_full=company_name_full,
                        company_name_short=company_name_short,
                        exchange=exchange,
                    )
                    self.session.add(company)
                    await self.session.flush()

                    logger.info(
                        "company_created_from_annual_report",
                        company_code=document.company_code,
                        company_name=company_name_full,
                    )
                else:
                    # Update existing company with better quality information
                    update_needed = False
                    updates_made = []

                    if document.raw_llm_output and isinstance(
                        document.raw_llm_output, dict
                    ):
                        extraction_data = document.raw_llm_output.get(
                            "extraction_data", {}
                        )
                        if extraction_data:
                            # Helper function to check if new data is better quality
                            def is_better_quality(
                                old_value: str | None, new_value: str | None
                            ) -> bool:
                                if not old_value:
                                    return bool(new_value)
                                if not new_value:
                                    return False

                                # Placeholder patterns that indicate low quality data
                                placeholders = [
                                    "待更新",
                                    "Company ",
                                    "未知",
                                    "Unknown",
                                    "TBD",
                                    "N/A",
                                ]

                                # Old value is placeholder
                                if any(ph in old_value for ph in placeholders):
                                    return True

                                # New value is longer and more specific
                                # (likely more complete)
                                if len(new_value) > len(old_value) * 1.5:
                                    return True

                                # New value contains more Chinese characters
                                # (for Chinese companies)
                                old_chinese = sum(
                                    1 for c in old_value if "\u4e00" <= c <= "\u9fff"
                                )
                                new_chinese = sum(
                                    1 for c in new_value if "\u4e00" <= c <= "\u9fff"
                                )
                                if (
                                    new_chinese > old_chinese
                                    and new_chinese > len(new_value) * 0.3
                                ):
                                    return True

                                return False

                            # Update exchange
                            new_exchange = extraction_data.get("exchange")
                            if is_better_quality(
                                (
                                    str(existing_company.exchange)
                                    if existing_company.exchange
                                    else None
                                ),
                                new_exchange,
                            ):
                                existing_company.exchange = new_exchange
                                update_needed = True
                                updates_made.append(f"exchange: {new_exchange}")

                            # Update company short name
                            new_short_name = extraction_data.get("company_name_short")
                            if is_better_quality(
                                (
                                    str(existing_company.company_name_short)
                                    if existing_company.company_name_short
                                    else None
                                ),
                                new_short_name,
                            ):
                                existing_company.company_name_short = new_short_name
                                update_needed = True
                                updates_made.append(f"short_name: {new_short_name}")

                            # Update company full name
                            new_full_name = extraction_data.get("company_name_full")
                            if is_better_quality(
                                (
                                    str(existing_company.company_name_full)
                                    if existing_company.company_name_full
                                    else None
                                ),
                                new_full_name,
                            ):
                                existing_company.company_name_full = new_full_name
                                update_needed = True
                                updates_made.append(f"full_name: {new_full_name}")

                    if update_needed:
                        await self.session.flush()
                        logger.info(
                            "company_updated_from_annual_report",
                            company_code=document.company_code,
                            updates=updates_made,
                            old_values={
                                "exchange": existing_company.exchange,
                                "short_name": existing_company.company_name_short,
                                "full_name": existing_company.company_name_full,
                            },
                        )
            else:
                # For research reports, company must already exist
                if not existing_company:
                    raise ValueError(
                        f"Company {document.company_code} not found in database. "
                        f"Research reports require existing company record. "
                        f"Please process an annual report for this company first."
                    )

                logger.info(
                    "research_report_using_existing_company",
                    company_code=document.company_code,
                    doc_type=document.doc_type.value,
                )

            # Create source document
            db_document = SourceDocumentModel.from_domain_entity(document)
            self.session.add(db_document)
            await self.session.flush()

            logger.info(
                "source_document_saved",
                doc_id=str(db_document.doc_id),
                company_code=document.company_code,
                doc_type=document.doc_type.value,
                file_hash=document.file_hash,
            )

            return db_document.doc_id

        except IntegrityError as e:
            if "uq_source_documents_file_hash" in str(e):
                logger.warning(
                    "duplicate_document_attempt",
                    file_hash=document.file_hash,
                    company_code=document.company_code,
                )
                raise IntegrityError(
                    f"Document with file_hash {document.file_hash} already exists",
                    params=None,
                    orig=e,
                ) from e
            elif "fk_source_documents_company_code" in str(e):
                logger.error(
                    "invalid_company_code",
                    company_code=document.company_code,
                )
                raise IntegrityError(
                    f"Invalid company_code: {document.company_code}",
                    params=None,
                    orig=e,
                ) from e
            else:
                raise

    async def find_by_id(self, doc_id: UUID) -> SourceDocument | None:
        """Find a source document by its ID.

        Args:
            doc_id: The UUID of the document to find

        Returns:
            SourceDocument if found, None otherwise
        """
        stmt = select(SourceDocumentModel).where(SourceDocumentModel.doc_id == doc_id)
        result = await self.session.execute(stmt)
        db_document = result.scalar_one_or_none()

        if db_document:
            return db_document.to_domain_entity(SourceDocument)
        return None

    async def find_by_file_hash(self, file_hash: str) -> SourceDocument | None:
        """Find a source document by its file hash.

        Args:
            file_hash: The SHA-256 hash of the file

        Returns:
            SourceDocument if found, None otherwise
        """
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.file_hash == file_hash
        )
        result = await self.session.execute(stmt)
        db_document = result.scalar_one_or_none()

        if db_document:
            return db_document.to_domain_entity(SourceDocument)
        return None

    async def find_by_company_and_date_range(
        self,
        company_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        doc_type: str | None = None,
    ) -> list[SourceDocument]:
        """Find source documents by company code and optional date range.

        Args:
            company_code: The stock code of the company
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            doc_type: Optional document type filter

        Returns:
            List of matching SourceDocument entities
        """
        conditions = [SourceDocumentModel.company_code == company_code]

        if start_date:
            conditions.append(
                SourceDocumentModel.doc_date >= date.fromisoformat(start_date)
            )
        if end_date:
            conditions.append(
                SourceDocumentModel.doc_date <= date.fromisoformat(end_date)
            )
        if doc_type:
            conditions.append(SourceDocumentModel.doc_type == doc_type)

        stmt = (
            select(SourceDocumentModel)
            .where(and_(*conditions))
            .order_by(SourceDocumentModel.doc_date.desc())
        )

        result = await self.session.execute(stmt)
        db_documents = result.scalars().all()

        return [doc.to_domain_entity(SourceDocument) for doc in db_documents]

    async def update_status(
        self, doc_id: UUID, status: str, error_message: str | None = None
    ) -> bool:
        """Update the processing status of a document.

        Args:
            doc_id: The document ID to update
            status: The new status
            error_message: Optional error message if status is 'failed'

        Returns:
            True if update was successful, False if document not found
        """
        stmt = (
            update(SourceDocumentModel)
            .where(SourceDocumentModel.doc_id == doc_id)
            .values(processing_status=status, error_message=error_message)
        )

        result = await self.session.execute(stmt)
        updated = result.rowcount > 0

        if updated:
            logger.info(
                "document_status_updated",
                doc_id=str(doc_id),
                status=status,
                has_error=error_message is not None,
            )

        return updated

    async def get_all_file_hashes(self) -> set[str]:
        """Get all file hashes from the database.

        Returns:
            Set of file hashes
        """
        stmt = select(SourceDocumentModel.file_hash).where(
            SourceDocumentModel.file_hash.isnot(None)
        )
        result = await self.session.execute(stmt)
        return {row[0] for row in result}

    async def get_statistics(self) -> dict[str, Any]:
        """Get repository statistics.

        Returns:
            Dictionary containing various statistics
        """
        # Total documents
        total_stmt = select(func.count()).select_from(SourceDocumentModel)
        total_result = await self.session.execute(total_stmt)
        total_documents = total_result.scalar() or 0

        # Documents by type
        type_stmt = select(
            SourceDocumentModel.doc_type,
            func.count().label("count"),
        ).group_by(SourceDocumentModel.doc_type)
        type_result = await self.session.execute(type_stmt)
        documents_by_type = {row[0]: row[1] for row in type_result}

        # Documents by status
        status_stmt = select(
            SourceDocumentModel.processing_status,
            func.count().label("count"),
        ).group_by(SourceDocumentModel.processing_status)
        status_result = await self.session.execute(status_stmt)
        documents_by_status = {row[0]: row[1] for row in status_result}

        # Latest document date
        latest_stmt = select(func.max(SourceDocumentModel.doc_date))
        latest_result = await self.session.execute(latest_stmt)
        latest_date = latest_result.scalar()

        return {
            "total_documents": total_documents,
            "documents_by_type": documents_by_type,
            "documents_by_status": documents_by_status,
            "latest_document_date": latest_date.isoformat() if latest_date else None,
        }

    async def exists(self, file_hash: str) -> bool:
        """Check if a document with the given file hash exists.

        Args:
            file_hash: The SHA-256 hash to check

        Returns:
            True if a document with this hash exists, False otherwise
        """
        stmt = select(
            select(SourceDocumentModel.doc_id)
            .where(SourceDocumentModel.file_hash == file_hash)
            .exists()
        )
        result = await self.session.execute(stmt)
        return result.scalar() or False
