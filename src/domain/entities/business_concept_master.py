"""Business Concept Master domain entity.

This module defines the BusinessConceptMaster entity which represents
the authoritative master data for business concepts of companies.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.shared.config.settings import get_settings


class BusinessConceptMaster(BaseModel):
    """Business concept master entity representing authoritative business data.

    This entity stores the master record for each business concept,
    with smart fusion of data from multiple source documents.
    """

    concept_id: UUID
    company_code: str = Field(max_length=10)
    concept_name: str = Field(max_length=255)
    concept_category: str = Field(max_length=50)
    importance_score: Decimal = Field(ge=0, le=1)
    development_stage: str | None = Field(default=None, max_length=50)
    embedding: bytes | None = Field(default=None)  # halfvec(2560) for future use
    concept_details: dict[str, Any]
    last_updated_from_doc_id: UUID | None = None
    version: int = Field(default=1, ge=1)
    is_active: bool = Field(default=True)
    created_at: datetime
    updated_at: datetime

    @field_validator("concept_category")
    @classmethod
    def validate_concept_category(cls, v: str) -> str:
        """Validate that concept category is one of allowed values."""
        settings = get_settings()
        allowed_categories = settings.fusion.concept_categories_set
        if v not in allowed_categories:
            raise ValueError(
                f"concept_category must be one of {allowed_categories}, got {v}"
            )
        return v

    @field_validator("importance_score")
    @classmethod
    def validate_importance_score(cls, v: Decimal) -> Decimal:
        """Ensure importance score is a valid decimal between 0 and 1."""
        if not isinstance(v, Decimal):
            v = Decimal(str(v))
        if v < 0 or v > 1:
            raise ValueError(f"importance_score must be between 0 and 1, got {v}")
        return v

    @field_validator("concept_details")
    @classmethod
    def validate_concept_details(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate concept_details has expected structure."""
        # Ensure it's a dictionary
        if not isinstance(v, dict):
            raise ValueError("concept_details must be a dictionary")

        # We don't enforce strict schema here as details can evolve
        # but we ensure it can be serialized to JSON
        return v

    def update_from_fusion(self, new_data: dict[str, Any], doc_id: UUID) -> None:
        """Update this entity based on fusion rules.

        Args:
            new_data: New business concept data to merge
            doc_id: Document ID that provided the new data
        """
        # Update time-sensitive fields (overwrite strategy)
        if "importance_score" in new_data:
            self.importance_score = Decimal(str(new_data["importance_score"]))

        if "development_stage" in new_data:
            self.development_stage = new_data["development_stage"]

        # Update concept_details with fusion logic
        if "metrics" in new_data:
            self.concept_details["metrics"] = new_data["metrics"]

        if "timeline" in new_data:
            self.concept_details["timeline"] = new_data["timeline"]

        # Merge cumulative fields (union strategy)
        if "relations" in new_data:
            self._merge_relations(new_data["relations"])

        # Smart merge for description (keep longer one)
        if "description" in new_data:
            current_desc = self.concept_details.get("description", "")
            new_desc = new_data["description"]
            if len(new_desc) > len(current_desc):
                self.concept_details["description"] = new_desc

        # Merge source sentences (union with limit)
        if "source_sentences" in new_data:
            self._merge_source_sentences(new_data["source_sentences"])

        # Update metadata
        self.last_updated_from_doc_id = doc_id
        self.version += 1
        self.updated_at = datetime.now(UTC)

    def _merge_relations(self, new_relations: dict[str, Any]) -> None:
        """Merge relations using union strategy."""
        if "relations" not in self.concept_details:
            self.concept_details["relations"] = {}

        current_relations = self.concept_details["relations"]

        # Merge customers
        if "customers" in new_relations:
            current_customers = set(current_relations.get("customers", []))
            new_customers = set(new_relations["customers"])
            current_relations["customers"] = list(current_customers | new_customers)

        # Merge partners
        if "partners" in new_relations:
            current_partners = set(current_relations.get("partners", []))
            new_partners = set(new_relations["partners"])
            current_relations["partners"] = list(current_partners | new_partners)

        # Merge subsidiaries
        if "subsidiaries_or_investees" in new_relations:
            current_subs = set(current_relations.get("subsidiaries_or_investees", []))
            new_subs = set(new_relations["subsidiaries_or_investees"])
            current_relations["subsidiaries_or_investees"] = list(
                current_subs | new_subs
            )

    def _merge_source_sentences(self, new_sentences: list[str]) -> None:
        """Merge source sentences with deduplication and limit."""
        current_sentences = self.concept_details.get("source_sentences", [])

        # Use ordered dict to maintain order while deduplicating
        merged = {}
        for sentence in current_sentences + new_sentences:
            merged[sentence] = None

        # Keep only configured max sentences
        settings = get_settings()
        max_sentences = settings.fusion.max_source_sentences
        self.concept_details["source_sentences"] = list(merged.keys())[:max_sentences]

    model_config = {
        "json_encoders": {UUID: str, datetime: lambda v: v.isoformat(), Decimal: str}
    }
