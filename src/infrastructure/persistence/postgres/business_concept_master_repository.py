"""PostgreSQL implementation of BusinessConceptMasterRepositoryPort.

This module provides the concrete implementation of the BusinessConceptMaster repository
using PostgreSQL with async SQLAlchemy.
"""

from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.business_concept_master_repository import (
    BusinessConceptMasterRepositoryPort,
)
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.infrastructure.persistence.postgres.models import BusinessConceptMasterModel
from src.shared.exceptions.business_exceptions import OptimisticLockError

logger = structlog.get_logger(__name__)


class PostgresBusinessConceptMasterRepository(BusinessConceptMasterRepositoryPort):
    """PostgreSQL implementation of BusinessConceptMaster repository."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: AsyncSession instance for database operations
        """
        self.session = session

    async def find_by_company_and_name(
        self, company_code: str, concept_name: str
    ) -> BusinessConceptMaster | None:
        """Find a business concept by company code and concept name.

        Args:
            company_code: The company code
            concept_name: The business concept name

        Returns:
            The business concept if found, None otherwise
        """
        stmt = select(BusinessConceptMasterModel).where(
            BusinessConceptMasterModel.company_code == company_code,
            BusinessConceptMasterModel.concept_name == concept_name,
            BusinessConceptMasterModel.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        db_concept = result.scalar_one_or_none()

        if db_concept:
            return db_concept.to_domain_entity(BusinessConceptMaster)
        return None

    async def save(
        self, business_concept: BusinessConceptMaster
    ) -> BusinessConceptMaster:
        """Save a new business concept.

        Args:
            business_concept: The business concept to save

        Returns:
            The saved business concept with generated ID

        Raises:
            IntegrityError: If a concept with the same company_code and name exists
        """
        try:
            db_concept = BusinessConceptMasterModel.from_domain_entity(business_concept)
            self.session.add(db_concept)
            await self.session.flush()

            logger.info(
                "business_concept_created",
                concept_id=str(db_concept.concept_id),
                company_code=business_concept.company_code,
                concept_name=business_concept.concept_name,
            )

            return db_concept.to_domain_entity(BusinessConceptMaster)

        except IntegrityError as e:
            if "uq_company_concept_name" in str(e):
                logger.warning(
                    "duplicate_business_concept",
                    company_code=business_concept.company_code,
                    concept_name=business_concept.concept_name,
                )
                raise IntegrityError(
                    f"Business concept {business_concept.concept_name} already exists "
                    f"for company {business_concept.company_code}",
                    params=None,
                    orig=e,
                )
            raise

    async def update(
        self, business_concept: BusinessConceptMaster
    ) -> BusinessConceptMaster:
        """Update an existing business concept.

        Args:
            business_concept: The business concept to update

        Returns:
            The updated business concept

        Raises:
            OptimisticLockError: If version conflict occurs
        """
        # Check current version to handle optimistic locking
        current_stmt = select(BusinessConceptMasterModel).where(
            BusinessConceptMasterModel.concept_id == business_concept.concept_id
        )
        current_result = await self.session.execute(current_stmt)
        current_db_concept = current_result.scalar_one_or_none()

        if not current_db_concept:
            raise ValueError(
                f"Business concept {business_concept.concept_id} not found"
            )

        if current_db_concept.version != business_concept.version - 1:
            logger.warning(
                "optimistic_lock_conflict",
                concept_id=str(business_concept.concept_id),
                current_version=current_db_concept.version,
                expected_version=business_concept.version - 1,
            )
            raise OptimisticLockError(
                f"Version conflict for concept {business_concept.concept_id}. "
                f"Expected version {business_concept.version - 1}, "
                f"but current version is {current_db_concept.version}"
            )

        # Update the concept
        stmt = (
            update(BusinessConceptMasterModel)
            .where(
                BusinessConceptMasterModel.concept_id == business_concept.concept_id,
                BusinessConceptMasterModel.version == business_concept.version - 1,
            )
            .values(
                concept_category=business_concept.concept_category,
                importance_score=business_concept.importance_score,
                development_stage=business_concept.development_stage,
                concept_details=business_concept.concept_details,
                last_updated_from_doc_id=business_concept.last_updated_from_doc_id,
                version=business_concept.version,
                updated_at=business_concept.updated_at,
            )
        )

        result = await self.session.execute(stmt)

        if result.rowcount == 0:
            # This shouldn't happen if we checked version above, but just in case
            raise OptimisticLockError(
                f"Failed to update concept {business_concept.concept_id} due to concurrent modification"
            )

        logger.info(
            "business_concept_updated",
            concept_id=str(business_concept.concept_id),
            company_code=business_concept.company_code,
            concept_name=business_concept.concept_name,
            new_version=business_concept.version,
        )

        # Return the updated entity
        return business_concept

    async def find_all_by_company(
        self, company_code: str
    ) -> list[BusinessConceptMaster]:
        """Find all business concepts for a company.

        Args:
            company_code: The company code

        Returns:
            List of business concepts for the company
        """
        stmt = (
            select(BusinessConceptMasterModel)
            .where(
                BusinessConceptMasterModel.company_code == company_code,
                BusinessConceptMasterModel.is_active.is_(True),
            )
            .order_by(BusinessConceptMasterModel.importance_score.desc())
        )

        result = await self.session.execute(stmt)
        db_concepts = result.scalars().all()

        return [
            concept.to_domain_entity(BusinessConceptMaster) for concept in db_concepts
        ]

    async def find_by_id(self, concept_id: UUID) -> BusinessConceptMaster | None:
        """Find a business concept by ID.

        Args:
            concept_id: The concept UUID

        Returns:
            The business concept if found, None otherwise
        """
        stmt = select(BusinessConceptMasterModel).where(
            BusinessConceptMasterModel.concept_id == concept_id
        )
        result = await self.session.execute(stmt)
        db_concept = result.scalar_one_or_none()

        if db_concept:
            return db_concept.to_domain_entity(BusinessConceptMaster)
        return None

    async def update_embedding(self, concept_id: UUID, embedding: list[float]) -> None:
        """Update only the embedding field for a business concept.

        Args:
            concept_id: The concept UUID
            embedding: The embedding vector as a list of floats

        Note:
            This method does not update the version field to avoid
            triggering business data version changes.
        """
        stmt = (
            update(BusinessConceptMasterModel)
            .where(BusinessConceptMasterModel.concept_id == concept_id)
            .values(embedding=embedding)
        )

        result = await self.session.execute(stmt)

        if result.rowcount == 0:
            logger.warning(
                "embedding_update_failed_not_found", concept_id=str(concept_id)
            )
        else:
            logger.info(
                "embedding_updated",
                concept_id=str(concept_id),
                embedding_dim=len(embedding),
            )

    async def batch_update_embeddings(
        self, embeddings: list[tuple[UUID, list[float]]]
    ) -> None:
        """Batch update embeddings for multiple business concepts.

        Args:
            embeddings: List of tuples containing (concept_id, embedding)

        Note:
            This method does not update the version field to avoid
            triggering business data version changes.
        """
        if not embeddings:
            return

        # Process in batches to avoid query size limits
        batch_size = 100
        successful_updates = 0

        for i in range(0, len(embeddings), batch_size):
            batch = embeddings[i : i + batch_size]

            # Build update data for bulk update
            update_data = []
            for concept_id, embedding in batch:
                update_data.append({"concept_id": concept_id, "embedding": embedding})

            # Execute updates individually to avoid bulk update issues
            for update_item in update_data:
                stmt = (
                    update(BusinessConceptMasterModel)
                    .where(
                        BusinessConceptMasterModel.concept_id
                        == update_item["concept_id"]
                    )
                    .values(embedding=update_item["embedding"])
                    .execution_options(synchronize_session=False)
                )
                result = await self.session.execute(stmt)
                successful_updates += result.rowcount

            await self.session.flush()

            logger.info(
                "batch_embeddings_updated",
                batch_start=i,
                batch_end=min(i + batch_size, len(embeddings)),
                successful_updates=successful_updates,
                total_count=len(embeddings),
            )

    async def find_concepts_needing_embeddings(
        self, limit: int | None = None
    ) -> list[BusinessConceptMaster]:
        """Find concepts that need embeddings (embedding is null).

        Args:
            limit: Optional limit on number of concepts to return

        Returns:
            List of business concepts needing embeddings
        """
        stmt = (
            select(BusinessConceptMasterModel)
            .where(
                BusinessConceptMasterModel.embedding.is_(None),
                BusinessConceptMasterModel.is_active.is_(True),
            )
            .order_by(
                BusinessConceptMasterModel.importance_score.desc(),
                BusinessConceptMasterModel.created_at.asc(),
            )
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self.session.execute(stmt)
        db_concepts = result.scalars().all()

        return [
            concept.to_domain_entity(BusinessConceptMaster) for concept in db_concepts
        ]
