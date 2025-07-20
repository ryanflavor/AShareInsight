"""Gemini API adapter for OpenAI-compatible format."""

import asyncio
import time
from typing import Any

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from openai import APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

from src.infrastructure.llm.langchain.base import LangChainBase, LangChainConfig
from src.shared.exceptions import LLMServiceError


class GeminiAdapter(LangChainBase):
    """Adapter for Gemini API using OpenAI-compatible format."""

    def __init__(self, config: LangChainConfig | None = None):
        """Initialize Gemini adapter.

        Args:
            config: Optional configuration object.
        """
        super().__init__(config)
        self.llm = self.get_llm()

    @retry(
        retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=60, max=180),
    )
    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        """Invoke Gemini model with retry logic.

        Args:
            messages: List of messages to send to the model.
            **kwargs: Additional arguments passed to the model.

        Returns:
            ChatResult containing the model response.

        Raises:
            LLMServiceError: If the request fails after all retries.
        """
        start_time = time.time()

        try:
            # Merge kwargs with default config
            invoke_kwargs = {
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                **kwargs,
            }

            try:
                result = self.llm.invoke(messages, **invoke_kwargs)
            except AttributeError as ae:
                # Handle case where API returns raw string instead of proper format
                if "'str' object has no attribute 'model_dump'" in str(ae):
                    # Try alternative approach - use raw API call
                    from langchain_core.messages import AIMessage

                    # Convert messages to OpenAI format
                    messages_dict = [
                        {
                            "role": (
                                "system"
                                if m.__class__.__name__ == "SystemMessage"
                                else "user"
                            ),
                            "content": m.content,
                        }
                        for m in messages
                    ]

                    # Make raw API call using httpx
                    import httpx

                    client = httpx.Client()
                    response = client.post(
                        f"{self.config.base_url}/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.config.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.config.model_name,
                            "messages": messages_dict,
                            "max_tokens": self.config.max_tokens,
                            "temperature": self.config.temperature,
                        },
                        timeout=self.config.timeout,
                    )
                    response.raise_for_status()

                    # Extract content from response
                    logger.debug(f"Raw API response status: {response.status_code}")
                    logger.debug(f"Raw API response headers: {response.headers}")
                    logger.debug(
                        f"Raw API response text: {response.text[:500]}"
                    )  # First 500 chars

                    response_json = response.json()
                    content = response_json["choices"][0]["message"]["content"]

                    # Extract token usage if available
                    usage = response_json.get("usage", {})

                    # Return as AIMessage with usage metadata
                    result = AIMessage(
                        content=content,
                        additional_kwargs={
                            "usage": {
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }
                        },
                    )
                    client.close()
                else:
                    raise

            elapsed_time = time.time() - start_time

            # Log metadata (will be enhanced with proper logging later)
            self._log_invocation_metadata(
                model=self.config.model_name, elapsed_time=elapsed_time, success=True
            )

            # Convert BaseMessage to ChatResult
            if isinstance(result, BaseMessage):
                generation = ChatGeneration(message=result)
                return ChatResult(generations=[generation])
            return result

        except (APITimeoutError, RateLimitError):
            # These will be retried by tenacity
            raise
        except Exception as e:
            import traceback

            elapsed_time = time.time() - start_time
            self._log_invocation_metadata(
                model=self.config.model_name,
                elapsed_time=elapsed_time,
                success=False,
                error=str(e),
            )
            # Log full traceback for debugging
            logger.error(
                "Failed to invoke Gemini model",
                error=str(e),
                traceback=traceback.format_exc(),
            )
            raise LLMServiceError(f"Failed to invoke Gemini model: {str(e)}")

    async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        """Async invoke Gemini model with retry logic.

        Args:
            messages: List of messages to send to the model.
            **kwargs: Additional arguments passed to the model.

        Returns:
            ChatResult containing the model response.

        Raises:
            LLMServiceError: If the request fails after all retries.
        """
        # Native async implementation would require async LLM client
        # For now, wrap the sync method
        loop = asyncio.get_event_loop()
        # Use lambda to properly handle kwargs
        return await loop.run_in_executor(None, lambda: self.invoke(messages, **kwargs))

    def stream(self, messages: list[BaseMessage], **kwargs: Any):
        """Stream responses from Gemini model.

        Args:
            messages: List of messages to send to the model.
            **kwargs: Additional arguments passed to the model.

        Yields:
            Chunks of the response as they become available.

        Raises:
            LLMServiceError: If the request fails.
        """
        try:
            # Merge kwargs with default config
            stream_kwargs = {
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "stream": True,
                **kwargs,
            }

            yield from self.llm.stream(messages, **stream_kwargs)

        except Exception as e:
            logger.error("Failed to stream from Gemini model", error=str(e))
            raise LLMServiceError(f"Failed to stream from Gemini model: {str(e)}")

    def _log_invocation_metadata(
        self, model: str, elapsed_time: float, success: bool, error: str | None = None
    ) -> None:
        """Log invocation metadata.

        This is a placeholder that will be enhanced with proper
        structured logging and OpenTelemetry integration.

        Args:
            model: Model name used.
            elapsed_time: Time taken for the invocation.
            success: Whether the invocation was successful.
            error: Error message if failed.
        """
        logger.debug(
            "LLM invocation completed",
            model=model,
            elapsed_time_seconds=elapsed_time,
            success=success,
            error=error,
        )

    def get_model_info(self) -> dict[str, Any]:
        """Get information about the configured model.

        Returns:
            Dictionary containing model configuration.
        """
        return {
            "model_name": self.config.model_name,
            "base_url": self.config.base_url,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "timeout": self.config.timeout,
            "max_retries": self.config.max_retries,
        }
