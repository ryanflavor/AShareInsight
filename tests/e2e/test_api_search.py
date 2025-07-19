"""
End-to-end tests for the search API endpoints.

These tests verify the complete flow of API requests and responses,
ensuring contract compliance and proper error handling.
"""

import pytest
from fastapi.testclient import TestClient

from src.interfaces.api.main import app


@pytest.fixture
def test_client() -> TestClient:
    """
    Create a test client for the FastAPI application.

    Returns:
        TestClient: Test client instance
    """
    return TestClient(app)


class TestSearchAPI:
    """Test suite for search API endpoints."""

    def test_fastapi_app_starts_successfully(self, test_client: TestClient) -> None:
        """Test that the FastAPI application can start successfully."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_search_similar_companies_endpoint_exists(
        self, test_client: TestClient
    ) -> None:
        """Test that the POST /api/v1/search/similar-companies endpoint exists."""
        response = test_client.post(
            "/api/v1/search/similar-companies",
            json={"query_identifier": "比亚迪"},
        )
        # Should return 200 OK, not 404 Not Found
        assert response.status_code == 200

    def test_valid_request_returns_correct_response_structure(
        self, test_client: TestClient
    ) -> None:
        """Test that valid requests return responses matching the contract."""
        # Test with minimal request
        response = test_client.post(
            "/api/v1/search/similar-companies",
            json={"query_identifier": "比亚迪"},
        )
        assert response.status_code == 200

        data = response.json()

        # Verify top-level structure
        assert "query_company" in data
        assert "metadata" in data
        assert "results" in data

        # Verify query_company structure
        query_company = data["query_company"]
        assert "name" in query_company
        assert "code" in query_company
        assert isinstance(query_company["name"], str)
        assert isinstance(query_company["code"], str)
        assert len(query_company["code"]) == 6  # Stock code format

        # Verify metadata structure
        metadata = data["metadata"]
        assert "total_results_before_limit" in metadata
        assert "filters_applied" in metadata
        assert isinstance(metadata["total_results_before_limit"], int)
        assert isinstance(metadata["filters_applied"], dict)

        # Verify results structure
        results = data["results"]
        assert isinstance(results, list)
        assert len(results) <= 20  # Default top_k

        # Verify each result structure
        for result in results:
            assert "company_name" in result
            assert "company_code" in result
            assert "relevance_score" in result
            assert "matched_concepts" in result
            assert isinstance(result["company_name"], str)
            assert isinstance(result["company_code"], str)
            assert len(result["company_code"]) == 6
            assert isinstance(result["relevance_score"], float)
            assert 0.0 <= result["relevance_score"] <= 1.0
            assert isinstance(result["matched_concepts"], list)

            # Verify matched concepts
            for concept in result["matched_concepts"]:
                assert "name" in concept
                assert "similarity_score" in concept
                assert isinstance(concept["name"], str)
                assert isinstance(concept["similarity_score"], float)
                assert 0.0 <= concept["similarity_score"] <= 1.0

    def test_request_with_all_parameters(self, test_client: TestClient) -> None:
        """Test request with all optional parameters."""
        response = test_client.post(
            "/api/v1/search/similar-companies?include_justification=true",
            json={
                "query_identifier": "宁德时代",
                "top_k": 5,
                "market_filters": {
                    "max_market_cap_cny": 10000000000,
                    "min_5day_avg_volume": 1000000,
                },
            },
        )
        assert response.status_code == 200

        data = response.json()
        results = data["results"]
        assert len(results) <= 5  # Respects top_k

        # Verify justification is included
        for result in results:
            assert "justification" in result
            if result["justification"]:
                assert "summary" in result["justification"]
                assert "supporting_evidence" in result["justification"]
                assert isinstance(result["justification"]["summary"], str)
                assert isinstance(result["justification"]["supporting_evidence"], list)

    def test_invalid_request_returns_422_error(self, test_client: TestClient) -> None:
        """Test that invalid requests return 422 Unprocessable Entity."""
        # Missing required field
        response = test_client.post(
            "/api/v1/search/similar-companies",
            json={},
        )
        assert response.status_code == 422

        error_data = response.json()
        assert "error" in error_data
        assert error_data["error"]["code"] == "VALIDATION_ERROR"
        assert "validation_errors" in error_data["error"]["details"]

        # Invalid field type
        response = test_client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "比亚迪",
                "top_k": "not_a_number",  # Should be int
            },
        )
        assert response.status_code == 422

        # Invalid field value
        response = test_client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "比亚迪",
                "top_k": 0,  # Should be >= 1
            },
        )
        assert response.status_code == 422

        # Invalid market filter
        response = test_client.post(
            "/api/v1/search/similar-companies",
            json={
                "query_identifier": "比亚迪",
                "market_filters": {
                    "max_market_cap_cny": -1000,  # Should be > 0
                },
            },
        )
        assert response.status_code == 422

    def test_response_contract_consistency(self, test_client: TestClient) -> None:
        """Test that responses are consistent with defined Pydantic models."""
        # Test multiple requests to ensure consistency
        identifiers = ["比亚迪", "宁德时代", "理想汽车"]

        for identifier in identifiers:
            response = test_client.post(
                "/api/v1/search/similar-companies",
                json={"query_identifier": identifier, "top_k": 3},
            )
            assert response.status_code == 200

            data = response.json()

            # Verify filters_applied matches request
            filters_applied = data["metadata"]["filters_applied"]
            assert filters_applied["market_cap_filter"] is False
            assert filters_applied["volume_filter"] is False

            # Verify results count matches top_k
            assert len(data["results"]) <= 3

            # Verify no justification when not requested
            for result in data["results"]:
                assert result.get("justification") is None

    def test_health_check_endpoint(self, test_client: TestClient) -> None:
        """Test the health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_openapi_documentation_available(self, test_client: TestClient) -> None:
        """Test that OpenAPI documentation is available."""
        # Test OpenAPI JSON endpoint
        response = test_client.get("/openapi.json")
        assert response.status_code == 200

        openapi_schema = response.json()
        assert openapi_schema["info"]["title"] == "AShareInsight API"
        assert openapi_schema["info"]["version"] == "0.1.0"

        # Verify our endpoint is documented
        assert "/api/v1/search/similar-companies" in openapi_schema["paths"]
