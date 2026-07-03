"""Live integration tests — batch market data."""

from __future__ import annotations

from decimal import Decimal

from brokers.tests.integration.upstox.conftest import skip_live


@skip_live
class TestLiveBatchMarketData:
    def test_ltp_batch(self, gateway):
        result = gateway.ltp_batch(["RELIANCE", "INFY", "TCS"], "NSE")
        assert len(result) == 3
        for sym in ("RELIANCE", "INFY", "TCS"):
            assert sym in result
            assert isinstance(result[sym], Decimal)

    def test_quote_batch(self, gateway):
        result = gateway.quote_batch(["RELIANCE", "INFY"], "NSE")
        assert len(result) == 2
        assert result["RELIANCE"].ltp > 0
