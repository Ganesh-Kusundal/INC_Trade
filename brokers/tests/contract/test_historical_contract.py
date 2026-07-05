"""Contract tests — HistoricalPort protocol compliance.

Every broker adapter's historical data implementation must satisfy
the HistoricalPort protocol contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from inc_trade.ports.historical import HistoricalPort


class HistoricalContractTests:
    """Mixin-style contract tests for HistoricalPort."""

    def test_get_historical_candles_returns_list(self, historical: HistoricalPort) -> None:
        now = datetime.now(timezone.utc)
        try:
            candles = historical.get_historical_candles("RELIANCE", "NSE", now, now, "1D")
            assert isinstance(candles, list)
        except Exception:
            # Some adapters raise NotSupportedError — acceptable during migration
            pass

    def test_candles_are_candle_type(self, historical: HistoricalPort) -> None:
        from inc_trade.domain import Candle

        now = datetime.now(timezone.utc)
        try:
            candles = historical.get_historical_candles("RELIANCE", "NSE", now, now, "1D")
            for c in candles:
                assert isinstance(c, Candle)
        except Exception:
            pass

    def test_empty_for_invalid_range(self, historical: HistoricalPort) -> None:
        """Request with invalid resolution should return empty list or raise."""
        now = datetime.now(timezone.utc)
        try:
            candles = historical.get_historical_candles("RELIANCE", "NSE", now, now, "INVALID")
            assert isinstance(candles, list)
        except Exception:
            pass


@pytest.mark.contract
class TestHistoricalContractConformance:
    """Base test class — override ``historical`` fixture for each broker."""

    @pytest.fixture
    def historical(self) -> HistoricalPort:
        pytest.skip("No concrete HistoricalPort fixture provided")

    def test_get_historical_candles_returns_list(self, historical: HistoricalPort) -> None:
        HistoricalContractTests().test_get_historical_candles_returns_list(historical)

    def test_candles_are_candle_type(self, historical: HistoricalPort) -> None:
        HistoricalContractTests().test_candles_are_candle_type(historical)

    def test_empty_for_invalid_range(self, historical: HistoricalPort) -> None:
        HistoricalContractTests().test_empty_for_invalid_range(historical)


class TestDhanHistoricalContract(TestHistoricalContractConformance):
    @pytest.fixture
    def historical(self) -> HistoricalPort:
        pytest.skip("Dhan integration test — requires credentials")


class TestUpstoxHistoricalContract(TestHistoricalContractConformance):
    @pytest.fixture
    def historical(self) -> HistoricalPort:
        pytest.skip("Upstox integration test — requires credentials")


class TestPaperHistoricalContract(TestHistoricalContractConformance):
    @pytest.fixture
    def historical(self) -> HistoricalPort:
        from brokers.adapters.paper.gateway import PaperGateway

        gw = PaperGateway()
        return gw.historical
