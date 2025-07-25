"""Market filter configuration module."""

from pydantic import BaseModel, Field


class TierConfig(BaseModel):
    """Configuration for a scoring tier."""

    min_value: float = Field(..., description="Minimum value (inclusive)")
    max_value: float = Field(..., description="Maximum value (exclusive)")
    score: float = Field(..., description="Score for this tier")
    label: str = Field(..., description="Descriptive label for the tier")


class MarketFilterConfig(BaseModel):
    """Configuration for market data filtering and scoring."""

    # Filter thresholds
    max_market_cap: float = Field(
        default=85e8, description="Maximum market cap threshold in CNY"
    )
    max_avg_volume_5d: float = Field(
        default=2e8, description="Maximum 5-day average volume threshold in CNY"
    )

    # Market cap tier configuration
    market_cap_tiers: list[TierConfig] = Field(
        default=[
            TierConfig(
                min_value=60e8, max_value=85e8, score=1.0, label="Quality mid-cap"
            ),
            TierConfig(
                min_value=40e8, max_value=60e8, score=2.0, label="Standard mid-cap"
            ),
            TierConfig(min_value=0, max_value=40e8, score=3.0, label="Small-cap"),
        ],
        description="Market cap scoring tiers",
    )

    # Volume tier configuration
    volume_tiers: list[TierConfig] = Field(
        default=[
            TierConfig(min_value=1e8, max_value=2e8, score=1.0, label="High liquidity"),
            TierConfig(
                min_value=0.5e8, max_value=1e8, score=2.0, label="Medium liquidity"
            ),
            TierConfig(min_value=0, max_value=0.5e8, score=3.0, label="Low liquidity"),
        ],
        description="Volume scoring tiers",
    )

    # Relevance mapping configuration (optional)
    relevance_mapping_enabled: bool = Field(
        default=False, description="Enable discrete relevance mapping"
    )
    relevance_tiers: list[TierConfig] = Field(
        default=[
            TierConfig(min_value=0.8, max_value=1.0, score=1.0, label="High relevance"),
            TierConfig(
                min_value=0.5, max_value=0.8, score=0.5, label="Medium relevance"
            ),
            TierConfig(min_value=0, max_value=0.5, score=0.1, label="Low relevance"),
        ],
        description="Relevance mapping rules (only used if relevance_mapping_enabled=True)",
    )

    def get_tier_score(self, value: float, tiers: list[TierConfig]) -> float:
        """Get score for a value based on tier configuration.

        Args:
            value: Value to score
            tiers: List of tier configurations

        Returns:
            Score for the value
        """
        for tier in tiers:
            if tier.min_value <= value < tier.max_value:
                return tier.score
        # Return highest score if value exceeds all tiers
        return tiers[-1].score

    def get_market_cap_score(self, market_cap: float) -> float:
        """Get market cap score.

        Args:
            market_cap: Market cap value in CNY

        Returns:
            Market cap score
        """
        return self.get_tier_score(market_cap, self.market_cap_tiers)

    def get_volume_score(self, volume: float) -> float:
        """Get volume score.

        Args:
            volume: Volume value in CNY

        Returns:
            Volume score
        """
        return self.get_tier_score(volume, self.volume_tiers)

    def get_relevance_coefficient(self, relevance_score: float) -> float:
        """Get relevance coefficient.

        Args:
            relevance_score: Raw relevance score (0-1)

        Returns:
            Relevance coefficient
        """
        if self.relevance_mapping_enabled:
            return self.get_tier_score(relevance_score, self.relevance_tiers)
        # Use continuous value if mapping not enabled
        return relevance_score
