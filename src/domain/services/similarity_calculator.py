"""Similarity calculator domain service.

This module implements the core ranking algorithm that combines
rerank scores with business concept importance scores to produce
final ranking scores.
"""

from typing import NamedTuple

from pydantic import BaseModel, Field, model_validator

from src.domain.value_objects.document import Document


class RankingWeight(BaseModel):
    """Configuration for ranking weight parameters.

    Attributes:
        rerank_weight: Weight for the rerank score (w1)
        importance_weight: Weight for the importance score (w2)
    """

    rerank_weight: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Weight for rerank score (w1)"
    )
    importance_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Weight for importance score (w2)"
    )

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "RankingWeight":
        """Ensure weights sum to 1.0."""
        weight_sum = self.rerank_weight + self.importance_weight
        if not (0.99 <= weight_sum <= 1.01):  # Allow small floating point errors
            raise ValueError(f"Weights must sum to 1.0, but sum is {weight_sum:.3f}")
        return self


class ScoredDocument(NamedTuple):
    """Document with calculated final ranking score."""

    document: Document
    final_score: float
    rerank_score: float | None


class SimilarityCalculator:
    """Domain service for calculating final ranking scores.

    This service implements the core ranking algorithm that combines
    multiple signals to produce a final relevance score for business concepts.

    The formula used is:
    RankingScore = w1 * RerankScore + w2 * SourceConcept_ImportanceScore
    """

    def calculate_final_scores(
        self,
        documents: list[Document],
        rerank_scores: dict[str, float] | None = None,
        weights: RankingWeight | None = None,
    ) -> list[ScoredDocument]:
        """Calculate final ranking scores for documents.

        This method applies the weighted formula to combine rerank scores
        with business concept importance scores. If rerank scores are not
        available, it gracefully degrades to using only importance scores.

        Args:
            documents: List of documents to score
            rerank_scores: Optional mapping of concept_id to rerank score
            weights: Optional weight configuration (uses defaults if not provided)

        Returns:
            List of ScoredDocument objects sorted by final score (descending)

        Raises:
            ValueError: If any scores are outside the valid range [0, 1]
        """
        if weights is None:
            weights = RankingWeight()

        scored_documents = []

        for doc in documents:
            # Validate importance score
            if not (0 <= doc.importance_score <= 1):
                raise ValueError(
                    f"Invalid importance score {doc.importance_score} for "
                    f"concept {doc.concept_id}. Must be in range [0, 1]."
                )

            # Get rerank score if available
            rerank_score = None
            if rerank_scores and str(doc.concept_id) in rerank_scores:
                rerank_score = rerank_scores[str(doc.concept_id)]

                # Validate rerank score
                if not (0 <= rerank_score <= 1):
                    raise ValueError(
                        f"Invalid rerank score {rerank_score} for "
                        f"concept {doc.concept_id}. Must be in range [0, 1]."
                    )

            # Calculate final score
            final_score = self._calculate_weighted_score(
                rerank_score=rerank_score,
                importance_score=float(doc.importance_score),
                weights=weights,
            )

            scored_documents.append(
                ScoredDocument(
                    document=doc,
                    final_score=final_score,
                    rerank_score=rerank_score,
                )
            )

        # Sort by final score (descending)
        scored_documents.sort(key=lambda x: x.final_score, reverse=True)

        return scored_documents

    def _calculate_weighted_score(
        self,
        rerank_score: float | None,
        importance_score: float,
        weights: RankingWeight,
    ) -> float:
        """Calculate weighted score with graceful degradation.

        If rerank score is not available, the formula degrades to:
        RankingScore = importance_score

        Args:
            rerank_score: Optional rerank score
            importance_score: Business concept importance score
            weights: Weight configuration

        Returns:
            Final weighted score in range [0, 1]
        """
        if rerank_score is None:
            # Graceful degradation: use importance score only
            return importance_score

        # Apply full weighted formula
        weighted_score = (
            weights.rerank_weight * rerank_score
            + weights.importance_weight * importance_score
        )

        # Ensure result is in valid range (handle floating point errors)
        return max(0.0, min(1.0, weighted_score))
