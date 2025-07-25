#!/usr/bin/env python3
"""Test timezone conversion in ORM models.

This script tests that timestamps are correctly converted to China timezone
when retrieving data through the ORM.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.persistence.postgres.models import (
    BusinessConceptMasterModel,
    CompanyModel,
    SourceDocumentModel,
)
from src.shared.config import settings


async def test_timezone_conversion():
    """Test timezone conversion in ORM models."""
    # Create engine and session
    # Use the async database URL
    async_url = settings.database.async_database_url

    engine = create_async_engine(
        async_url,
        echo=False,
        connect_args={
            "server_settings": {"timezone": "Asia/Shanghai"},
        },
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("=== Testing Timezone Conversion in ORM Models ===\n")

        # Test CompanyModel
        print("1. Testing CompanyModel:")
        stmt = select(CompanyModel).limit(2)
        result = await session.execute(stmt)
        companies = result.scalars().all()

        for company in companies:
            print(f"\n   Company: {company.company_code}")
            print(f"   Raw created_at: {company.created_at}")
            print(f"   Raw updated_at: {company.updated_at}")

        # Test SourceDocumentModel
        print("\n2. Testing SourceDocumentModel:")
        stmt = select(SourceDocumentModel).limit(2)
        result = await session.execute(stmt)
        documents = result.scalars().all()

        for doc in documents:
            print(f"\n   Document: {doc.doc_id}")
            print(f"   Raw created_at: {doc.created_at}")
            # Convert to domain entity
            domain_doc = doc.to_domain_entity(
                type(
                    "SourceDocument",
                    (),
                    {
                        "__init__": lambda self, **kwargs: [
                            setattr(self, k, v) for k, v in kwargs.items()
                        ]
                    },
                )
            )
            print(f"   Domain entity created_at: {domain_doc.created_at}")

        # Test BusinessConceptMasterModel
        print("\n3. Testing BusinessConceptMasterModel:")
        stmt = select(BusinessConceptMasterModel).limit(2)
        result = await session.execute(stmt)
        concepts = result.scalars().all()

        for concept in concepts:
            print(f"\n   Concept: {concept.concept_id}")
            print(f"   Raw created_at: {concept.created_at}")
            print(f"   Raw updated_at: {concept.updated_at}")
            # Convert to domain entity
            domain_concept = concept.to_domain_entity(
                type(
                    "BusinessConceptMaster",
                    (),
                    {
                        "__init__": lambda self, **kwargs: [
                            setattr(self, k, v) for k, v in kwargs.items()
                        ]
                    },
                )
            )
            print(f"   Domain entity created_at: {domain_concept.created_at}")
            print(f"   Domain entity updated_at: {domain_concept.updated_at}")

    await engine.dispose()
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(test_timezone_conversion())
