"""Factory functions for creating application components with proper dependencies.

This module provides factory functions that wire up use cases with their
dependencies, including proper transaction management.
"""

from typing import Any
from uuid import UUID

from src.application.use_cases.archive_extraction_result import (
    ArchiveExtractionResultUseCase,
)
from src.application.use_cases.update_master_data import UpdateMasterDataUseCase
from src.domain.entities.source_document import SourceDocumentMetadata
from src.domain.services.data_fusion_service import DataFusionService
from src.infrastructure.persistence.postgres.business_concept_master_repository import (
    PostgresBusinessConceptMasterRepository,
)
from src.infrastructure.persistence.postgres.connection import get_db_connection
from src.infrastructure.persistence.postgres.session_factory import SessionFactory
from src.infrastructure.persistence.postgres.source_document_repository import (
    PostgresSourceDocumentRepository,
)


async def create_archive_use_case_with_fusion() -> ArchiveExtractionResultUseCase:
    """Create an archive use case with master data fusion capability.

    This factory creates an ArchiveExtractionResultUseCase that will automatically
    trigger master data fusion after successful archival. The use cases will manage
    their own database sessions to ensure proper transaction boundaries.

    Returns:
        ArchiveExtractionResultUseCase configured with fusion capability
    """
    # Get database connection
    db_connection = await get_db_connection()

    # Create session factory
    session_factory = SessionFactory(db_connection.engine)

    # Create a wrapper class that manages sessions per operation
    class SessionManagedArchiveUseCase(ArchiveExtractionResultUseCase):
        def __init__(
            self, session_factory: SessionFactory, fusion_enabled: bool = True
        ):
            self.session_factory = session_factory
            self.fusion_enabled = fusion_enabled
            # Don't call super().__init__ yet as we need dynamic repositories

        async def execute(
            self,
            raw_llm_output: dict[str, Any],
            metadata: dict[str, Any] | SourceDocumentMetadata,
        ) -> UUID:
            """Execute with proper session management."""
            async with self.session_factory.get_session() as session:
                # Create repositories with the session
                source_doc_repo = PostgresSourceDocumentRepository(session)
                business_concept_repo = PostgresBusinessConceptMasterRepository(session)

                # Create the update master data use case if fusion is enabled
                update_master_data_use_case = None
                if self.fusion_enabled:
                    data_fusion_service = DataFusionService()
                    update_master_data_use_case = UpdateMasterDataUseCase(
                        source_document_repo=source_doc_repo,
                        business_concept_repo=business_concept_repo,
                        data_fusion_service=data_fusion_service,
                    )

                # Set up the parent class with the session-scoped dependencies
                self.repository = source_doc_repo
                self.update_master_data_use_case = update_master_data_use_case

                # Execute the parent class method
                return await super().execute(raw_llm_output, metadata)

    return SessionManagedArchiveUseCase(session_factory)


async def create_standalone_fusion_use_case() -> UpdateMasterDataUseCase:
    """Create a standalone master data fusion use case.

    This factory creates an UpdateMasterDataUseCase that can be used
    independently to update master data for already archived documents.

    Returns:
        UpdateMasterDataUseCase ready for use
    """
    # Get database connection
    db_connection = await get_db_connection()

    # Create session factory
    session_factory = SessionFactory(db_connection.engine)

    # Create a wrapper class that manages sessions per operation
    class SessionManagedUpdateMasterDataUseCase(UpdateMasterDataUseCase):
        def __init__(self, session_factory: SessionFactory):
            self.session_factory = session_factory
            self.data_fusion_service = DataFusionService()
            self.batch_size = 50  # Set default batch size
            # Don't call super().__init__ yet as we need dynamic repositories

        async def execute(self, doc_id: UUID) -> dict[str, Any]:
            """Execute with proper session management."""
            async with self.session_factory.get_session() as session:
                # Create repositories with the session
                source_doc_repo = PostgresSourceDocumentRepository(session)
                business_concept_repo = PostgresBusinessConceptMasterRepository(session)

                # Set up the parent class with the session-scoped dependencies
                self.source_document_repo = source_doc_repo
                self.business_concept_repo = business_concept_repo

                # Execute the parent class method
                return await super().execute(doc_id)

    return SessionManagedUpdateMasterDataUseCase(session_factory)
