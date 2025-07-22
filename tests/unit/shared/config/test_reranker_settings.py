"""Unit tests for reranker configuration settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.shared.config.settings import Settings


class TestRerankerSettings:
    """Test cases for reranker configuration in Settings."""

    def test_default_reranker_settings(self):
        """Test default reranker settings."""
        settings = Settings()

        # Verify defaults for HTTP service
        assert settings.reranker.reranker_enabled is True
        assert settings.reranker.reranker_service_url == "http://localhost:9547"
        assert settings.reranker.reranker_timeout_seconds == 5.0
        assert settings.reranker.reranker_max_retries == 2
        assert settings.reranker.reranker_retry_backoff == 0.5

    def test_reranker_settings_from_env(self):
        """Test reranker settings loaded from environment variables."""
        # For nested settings, we need to create new instances after env vars are set
        with patch.dict(
            os.environ,
            {
                "RERANKER_ENABLED": "false",
                "RERANKER_SERVICE_URL": "http://custom-service:8080",
                "RERANKER_TIMEOUT_SECONDS": "10.0",
                "RERANKER_MAX_RETRIES": "3",
                "RERANKER_RETRY_BACKOFF": "1.0",
            },
            clear=True,
        ):
            # Create fresh instances to pick up env vars
            from src.shared.config.settings import RerankerSettings

            reranker_settings = RerankerSettings()

            # Verify environment overrides
            assert reranker_settings.reranker_enabled is False
            assert (
                reranker_settings.reranker_service_url == "http://custom-service:8080"
            )
            assert reranker_settings.reranker_timeout_seconds == 10.0
            assert reranker_settings.reranker_max_retries == 3
            assert reranker_settings.reranker_retry_backoff == 1.0

    def test_timeout_too_small(self):
        """Test validation error for timeout below minimum."""
        with patch.dict(os.environ, {"RERANKER_TIMEOUT_SECONDS": "0.05"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            with pytest.raises(ValidationError) as exc_info:
                RerankerSettings()

            errors = exc_info.value.errors()
            assert any(
                "reranker_timeout_seconds" in str(error["loc"])
                and "greater than or equal to 0.1" in str(error["msg"])
                for error in errors
            )

    def test_timeout_too_large(self):
        """Test validation error for timeout exceeding maximum."""
        with patch.dict(os.environ, {"RERANKER_TIMEOUT_SECONDS": "35.0"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            with pytest.raises(ValidationError) as exc_info:
                RerankerSettings()

            errors = exc_info.value.errors()
            assert any(
                "reranker_timeout_seconds" in str(error["loc"])
                and "less than or equal to 30" in str(error["msg"])
                for error in errors
            )

    def test_negative_retries(self):
        """Test validation error for negative retries."""
        with patch.dict(os.environ, {"RERANKER_MAX_RETRIES": "-1"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            with pytest.raises(ValidationError) as exc_info:
                RerankerSettings()

            errors = exc_info.value.errors()
            assert any(
                "reranker_max_retries" in str(error["loc"])
                and "greater than or equal to 0" in str(error["msg"])
                for error in errors
            )

    def test_retries_too_many(self):
        """Test validation error for too many retries."""
        with patch.dict(os.environ, {"RERANKER_MAX_RETRIES": "6"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            with pytest.raises(ValidationError) as exc_info:
                RerankerSettings()

            errors = exc_info.value.errors()
            assert any(
                "reranker_max_retries" in str(error["loc"])
                and "less than or equal to 5" in str(error["msg"])
                for error in errors
            )

    def test_retry_backoff_too_small(self):
        """Test validation error for retry backoff below minimum."""
        with patch.dict(os.environ, {"RERANKER_RETRY_BACKOFF": "0.05"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            with pytest.raises(ValidationError) as exc_info:
                RerankerSettings()

            errors = exc_info.value.errors()
            assert any(
                "reranker_retry_backoff" in str(error["loc"])
                and "greater than or equal to 0.1" in str(error["msg"])
                for error in errors
            )

    def test_retry_backoff_too_large(self):
        """Test validation error for retry backoff exceeding maximum."""
        with patch.dict(os.environ, {"RERANKER_RETRY_BACKOFF": "6.0"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            with pytest.raises(ValidationError) as exc_info:
                RerankerSettings()

            errors = exc_info.value.errors()
            assert any(
                "reranker_retry_backoff" in str(error["loc"])
                and "less than or equal to 5" in str(error["msg"])
                for error in errors
            )

    def test_boolean_parsing(self):
        """Test boolean parsing for reranker_enabled."""
        with patch.dict(os.environ, {"RERANKER_ENABLED": "yes"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            reranker_settings = RerankerSettings()
            # "yes" should be parsed as True by Pydantic
            assert reranker_settings.reranker_enabled is True

    def test_boolean_parsing_false(self):
        """Test boolean parsing for reranker_enabled with false value."""
        with patch.dict(os.environ, {"RERANKER_ENABLED": "0"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            reranker_settings = RerankerSettings()
            assert reranker_settings.reranker_enabled is False

    def test_reranker_integration_with_other_settings(self):
        """Test reranker settings don't interfere with other settings."""
        settings = Settings()

        # Verify other settings remain intact
        assert settings.database.postgres_user == "ashareinsight"
        assert settings.api.default_similarity_threshold == 0.7
        assert settings.api.default_top_k == 50

        # Verify reranker settings exist
        assert hasattr(settings.reranker, "reranker_enabled")
        assert hasattr(settings.reranker, "reranker_service_url")
        assert hasattr(settings.reranker, "reranker_timeout_seconds")
        assert hasattr(settings.reranker, "reranker_max_retries")
        assert hasattr(settings.reranker, "reranker_retry_backoff")

    def test_service_url_format(self):
        """Test that service URL can be any string format."""
        # This should not raise an error - URLs are validated at runtime
        with patch.dict(
            os.environ, {"RERANKER_SERVICE_URL": "invalid-url"}, clear=True
        ):
            from src.shared.config.settings import RerankerSettings

            reranker_settings = RerankerSettings()
            assert reranker_settings.reranker_service_url == "invalid-url"

    def test_reranker_disabled_by_default(self):
        """Test behavior when reranker is disabled."""
        with patch.dict(os.environ, {"RERANKER_ENABLED": "false"}, clear=True):
            from src.shared.config.settings import RerankerSettings

            reranker_settings = RerankerSettings()
            assert reranker_settings.reranker_enabled is False
            # Other settings should still be accessible
            assert reranker_settings.reranker_service_url == "http://localhost:9547"
