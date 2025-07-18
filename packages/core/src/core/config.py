"""
Configuration module for AShareInsight core services.

Provides centralized configuration management for database connections,
embedding services, and other core components.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    """Database configuration settings."""

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    database: str = Field(default="ashareinsight", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: str = Field(default="test123", description="Database password")
    min_pool_size: int = Field(default=2, description="Minimum connection pool size")
    max_pool_size: int = Field(default=10, description="Maximum connection pool size")

    @property
    def connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def sqlalchemy_url(self) -> str:
        """Generate SQLAlchemy connection URL with psycopg driver."""
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class EmbeddingServiceConfig(BaseModel):
    """Qwen embedding service configuration."""

    base_url: str = Field(
        default="http://localhost:9547",
        description="Base URL of the Qwen embedding service",
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retry attempts")
    embedding_dimension: int = Field(
        default=2560, description="Dimension of embedding vectors"
    )
    batch_size: int = Field(
        default=64, description="Default batch size for embedding generation"
    )
    normalize: bool = Field(
        default=True, description="Whether to normalize embeddings by default"
    )

    @field_validator("embedding_dimension")
    @classmethod
    def validate_dimension(cls, v: int) -> int:
        """Ensure embedding dimension matches Qwen model output."""
        if v != 2560:
            raise ValueError(
                "Embedding dimension must be 2560 for Qwen3-Embedding-4B model"
            )
        return v


class LoggingConfig(BaseModel):
    """Logging configuration settings."""

    level: str = Field(default="INFO", description="Logging level")
    format: str = Field(default="json", description="Log format (json or text)")
    output_file: str | None = Field(default=None, description="Optional log file path")


class Settings(BaseSettings):
    """
    Main settings class that aggregates all configuration.

    Uses pydantic-settings to load from environment variables.
    Environment variables should be prefixed with ASHARE_.
    """

    # Sub-configurations
    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig,
        description="Database configuration",
    )
    embedding_service: EmbeddingServiceConfig = Field(
        default_factory=EmbeddingServiceConfig,
        description="Embedding service configuration",
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration",
    )

    # Application settings
    app_name: str = Field(default="AShareInsight", description="Application name")
    environment: str = Field(
        default="development",
        description="Environment (development, staging, production)",
    )
    debug: bool = Field(default=False, description="Debug mode")

    model_config = SettingsConfigDict(
        env_prefix="ASHARE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        """
        Create settings from environment variables.

        Environment variable examples:
        - ASHARE_DATABASE__HOST=localhost
        - ASHARE_DATABASE__PORT=5432
        - ASHARE_EMBEDDING_SERVICE__BASE_URL=http://localhost:9547
        """
        return cls()

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary."""
        return self.model_dump()


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get or create global settings instance.

    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """Reset global settings (useful for testing)."""
    global _settings
    _settings = None
