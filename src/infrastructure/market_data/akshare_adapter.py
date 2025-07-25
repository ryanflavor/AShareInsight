"""Akshare market data adapter for fetching A-share market data."""

import asyncio
import decimal
import time
from datetime import datetime
from decimal import Decimal

import pandas as pd
from pydantic import BaseModel, Field

import akshare as ak
from src.shared.utils.logger import get_logger
from src.shared.utils.timezone import now_china

logger = get_logger(__name__)


class MarketSnapshot(BaseModel):
    """Single stock market data snapshot."""

    company_code: str = Field(..., description="Stock code")
    company_name: str = Field(..., description="Company name")
    total_market_cap: Decimal = Field(..., description="Total market cap in CNY")
    circulating_market_cap: Decimal = Field(
        ..., description="Circulating market cap in CNY"
    )
    turnover_amount: Decimal = Field(..., description="Turnover amount in CNY")
    trading_date: datetime = Field(..., description="Trading date")


class AkshareMarketDataAdapter:
    """Adapter for fetching A-share market data from akshare."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """Initialize the adapter.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def get_all_market_snapshot(self) -> list[MarketSnapshot]:
        """Get market snapshot for all A-shares including BSE.

        Returns:
            List of market snapshots for all stocks

        Raises:
            Exception: If data fetching fails after retries
        """
        try:
            # Run synchronous akshare calls in thread pool
            loop = asyncio.get_event_loop()
            sh_sz_data, bj_data = await asyncio.gather(
                loop.run_in_executor(None, self._fetch_sh_sz_data),
                loop.run_in_executor(None, self._fetch_bj_data),
            )

            # Combine and process data
            all_data = self._combine_market_data(sh_sz_data, bj_data)

            logger.info(f"Successfully fetched market data for {len(all_data)} stocks")
            return all_data

        except Exception as e:
            logger.error(f"Failed to fetch market snapshot: {str(e)}")
            raise

    def _fetch_sh_sz_data(self) -> pd.DataFrame:
        """Fetch Shanghai and Shenzhen A-share data with retries."""
        for attempt in range(self.max_retries):
            try:
                df = ak.stock_zh_a_spot_em()
                logger.info(f"Fetched {len(df)} SH/SZ stocks")
                return df
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed for SH/SZ data: {str(e)}"
                    )
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(
                        f"Failed to fetch SH/SZ data after {self.max_retries} attempts: {str(e)}"
                    )

    def _fetch_bj_data(self) -> pd.DataFrame:
        """Fetch Beijing Stock Exchange data with retries."""
        for attempt in range(self.max_retries):
            try:
                df = ak.stock_bj_a_spot_em()
                logger.info(f"Fetched {len(df)} BSE stocks")
                return df
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1} failed for BSE data: {str(e)}"
                    )
                    time.sleep(self.retry_delay)
                else:
                    # BSE data is optional, log error but don't fail
                    logger.error(
                        f"Failed to fetch BSE data after {self.max_retries} attempts: {str(e)}"
                    )
                    return pd.DataFrame()

    def _combine_market_data(
        self, sh_sz_df: pd.DataFrame, bj_df: pd.DataFrame
    ) -> list[MarketSnapshot]:
        """Combine and process market data from different exchanges.

        Args:
            sh_sz_df: Shanghai and Shenzhen data
            bj_df: Beijing Stock Exchange data

        Returns:
            List of processed market snapshots
        """
        snapshots = []
        trading_date = now_china()

        # Process SH/SZ data
        if not sh_sz_df.empty:
            snapshots.extend(self._process_dataframe(sh_sz_df, trading_date))

        # Process BSE data
        if not bj_df.empty:
            snapshots.extend(self._process_dataframe(bj_df, trading_date))

        return snapshots

    def _process_dataframe(
        self, df: pd.DataFrame, trading_date: datetime
    ) -> list[MarketSnapshot]:
        """Process a dataframe into market snapshots.

        Args:
            df: Raw market data dataframe
            trading_date: Current trading date

        Returns:
            List of market snapshots
        """
        snapshots = []

        # Expected columns mapping
        column_mapping = {
            "代码": "company_code",
            "名称": "company_name",
            "总市值": "total_market_cap",
            "流通市值": "circulating_market_cap",
            "成交额": "turnover_amount",
        }

        # Validate required columns exist
        missing_columns = [
            col for col in column_mapping.keys() if col not in df.columns
        ]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            return snapshots

        for _, row in df.iterrows():
            try:
                # Extract and validate data
                company_code = str(row["代码"]).strip()
                company_name = str(row["名称"]).strip()

                # Convert to Decimal for precision
                total_market_cap = self._safe_decimal_conversion(row.get("总市值", 0))
                circulating_market_cap = self._safe_decimal_conversion(
                    row.get("流通市值", 0)
                )
                turnover_amount = self._safe_decimal_conversion(row.get("成交额", 0))

                # Skip invalid records
                if not company_code or total_market_cap <= 0:
                    continue

                snapshot = MarketSnapshot(
                    company_code=company_code,
                    company_name=company_name,
                    total_market_cap=total_market_cap,
                    circulating_market_cap=circulating_market_cap,
                    turnover_amount=turnover_amount,
                    trading_date=trading_date,
                )
                snapshots.append(snapshot)

            except Exception as e:
                logger.warning(
                    f"Failed to process row for {row.get('代码', 'unknown')}: {str(e)}"
                )
                continue

        return snapshots

    def _safe_decimal_conversion(self, value) -> Decimal:
        """Safely convert value to Decimal.

        Args:
            value: Value to convert

        Returns:
            Decimal value or 0 if conversion fails
        """
        try:
            if pd.isna(value) or value is None:
                return Decimal(0)
            return Decimal(str(value))
        except (ValueError, TypeError, decimal.InvalidOperation):
            return Decimal(0)
