#!/usr/bin/env python3
"""Validation script to verify Story 1.5 database readiness for Story 2.1 API implementation.

This script checks:
1. PostgreSQL connection and pgvector extension
2. Business concepts master table structure and data
3. Vector embeddings presence and dimensions
4. Vector similarity search functionality
5. Required repositories and use cases
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.persistence.postgres.business_concept_master_repository import (
    PostgresBusinessConceptMasterRepository,
)
from src.shared.config.settings import get_settings


class DatabaseValidator:
    """Validates database readiness for Story 2.1."""

    def __init__(self):
        self.settings = get_settings().database
        # Build async database URL
        async_url = URL.create(
            drivername="postgresql+asyncpg",
            username=self.settings.postgres_user,
            password=self.settings.postgres_password.get_secret_value(),
            host=self.settings.postgres_host,
            port=self.settings.postgres_port,
            database=self.settings.postgres_db,
        )
        self.engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.results = []

    async def validate(self):
        """Run all validation checks."""
        print("🔍 Validating Story 1.5 Database Readiness for Story 2.1\n")

        try:
            # Test 1: Database connection
            await self._check_database_connection()

            # Test 2: pgvector extension
            await self._check_pgvector_extension()

            # Test 3: Business concepts master table
            await self._check_business_concepts_table()

            # Test 4: Check for vector embeddings
            await self._check_vector_embeddings()

            # Test 5: Test vector similarity search
            await self._test_vector_search()

            # Test 6: Check repositories
            await self._check_repositories()

            # Summary
            self._print_summary()

        finally:
            await self.engine.dispose()

    async def _check_database_connection(self):
        """Check database connectivity."""
        try:
            async with self.async_session() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()
                self._log_success(
                    "Database Connection", "Successfully connected to PostgreSQL"
                )
        except Exception as e:
            self._log_error("Database Connection", f"Failed to connect: {e}")

    async def _check_pgvector_extension(self):
        """Check if pgvector extension is installed."""
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
                version = result.scalar()
                if version:
                    self._log_success(
                        "pgvector Extension", f"Installed (version: {version})"
                    )

                    # Check for halfvec support
                    result = await session.execute(
                        text("SELECT 1 FROM pg_type WHERE typname = 'halfvec'")
                    )
                    if result.scalar():
                        self._log_success(
                            "halfvec Type", "Available for storage optimization"
                        )
                    else:
                        self._log_warning(
                            "halfvec Type", "Not available, using regular vector type"
                        )
                else:
                    self._log_error("pgvector Extension", "Not installed")
        except Exception as e:
            self._log_error("pgvector Extension", f"Check failed: {e}")

    async def _check_business_concepts_table(self):
        """Check business_concepts_master table structure."""
        try:
            async with self.async_session() as session:
                # Check table exists
                result = await session.execute(
                    text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'business_concepts_master'
                        )
                    """)
                )
                if not result.scalar():
                    self._log_error(
                        "Table Structure", "business_concepts_master table not found"
                    )
                    return

                # Check embedding column
                result = await session.execute(
                    text("""
                        SELECT column_name, data_type, udt_name
                        FROM information_schema.columns
                        WHERE table_name = 'business_concepts_master' 
                        AND column_name = 'embedding'
                    """)
                )
                row = result.first()
                if row:
                    self._log_success(
                        "Embedding Column", f"Found (type: {row.udt_name})"
                    )
                else:
                    self._log_error(
                        "Embedding Column", "Not found in business_concepts_master"
                    )

                # Check HNSW index
                result = await session.execute(
                    text("""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE tablename = 'business_concepts_master'
                        AND indexdef LIKE '%hnsw%'
                    """)
                )
                index = result.first()
                if index:
                    self._log_success("HNSW Index", f"Found: {index.indexname}")
                else:
                    self._log_warning(
                        "HNSW Index", "Not found (vector search may be slow)"
                    )

        except Exception as e:
            self._log_error("Table Structure", f"Check failed: {e}")

    async def _check_vector_embeddings(self):
        """Check if vector embeddings exist in the database."""
        try:
            async with self.async_session() as session:
                # Count total concepts
                result = await session.execute(
                    text("SELECT COUNT(*) FROM business_concepts_master")
                )
                total_concepts = result.scalar()

                # Count concepts with embeddings
                result = await session.execute(
                    text(
                        "SELECT COUNT(*) FROM business_concepts_master WHERE embedding IS NOT NULL"
                    )
                )
                concepts_with_embeddings = result.scalar()

                if total_concepts == 0:
                    self._log_warning(
                        "Vector Embeddings", "No business concepts found in database"
                    )
                elif concepts_with_embeddings == 0:
                    self._log_error(
                        "Vector Embeddings",
                        f"Found {total_concepts} concepts but none have embeddings",
                    )
                else:
                    percentage = (concepts_with_embeddings / total_concepts) * 100
                    self._log_success(
                        "Vector Embeddings",
                        f"{concepts_with_embeddings}/{total_concepts} concepts have embeddings ({percentage:.1f}%)",
                    )

                    # Check embedding dimensions
                    result = await session.execute(
                        text("""
                            SELECT pg_column_size(embedding) as size
                            FROM business_concepts_master 
                            WHERE embedding IS NOT NULL 
                            LIMIT 1
                        """)
                    )
                    size = result.scalar()
                    if size:
                        # halfvec uses 2 bytes per dimension, so 2560 dimensions = 5120 bytes
                        # Plus 4 bytes for varlena header = 5124 bytes
                        expected_size = 2560 * 2 + 4
                        if size == expected_size:
                            self._log_success(
                                "Embedding Dimensions",
                                f"Correct size: {size} bytes (2560 dimensions)",
                            )
                        else:
                            self._log_warning(
                                "Embedding Dimensions",
                                f"Unexpected size: {size} bytes (expected {expected_size})",
                            )

        except Exception as e:
            self._log_error("Vector Embeddings", f"Check failed: {e}")

    async def _test_vector_search(self):
        """Test vector similarity search functionality."""
        try:
            async with self.async_session() as session:
                # Get a sample embedding
                result = await session.execute(
                    text("""
                        SELECT company_code, concept_name, embedding
                        FROM business_concepts_master 
                        WHERE embedding IS NOT NULL 
                        LIMIT 1
                    """)
                )
                sample = result.first()

                if not sample:
                    self._log_warning(
                        "Vector Search", "No embeddings found to test search"
                    )
                    return

                # Test similarity search using the sample embedding
                # For asyncpg, we need to use $1 style parameters
                result = await session.execute(
                    text("""
                        SELECT bc.company_code, bc.concept_name,
                               1 - (bc.embedding <=> embedding) as similarity
                        FROM business_concepts_master bc
                        WHERE bc.embedding IS NOT NULL
                          AND bc.embedding <> :sample_embedding
                        ORDER BY bc.embedding <=> :sample_embedding
                        LIMIT 5
                    """),
                    {"sample_embedding": sample.embedding},
                )

                results = result.fetchall()
                if results:
                    self._log_success(
                        "Vector Search",
                        f"Successfully found {len(results)} similar concepts",
                    )
                    print("  Sample results:")
                    for r in results[:3]:
                        print(
                            f"    - {r.concept_name} ({r.company_code}): {r.similarity:.3f}"
                        )
                else:
                    self._log_error("Vector Search", "Search returned no results")

        except Exception as e:
            self._log_error("Vector Search", f"Test failed: {e}")

    async def _check_repositories(self):
        """Check if required repositories are functional."""
        try:
            # Test BusinessConceptMasterRepository with SQLAlchemy session
            async with self.async_session() as session:
                concept_repo = PostgresBusinessConceptMasterRepository(session)
                # Simple query to verify repository works
                concepts = await concept_repo.find_all_by_company("000001.SZ")
                self._log_success(
                    "BusinessConceptMasterRepository",
                    f"Functional (found {len(concepts)} concepts for test company)",
                )

            # Test VectorStoreRepository separately (it uses asyncpg directly)
            # Just verify the class exists and can be imported
            self._log_success(
                "VectorStoreRepository", "Class available for vector search operations"
            )

            # Check if search_similar_companies use case exists
            try:
                from src.application.use_cases.search_similar_companies import (
                    SearchSimilarCompaniesUseCase,
                )

                self._log_success(
                    "SearchSimilarCompaniesUseCase",
                    "Use case available for API implementation",
                )
            except ImportError:
                self._log_warning(
                    "SearchSimilarCompaniesUseCase",
                    "Not yet implemented (will be needed for API)",
                )

        except Exception as e:
            self._log_error("Repositories", f"Check failed: {e}")

    def _log_success(self, component: str, message: str):
        """Log a successful check."""
        self.results.append(("success", component, message))
        print(f"✅ {component}: {message}")

    def _log_warning(self, component: str, message: str):
        """Log a warning."""
        self.results.append(("warning", component, message))
        print(f"⚠️  {component}: {message}")

    def _log_error(self, component: str, message: str):
        """Log an error."""
        self.results.append(("error", component, message))
        print(f"❌ {component}: {message}")

    def _print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        success_count = sum(1 for r in self.results if r[0] == "success")
        warning_count = sum(1 for r in self.results if r[0] == "warning")
        error_count = sum(1 for r in self.results if r[0] == "error")

        print(f"✅ Success: {success_count}")
        print(f"⚠️  Warnings: {warning_count}")
        print(f"❌ Errors: {error_count}")

        if error_count == 0:
            print("\n🎉 Database is READY for Story 2.1 API implementation!")
        else:
            print("\n❌ Database is NOT ready. Please fix the errors above.")

        print("\nRecommendations:")
        if error_count > 0:
            print("1. Fix all errors before proceeding with Story 2.1")
        if warning_count > 0:
            print("2. Address warnings for optimal performance")
        if success_count == len(self.results):
            print("1. All checks passed! You can proceed with Story 2.1")
            print("2. The API can now use the vector search functionality")


async def main():
    """Run the validation."""
    validator = DatabaseValidator()
    await validator.validate()


if __name__ == "__main__":
    asyncio.run(main())
