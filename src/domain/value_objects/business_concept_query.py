"""Business concept query value object for vector similarity search.

This module defines the query parameters for searching similar business concepts
based on company identification and optional text embeddings.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BusinessConceptQuery(BaseModel):
    """Value object representing a query for similar business concepts.

    Attributes:
        target_identifier: Company code or name to search for
        text_to_embed: Optional text to embed and search with
        top_k: Number of top results to return
        similarity_threshold: Minimum similarity score threshold
    """

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    target_identifier: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Company code (e.g., '000001') or name to search",
    )
    text_to_embed: str | None = Field(
        None, max_length=2000, description="Optional text to embed for semantic search"
    )
    top_k: int = Field(
        default=50, ge=1, le=100, description="Number of top results to return"
    )
    similarity_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum similarity score (0.0 to 1.0)"
    )

    @field_validator("target_identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        """Validate target identifier is not empty after stripping."""
        if not v or not v.strip():
            raise ValueError("Target identifier cannot be empty")
        return v
