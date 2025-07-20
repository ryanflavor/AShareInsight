"""Unit tests for similarity calculator domain service.

This module tests the core ranking algorithm implementation.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.domain.services import RankingWeight, ScoredDocument, SimilarityCalculator
from src.domain.value_objects.document import Document


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    return [
        Document(
            concept_id=UUID("12345678-1234-5678-1234-567812345678"),
            company_code="000001",
            company_name="平安银行",
            concept_name="零售银行业务",
            concept_category="主营业务",
            importance_score=Decimal("0.8"),
            similarity_score=0.85,
            source_concept_id=UUID("87654321-4321-8765-4321-876543218765"),
        ),
        Document(
            concept_id=UUID("23456789-2345-6789-2345-678923456789"),
            company_code="600036",
            company_name="招商银行",
            concept_name="信用卡业务",
            concept_category="主营业务",
            importance_score=Decimal("0.6"),
            similarity_score=0.75,
            source_concept_id=UUID("87654321-4321-8765-4321-876543218765"),
        ),
        Document(
            concept_id=UUID("34567890-3456-7890-3456-789034567890"),
            company_code="000002",
            company_name="万科A",
            concept_name="住宅开发",
            concept_category="主营业务",
            importance_score=Decimal("0.9"),
            similarity_score=0.70,
            source_concept_id=UUID("87654321-4321-8765-4321-876543218765"),
        ),
    ]


@pytest.fixture
def similarity_calculator():
    """Create a similarity calculator instance."""
    return SimilarityCalculator()


class TestRankingWeight:
    """Test cases for RankingWeight model."""

    def test_default_weights(self):
        """Test default weight values."""
        weights = RankingWeight()
        assert weights.rerank_weight == 0.7
        assert weights.importance_weight == 0.3

    def test_custom_weights(self):
        """Test custom weight values."""
        weights = RankingWeight(rerank_weight=0.6, importance_weight=0.4)
        assert weights.rerank_weight == 0.6
        assert weights.importance_weight == 0.4

    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        # Valid sum
        weights = RankingWeight(rerank_weight=0.5, importance_weight=0.5)
        assert weights.rerank_weight + weights.importance_weight == 1.0

        # Invalid sum
        with pytest.raises(ValidationError) as exc_info:
            RankingWeight(rerank_weight=0.7, importance_weight=0.5)
        assert "Weights must sum to 1.0" in str(exc_info.value)

    def test_weights_with_floating_point_tolerance(self):
        """Test weights sum validation with floating point tolerance."""
        # Should accept small floating point errors
        weights = RankingWeight(rerank_weight=0.7, importance_weight=0.30000001)
        assert weights.rerank_weight == 0.7
        assert weights.importance_weight == 0.30000001

    def test_weights_out_of_range(self):
        """Test weight value range validation."""
        # Negative weight
        with pytest.raises(ValidationError):
            RankingWeight(rerank_weight=-0.1, importance_weight=1.1)

        # Weight > 1
        with pytest.raises(ValidationError):
            RankingWeight(rerank_weight=1.5, importance_weight=-0.5)


class TestSimilarityCalculator:
    """Test cases for SimilarityCalculator."""

    def test_calculate_with_rerank_scores(
        self, similarity_calculator, sample_documents
    ):
        """Test calculation with both rerank and importance scores."""
        rerank_scores = {
            "12345678-1234-5678-1234-567812345678": 0.9,
            "23456789-2345-6789-2345-678923456789": 0.7,
            "34567890-3456-7890-3456-789034567890": 0.5,
        }

        results = similarity_calculator.calculate_final_scores(
            documents=sample_documents,
            rerank_scores=rerank_scores,
        )

        # Check results structure
        assert len(results) == 3
        assert all(isinstance(r, ScoredDocument) for r in results)

        # Check sorting (descending by final score)
        assert results[0].final_score > results[1].final_score
        assert results[1].final_score > results[2].final_score

        # Check specific calculations (default weights: 0.7 * rerank + 0.3 * importance)
        # First document: 0.7 * 0.9 + 0.3 * 0.8 = 0.63 + 0.24 = 0.87
        assert abs(results[0].final_score - 0.87) < 0.001
        assert results[0].document.company_code == "000001"

    def test_calculate_without_rerank_scores(
        self, similarity_calculator, sample_documents
    ):
        """Test graceful degradation when no rerank scores available."""
        results = similarity_calculator.calculate_final_scores(
            documents=sample_documents,
            rerank_scores=None,
        )

        # Should use importance scores as final scores
        assert len(results) == 3

        # Check sorting by importance score
        assert results[0].document.importance_score == Decimal("0.9")  # 万科A
        assert results[1].document.importance_score == Decimal("0.8")  # 平安银行
        assert results[2].document.importance_score == Decimal("0.6")  # 招商银行

        # Final scores should equal importance scores
        assert results[0].final_score == 0.9
        assert results[1].final_score == 0.8
        assert results[2].final_score == 0.6

        # Rerank scores should be None
        assert all(r.rerank_score is None for r in results)

    def test_partial_rerank_scores(self, similarity_calculator, sample_documents):
        """Test when only some documents have rerank scores."""
        # Only provide rerank score for first document
        rerank_scores = {
            "12345678-1234-5678-1234-567812345678": 0.95,
        }

        results = similarity_calculator.calculate_final_scores(
            documents=sample_documents,
            rerank_scores=rerank_scores,
        )

        # First document should use weighted formula
        first_result = next(
            r
            for r in results
            if r.document.concept_id == UUID("12345678-1234-5678-1234-567812345678")
        )
        expected_score = 0.7 * 0.95 + 0.3 * 0.8  # 0.665 + 0.24 = 0.905
        assert abs(first_result.final_score - 0.905) < 0.001
        assert first_result.rerank_score == 0.95

        # Other documents should use importance score only
        other_results = [
            r
            for r in results
            if r.document.concept_id != UUID("12345678-1234-5678-1234-567812345678")
        ]
        for result in other_results:
            assert result.rerank_score is None
            assert result.final_score == float(result.document.importance_score)

    def test_custom_weights(self, similarity_calculator, sample_documents):
        """Test calculation with custom weight configuration."""
        rerank_scores = {
            "12345678-1234-5678-1234-567812345678": 0.9,
            "23456789-2345-6789-2345-678923456789": 0.7,
            "34567890-3456-7890-3456-789034567890": 0.5,
        }

        custom_weights = RankingWeight(rerank_weight=0.5, importance_weight=0.5)

        results = similarity_calculator.calculate_final_scores(
            documents=sample_documents,
            rerank_scores=rerank_scores,
            weights=custom_weights,
        )

        # Check calculation with 50/50 weights
        # First document: 0.5 * 0.9 + 0.5 * 0.8 = 0.45 + 0.4 = 0.85
        first = next(r for r in results if r.document.company_code == "000001")
        assert abs(first.final_score - 0.85) < 0.001

    def test_boundary_scores(self, similarity_calculator):
        """Test handling of boundary score values (0 and 1)."""
        documents = [
            Document(
                concept_id=UUID("12345678-1234-5678-1234-567812345678"),
                company_code="TEST01",
                company_name="Test Company 1",
                concept_name="Test Concept 1",
                importance_score=Decimal("0.0"),
                similarity_score=0.0,
            ),
            Document(
                concept_id=UUID("23456789-2345-6789-2345-678923456789"),
                company_code="TEST02",
                company_name="Test Company 2",
                concept_name="Test Concept 2",
                importance_score=Decimal("1.0"),
                similarity_score=1.0,
            ),
        ]

        rerank_scores = {
            "12345678-1234-5678-1234-567812345678": 0.0,
            "23456789-2345-6789-2345-678923456789": 1.0,
        }

        results = similarity_calculator.calculate_final_scores(
            documents=documents,
            rerank_scores=rerank_scores,
        )

        # Check minimum score
        assert results[1].final_score == 0.0
        assert results[1].document.company_code == "TEST01"

        # Check maximum score
        assert results[0].final_score == 1.0
        assert results[0].document.company_code == "TEST02"

    def test_invalid_importance_score(self, similarity_calculator):
        """Test validation of importance scores - Document model validates this."""
        # Document model should validate importance score at creation time
        with pytest.raises(ValidationError) as exc_info:
            Document(
                concept_id=UUID("12345678-1234-5678-1234-567812345678"),
                company_code="INVALID",
                company_name="Invalid Company",
                concept_name="Invalid Concept",
                importance_score=Decimal("1.5"),  # Invalid: > 1.0
                similarity_score=0.8,
            )

        assert "less than or equal to 1.0" in str(exc_info.value)

    def test_invalid_rerank_score(self, similarity_calculator, sample_documents):
        """Test validation of rerank scores."""
        # Provide invalid rerank score
        invalid_rerank_scores = {
            "12345678-1234-5678-1234-567812345678": 1.2,  # Invalid: > 1.0
        }

        with pytest.raises(ValueError) as exc_info:
            similarity_calculator.calculate_final_scores(
                documents=sample_documents,
                rerank_scores=invalid_rerank_scores,
            )

        assert "Invalid rerank score 1.2" in str(exc_info.value)
        assert "Must be in range [0, 1]" in str(exc_info.value)

    def test_empty_documents_list(self, similarity_calculator):
        """Test handling of empty documents list."""
        results = similarity_calculator.calculate_final_scores(
            documents=[],
            rerank_scores={},
        )

        assert results == []

    def test_result_ordering_stability(self, similarity_calculator):
        """Test that documents with same scores maintain stable ordering."""
        # Create documents with same importance scores
        documents = [
            Document(
                concept_id=UUID(f"12345678-1234-5678-1234-56781234567{i}"),
                company_code=f"00000{i}",
                company_name=f"Company {i}",
                concept_name="Same Concept",
                importance_score=Decimal("0.5"),
                similarity_score=0.5,
            )
            for i in range(5)
        ]

        results = similarity_calculator.calculate_final_scores(documents)

        # All should have same final score
        assert all(r.final_score == 0.5 for r in results)

        # Original order should be preserved for equal scores
        for i, result in enumerate(results):
            assert result.document.company_code == f"00000{i}"
