"""Business concept entity for AShareInsight domain.

This module defines the BusinessConcept entity representing a company's
business concept with its associated embedding vector.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessConcept(BaseModel):
    """Entity representing a business concept with its semantic embedding.

    Attributes:
        concept_id: Unique identifier for the business concept
        company_code: Stock code of the associated company
        concept_name: Name of the business concept
        concept_category: Category classification of the concept
        importance_score: Score indicating concept importance (0.0 to 1.0)
        source_document_id: Reference to the source document
        created_at: Timestamp when the concept was created
        updated_at: Timestamp when the concept was last updated
        is_active: Whether the concept is currently active
        embedding: The semantic embedding vector (stored separately in DB)
    """

    model_config = ConfigDict(
        str_strip_whitespace=True, frozen=True, from_attributes=True
    )

    concept_id: UUID = Field(
        ..., description="Unique identifier for the business concept"
    )
    company_code: str = Field(
        ..., max_length=10, description="Stock code of the company"
    )
    concept_name: str = Field(
        ..., max_length=255, description="Name of the business concept"
    )
    concept_category: str | None = Field(
        None, max_length=100, description="Category classification"
    )
    importance_score: Decimal = Field(
        ..., ge=0.0, le=1.0, description="Importance score between 0 and 1"
    )
    source_document_id: UUID | None = Field(
        None, description="Reference to source document"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    is_active: bool = Field(default=True, description="Whether concept is active")

    # Note: embedding vector is not included here as it's a technical detail
    # stored in the infrastructure layer (halfvec type in PostgreSQL)
