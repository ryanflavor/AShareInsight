"""Base LangChain integration module for LLM services."""

import httpx
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.shared.config.settings import get_settings


class LangChainConfig(BaseModel):
    """Configuration for LangChain LLM services."""

    base_url: str = Field(default_factory=lambda: get_settings().llm.gemini_base_url)
    api_key: str = Field(default_factory=lambda: get_settings().llm.gemini_api_key)
    model_name: str = Field(
        default_factory=lambda: get_settings().llm.gemini_model_name
    )
    max_tokens: int = Field(
        default_factory=lambda: get_settings().llm.gemini_max_tokens
    )
    temperature: float = Field(
        default_factory=lambda: get_settings().llm.gemini_temperature
    )
    timeout: int = Field(default_factory=lambda: get_settings().llm.gemini_timeout)
    max_retries: int = Field(
        default_factory=lambda: get_settings().llm.gemini_max_retries
    )
    retry_delay: int = Field(default=60)  # 60 seconds between retries


class LangChainBase:
    """Base class for LangChain integrations."""

    def __init__(self, config: LangChainConfig | None = None):
        """Initialize LangChain base with configuration.

        Args:
            config: Optional configuration object. If not provided, uses defaults.
        """
        self.config = config or LangChainConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate configuration values."""
        if not self.config.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is required but not set"
            )
        if not self.config.base_url:
            raise ValueError(
                "GEMINI_BASE_URL environment variable is required but not set"
            )

    def get_llm(self) -> ChatOpenAI:
        """Get configured LLM instance with connection pooling.

        Returns:
            Configured ChatOpenAI instance with Gemini settings and connection pool.
        """
        # Configure HTTP client with connection pooling
        http_client = httpx.Client(
            limits=httpx.Limits(
                max_keepalive_connections=get_settings().llm.connection_pool_size,
                max_connections=get_settings().llm.connection_pool_size * 2,
                keepalive_expiry=30.0,  # Keep connections alive for 30 seconds
            ),
            timeout=httpx.Timeout(
                timeout=float(self.config.timeout),
                connect=10.0,  # Connection timeout
                read=float(self.config.timeout),  # Read timeout
                write=10.0,  # Write timeout
            ),
        )

        return ChatOpenAI(
            base_url=f"{self.config.base_url}/v1",
            api_key=self.config.api_key,
            model=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            http_client=http_client,
        )
