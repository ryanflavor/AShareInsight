"""
Pydantic models for search API endpoints.

These models define the contract for the search API, ensuring type safety
and automatic validation for all requests and responses.
"""

from pydantic import BaseModel, Field, model_validator


class MarketFilters(BaseModel):
    """
    Market-based filtering criteria for company search.

    Attributes:
        max_market_cap_cny: Maximum market capitalization in CNY
        min_5day_avg_volume: Minimum 5-day average trading volume
    """

    max_market_cap_cny: int | None = Field(
        None,
        description="Maximum market capitalization in Chinese Yuan (CNY)",
        gt=0,
        examples=[1000000000],
    )
    min_5day_avg_volume: int | None = Field(
        None,
        description="Minimum 5-day average trading volume",
        gt=0,
        examples=[100000],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "max_market_cap_cny": 5000000000,
                    "min_5day_avg_volume": 500000,
                }
            ]
        }
    }


class SearchSimilarCompaniesRequest(BaseModel):
    """
    Request model for searching similar companies.

    Attributes:
        query_identifier: Company name or stock code to search for
        top_k: Number of similar companies to return
        market_filters: Optional market-based filtering criteria
    """

    query_identifier: str = Field(
        ...,
        description="Company name or stock code (e.g., '比亚迪' or '002594')",
        min_length=1,
        max_length=100,
        examples=["比亚迪", "002594", "宁德时代"],
    )
    top_k: int = Field(
        20,
        description="Number of similar companies to return",
        ge=1,
        le=100,
    )
    market_filters: MarketFilters | None = Field(
        None,
        description="Optional market-based filtering criteria",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query_identifier": "比亚迪",
                    "top_k": 10,
                    "market_filters": {
                        "max_market_cap_cny": 5000000000,
                        "min_5day_avg_volume": 500000,
                    },
                }
            ]
        }
    }


class QueryCompany(BaseModel):
    """
    Information about the query company.

    Attributes:
        name: Company name
        code: Stock code
    """

    name: str = Field(
        ...,
        description="Company name",
        examples=["比亚迪股份有限公司"],
    )
    code: str = Field(
        ...,
        description="Stock code",
        pattern=r"^\d{6}$",
        examples=["002594"],
    )


class MatchedConcept(BaseModel):
    """
    A business concept that matches between companies.

    Attributes:
        name: Concept name
        similarity_score: Similarity score between 0 and 1
    """

    name: str = Field(
        ...,
        description="Business concept name",
        examples=["新能源汽车", "动力电池"],
    )
    similarity_score: float = Field(
        ...,
        description="Similarity score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
        examples=[0.85],
    )


class Justification(BaseModel):
    """
    Detailed justification for why a company is considered similar.

    Attributes:
        summary: Brief explanation of similarity
        supporting_evidence: List of specific evidence points
    """

    summary: str = Field(
        ...,
        description="Brief explanation of why this company is similar",
        min_length=1,
        max_length=500,
        examples=["Both companies are leaders in electric vehicle manufacturing"],
    )
    supporting_evidence: list[str] = Field(
        ...,
        description="Specific evidence supporting the similarity",
        min_length=1,
        max_length=10,
        examples=[["Strong R&D in battery technology", "Major EV production capacity"]],
    )


class CompanyResult(BaseModel):
    """
    A single company in the search results.

    Attributes:
        company_name: Full company name
        company_code: Stock code
        relevance_score: Overall relevance score
        matched_concepts: List of matching business concepts
        justification: Optional detailed justification (when requested)
    """

    company_name: str = Field(
        ...,
        description="Full company name",
        examples=["宁德时代新能源科技股份有限公司"],
    )
    company_code: str = Field(
        ...,
        description="Stock code",
        pattern=r"^\d{6}$",
        examples=["300750"],
    )
    relevance_score: float = Field(
        ...,
        description="Overall relevance score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
        examples=[0.92],
    )
    matched_concepts: list[MatchedConcept] = Field(
        ...,
        description="List of matching business concepts",
        min_length=0,
    )
    justification: Justification | None = Field(
        None,
        description="Detailed justification (only when include_justification=true)",
    )

    @model_validator(mode="after")
    def validate_concepts_exist_when_relevant(self) -> "CompanyResult":
        """Ensure matched concepts exist when relevance score is high."""
        if self.relevance_score > 0 and len(self.matched_concepts) == 0:
            raise ValueError(
                "matched_concepts cannot be empty when relevance_score > 0"
            )
        return self


class SearchMetadata(BaseModel):
    """
    Metadata about the search results.

    Attributes:
        total_results_before_limit: Total matching companies before applying top_k
        filters_applied: Summary of applied filters
    """

    total_results_before_limit: int = Field(
        ...,
        description="Total number of matching companies before applying top_k limit",
        ge=0,
        examples=[150],
    )
    filters_applied: dict = Field(
        ...,
        description="Summary of filters that were applied",
        examples=[{"market_cap_filter": True, "volume_filter": False}],
    )


class SearchSimilarCompaniesResponse(BaseModel):
    """
    Response model for similar companies search.

    Attributes:
        query_company: Information about the searched company
        metadata: Search metadata
        results: List of similar companies
    """

    query_company: QueryCompany = Field(
        ...,
        description="Information about the company that was searched",
    )
    metadata: SearchMetadata = Field(
        ...,
        description="Metadata about the search results",
    )
    results: list[CompanyResult] = Field(
        ...,
        description="List of similar companies ordered by relevance",
        max_length=100,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query_company": {
                        "name": "比亚迪股份有限公司",
                        "code": "002594",
                    },
                    "metadata": {
                        "total_results_before_limit": 45,
                        "filters_applied": {
                            "market_cap_filter": True,
                            "volume_filter": False,
                        },
                    },
                    "results": [
                        {
                            "company_name": "宁德时代新能源科技股份有限公司",
                            "company_code": "300750",
                            "relevance_score": 0.92,
                            "matched_concepts": [
                                {
                                    "name": "新能源汽车产业链",
                                    "similarity_score": 0.95,
                                },
                                {
                                    "name": "动力电池制造",
                                    "similarity_score": 0.88,
                                },
                            ],
                        }
                    ],
                }
            ]
        }
    }
