"""Integration tests for the search API with aggregation and filtering.

This module tests the complete search flow including vector search,
company aggregation, market filtering, and API response formatting.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.domain.services import (
    MarketData,
    MarketDataRepository,
)
from src.domain.value_objects import Document
from src.interfaces.api.main import app


class MockVectorStore:
    """Mock vector store for testing."""

    def __init__(self, documents: list[Document]):
        """Initialize with test documents."""
        self.documents = documents

    async def search_similar_concepts(self, query) -> list[Document]:
        """Return mock documents."""
        # Filter by similarity threshold
        filtered = [
            doc
            for doc in self.documents
            if doc.similarity_score >= query.similarity_threshold
        ]
        # Return top_k documents
        return filtered[: query.top_k]


class MockMarketDataRepository(MarketDataRepository):
    """Mock market data repository for testing."""

    def __init__(self, market_data: dict[str, MarketData]):
        """Initialize with test market data."""
        self.market_data = market_data

    async def get_market_data(self, company_codes: list[str]) -> dict[str, MarketData]:
        """Return configured market data."""
        return {
            code: data
            for code, data in self.market_data.items()
            if code in company_codes
        }


@pytest.fixture
def test_documents() -> list[Document]:
    """Create test documents for various companies."""
    base_time = datetime.now(UTC)

    return [
        # BYD - multiple high-scoring concepts
        Document(
            concept_id=uuid4(),
            company_code="002594",
            company_name="比亚迪股份有限公司",
            concept_name="新能源汽车",
            concept_category="Technology",
            importance_score=Decimal("0.95"),
            similarity_score=0.98,
            matched_at=base_time,
        ),
        Document(
            concept_id=uuid4(),
            company_code="002594",
            company_name="比亚迪股份有限公司",
            concept_name="动力电池",
            concept_category="Technology",
            importance_score=Decimal("0.90"),
            similarity_score=0.92,
            matched_at=base_time,
        ),
        Document(
            concept_id=uuid4(),
            company_code="002594",
            company_name="比亚迪股份有限公司",
            concept_name="智能驾驶",
            concept_category="Technology",
            importance_score=Decimal("0.85"),
            similarity_score=0.85,
            matched_at=base_time,
        ),
        # CATL - battery focus
        Document(
            concept_id=uuid4(),
            company_code="300750",
            company_name="宁德时代新能源科技股份有限公司",
            concept_name="动力电池",
            concept_category="Technology",
            importance_score=Decimal("0.95"),
            similarity_score=0.95,
            matched_at=base_time,
        ),
        Document(
            concept_id=uuid4(),
            company_code="300750",
            company_name="宁德时代新能源科技股份有限公司",
            concept_name="储能系统",
            concept_category="Energy",
            importance_score=Decimal("0.88"),
            similarity_score=0.88,
            matched_at=base_time,
        ),
        # Li Auto - EV manufacturer
        Document(
            concept_id=uuid4(),
            company_code="002015",
            company_name="理想汽车",
            concept_name="新能源汽车",
            concept_category="Technology",
            importance_score=Decimal("0.92"),
            similarity_score=0.82,
            matched_at=base_time,
        ),
        # Low score company - should be filtered by threshold
        Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="平安银行",
            concept_name="金融科技",
            concept_category="Finance",
            importance_score=Decimal("0.80"),
            similarity_score=0.65,  # Below default threshold
            matched_at=base_time,
        ),
    ]


@pytest.fixture
def test_market_data() -> dict[str, MarketData]:
    """Create test market data for companies."""
    return {
        "002594": MarketData(
            company_code="002594",
            market_cap_cny=Decimal("800000000000"),  # 800B - large cap
            avg_volume_5day=Decimal("50000000"),  # 50M - high volume
        ),
        "300750": MarketData(
            company_code="300750",
            market_cap_cny=Decimal("500000000000"),  # 500B - large cap
            avg_volume_5day=Decimal("30000000"),  # 30M - high volume
        ),
        "002015": MarketData(
            company_code="002015",
            market_cap_cny=Decimal("50000000000"),  # 50B - mid cap
            avg_volume_5day=Decimal("5000000"),  # 5M - medium volume
        ),
        "000001": MarketData(
            company_code="000001",
            market_cap_cny=Decimal("200000000000"),  # 200B
            avg_volume_5day=Decimal("10000000"),  # 10M
        ),
    }


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_search_api_basic_aggregation(
    client: TestClient,
    test_documents: list[Document],
):
    """Test basic search with company aggregation."""
    # Mock dependencies
    mock_vector_store = MockVectorStore(test_documents)

    with patch(
        "src.interfaces.api.dependencies.get_vector_store_repository"
    ) as mock_get_store:
        # Configure mock
        async def mock_store_gen():
            yield mock_vector_store

        mock_get_store.return_value = mock_store_gen()

        # Make request
        response = client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "比亚迪",
                "top_k": 10,
                "similarity_threshold": 0.7,
            },
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # Check query company resolution
        assert data["query_company"]["name"] == "比亚迪股份有限公司"
        assert data["query_company"]["code"] == "002594"

        # Check results - should have 3 companies (平安银行 filtered by threshold)
        assert len(data["results"]) == 3

        # Check BYD is first with highest score
        byd = data["results"][0]
        assert byd["company_code"] == "002594"
        assert byd["relevance_score"] == 0.98  # Highest concept score
        assert len(byd["matched_concepts"]) == 3

        # Check concepts are sorted by score
        concepts = byd["matched_concepts"]
        assert concepts[0]["name"] == "新能源汽车"
        assert concepts[0]["similarity_score"] == 0.98
        assert concepts[1]["name"] == "动力电池"
        assert concepts[1]["similarity_score"] == 0.92

        # Check metadata
        assert data["metadata"]["total_results_before_limit"] == 3
        assert data["metadata"]["filters_applied"]["similarity_threshold"] is True
        assert data["metadata"]["filters_applied"]["market_cap_filter"] is False
        assert data["metadata"]["filters_applied"]["volume_filter"] is False


@pytest.mark.asyncio
async def test_search_api_with_market_filters(
    client: TestClient,
    test_documents: list[Document],
    test_market_data: dict[str, MarketData],
):
    """Test search with market cap and volume filters."""
    # Mock dependencies
    mock_vector_store = MockVectorStore(test_documents)
    mock_market_repo = MockMarketDataRepository(test_market_data)

    with (
        patch(
            "src.interfaces.api.dependencies.get_vector_store_repository"
        ) as mock_get_store,
        patch(
            "src.interfaces.api.dependencies.get_market_data_repository"
        ) as mock_get_market,
    ):
        # Configure mocks
        async def mock_store_gen():
            yield mock_vector_store

        async def mock_market_gen():
            yield mock_market_repo

        mock_get_store.return_value = mock_store_gen()
        mock_get_market.return_value = mock_market_gen()

        # Make request with market filters
        response = client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "002594",
                "top_k": 10,
                "similarity_threshold": 0.7,
                "market_filters": {
                    "max_market_cap_cny": 100000000000,  # 100B max
                    "min_5day_avg_volume": 1000000,  # 1M min
                },
            },
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # Only Li Auto should pass filters (50B cap, 5M volume)
        assert len(data["results"]) == 1
        assert data["results"][0]["company_code"] == "002015"
        assert data["results"][0]["company_name"] == "理想汽车"

        # Check filters were applied
        assert data["metadata"]["filters_applied"]["market_cap_filter"] is True
        assert data["metadata"]["filters_applied"]["volume_filter"] is True


@pytest.mark.asyncio
async def test_search_api_with_justification(
    client: TestClient,
    test_documents: list[Document],
):
    """Test search with justification included."""
    # Mock dependencies
    mock_vector_store = MockVectorStore(test_documents[:3])  # Just BYD docs

    with patch(
        "src.interfaces.api.dependencies.get_vector_store_repository"
    ) as mock_get_store:
        # Configure mock
        async def mock_store_gen():
            yield mock_vector_store

        mock_get_store.return_value = mock_store_gen()

        # Make request with justification
        response = client.post(
            "/api/v1/search/similar-companies?include_justification=true",
            json={
                "query_identifier": "比亚迪",
                "top_k": 5,
                "similarity_threshold": 0.8,
            },
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # Check justification is included
        byd = data["results"][0]
        assert byd["justification"] is not None
        assert "Matched 3 business concepts" in byd["justification"]["summary"]
        assert len(byd["justification"]["supporting_evidence"]) == 3
        assert (
            "新能源汽车 (score: 0.98)" in byd["justification"]["supporting_evidence"][0]
        )


@pytest.mark.asyncio
async def test_search_api_top_k_limit(
    client: TestClient,
    test_documents: list[Document],
):
    """Test that top_k limit is applied after aggregation."""
    # Mock dependencies
    mock_vector_store = MockVectorStore(test_documents)

    with patch(
        "src.interfaces.api.dependencies.get_vector_store_repository"
    ) as mock_get_store:
        # Configure mock
        async def mock_store_gen():
            yield mock_vector_store

        mock_get_store.return_value = mock_store_gen()

        # Make request with top_k=2
        response = client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "新能源",
                "top_k": 2,
                "similarity_threshold": 0.7,
            },
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # Should only return 2 companies
        assert len(data["results"]) == 2
        # Should be the highest scoring ones
        assert data["results"][0]["company_code"] == "002594"  # BYD
        assert data["results"][1]["company_code"] == "300750"  # CATL


@pytest.mark.asyncio
async def test_search_api_no_market_data_graceful_degradation(
    client: TestClient,
    test_documents: list[Document],
):
    """Test graceful degradation when market data is unavailable."""
    # Mock dependencies
    mock_vector_store = MockVectorStore(test_documents)
    mock_market_repo = MockMarketDataRepository({})  # Empty market data

    with (
        patch(
            "src.interfaces.api.dependencies.get_vector_store_repository"
        ) as mock_get_store,
        patch(
            "src.interfaces.api.dependencies.get_market_data_repository"
        ) as mock_get_market,
    ):
        # Configure mocks
        async def mock_store_gen():
            yield mock_vector_store

        async def mock_market_gen():
            yield mock_market_repo

        mock_get_store.return_value = mock_store_gen()
        mock_get_market.return_value = mock_market_gen()

        # Make request with market filters
        response = client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "比亚迪",
                "top_k": 10,
                "market_filters": {
                    "max_market_cap_cny": 100000000000,
                    "min_5day_avg_volume": 1000000,
                },
            },
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # All companies should be returned (filters not applied)
        assert len(data["results"]) == 3

        # Filters should show as not applied
        assert data["metadata"]["filters_applied"]["market_cap_filter"] is False
        assert data["metadata"]["filters_applied"]["volume_filter"] is False


@pytest.mark.asyncio
async def test_search_api_company_not_found(client: TestClient):
    """Test error handling when company not found."""
    # Mock empty vector store
    mock_vector_store = MockVectorStore([])

    with patch(
        "src.interfaces.api.dependencies.get_vector_store_repository"
    ) as mock_get_store:
        # Configure mock to raise exception
        mock_vector_store.search_similar_concepts = AsyncMock(
            side_effect=Exception("Company not found")
        )

        async def mock_store_gen():
            yield mock_vector_store

        mock_get_store.return_value = mock_store_gen()

        # Make request
        response = client.post(
            "/api/v1/search/similar-companies",
            json={"query_identifier": "NonExistentCompany", "top_k": 10},
        )

        # Assert error response
        assert response.status_code == 500


@pytest.mark.asyncio
async def test_search_api_concept_limit_per_company(
    client: TestClient,
):
    """Test that only top 5 concepts are returned per company."""
    # Create many concepts for one company
    base_time = datetime.now(UTC)
    many_concepts = [
        Document(
            concept_id=uuid4(),
            company_code="000001",
            company_name="Test Company",
            concept_name=f"Concept {i}",
            concept_category="Test",
            importance_score=Decimal("0.8"),
            similarity_score=0.9 - (i * 0.01),  # Decreasing scores
            matched_at=base_time,
        )
        for i in range(10)
    ]

    mock_vector_store = MockVectorStore(many_concepts)

    with patch(
        "src.interfaces.api.dependencies.get_vector_store_repository"
    ) as mock_get_store:
        # Configure mock
        async def mock_store_gen():
            yield mock_vector_store

        mock_get_store.return_value = mock_store_gen()

        # Make request
        response = client.post(
            "/api/v1/search/similar-companies",
            json={"query_identifier": "test", "top_k": 10},
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()

        # Should have one company with only 5 concepts
        assert len(data["results"]) == 1
        assert len(data["results"][0]["matched_concepts"]) == 5

        # Should be the top 5 by score
        concepts = data["results"][0]["matched_concepts"]
        for i in range(5):
            assert concepts[i]["name"] == f"Concept {i}"
