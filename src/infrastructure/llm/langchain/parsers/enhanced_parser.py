"""Enhanced parser with logging and error handling."""

import json
import time
from typing import Any

import structlog
from pydantic import BaseModel

from src.shared.exceptions import LLMServiceError

logger = structlog.get_logger(__name__)

from .base import BaseOutputParser, T


class ParsingMetrics(BaseModel):
    """Metrics collected during parsing."""

    extraction_time_ms: float
    json_length: int
    validation_passed: bool
    error_message: str | None = None


class EnhancedOutputParser(BaseOutputParser[T]):
    """Enhanced parser with comprehensive logging and metrics."""

    def __init__(self, pydantic_model: type[T], parser_name: str = ""):
        """Initialize enhanced parser.

        Args:
            pydantic_model: The Pydantic model class to validate against.
            parser_name: Name for logging purposes.
        """
        super().__init__(pydantic_model)
        self.parser_name = parser_name or pydantic_model.__name__

    def get_format_instructions(self) -> str:
        """Get format instructions including schema info."""
        schema = self.get_json_schema()
        return (
            f"Output must be valid JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2, ensure_ascii=False)}\n\n"
            "Important:\n"
            "- All numeric fields must be numbers, not strings\n"
            "- Use null for missing values, not empty strings\n"
            "- Arrays must be valid JSON arrays\n"
            "- Wrap the JSON in ```json ... ``` code blocks"
        )

    def parse_with_metrics(self, text: str) -> tuple[T, ParsingMetrics]:
        """Parse with detailed metrics collection.

        Args:
            text: Raw LLM output text.

        Returns:
            Tuple of (parsed model, metrics).

        Raises:
            LLMServiceError: If parsing fails.
        """
        start_time = time.time()
        metrics = ParsingMetrics(
            extraction_time_ms=0, json_length=0, validation_passed=False
        )

        try:
            # Extract JSON
            json_str = self.markdown_extractor.extract_json_from_text(text)
            metrics.json_length = len(json_str)

            # Parse and validate
            result = self.parse(text)

            # Update metrics
            metrics.validation_passed = True
            metrics.extraction_time_ms = (time.time() - start_time) * 1000

            # Log success
            self._log_parsing_success(metrics)

            return result, metrics

        except LLMServiceError as e:
            # Update metrics
            metrics.extraction_time_ms = (time.time() - start_time) * 1000
            metrics.error_message = str(e)

            # Log failure
            self._log_parsing_failure(text, metrics)

            raise

    def parse_with_retry(self, text: str, max_attempts: int = 2) -> T:
        """Parse with retry logic for recoverable errors.

        Args:
            text: Raw LLM output text.
            max_attempts: Maximum number of parse attempts.

        Returns:
            Validated model instance.

        Raises:
            LLMServiceError: If all attempts fail.
        """
        last_error = None

        for attempt in range(max_attempts):
            try:
                result, _ = self.parse_with_metrics(text)
                return result
            except LLMServiceError as e:
                last_error = e

                # Try to fix common issues
                if attempt < max_attempts - 1:
                    text = self._attempt_fix(text, str(e))

        raise last_error or LLMServiceError("Failed to parse after retries")

    def _attempt_fix(self, text: str, error_msg: str) -> str:
        """Attempt to fix common parsing issues.

        Args:
            text: Original text that failed to parse.
            error_msg: Error message from failed attempt.

        Returns:
            Potentially fixed text.
        """
        # If JSON extraction failed, try to add code block markers
        if "No valid JSON found" in error_msg:
            # Find potential JSON and wrap it
            import re

            json_pattern = r"(\{[\s\S]*\})"
            match = re.search(json_pattern, text)
            if match:
                return f"```json\n{match.group(1)}\n```"

        # If validation failed due to string numbers, try to fix
        if "type=type_error" in error_msg and "number" in error_msg:
            try:
                # Extract JSON and fix string numbers
                json_str = self.markdown_extractor.extract_json_from_text(text)
                data = json.loads(json_str)
                fixed_data = self._fix_numeric_strings(data)
                fixed_json = json.dumps(fixed_data, ensure_ascii=False, indent=2)
                return f"```json\n{fixed_json}\n```"
            except:
                pass

        return text

    def _fix_numeric_strings(self, data: Any, parent_key: str = "") -> Any:
        """Recursively convert numeric strings to numbers."""
        if isinstance(data, dict):
            return {
                k: self._fix_numeric_strings(v, parent_key=k) for k, v in data.items()
            }
        elif isinstance(data, list):
            return [
                self._fix_numeric_strings(item, parent_key=parent_key) for item in data
            ]
        elif isinstance(data, str):
            # Skip empty strings
            if not data.strip():
                return data

            # Special handling: profit_forecast values should remain as strings
            if parent_key == "value" and "forecast" in str(data):
                return data

            # Special handling: don't convert values in profit_forecast or valuation
            if parent_key in ["value", "yoy_growth"]:
                return data

            # Try to extract numeric value from common patterns
            import re

            # Handle percentage strings like "150%", "超过60%"
            percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", data)
            if percent_match:
                return float(percent_match.group(1))

            # Handle "超过", "约", etc. prefixes
            approx_match = re.search(
                r"(?:超过|约|大于|小于|不低于|不超过)?\s*(\d+(?:\.\d+)?)", data
            )
            if approx_match:
                return float(approx_match.group(1))

            # Handle numbers with units like "1.25亿美元", "6200万元"
            unit_match = re.search(
                r"(\d+(?:\.\d+)?)\s*(亿|万|千|百万|million|billion)", data
            )
            if unit_match:
                num = float(unit_match.group(1))
                unit = unit_match.group(2)
                multipliers = {
                    "万": 10000,
                    "亿": 100000000,
                    "千": 1000,
                    "百万": 1000000,
                    "million": 1000000,
                    "billion": 1000000000,
                }
                if unit in multipliers:
                    return num * multipliers[unit]

            # Try simple conversion
            try:
                if "." in data:
                    return float(data)
                else:
                    return int(data)
            except ValueError:
                return data
        else:
            return data

    def _log_parsing_success(self, metrics: ParsingMetrics) -> None:
        """Log successful parsing."""
        logger.info(
            "Parsing successful",
            parser_name=self.parser_name,
            extraction_time_ms=metrics.extraction_time_ms,
            json_length=metrics.json_length,
            validation_passed=metrics.validation_passed,
        )

    def _log_parsing_failure(self, text: str, metrics: ParsingMetrics) -> None:
        """Log parsing failure."""
        logger.error(
            "Parsing failed",
            parser_name=self.parser_name,
            extraction_time_ms=metrics.extraction_time_ms,
            json_length=metrics.json_length,
            validation_passed=metrics.validation_passed,
            error_message=metrics.error_message,
            input_preview=text[:500],
        )
