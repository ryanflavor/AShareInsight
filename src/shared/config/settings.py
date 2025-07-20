"""Application settings and configuration management."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM-specific settings."""

    gemini_base_url: str = "https://apius.tu-zi.com"
    gemini_api_key: str = ""
    gemini_model_name: str = "gemini-2.5-pro-preview-06-05"
    gemini_max_tokens: int = 30000
    gemini_temperature: float = 1.0
    gemini_timeout: int = 180  # 3 minutes
    gemini_max_retries: int = 3

    # Batch processing settings
    batch_size: int = 10  # Number of concurrent LLM calls
    rate_limit_per_minute: int = 30  # API rate limit
    connection_pool_size: int = 20  # Connection pool for HTTP clients
    max_workers: int = 5  # Thread pool size for concurrent processing

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


class DatabaseSettings(BaseSettings):
    """Database-specific settings."""

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ashareinsight"
    postgres_user: str = "postgres"
    postgres_password: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )

    @property
    def database_url(self) -> str:
        """Construct database URL from components."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class MonitoringSettings(BaseSettings):
    """Monitoring and observability settings."""

    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "ashareinsight"
    log_level: str = "INFO"

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
    database: DatabaseSettings = DatabaseSettings()
    monitoring: MonitoringSettings = MonitoringSettings()

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
