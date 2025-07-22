"""Base LangChain integration module for LLM services."""

import httpx

# Using OpenAI format for Gemini-compatible API
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from src.shared.config.settings import get_settings


class LangChainConfig(BaseModel):
    """Configuration for LangChain LLM services."""

    base_url: str = Field(default_factory=lambda: get_settings().llm.gemini_base_url)
    api_key: str = Field(
        default_factory=lambda: get_settings().llm.gemini_api_key.get_secret_value()
    )
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

    # Retry configuration
    retry_multiplier: int = Field(
        default_factory=lambda: get_settings().llm.gemini_retry_multiplier
    )
    retry_wait_min: int = Field(
        default_factory=lambda: get_settings().llm.gemini_retry_wait_min
    )
    retry_wait_max: int = Field(
        default_factory=lambda: get_settings().llm.gemini_retry_wait_max
    )


class LangChainBase:
    """Base class for LangChain integrations."""

    def __init__(self, config: LangChainConfig | None = None):
        """Initialize LangChain base with configuration.

        Args:
            config: Optional configuration object. If not provided, uses defaults.
        """
        self.config = config or LangChainConfig()
        self._validate_config()
        self._http_client: httpx.Client | None = None
        self._llm: ChatOpenAI | None = None

    def __del__(self):
        """Cleanup HTTP client on deletion."""
        if hasattr(self, "_http_client") and self._http_client:
            self._http_client.close()

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
        if self._llm is None:
            # Configure HTTP client with connection pooling (only once)
            if self._http_client is None:
                settings = get_settings()
                self._http_client = httpx.Client(
                    limits=httpx.Limits(
                        max_keepalive_connections=settings.llm.connection_pool_size,
                        max_connections=settings.llm.connection_pool_size * 2,
                        keepalive_expiry=settings.llm.http_keepalive_expiry,
                    ),
                    timeout=httpx.Timeout(
                        timeout=float(self.config.timeout),
                        connect=settings.llm.http_connect_timeout,
                        read=float(self.config.timeout),  # Read timeout
                        write=settings.llm.http_write_timeout,
                    ),
                )

            self._llm = ChatOpenAI(
                base_url=f"{self.config.base_url}/v1",
                api_key=SecretStr(self.config.api_key),
                model=self.config.model_name,
                temperature=self.config.temperature,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
                http_client=self._http_client,
            )

        return self._llm
