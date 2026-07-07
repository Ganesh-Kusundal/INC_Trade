"""Unit tests for Upstox tick mapper."""

from __future__ import annotations

from decimal import Decimal

from brokers.domain import Quote

from brokers.adapters.upstox.tick_mapper import frame_to_quote


class TestTickMapper:
    def test_frame_to_quote_ltpc(self):
        quote = frame_to_quote(
            {"symbol": "RELIANCE", "exchange": "NSE", "ltp": 2500.5, "volume": 10}
        )
        assert isinstance(quote, Quote)
        assert quote.ltp == Decimal("2500.5")
        assert quote.volume == 10

    def test_frame_to_quote_missing_ltp(self):
        assert frame_to_quote({"symbol": "X"}) is None
