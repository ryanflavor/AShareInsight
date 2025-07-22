"""
Domain service for text vectorization preparation.

This service contains business logic for preparing texts before vectorization,
ensuring consistent text formatting and handling of business concepts.
"""

import logging
import re
from typing import Any

import numpy as np

from src.application.ports.embedding_service_port import (
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingServicePort,
)
from src.domain.entities.business_concept_master import BusinessConceptMaster
from src.shared.config.settings import QwenEmbeddingSettings

logger = logging.getLogger(__name__)


class VectorizationService:
    """Service for preparing business concept texts for vectorization.

    This domain service encapsulates the business logic for combining
    concept names and descriptions into texts suitable for embedding,
    handling edge cases and text normalization.
    """

    def __init__(
        self,
        embedding_service: EmbeddingServicePort,
        qwen_settings: QwenEmbeddingSettings | None = None,
        max_text_length: int | None = None,
        concept_weight: float = 1.0,
        description_weight: float = 1.0,
    ) -> None:
        """Initialize the vectorization service.

        Args:
            embedding_service: Service for generating embeddings.
            qwen_settings: Qwen embedding settings for configuration.
            max_text_length: Override for maximum character length for combined text.
            concept_weight: Weight multiplier for concept name (future use).
            description_weight: Weight multiplier for description (future use).
        """
        self.embedding_service = embedding_service
        self.qwen_settings = qwen_settings or QwenEmbeddingSettings()
        self.max_text_length = (
            max_text_length or self.qwen_settings.qwen_max_text_length
        )
        self.concept_weight = concept_weight
        self.description_weight = description_weight

    def prepare_text_for_embedding(
        self, concept_name: str, description: str | None = None
    ) -> str:
        """Prepare business concept text for embedding.

        Combines concept name and description into a single text suitable
        for vectorization, handling null values and special characters.

        Args:
            concept_name: Name of the business concept.
            description: Optional description of the concept.

        Returns:
            Formatted text ready for embedding.
        """
        # Clean and normalize concept name
        cleaned_name = self._clean_text(concept_name)

        if not cleaned_name:
            return ""

        # Handle description
        if description:
            cleaned_description = self._clean_text(description)
            if cleaned_description:
                # Combine using the recommended format
                combined_text = f"{cleaned_name}: {cleaned_description}"
            else:
                combined_text = cleaned_name
        else:
            combined_text = cleaned_name

        # Truncate if necessary
        if len(combined_text) > self.max_text_length:
            # Ensure we keep the concept name and truncate description
            if description and len(cleaned_name) < self.max_text_length:
                max_desc_length = self.max_text_length - len(cleaned_name) - 2  # ": "
                truncated_desc = cleaned_description[:max_desc_length] + "..."
                combined_text = f"{cleaned_name}: {truncated_desc}"
            else:
                combined_text = combined_text[: self.max_text_length - 3] + "..."

        return combined_text

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for embedding.

        Args:
            text: Raw text to clean.

        Returns:
            Cleaned and normalized text.
        """
        if not text:
            return ""

        # Remove excessive whitespace
        text = " ".join(text.split())

        # Remove control characters but keep Chinese characters
        text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)

        # Normalize quotes - using unicode escapes for clarity
        text = text.replace("\u201c", '"').replace("\u201d", '"')  # " and "
        text = text.replace("\u2018", "'").replace("\u2019", "'")  # ' and '

        # Remove zero-width characters
        text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)

        return text.strip()

    def calculate_text_similarity_threshold(self) -> float:
        """Calculate similarity threshold for duplicate detection.

        Returns:
            Similarity threshold value (0.0 to 1.0) from settings.
        """
        return self.qwen_settings.qwen_similarity_threshold

    def should_update_embedding(
        self, old_text: str, new_text: str, similarity_threshold: float | None = None
    ) -> bool:
        """Determine if embedding should be updated based on text changes.

        Args:
            old_text: Previous text used for embedding.
            new_text: New text to compare.
            similarity_threshold: Optional custom threshold.

        Returns:
            True if embedding should be updated, False otherwise.
        """
        if not old_text or not new_text:
            return old_text != new_text

        # Simple character-based comparison
        # In production, could use more sophisticated similarity metrics
        old_cleaned = self._clean_text(old_text)
        new_cleaned = self._clean_text(new_text)

        if old_cleaned == new_cleaned:
            return False

        # Check if changes are significant enough
        # This is a simple length-based heuristic
        length_ratio = (
            len(new_cleaned) / len(old_cleaned) if old_cleaned else float("inf")
        )

        # Update if length changed significantly based on configured thresholds
        if (
            length_ratio < self.qwen_settings.qwen_length_ratio_min
            or length_ratio > self.qwen_settings.qwen_length_ratio_max
        ):
            return True

        # For minor changes, could implement more sophisticated logic
        # For now, any change triggers update
        return True

    async def vectorize_business_concept(
        self, concept: BusinessConceptMaster
    ) -> tuple[np.ndarray, str]:
        """Vectorize a single business concept.

        Args:
            concept: Business concept to vectorize.

        Returns:
            Tuple of (embedding vector, prepared text).
        """
        # Prepare text for embedding
        description = concept.concept_details.get("description")
        text = self.prepare_text_for_embedding(concept.concept_name, description)

        if not text:
            logger.warning(
                f"Empty text for concept {concept.concept_id}, returning zero vector"
            )
            dimension = self.embedding_service.get_embedding_dimension()
            return np.zeros(dimension), text

        # Generate embedding
        try:
            embedding = await self.embedding_service.embed_text(text)
            logger.info(
                f"Generated embedding for concept {concept.concept_id} "
                f"with dimension {len(embedding)}"
            )
            return embedding, text
        except Exception as e:
            logger.error(
                f"Failed to generate embedding for concept {concept.concept_id}: {e}"
            )
            raise

    async def vectorize_business_concepts_batch(
        self,
        concepts: list[BusinessConceptMaster],
        batch_size: int | None = None,
    ) -> list[tuple[BusinessConceptMaster, np.ndarray, str]]:
        """Vectorize multiple business concepts in batches.

        Args:
            concepts: List of business concepts to vectorize.
            batch_size: Number of concepts to process per batch (defaults to settings).

        Returns:
            List of tuples (concept, embedding, prepared_text).
        """
        if not concepts:
            return []

        # Use configured batch size if not provided
        effective_batch_size = batch_size or self.qwen_settings.qwen_max_batch_size

        # Prepare all texts
        prepared_data = []
        texts_to_embed = []

        for concept in concepts:
            description = concept.concept_details.get("description")
            text = self.prepare_text_for_embedding(concept.concept_name, description)
            prepared_data.append((concept, text))
            texts_to_embed.append(text)

        # Generate embeddings in batches
        try:
            embeddings = await self.embedding_service.embed_texts(
                texts_to_embed, batch_size=effective_batch_size
            )

            # Combine results
            results = []
            for (concept, text), embedding in zip(
                prepared_data, embeddings, strict=False
            ):
                if text:  # Only add if text is not empty
                    results.append((concept, embedding, text))
                else:
                    # Handle empty text case
                    dimension = self.embedding_service.get_embedding_dimension()
                    results.append((concept, np.zeros(dimension), text))

            logger.info(f"Successfully vectorized {len(results)} business concepts")
            return results

        except Exception as e:
            logger.error(f"Failed to vectorize batch of {len(concepts)} concepts: {e}")
            raise

    async def vectorize_with_metadata(
        self,
        concepts: list[BusinessConceptMaster],
        batch_size: int | None = None,
    ) -> list[EmbeddingResult]:
        """Vectorize concepts with metadata for tracking.

        Args:
            concepts: List of business concepts to vectorize.
            batch_size: Number of concepts to process per batch (defaults to settings).

        Returns:
            List of EmbeddingResult objects with metadata.
        """
        if not concepts:
            return []

        # Use configured batch size if not provided
        effective_batch_size = batch_size or self.qwen_settings.qwen_max_batch_size

        # Prepare embedding requests with metadata
        requests = []
        for concept in concepts:
            description = concept.concept_details.get("description")
            text = self.prepare_text_for_embedding(concept.concept_name, description)
            metadata = {
                "concept_id": str(concept.concept_id),
                "concept_name": concept.concept_name,
                "has_description": bool(description),
                "source": concept.concept_details.get("source", ""),
            }
            requests.append(EmbeddingRequest(text=text, metadata=metadata))

        # Generate embeddings with metadata
        try:
            results = await self.embedding_service.embed_texts_with_metadata(
                requests, batch_size=effective_batch_size
            )
            logger.info(
                f"Successfully vectorized {len(results)} concepts with metadata"
            )
            return results
        except Exception as e:
            logger.error(f"Failed to vectorize concepts with metadata: {e}")
            raise

    def get_embedding_info(self) -> dict[str, Any]:
        """Get information about the embedding service.

        Returns:
            Dictionary with embedding service information.
        """
        return {
            "model_name": self.embedding_service.get_model_name(),
            "embedding_dimension": self.embedding_service.get_embedding_dimension(),
            "max_text_length": self.max_text_length,
        }
