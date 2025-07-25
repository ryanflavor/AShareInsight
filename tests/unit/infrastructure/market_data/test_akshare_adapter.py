"""Unit tests for akshare market data adapter."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
import pytest

from src.infrastructure.market_data.akshare_adapter import (
    AkshareMarketDataAdapter,
    MarketSnapshot,
)


class TestAkshareMarketDataAdapter:
    """Test cases for AkshareMarketDataAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return AkshareMarketDataAdapter(max_retries=2, retry_delay=0.1)

    @pytest.fixture
    def mock_sh_sz_data(self):
        """Mock Shanghai/Shenzhen market data."""
        return pd.DataFrame(
            {
                "代码": ["000001", "000002", "600000"],
                "名称": ["平安银行", "万科A", "浦发银行"],
                "总市值": [2500000000000, 1800000000000, 3200000000000],
                "流通市值": [2300000000000, 1700000000000, 3000000000000],
                "成交额": [1200000000, 800000000, 1500000000],
            }
        )

    @pytest.fixture
    def mock_bj_data(self):
        """Mock Beijing Stock Exchange data."""
        return pd.DataFrame(
            {
                "代码": ["430001", "430002"],
                "名称": ["北交所股票1", "北交所股票2"],
                "总市值": [500000000000, 600000000000],
                "流通市值": [400000000000, 500000000000],
                "成交额": [50000000, 60000000],
            }
        )

    @pytest.mark.asyncio
    async def test_get_all_market_snapshot_success(
        self, adapter, mock_sh_sz_data, mock_bj_data
    ):
        """Test successful market snapshot retrieval."""
        with (
            patch.object(adapter, "_fetch_sh_sz_data", return_value=mock_sh_sz_data),
            patch.object(adapter, "_fetch_bj_data", return_value=mock_bj_data),
        ):
            snapshots = await adapter.get_all_market_snapshot()

            # Verify result
            assert len(snapshots) == 5  # 3 SH/SZ + 2 BSE
            assert all(isinstance(s, MarketSnapshot) for s in snapshots)

            # Check first snapshot
            first = snapshots[0]
            assert first.company_code == "000001"
            assert first.company_name == "平安银行"
            assert first.total_market_cap == Decimal("2500000000000")
            assert first.circulating_market_cap == Decimal("2300000000000")
            assert first.turnover_amount == Decimal("1200000000")

    @pytest.mark.asyncio
    async def test_get_all_market_snapshot_bse_failure(self, adapter, mock_sh_sz_data):
        """Test graceful handling when BSE data fails."""
        with (
            patch.object(adapter, "_fetch_sh_sz_data", return_value=mock_sh_sz_data),
            patch.object(adapter, "_fetch_bj_data", return_value=pd.DataFrame()),
        ):
            snapshots = await adapter.get_all_market_snapshot()

            # Should still return SH/SZ data
            assert len(snapshots) == 3
            assert all(
                s.company_code in ["000001", "000002", "600000"] for s in snapshots
            )

    @pytest.mark.asyncio
    async def test_get_all_market_snapshot_complete_failure(self, adapter):
        """Test handling when all data fetching fails."""
        with (
            patch.object(
                adapter, "_fetch_sh_sz_data", side_effect=Exception("Network error")
            ),
            patch.object(adapter, "_fetch_bj_data", return_value=pd.DataFrame()),
        ):
            with pytest.raises(Exception, match="Network error"):
                await adapter.get_all_market_snapshot()

    def test_process_dataframe_with_invalid_data(self, adapter):
        """Test processing dataframe with invalid/missing data."""
        # Create dataframe with missing and invalid data
        df = pd.DataFrame(
            {
                "代码": ["000001", "", "000003", "000004"],
                "名称": ["公司1", "公司2", "公司3", "公司4"],
                "总市值": [1000000000000, 2000000000000, None, -1000000000000],
                "流通市值": [900000000000, 1800000000000, 500000000000, 900000000000],
                "成交额": [100000000, None, 300000000, 400000000],
            }
        )

        trading_date = datetime.now()
        snapshots = adapter._process_dataframe(df, trading_date)

        # Should skip rows with empty code, None market cap, or negative market cap
        assert len(snapshots) == 1
        assert snapshots[0].company_code == "000001"
        assert snapshots[0].total_market_cap == Decimal("1000000000000")

    def test_safe_decimal_conversion(self, adapter):
        """Test safe decimal conversion with various inputs."""
        # Normal values
        assert adapter._safe_decimal_conversion(123.45) == Decimal("123.45")
        assert adapter._safe_decimal_conversion("678.90") == Decimal("678.90")
        assert adapter._safe_decimal_conversion(0) == Decimal("0")

        # Invalid values
        assert adapter._safe_decimal_conversion(None) == Decimal("0")
        assert adapter._safe_decimal_conversion(pd.NA) == Decimal("0")
        assert adapter._safe_decimal_conversion("invalid") == Decimal("0")

    @patch("akshare.stock_zh_a_spot_em")
    def test_fetch_sh_sz_data_with_retries(self, mock_ak, adapter):
        """Test SH/SZ data fetching with retry logic."""
        # First attempt fails, second succeeds
        mock_ak.side_effect = [
            Exception("Connection error"),
            pd.DataFrame({"代码": ["000001"]}),
        ]

        with patch("time.sleep"):  # Skip actual sleep
            result = adapter._fetch_sh_sz_data()

        assert len(result) == 1
        assert mock_ak.call_count == 2

    @patch("akshare.stock_zh_a_spot_em")
    def test_fetch_sh_sz_data_all_retries_fail(self, mock_ak, adapter):
        """Test SH/SZ data fetching when all retries fail."""
        mock_ak.side_effect = Exception("Persistent error")

        with (
            patch("time.sleep"),
            pytest.raises(Exception, match="Failed to fetch SH/SZ data"),
        ):
            adapter._fetch_sh_sz_data()

        assert mock_ak.call_count == adapter.max_retries
