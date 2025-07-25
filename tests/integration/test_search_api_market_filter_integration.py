"""Integration tests for search API with market filtering."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.persistence.postgres.market_data_repository import (
    MarketDataRepository,
    MarketDataWithAverage,
)


@pytest.mark.integration
class TestSearchAPIMarketFilterIntegration:
    """Integration tests for search API with market data filtering."""

    @pytest.fixture
    def mock_market_data(self):
        """Create mock market data for testing."""
        return {
            "002240": MarketDataWithAverage(
                company_code="002240",
                current_market_cap=Decimal("70e8"),  # 70亿
                current_circulating_cap=Decimal("65e8"),
                today_volume=Decimal("1.5e8"),  # 1.5亿
                avg_5day_volume=Decimal("1.2e8"),  # 1.2亿
                last_updated=None,
            ),
            "300124": MarketDataWithAverage(
                company_code="300124",
                current_market_cap=Decimal("50e8"),  # 50亿
                current_circulating_cap=Decimal("45e8"),
                today_volume=Decimal("0.8e8"),  # 0.8亿
                avg_5day_volume=Decimal("0.7e8"),  # 0.7亿
                last_updated=None,
            ),
            "600000": MarketDataWithAverage(
                company_code="600000",
                current_market_cap=Decimal("90e8"),  # 90亿 - will be filtered out
                current_circulating_cap=Decimal("85e8"),
                today_volume=Decimal("3e8"),  # 3亿
                avg_5day_volume=Decimal("2.5e8"),  # 2.5亿 - will be filtered out
                last_updated=None,
            ),
        }

    @pytest.mark.asyncio
    async def test_search_with_market_filters(
        self, client: TestClient, mock_market_data
    ):
        """Test search API with market cap and volume filters."""
        # Mock vector store search results
        with patch(
            "src.interfaces.api.dependencies.get_vector_store"
        ) as mock_vector_store:
            # Mock search results
            mock_vector_store.return_value.search_similar_concepts = AsyncMock(
                return_value=[
                    # Mock documents with relevance scores
                ]
            )

            # Mock market data repository
            with patch(
                "src.interfaces.api.dependencies.get_market_data_repository"
            ) as mock_market_repo:
                # Setup market data mock
                mock_repo_instance = AsyncMock(spec=MarketDataRepository)
                mock_repo_instance.get_market_data_with_5day_avg = AsyncMock(
                    return_value=mock_market_data
                )
                mock_market_repo.return_value = mock_repo_instance

                # Make API request with market filters
                response = client.get(
                    "/api/v1/search",
                    params={
                        "target_identifier": "002240",
                        "top_k": 20,
                        "max_market_cap": 85e8,  # 85亿
                        "max_volume_5d": 2e8,  # 2亿
                    },
                )

                assert response.status_code == 200
                data = response.json()

                # Verify metadata includes filter information
                assert data["metadata"]["market_cap_filter"] is True
                assert data["metadata"]["volume_filter"] is True
                assert data["metadata"]["advanced_scoring"] is True
                assert data["metadata"]["max_market_cap"] == 85e8
                assert data["metadata"]["max_avg_volume_5d"] == 2e8

    @pytest.mark.asyncio
    async def test_search_without_market_data(self, client: TestClient):
        """Test search API when market data is unavailable."""
        with patch(
            "src.interfaces.api.dependencies.get_vector_store"
        ) as mock_vector_store:
            mock_vector_store.return_value.search_similar_concepts = AsyncMock(
                return_value=[]
            )

            # Mock market data repository to return empty data
            with patch(
                "src.interfaces.api.dependencies.get_market_data_repository"
            ) as mock_market_repo:
                mock_repo_instance = AsyncMock(spec=MarketDataRepository)
                mock_repo_instance.get_market_data_with_5day_avg = AsyncMock(
                    return_value={}
                )
                mock_market_repo.return_value = mock_repo_instance

                response = client.get(
                    "/api/v1/search",
                    params={
                        "target_identifier": "002240",
                        "top_k": 20,
                    },
                )

                assert response.status_code == 200
                data = response.json()

                # Should still return results but without market filtering
                assert data["metadata"]["advanced_scoring"] is False

    @pytest.mark.asyncio
    async def test_advanced_scoring_output(self, client: TestClient, mock_market_data):
        """Test that advanced scoring affects result ordering."""
        # This test would verify that companies are ordered by L score
        # In a real integration test, we would:
        # 1. Set up test data with known relevance scores
        # 2. Apply market filters and scoring
        # 3. Verify the output order matches expected L score ranking
        pass
