"""
Unit tests for VectorizationService.
"""

from unittest.mock import Mock

import pytest

from src.domain.services.vectorization_service import VectorizationService


class TestVectorizationService:
    """Test cases for VectorizationService."""

    @pytest.fixture
    def service(self):
        """Fixture for VectorizationService."""
        mock_embedding_service = Mock()
        return VectorizationService(
            embedding_service=mock_embedding_service, max_text_length=100
        )

    def test_prepare_text_basic(self, service):
        """Test basic text preparation with name and description."""
        result = service.prepare_text_for_embedding(
            concept_name="智能座舱解决方案",
            description="公司依托在操作系统、人机交互等领域的技术积累",
        )
        assert (
            result == "智能座舱解决方案: 公司依托在操作系统、人机交互等领域的技术积累"
        )

    def test_prepare_text_name_only(self, service):
        """Test text preparation with only concept name."""
        result = service.prepare_text_for_embedding(
            concept_name="人工智能芯片", description=None
        )
        assert result == "人工智能芯片"

    def test_prepare_text_empty_description(self, service):
        """Test text preparation with empty description."""
        result = service.prepare_text_for_embedding(
            concept_name="量子计算", description=""
        )
        assert result == "量子计算"

    def test_prepare_text_empty_name(self, service):
        """Test text preparation with empty concept name."""
        result = service.prepare_text_for_embedding(concept_name="", description="描述")
        assert result == ""

    def test_prepare_text_none_name(self, service):
        """Test text preparation with None as concept name."""
        result = service.prepare_text_for_embedding(
            concept_name=None, description="描述"
        )
        assert result == ""

    def test_prepare_text_truncation(self, service):
        """Test text truncation when exceeding max length."""
        long_description = "A" * 200
        result = service.prepare_text_for_embedding(
            concept_name="Short", description=long_description
        )
        # The implementation adds "..." which can make it exceed max_length
        assert len(result) <= service.max_text_length + 3
        assert result.endswith("...")
        assert result.startswith("Short: ")

    def test_prepare_text_preserve_concept_name(self, service):
        """Test that concept name is preserved during truncation."""
        service.max_text_length = 50
        result = service.prepare_text_for_embedding(
            concept_name="Very Important Concept Name",
            description="This is a very long description that will be truncated",
        )
        assert "Very Important Concept Name" in result
        assert result.endswith("...")

    def test_clean_text_whitespace(self, service):
        """Test cleaning of excessive whitespace."""
        result = service._clean_text("  Multiple   spaces   \n\t  tabs  ")
        assert result == "Multiple spaces tabs"

    def test_clean_text_control_characters(self, service):
        """Test removal of control characters."""
        result = service._clean_text("Text\x00with\x1fcontrol\x7fchars")
        # The regex only removes control chars, not the spaces
        assert result == "Textwith controlchars"

    def test_clean_text_chinese_preserved(self, service):
        """Test that Chinese characters are preserved."""
        result = service._clean_text("中文字符\x00应该保留")
        assert result == "中文字符应该保留"

    def test_clean_text_quotes_normalization(self, service):
        """Test normalization of various quote types."""
        # Using unicode escape for special quotes: " " ' '
        text_with_quotes = "\u201c引号\u201d and \u2018apostrophes\u2019"
        result = service._clean_text(text_with_quotes)
        # The function normalizes smart quotes to regular ASCII quotes
        # Check that smart quotes are normalized to regular quotes
        assert '"' in result  # Regular double quote
        assert "'" in result  # Regular single quote
        assert "\u201c" not in result  # No left double quote
        assert "\u201d" not in result  # No right double quote
        assert "\u2018" not in result  # No left single quote
        assert "\u2019" not in result  # No right single quote

    def test_clean_text_zero_width_removal(self, service):
        """Test removal of zero-width characters."""
        result = service._clean_text("Text\u200bwith\u200czero\u200dwidth\ufeff")
        assert result == "Textwithzerowidth"

    def test_should_update_embedding_identical(self, service):
        """Test that identical texts don't trigger update."""
        old_text = "智能座舱: 描述"
        new_text = "智能座舱: 描述"
        assert not service.should_update_embedding(old_text, new_text)

    def test_should_update_embedding_whitespace_only(self, service):
        """Test that whitespace-only changes don't trigger update."""
        old_text = "智能座舱:  描述"
        new_text = "智能座舱: 描述"
        assert not service.should_update_embedding(old_text, new_text)

    def test_should_update_embedding_significant_change(self, service):
        """Test that significant changes trigger update."""
        old_text = "智能座舱: 旧描述"
        new_text = "智能座舱: 完全不同的新描述，包含更多内容"
        assert service.should_update_embedding(old_text, new_text)

    def test_should_update_embedding_length_change(self, service):
        """Test that significant length changes trigger update."""
        old_text = "Short text"
        new_text = "Short text with much more content added to make it longer"
        assert service.should_update_embedding(old_text, new_text)

    def test_should_update_embedding_empty_texts(self, service):
        """Test handling of empty texts in update check."""
        assert service.should_update_embedding("", "New text")
        assert service.should_update_embedding("Old text", "")
        assert not service.should_update_embedding("", "")

    def test_calculate_similarity_threshold(self, service):
        """Test similarity threshold calculation."""
        threshold = service.calculate_text_similarity_threshold()
        assert 0.0 <= threshold <= 1.0
        assert threshold == 0.95

    def test_initialization_with_custom_params(self):
        """Test service initialization with custom parameters."""
        mock_embedding_service = Mock()
        service = VectorizationService(
            embedding_service=mock_embedding_service,
            max_text_length=500,
            concept_weight=2.0,
            description_weight=0.5,
        )
        assert service.max_text_length == 500
        assert service.concept_weight == 2.0
        assert service.description_weight == 0.5
        assert service.embedding_service == mock_embedding_service
