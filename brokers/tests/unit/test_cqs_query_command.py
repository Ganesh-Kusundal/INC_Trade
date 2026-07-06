"""Tests for MarketDataQuery (CQS query side) and OrderCommand (CQS command side)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from inc_trade.market.instrument import Instrument
from inc_trade.market.order import OrderCommand
from inc_trade.market.query import MarketDataQuery

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def equity() -> Instrument:
    return Instrument(symbol="RELIANCE", exchange="NSE", lot_size=1, tick_size=Decimal("0.05"))


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.quote.return_value = {"symbol": "RELIANCE", "ltp": 2850.50}
    provider.ltp.return_value = Decimal("2850.50")
    provider.depth.return_value = {"bids": [], "asks": []}
    return provider


@pytest.fixture
def mock_order_provider() -> MagicMock:
    provider = MagicMock()
    provider.place_order.return_value = {"order_id": "12345", "status": "PENDING"}
    return provider


# ── MarketDataQuery Tests ───────────────────────────────────────────────


class TestMarketDataQuery:
    """Tests for MarketDataQuery — CQS query side."""

    def test_quote_delegates_to_provider(
        self, equity: Instrument, mock_provider: MagicMock
    ) -> None:
        query = MarketDataQuery(equity, provider=mock_provider)
        result = query.quote()
        mock_provider.quote.assert_called_once_with("RELIANCE", "NSE")
        assert result == {"symbol": "RELIANCE", "ltp": 2850.50}

    def test_ltp_delegates_to_provider(self, equity: Instrument, mock_provider: MagicMock) -> None:
        query = MarketDataQuery(equity, provider=mock_provider)
        result = query.ltp()
        mock_provider.ltp.assert_called_once_with("RELIANCE", "NSE")
        assert result == Decimal("2850.50")

    def test_depth_delegates_to_provider(
        self, equity: Instrument, mock_provider: MagicMock
    ) -> None:
        query = MarketDataQuery(equity, provider=mock_provider)
        result = query.depth(levels=5)
        mock_provider.depth.assert_called_once_with("RELIANCE", "NSE", 5)
        assert result == {"bids": [], "asks": []}

    def test_depth_uses_dedicated_depth_provider(self, equity: Instrument) -> None:
        depth_provider = MagicMock()
        depth_provider.depth.return_value = {"bids": [{"price": 100}], "asks": [{"price": 101}]}
        query = MarketDataQuery(equity, depth_provider=depth_provider)
        result = query.depth(levels=200)
        depth_provider.depth.assert_called_once_with("RELIANCE", "NSE", 200)
        assert result == {"bids": [{"price": 100}], "asks": [{"price": 101}]}

    def test_depth_falls_back_to_instrument_provider(
        self, equity: Instrument, mock_provider: MagicMock
    ) -> None:
        equity.with_providers(provider=mock_provider)
        query = MarketDataQuery(equity)  # No explicit provider
        result = query.depth(levels=5)
        mock_provider.depth.assert_called_once_with("RELIANCE", "NSE", 5)
        assert result == {"bids": [], "asks": []}

    def test_quote_raises_without_provider(self, equity: Instrument) -> None:
        query = MarketDataQuery(equity)  # No provider at all
        with pytest.raises(RuntimeError, match="No market data context"):
            query.quote()

    def test_subscribe_delegates_to_streaming(self, equity: Instrument) -> None:
        streaming = MagicMock()
        streaming.subscribe.return_value = "handle_123"
        callback = MagicMock()
        query = MarketDataQuery(equity, streaming_provider=streaming)
        result = query.subscribe(callback)
        streaming.subscribe.assert_called_once_with(equity, callback)
        assert result == "handle_123"

    def test_snapshot_returns_quote(self, equity: Instrument, mock_provider: MagicMock) -> None:
        query = MarketDataQuery(equity, provider=mock_provider)
        result = query.snapshot()
        assert result == {"symbol": "RELIANCE", "ltp": 2850.50}

    def test_instrument_property(self, equity: Instrument) -> None:
        query = MarketDataQuery(equity)
        assert query.instrument is equity

    def test_historical_uses_dedicated_provider(self, equity: Instrument) -> None:
        historical = MagicMock()
        historical.get_candles.return_value = [{"open": 100, "close": 101}]
        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 2)
        query = MarketDataQuery(equity, historical_provider=historical)
        result = query.ohlcv(start_time=start, end_time=end, resolution="1")
        historical.get_candles.assert_called_once_with(
            symbol="RELIANCE", exchange="NSE", start_time=start, end_time=end, resolution="1"
        )
        assert result == [{"open": 100, "close": 101}]

    def test_history_alias(self, equity: Instrument) -> None:
        historical = MagicMock()
        historical.get_candles.return_value = [{"open": 100}]
        query = MarketDataQuery(equity, historical_provider=historical)
        result = query.history(
            start_time=datetime(2025, 1, 1),
            end_time=datetime(2025, 1, 2),
            resolution="1D",
        )
        historical.get_candles.assert_called_once()
        assert result == [{"open": 100}]


# ── OrderCommand Tests ───────────────────────────────────────────────────


class TestOrderCommand:
    """Tests for OrderCommand — CQS command side."""

    def test_buy_delegates_to_order_provider(
        self, equity: Instrument, mock_order_provider: MagicMock
    ) -> None:
        cmd = OrderCommand(equity, order_provider=mock_order_provider)
        result = cmd.buy(quantity=10)
        mock_order_provider.place_order.assert_called_once()
        call_kwargs = mock_order_provider.place_order.call_args[1]
        assert call_kwargs["symbol"] == "RELIANCE"
        assert call_kwargs["exchange"] == "NSE"
        assert call_kwargs["side"] == "BUY"
        assert call_kwargs["quantity"] == 10
        assert result == {"order_id": "12345", "status": "PENDING"}

    def test_sell_delegates_to_order_provider(
        self, equity: Instrument, mock_order_provider: MagicMock
    ) -> None:
        cmd = OrderCommand(equity, order_provider=mock_order_provider)
        result = cmd.sell(quantity=5)
        mock_order_provider.place_order.assert_called_once()
        call_kwargs = mock_order_provider.place_order.call_args[1]
        assert call_kwargs["side"] == "SELL"
        assert call_kwargs["quantity"] == 5
        assert result == {"order_id": "12345", "status": "PENDING"}

    def test_buy_falls_back_to_instrument_order_provider(self, equity: Instrument) -> None:
        provider = MagicMock()
        provider.place_order.return_value = {"order_id": "67890"}
        equity.with_providers(order_provider=provider)
        cmd = OrderCommand(equity)  # No explicit provider
        result = cmd.buy(quantity=10)
        assert result == {"order_id": "67890"}

    def test_buy_raises_without_provider(self, equity: Instrument) -> None:
        cmd = OrderCommand(equity)  # No provider at all
        with pytest.raises(RuntimeError, match="No order provider"):
            cmd.buy(quantity=10)

    def test_sell_raises_without_provider(self, equity: Instrument) -> None:
        cmd = OrderCommand(equity)
        with pytest.raises(RuntimeError, match="No order provider"):
            cmd.sell(quantity=10)

    def test_instrument_property(self, equity: Instrument) -> None:
        cmd = OrderCommand(equity)
        assert cmd.instrument is equity

    def test_buy_passes_kwargs(self, equity: Instrument, mock_order_provider: MagicMock) -> None:
        cmd = OrderCommand(equity, order_provider=mock_order_provider)
        cmd.buy(quantity=10, product_type="INTRADAY", validity="DAY")
        call_kwargs = mock_order_provider.place_order.call_args[1]
        assert call_kwargs["product_type"] == "INTRADAY"
        assert call_kwargs["validity"] == "DAY"

    def test_buy_default_order_type(
        self, equity: Instrument, mock_order_provider: MagicMock
    ) -> None:
        cmd = OrderCommand(equity, order_provider=mock_order_provider)
        cmd.buy(quantity=10)
        call_kwargs = mock_order_provider.place_order.call_args[1]
        from inc_trade.domain.enums import OrderType

        assert call_kwargs["order_type"] == OrderType.MARKET


# ── Event Publishing Tests ───────────────────────────────────────────────────


class TestMarketDataQueryEvents:
    """Tests for event publishing in MarketDataQuery."""

    def test_subscribe_publishes_quote_event(self, equity: Instrument) -> None:
        """When event_publisher is set, subscribe wraps the callback to publish events."""
        from unittest.mock import MagicMock

        from inc_trade.domain.events import QuoteTickEvent

        event_publisher = MagicMock()
        streaming = MagicMock()
        streaming.broker_id = "mock"
        streaming.subscribe.return_value = "handle_123"
        user_callback = MagicMock()

        query = MarketDataQuery(
            equity,
            streaming_provider=streaming,
            event_publisher=event_publisher,
        )

        # Subscribe with event publishing
        result = query.subscribe(user_callback)
        assert result == "handle_123"

        # Verify the streaming provider was called with a wrapper
        assert streaming.subscribe.call_count == 1
        call_args = streaming.subscribe.call_args[0]
        assert call_args[0] is equity  # instrument
        assert call_args[1] is not user_callback  # wrapper, not the original

        # Simulate a tick arriving — the wrapper should publish event + call user
        fake_quote = MagicMock()
        fake_quote.ltp = "2850.50"
        fake_quote.bid = "2850.00"
        fake_quote.ask = "2851.00"
        fake_quote.volume = 1000
        fake_quote.oi = 5000

        call_args[1](fake_quote)  # invoke the wrapper

        # Event should have been published
        assert event_publisher.publish.call_count == 1
        published_event = event_publisher.publish.call_args[0][0]
        assert isinstance(published_event, QuoteTickEvent)
        assert published_event.symbol == "RELIANCE"
        assert published_event.exchange == "NSE"

        # User callback should have been called
        user_callback.assert_called_once_with(fake_quote)

    def test_subscribe_no_event_publisher(self, equity: Instrument) -> None:
        """Without event_publisher, subscribe works normally."""
        streaming = MagicMock()
        streaming.subscribe.return_value = "handle_456"
        user_callback = MagicMock()

        query = MarketDataQuery(
            equity,
            streaming_provider=streaming,
            event_publisher=None,  # No event publishing
        )

        result = query.subscribe(user_callback)
        assert result == "handle_456"

        # Verify the streaming provider was called with the ORIGINAL callback
        call_args = streaming.subscribe.call_args[0]
        assert call_args[1] is user_callback  # No wrapper
