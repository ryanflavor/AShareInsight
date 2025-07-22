"""Document value object representing vector search results.

This module defines the Document value object that encapsulates
the results from vector similarity searches.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    """Value object representing a document from vector search results.

    This represents a search result containing business concept information
    along with similarity scores and metadata.

    Attributes:
        concept_id: Unique identifier of the business concept
        company_code: Stock code of the company
        company_name: Full name of the company
        concept_name: Name of the business concept
        concept_category: Category of the business concept
        importance_score: Importance score of the concept (0.0 to 1.0)
        similarity_score: Cosine similarity score from vector search
        source_concept_id: ID of the source concept used in search
        matched_at: Timestamp when the match was found
    """

    model_config = ConfigDict(
        str_strip_whitespace=True, frozen=True, from_attributes=True
    )

    concept_id: UUID = Field(
        ..., description="Unique identifier of the business concept"
    )
    company_code: str = Field(
        ..., max_length=10, description="Stock code of the company"
    )
    company_name: str = Field(
        ..., max_length=255, description="Full name of the company"
    )
    concept_name: str = Field(
        ..., max_length=255, description="Name of the business concept"
    )
    concept_category: str | None = Field(
        None, max_length=100, description="Category of the concept"
    )
    importance_score: Decimal = Field(
        ..., ge=0.0, le=1.0, description="Importance score (0.0 to 1.0)"
    )
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Cosine similarity score"
    )
    source_concept_id: UUID | None = Field(
        None, description="ID of source concept used in search"
    )
    matched_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when match was found",
    )
