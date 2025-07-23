"""Base parser for LLM outputs with Markdown extraction support."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, ValidationError

from src.shared.exceptions import LLMServiceError

T = TypeVar("T", bound=BaseModel)


class MarkdownExtractor:
    """Utility to extract JSON from Markdown code blocks."""

    @staticmethod
    def extract_json_from_text(text: str) -> str:
        """Extract JSON from text, handling Markdown code blocks.

        Args:
            text: Raw text that may contain JSON in various formats.

        Returns:
            Extracted JSON string.

        Raises:
            LLMServiceError: If no valid JSON can be extracted.
        """
        # First, check if there's a <think> section and skip it
        think_end = text.find("</think>")
        if think_end != -1:
            # Use only the text after the thinking section
            text = text[think_end + len("</think>") :]

        # First, try to find JSON in markdown code blocks
        # Pattern matches ```json or ```JSON followed by content and closing ```
        # Note: Allow optional whitespace after json/JSON and handle different newline formats
        json_block_pattern = r"```(?:json|JSON)\s*[\r\n]*([\s\S]*?)[\r\n]*```"
        matches = re.findall(json_block_pattern, text)

        # If no complete markdown blocks found, check for incomplete ones (missing closing ```)
        if not matches:
            incomplete_pattern = r"```(?:json|JSON)\s*[\r\n]*([\s\S]*?)$"
            incomplete_matches = re.findall(incomplete_pattern, text)
            if incomplete_matches:
                matches = incomplete_matches

        if matches:
            # If multiple JSON blocks found, return the one with the most top-level keys
            # This helps avoid returning partial/incomplete JSON blocks
            best_match = None
            max_keys = 0

            for match in matches:
                try:
                    # Clean up common JSON formatting issues
                    cleaned_match = match.strip()
                    # Fix issue where there might be extra space before a key
                    cleaned_match = re.sub(r'"\s+"(\w+)":', r'"\1":', cleaned_match)

                    parsed = json.loads(cleaned_match)
                    if isinstance(parsed, dict):
                        num_keys = len(parsed.keys())
                        if num_keys > max_keys:
                            max_keys = num_keys
                            best_match = cleaned_match
                except json.JSONDecodeError:
                    continue

            if best_match:
                return best_match
            # Fallback to first match if none could be parsed
            return matches[0].strip()

        # If no markdown block, try to find raw JSON
        # Look for content between outermost { }
        json_pattern = r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})"
        json_matches = re.findall(json_pattern, text, re.DOTALL)

        if json_matches:
            # Return the largest match (likely the complete JSON)
            return max(json_matches, key=len).strip()

        # If still no match, check if the entire text is valid JSON
        try:
            json.loads(text)
            return text.strip()
        except json.JSONDecodeError:
            pass

        raise LLMServiceError(
            "No valid JSON found in the response. "
            "Expected JSON in markdown code block or raw JSON format."
        )


class BaseOutputParser[T: BaseModel](ABC):
    """Base class for parsing LLM outputs with Pydantic validation."""

    def __init__(self, pydantic_model: type[T]):
        """Initialize parser with a Pydantic model.

        Args:
            pydantic_model: The Pydantic model class to validate against.
        """
        self.pydantic_model = pydantic_model
        self.pydantic_parser = PydanticOutputParser(pydantic_object=pydantic_model)
        self.markdown_extractor = MarkdownExtractor()

    @abstractmethod
    def get_format_instructions(self) -> str:
        """Get format instructions for the prompt.

        Returns:
            Instructions to include in the prompt.
        """
        pass

    def parse(self, text: str) -> T:
        """Parse LLM output text into validated Pydantic model.

        Args:
            text: Raw LLM output text.

        Returns:
            Validated Pydantic model instance.

        Raises:
            LLMServiceError: If parsing or validation fails.
        """
        try:
            # Extract JSON from the text
            json_str = self.markdown_extractor.extract_json_from_text(text)

            # Parse JSON string
            json_data = json.loads(json_str)

            # Validate with Pydantic
            return self.pydantic_model(**json_data)

        except json.JSONDecodeError as e:
            raise LLMServiceError(
                f"Failed to parse JSON: {str(e)}. "
                f"Extracted content: {json_str[:200]}..."
            ) from e
        except ValidationError as e:
            raise LLMServiceError(
                f"Validation failed: {str(e)}. "
                "The JSON structure doesn't match the expected schema."
            ) from e
        except Exception as e:
            raise LLMServiceError(f"Unexpected error during parsing: {str(e)}") from e

    def parse_with_fallback(
        self, text: str, fallback_value: Any | None = None
    ) -> tuple[T | None, str | None]:
        """Parse with fallback on error.

        Args:
            text: Raw LLM output text.
            fallback_value: Value to return if parsing fails.

        Returns:
            Tuple of (parsed_model or fallback, error_message or None).
        """
        try:
            return self.parse(text), None
        except LLMServiceError as e:
            return fallback_value, str(e)

    def get_json_schema(self) -> dict[str, Any]:
        """Get the JSON schema of the Pydantic model.

        Returns:
            JSON schema dictionary.
        """
        return self.pydantic_model.model_json_schema()
