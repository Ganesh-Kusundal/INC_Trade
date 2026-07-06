"""Tests for PaperAdapter — in-memory broker adapter for testing.

Verifies:
- Adapter lifecycle (connect/disconnect)
- Market data operations (quote, ltp, depth)
- Order operations (place, modify, cancel)
- Streaming subscription
- Test helpers (set_quote, simulate_tick)
- Error handling when not connected
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.adapters.paper.adapter import PaperAdapter


class TestPaperAdapterLifecycle:
    """Adapter construction and connect/disconnect."""

    def test_constructor_defaults(self) -> None:
        """Adapter can be created with default params."""
        adapter = PaperAdapter()
        assert adapter.broker_id == "paper"
        assert not adapter.is_connected
        assert adapter.max_levels == 5

    def test_constructor_with_initial_cash(self) -> None:
        """Adapter can be created with custom initial cash."""
        adapter = PaperAdapter(initial_cash=Decimal("500000.00"))
        assert not adapter.is_connected

    def test_connect_success(self) -> None:
        """connect() initialises all in-memory sub-adapters."""
        adapter = PaperAdapter()
        adapter.connect()

        assert adapter.is_connected
        assert adapter._orders is not None
        assert adapter._market_data is not None
        assert adapter._historical is not None
        assert adapter._streaming is not None

    def test_disconnect_clears_state(self) -> None:
        """disconnect() clears all in-memory state."""
        adapter = PaperAdapter()
        adapter.connect()
        assert adapter.is_connected

        adapter.disconnect()
        assert not adapter.is_connected
        assert adapter._orders is None
        assert adapter._market_data is None

    def test_double_connect(self) -> None:
        """connect() can be called multiple times."""
        adapter = PaperAdapter()
        adapter.connect()
        adapter.connect()  # Should not raise
        assert adapter.is_connected

    def test_operations_raise_when_not_connected(self) -> None:
        """All provider methods raise RuntimeError if not connected."""
        adapter = PaperAdapter()

        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.quote("RELIANCE", "NSE")

        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.ltp("RELIANCE", "NSE")

        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.depth("RELIANCE", "NSE")

        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.place_order("RELIANCE", "NSE", "BUY", 10)

        with pytest.raises((RuntimeError, ConnectionError), match="not connected"):
            adapter.subscribe(MagicMock(), MagicMock())


class TestPaperAdapterMarketData:
    """Market data operations."""

    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_quote_default(self, adapter: PaperAdapter) -> None:
        """quote() returns default Quote with LTP=100."""
        quote = adapter.quote("RELIANCE", "NSE")
        assert quote.symbol == "RELIANCE"
        assert quote.ltp == Decimal("100.00")

    def test_ltp_default(self, adapter: PaperAdapter) -> None:
        """ltp() returns default LTP=100."""
        ltp = adapter.ltp("RELIANCE", "NSE")
        assert ltp == Decimal("100.00")

    def test_set_quote_updates_ltp(self, adapter: PaperAdapter) -> None:
        """set_quote() updates the LTP for subsequent queries."""
        adapter.set_quote("RELIANCE", Decimal("2850.50"))

        assert adapter.ltp("RELIANCE", "NSE") == Decimal("2850.50")

        quote = adapter.quote("RELIANCE", "NSE")
        assert quote.ltp == Decimal("2850.50")

    def test_depth_returns_empty_market_depth(self, adapter: PaperAdapter) -> None:
        """depth() returns empty MarketDepth."""
        depth = adapter.depth("RELIANCE", "NSE")
        assert depth is not None
        assert depth.symbol == "RELIANCE"

    def test_quote_batch(self, adapter: PaperAdapter) -> None:
        """quote_batch() returns quotes for multiple symbols."""
        adapter.set_quote("RELIANCE", Decimal("2850"))
        adapter.set_quote("TCS", Decimal("4200"))

        quotes = adapter.quote_batch(["RELIANCE", "TCS"], "NSE")
        assert len(quotes) == 2
        assert quotes["RELIANCE"].ltp == Decimal("2850")
        assert quotes["TCS"].ltp == Decimal("4200")


class TestPaperAdapterOrders:
    """Order operations."""

    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_place_order(self, adapter: PaperAdapter) -> None:
        """place_order() returns a successful OrderResponse."""
        response = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        assert response.success
        assert response.order_id.startswith("PAPER-")

    def test_place_order_sell(self, adapter: PaperAdapter) -> None:
        """place_order() works for sell side."""
        response = adapter.place_order("RELIANCE", "NSE", "SELL", 5)
        assert response.success

    def test_modify_order(self, adapter: PaperAdapter) -> None:
        """modify_order() updates an existing order."""
        response = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        modified = adapter.modify_order(response.order_id, quantity=15)
        assert modified.success

    def test_cancel_order(self, adapter: PaperAdapter) -> None:
        """cancel_order() cancels an existing order."""
        response = adapter.place_order("RELIANCE", "NSE", "BUY", 10)
        cancelled = adapter.cancel_order(response.order_id)
        assert cancelled.success

    def test_modify_nonexistent_order(self, adapter: PaperAdapter) -> None:
        """modify_order() returns failure for unknown order."""
        result = adapter.modify_order("NONEXISTENT")
        assert not result.success

    def test_cancel_nonexistent_order(self, adapter: PaperAdapter) -> None:
        """cancel_order() returns failure for unknown order."""
        result = adapter.cancel_order("NONEXISTENT")
        assert not result.success


class TestPaperAdapterStreaming:
    """Streaming subscription operations."""

    @pytest.fixture
    def adapter(self) -> PaperAdapter:
        adapter = PaperAdapter()
        adapter.connect()
        return adapter

    def test_subscribe_returns_handle(self, adapter: PaperAdapter) -> None:
        """subscribe() returns a stream handle."""
        instrument = MagicMock()
        instrument.symbol = "RELIANCE"
        instrument.exchange = "NSE"

        handle = adapter.subscribe(instrument, MagicMock())
        assert handle is not None

    def test_simulate_tick_triggers_callback(self, adapter: PaperAdapter) -> None:
        """simulate_tick() triggers the registered callback."""
        instrument = MagicMock()
        instrument.symbol = "RELIANCE"
        instrument.exchange = "NSE"

        received = []

        def callback(quote: object) -> None:
            received.append(quote)

        adapter.subscribe(instrument, callback)
        adapter.simulate_tick("RELIANCE", Decimal("2850.50"))

        assert len(received) == 1
        assert received[0].ltp == Decimal("2850.50")

    def test_unsubscribe_stops_callbacks(self, adapter: PaperAdapter) -> None:
        """After unsubscribe, simulate_tick does not trigger callback."""
        instrument = MagicMock()
        instrument.symbol = "RELIANCE"
        instrument.exchange = "NSE"

        received = []

        def callback(quote: object) -> None:
            received.append(quote)

        adapter.subscribe(instrument, callback)
        adapter.unsubscribe(instrument)
        adapter.simulate_tick("RELIANCE", Decimal("2850.50"))

        assert len(received) == 0

    def test_get_candles_returns_empty_list(self, adapter: PaperAdapter) -> None:
        """get_candles() returns empty list (not supported)."""
        from datetime import datetime

        result = adapter.get_candles(
            "RELIANCE",
            "NSE",
            datetime(2025, 1, 1),
            datetime(2025, 1, 31),
            "1D",
        )
        assert result == []
