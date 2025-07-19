"""Configuration settings for AShareInsight application.

This module defines application settings using Pydantic Settings
for type safety and environment variable management.
"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings.

    Settings are loaded from environment variables with fallback to defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # PostgreSQL settings
    postgres_user: str = Field(default="ashareinsight")
    postgres_password: SecretStr = Field(default=SecretStr("ashareinsight_password"))
    postgres_db: str = Field(default="ashareinsight_db")
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)

    # Connection pool settings
    db_pool_min_size: int = Field(default=5)
    db_pool_max_size: int = Field(default=20)
    db_pool_timeout: float = Field(default=30.0)

    # Redis settings (for future caching)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)

    # API settings
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    # Search settings
    default_similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    default_top_k: int = Field(default=50, ge=1, le=100)

    # Reranker settings
    reranker_enabled: bool = Field(default=True)
    reranker_service_url: str = Field(default="http://localhost:9547")
    reranker_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30.0)
    reranker_max_retries: int = Field(default=2, ge=0, le=5)
    reranker_retry_backoff: float = Field(default=0.5, ge=0.1, le=5.0)

    @property
    def postgres_dsn(self) -> str:
        """Get PostgreSQL connection string."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """Get synchronous PostgreSQL connection string."""
        return (
            f"postgresql://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Global settings instance
settings = Settings()
