"""Application settings and configuration management."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM-specific settings."""

    gemini_base_url: str = "https://apius.tu-zi.com"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model_name: str = "gemini-2.5-pro-preview-06-05"
    gemini_max_tokens: int = 30000
    gemini_temperature: float = 1.0
    gemini_timeout: int = 180  # 3 minutes
    gemini_max_retries: int = 3

    # Retry logic settings
    gemini_retry_multiplier: int = 1
    gemini_retry_wait_min: int = 60  # seconds
    gemini_retry_wait_max: int = 180  # seconds

    # Default text constants
    default_company_name: str = "未知公司"
    default_annual_report_type: str = "年度报告"
    default_research_report_type: str = "研究报告"

    # HTTP connection settings
    http_keepalive_expiry: float = 30.0  # seconds
    http_connect_timeout: float = 10.0  # seconds
    http_write_timeout: float = 10.0  # seconds

    # Batch processing settings
    batch_size: int = 10  # Number of concurrent LLM calls
    rate_limit_per_minute: int = 30  # API rate limit
    connection_pool_size: int = 20  # Connection pool for HTTP clients
    max_workers: int = 5  # Thread pool size for concurrent processing

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class QwenEmbeddingSettings(BaseSettings):
    """Qwen embedding service settings."""

    qwen_base_url: str = "http://localhost:9547"
    qwen_model_name: str = "Qwen3-Embedding-4B"
    qwen_timeout: int = 300  # 5 minutes
    qwen_max_batch_size: int = 50
    qwen_normalize: bool = True
    qwen_max_retries: int = 3
    qwen_retry_wait_min: int = 1  # seconds
    qwen_retry_wait_max: int = 10  # seconds
    qwen_embedding_dimension: int = 2560

    # Text processing settings
    qwen_max_text_length: int = 8000  # token limit
    qwen_similarity_threshold: float = 0.7
    qwen_length_ratio_min: float = 0.9
    qwen_length_ratio_max: float = 1.1

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class DatabaseSettings(BaseSettings):
    """Database-specific settings."""

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ashareinsight_db"
    postgres_user: str = "ashareinsight"
    postgres_password: SecretStr = SecretStr("ashareinsight_password")

    # Connection pool settings
    db_pool_min_size: int = Field(default=5)
    db_pool_max_size: int = Field(default=20)
    db_pool_timeout: float = Field(default=30.0)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )

    @property
    def database_url(self) -> str:
        """Construct database URL from components.

        Note: This returns a sync URL. For async operations, use postgres_dsn instead.
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn(self) -> str:
        """Get PostgreSQL connection string for async."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """Get synchronous PostgreSQL connection string."""
        return self.database_url

    @property
    def async_database_url(self) -> str:
        """Get async database URL. Alias for postgres_dsn for clarity."""
        return self.postgres_dsn


class MonitoringSettings(BaseSettings):
    """Monitoring and observability settings."""

    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "ashareinsight"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class FusionSettings(BaseSettings):
    """Data fusion-specific settings."""

    # Batch processing
    fusion_batch_size: int = 50  # Number of concepts to process per batch
    fusion_batch_delay_seconds: float = 0.1  # Delay between batches

    # Retry logic
    fusion_max_retries: int = 3  # Max retries for optimistic lock conflicts
    fusion_retry_base_delay: float = 0.1  # Base delay for retry backoff

    # Business concept limits
    max_source_sentences: int = 20  # Maximum source sentences to keep

    # Business concept categories (comma-separated)
    allowed_concept_categories: str = "核心业务,新兴业务,战略布局"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )

    @property
    def concept_categories_set(self) -> set[str]:
        """Get allowed concept categories as a set."""
        return {cat.strip() for cat in self.allowed_concept_categories.split(",")}


class APISettings(BaseSettings):
    """API-specific settings."""

    # API settings
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    # Search settings
    default_similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    default_top_k: int = Field(default=50, ge=1, le=200)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class RerankerSettings(BaseSettings):
    """Reranker service settings."""

    # Reranker settings
    reranker_enabled: bool = Field(default=False)
    reranker_service_url: str = Field(default="http://localhost:9547")
    reranker_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    reranker_max_retries: int = Field(default=2, ge=0, le=5)
    reranker_retry_backoff: float = Field(default=0.5, ge=0.1, le=5.0)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class CacheSettings(BaseSettings):
    """Cache settings."""

    # Redis settings (for future caching)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class Settings(BaseSettings):
    """Main application settings."""

    # Application metadata
    app_name: str = "AShareInsight"
    app_version: str = "1.0.0"
    environment: str = "development"

    # Sub-settings
    llm: LLMSettings = LLMSettings()
    qwen_embedding: QwenEmbeddingSettings = QwenEmbeddingSettings()
    database: DatabaseSettings = DatabaseSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    fusion: FusionSettings = FusionSettings()
    api: APISettings = APISettings()
    reranker: RerankerSettings = RerankerSettings()
    cache: CacheSettings = CacheSettings()

    # Feature flags
    debug_mode: bool = False

    # Batch processing settings
    batch_checkpoint_interval: int = 100  # Save progress every N files
    batch_error_threshold: float = 0.1  # Stop if error rate > 10%
    batch_resume_enabled: bool = True  # Enable resuming from checkpoint

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings instance with all configuration loaded.
    """
    return Settings()


# Global settings instance for convenience
settings = get_settings()
