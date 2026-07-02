"""Tests for DhanMarketFeed and DhanOrderStream — API surface verification."""

from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path for direct pytest invocation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream


class TestDhanMarketFeed:
    """Verify DhanMarketFeed construction and API surface."""

    def test_market_feed_init(self):
        """Construction with client_id, access_token, and instruments must succeed."""
        instruments = [
            (1, "2885", 15),  # NSE_EQ, RELIANCE, Ticker mode
            (1, "2886", 17),  # NSE_EQ, another stock, Quote mode
        ]
        feed = DhanMarketFeed(
            client_id="TEST_CLIENT",
            access_token="TEST_TOKEN",
            instruments=instruments,
        )

        assert feed._instruments == [(1, "2885", 15), (1, "2886", 17)]
        assert feed._context.get_client_id() == "TEST_CLIENT"
        assert feed._context.get_access_token() == "TEST_TOKEN"
        assert feed._feed is None  # SDK feed not created until connect()
        assert feed._thread is None

    def test_market_feed_init_with_resolver(self):
        """Construction with an optional resolver must succeed."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
            resolver="fake_resolver",  # just verifying it's stored
        )
        assert feed._resolver == "fake_resolver"

    def test_is_connected_default_false(self):
        """is_connected must be False before connect() is called."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        assert feed.is_connected is False

    def test_callback_registration_quote(self):
        """on_quote must accept a callable and store it."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )

        received = []
        feed.on_quote(lambda data: received.append(data))

        assert len(feed._quote_callbacks) == 1
        assert callable(feed._quote_callbacks[0])

    def test_callback_registration_depth(self):
        """on_depth must accept a callable and store it."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )

        feed.on_depth(lambda data: None)
        assert len(feed._depth_callbacks) == 1

    def test_multiple_callbacks(self):
        """Multiple callbacks can be registered for the same event."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )

        feed.on_quote(lambda d: None)
        feed.on_quote(lambda d: None)
        feed.on_quote(lambda d: None)

        assert len(feed._quote_callbacks) == 3

    def test_subscribe_before_connect_stores_instruments(self):
        """subscribe() before connect stores instruments for deferred SDK subscription."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )

        feed.subscribe([(1, "2885", 15)])
        assert len(feed._instruments) == 1
        assert feed._instruments[0] == (1, "2885", 15)

    def test_unsubscribe_before_connect_updates_local_state(self):
        """unsubscribe() clears local tracking even when SDK feed is not connected."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        feed.subscribe([(1, "2885", 15)])
        assert len(feed._subscribed_instruments) == 1

        feed.unsubscribe([(1, "2885", 15)])
        assert len(feed._subscribed_instruments) == 0
        assert len(feed._instruments) == 0

    def test_transform_quote_without_resolver(self):
        """_transform_quote must produce a canonical dict even without resolver."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )

        raw = {
            "type": "Quote Data",
            "security_id": 2885,
            "LTP": "2450.50",
            "open": "2440.00",
            "high": "2460.00",
            "low": "2435.00",
            "close": "2445.00",
            "volume": 1234567,
        }

        result = feed._transform_quote(raw)

        assert result["symbol"] == "2885"  # Falls back to security_id
        assert str(result["ltp"]) == "2450.50"
        assert str(result["open"]) == "2440.00"
        assert str(result["high"]) == "2460.00"
        assert str(result["low"]) == "2435.00"
        assert str(result["close"]) == "2445.00"
        assert result["volume"] == 1234567

    def test_transform_depth_without_resolver(self):
        """_transform_depth must produce a canonical dict even without resolver."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )

        raw = {
            "type": "Market Depth",
            "security_id": 2885,
            "LTP": "2450.50",
            "depth": [
                {
                    "bid_quantity": 100,
                    "ask_quantity": 50,
                    "bid_price": "2450.00",
                    "ask_price": "2451.00",
                },
            ],
        }

        result = feed._transform_depth(raw)

        assert result["symbol"] == "2885"
        assert str(result["ltp"]) == "2450.50"
        assert len(result["depth"]["bids"]) == 1
        assert len(result["depth"]["asks"]) == 1
        assert str(result["depth"]["bids"][0]["price"]) == "2450.00"
        assert str(result["depth"]["asks"][0]["price"]) == "2451.00"

    def test_on_message_publishes_tick_event(self):
        from infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
            event_bus=bus,
        )
        feed._on_message(
            None,
            {
                "type": "Quote Data",
                "security_id": 2885,
                "LTP": "2450.50",
                "open": "2440.00",
                "high": "2460.00",
                "low": "2435.00",
                "close": "2445.00",
                "volume": 1234567,
            },
        )
        assert len(received) == 1
        assert received[0].event_type == "TICK"
        assert received[0].payload["quote"].symbol == "2885"

    def test_on_message_publishes_depth_event(self):
        from infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        bus.subscribe("DEPTH", lambda e: received.append(e))
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
            event_bus=bus,
        )
        feed._on_message(
            None,
            {
                "type": "Market Depth",
                "security_id": 2885,
                "LTP": "2450.50",
                "depth": {"bids": [{"price": "2450.00", "quantity": 100, "orders": 5}], "asks": []},
            },
        )
        assert len(received) == 1
        assert received[0].event_type == "DEPTH"


class TestDhanOrderStream:
    """Verify DhanOrderStream construction and API surface."""

    def test_order_stream_init(self):
        """Construction with client_id and access_token must succeed."""
        stream = DhanOrderStream(
            client_id="TEST_CLIENT",
            access_token="TEST_TOKEN",
        )

        assert stream._context.get_client_id() == "TEST_CLIENT"
        assert stream._context.get_access_token() == "TEST_TOKEN"
        assert stream._order_update is None  # SDK object not created until connect()
        assert stream._thread is None

    def test_is_connected_default_false(self):
        """is_connected must be False before connect() is called."""
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert stream.is_connected is False

    def test_callback_registration(self):
        """on_order_update must accept a callable and store it."""
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        received = []
        stream.on_order_update(lambda data: received.append(data))

        assert len(stream._order_callbacks) == 1
        assert callable(stream._order_callbacks[0])

    def test_multiple_order_callbacks(self):
        """Multiple order update callbacks can be registered."""
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        stream.on_order_update(lambda d: None)
        stream.on_order_update(lambda d: None)

        assert len(stream._order_callbacks) == 2

    def test_transform_order(self):
        """_transform_order must produce a canonical dict from SDK data."""
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        raw = {
            "orderNo": "123456789",
            "status": "COMPLETE",
            "tradingSymbol": "RELIANCE",
            "quantity": 10,
            "filledQty": 10,
            "price": "2450.50",
        }

        result = stream._transform_order(raw)

        assert result["order_id"] == "123456789"
        assert result["status"] == "COMPLETE"
        assert result["symbol"] == "RELIANCE"
        assert result["quantity"] == 10
        assert result["filled_quantity"] == 10
        assert str(result["price"]) == "2450.50"

    def test_transform_order_missing_fields(self):
        """_transform_order must handle missing fields gracefully."""
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        result = stream._transform_order({})

        assert result["order_id"] == ""
        assert result["status"] == "UNKNOWN"
        assert result["symbol"] == ""
        assert result["quantity"] == 0
        assert result["filled_quantity"] == 0
        assert str(result["price"]) == "0"

    def test_on_order_update_ignores_non_order_messages(self):
        """_on_order_update should ignore messages without Type=order_alert."""
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )

        received = []
        stream.on_order_update(lambda d: received.append(d))

        # Send a non-order message
        stream._on_order_update({"Type": "heartbeat"})
        assert len(received) == 0

        # Send an empty message
        stream._on_order_update({})
        assert len(received) == 0

        # Send a valid order update
        stream._on_order_update(
            {
                "Type": "order_alert",
                "Data": {
                    "orderNo": "999",
                    "status": "COMPLETE",
                    "tradingSymbol": "INFY",
                    "quantity": 5,
                    "filledQty": 5,
                    "price": "1500.00",
                },
            }
        )
        assert len(received) == 1
        assert received[0]["order_id"] == "999"

    def test_on_order_update_publishes_event(self):
        from infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        bus.subscribe("ORDER_UPDATED", lambda e: received.append(e))
        bus.subscribe("TRADE", lambda e: received.append(e))
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
            event_bus=bus,
        )
        stream._on_order_update(
            {
                "Type": "order_alert",
                "Data": {
                    "orderNo": "999",
                    "status": "COMPLETE",
                    "tradingSymbol": "INFY",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 5,
                    "filledQty": 5,
                    "price": "1500.00",
                    "averagePrice": "1500.00",
                    "productType": "INTRADAY",
                    "orderType": "MARKET",
                    "validity": "DAY",
                },
            }
        )
        assert len(received) == 2
        assert received[0].event_type == "ORDER_UPDATED"
        assert received[0].payload["order"].order_id == "999"
        assert received[1].event_type == "TRADE"

    def test_partial_fill_publishes_incremental_trade_qty(self):
        """Cumulative filledQty from Dhan must map to incremental TRADE qty."""
        from infrastructure.event_bus import EventBus

        bus = EventBus()
        trades = []
        bus.subscribe("TRADE", lambda e: trades.append(e))
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
            event_bus=bus,
        )
        base_data = {
            "Type": "order_alert",
            "Data": {
                "orderNo": "ORD-1",
                "status": "PARTIALLY_FILLED",
                "tradingSymbol": "INFY",
                "exchangeSegment": "NSE_EQ",
                "transactionType": "BUY",
                "quantity": 100,
                "price": "1500.00",
                "averagePrice": "1500.00",
                "productType": "INTRADAY",
                "orderType": "MARKET",
                "validity": "DAY",
            },
        }
        first = {**base_data, "Data": {**base_data["Data"], "filledQty": 40}}
        stream._on_order_update(first)
        assert len(trades) == 1
        assert trades[0].payload["trade"].quantity == 40

        second = {**base_data, "Data": {**base_data["Data"], "filledQty": 100}}
        stream._on_order_update(second)
        assert len(trades) == 2
        assert trades[1].payload["trade"].quantity == 60

    def test_on_order_update_increments_mix_message_count(self):
        """Plan §7.2: DhanOrderStream must use the mixin _note_message_received
        so health() reports the same freshness as every other Dhan WS
        service. Previous implementation set _last_message_at manually
        and never bumped a message counter, so message_count was always 0.
        """
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        assert stream._message_count == 0
        assert stream._last_message_at is None
        stream._on_order_update(
            {
                "Type": "order_alert",
                "Data": {
                    "orderNo": "1",
                    "status": "COMPLETE",
                    "tradingSymbol": "INFY",
                    "quantity": 1,
                    "filledQty": 1,
                    "price": "1500.00",
                    "averagePrice": "1500.00",
                },
            }
        )
        assert stream._message_count == 1
        assert stream._last_message_at is not None

    def test_health_metrics_include_message_count(self):
        stream = DhanOrderStream(
            client_id="CLIENT",
            access_token="TOKEN",
        )
        h = stream.health()
        assert "message_count" in h.metrics
        assert h.metrics["message_count"] == 0


class TestConnectionWiring:
    """Verify DhanConnection exposes market_feed and order_stream."""

    def test_connection_market_feed_default_none(self):
        """DhanConnection.market_feed must be None by default."""
        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.tests.conftest import FakeHttpClient

        conn = DhanConnection(client=FakeHttpClient())
        assert conn.market_feed is None

    def test_connection_order_stream_default_none(self):
        """DhanConnection.order_stream must be None by default."""
        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.tests.conftest import FakeHttpClient

        conn = DhanConnection(client=FakeHttpClient())
        assert conn.order_stream is None

    def test_connection_market_feed_setter(self):
        """DhanConnection.market_feed setter must store the value."""
        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.tests.conftest import FakeHttpClient

        conn = DhanConnection(client=FakeHttpClient())
        feed = DhanMarketFeed("CLIENT", "TOKEN", [])
        conn.market_feed = feed
        assert conn.market_feed is feed

    def test_connection_order_stream_setter(self):
        """DhanConnection.order_stream setter must store the value."""
        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.tests.conftest import FakeHttpClient

        conn = DhanConnection(client=FakeHttpClient())
        stream = DhanOrderStream("CLIENT", "TOKEN")
        conn.order_stream = stream
        assert conn.order_stream is stream


# ---------------------------------------------------------------------------
# PollingMarketFeed tests
# ---------------------------------------------------------------------------


class TestPollingMarketFeed:
    """Verify PollingMarketFeed API surface and behavior."""

    def test_init(self):
        from brokers.dhan.tests.conftest import FakeHttpClient
        from brokers.dhan.websocket import PollingMarketFeed

        client = FakeHttpClient()
        instruments = [("NSE_EQ", "2885", "LTP")]
        feed = PollingMarketFeed(
            http_client=client,
            resolver=None,
            instruments=instruments,
            interval_seconds=1.0,
        )
        assert feed._client is client
        assert feed._instruments == instruments
        assert feed._interval == 1.0
        assert not feed.is_connected

    def test_on_quote_callback_registration(self):
        from brokers.dhan.tests.conftest import FakeHttpClient
        from brokers.dhan.websocket import PollingMarketFeed

        feed = PollingMarketFeed(
            http_client=FakeHttpClient(),
            resolver=None,
            instruments=[("NSE_EQ", "2885", "LTP")],
        )
        ticks = []
        feed.on_quote(lambda t: ticks.append(t))
        assert len(feed._quote_callbacks) == 1

    def test_connect_starts_thread(self):
        import time

        from brokers.dhan.tests.conftest import FakeHttpClient
        from brokers.dhan.websocket import PollingMarketFeed

        feed = PollingMarketFeed(
            http_client=FakeHttpClient(),
            resolver=None,
            instruments=[("NSE_EQ", "2885", "LTP")],
            interval_seconds=0.1,
        )
        feed.connect()
        assert feed.is_connected
        assert feed._thread is not None
        assert feed._thread.is_alive()
        # Clean up
        feed.disconnect()
        time.sleep(0.5)
        assert not feed.is_connected

    def test_disconnect_stops_thread(self):
        import time

        from brokers.dhan.tests.conftest import FakeHttpClient
        from brokers.dhan.websocket import PollingMarketFeed

        feed = PollingMarketFeed(
            http_client=FakeHttpClient(),
            resolver=None,
            instruments=[("NSE_EQ", "2885", "LTP")],
            interval_seconds=0.1,
        )
        feed.connect()
        assert feed.is_connected
        feed.disconnect()
        time.sleep(0.5)
        assert not feed.is_connected

    def test_double_connect_is_safe(self):
        import time

        from brokers.dhan.tests.conftest import FakeHttpClient
        from brokers.dhan.websocket import PollingMarketFeed

        feed = PollingMarketFeed(
            http_client=FakeHttpClient(),
            resolver=None,
            instruments=[("NSE_EQ", "2885", "LTP")],
            interval_seconds=0.1,
        )
        feed.connect()
        thread1 = feed._thread
        feed.connect()  # Should not create a second thread
        assert feed._thread is thread1
        feed.disconnect()
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Backfill tests
# ---------------------------------------------------------------------------


class TestDhanMarketFeedBackfill:
    """Verify reconnect backfill logic."""

    def test_backfill_callback_stored(self):
        """backfill_callback must be stored on construction."""

        def cb(symbol, from_dt, to_dt):
            return []

        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
            backfill_callback=cb,
        )
        assert feed._backfill_callback is cb

    def test_backfill_callback_default_none(self):
        """backfill_callback must default to None."""
        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        assert feed._backfill_callback is None

    def test_track_tick_time(self):
        """_track_tick_time must record latest tick time per symbol."""
        from datetime import datetime

        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        feed._track_tick_time({"symbol": "RELIANCE"})
        assert "RELIANCE" in feed._last_tick_time
        assert isinstance(feed._last_tick_time["RELIANCE"], datetime)

    def test_on_close_records_disconnect_time(self):
        """_on_close must record disconnect_time."""
        from datetime import datetime

        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        feed._on_close(None)
        assert feed._disconnect_time is not None
        assert isinstance(feed._disconnect_time, datetime)

    def test_on_connect_clears_disconnect_time(self):
        """_on_connect must clear disconnect_time after backfill."""
        from datetime import datetime, timezone

        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
        )
        feed._disconnect_time = datetime.now(timezone.utc)
        feed._on_connect(None)
        assert feed._disconnect_time is None

    def test_backfill_calls_callback(self):
        """_backfill_gap must call backfill_callback for each symbol."""
        from datetime import datetime, timezone

        called_with = []

        def backfill(symbol, from_dt, to_dt):
            called_with.append((symbol, from_dt, to_dt))
            return [
                {
                    "symbol": symbol,
                    "ltp": 100,
                    "open": 100,
                    "high": 100,
                    "low": 100,
                    "close": 100,
                    "volume": 1,
                }
            ]

        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
            backfill_callback=backfill,
        )
        now = datetime.now(timezone.utc)
        feed._last_tick_time["RELIANCE"] = now
        feed._backfill_gap(now)
        assert len(called_with) == 1
        assert called_with[0][0] == "RELIANCE"

    def test_backfill_publishes_tick_events(self):
        """_backfill_gap must publish TICK events for backfilled bars."""
        from datetime import datetime, timezone

        from infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        def backfill(symbol, from_dt, to_dt):
            return [
                {
                    "symbol": symbol,
                    "ltp": 100,
                    "open": 100,
                    "high": 100,
                    "low": 100,
                    "close": 100,
                    "volume": 1,
                }
            ]

        feed = DhanMarketFeed(
            client_id="CLIENT",
            access_token="TOKEN",
            instruments=[],
            event_bus=bus,
            backfill_callback=backfill,
        )
        now = datetime.now(timezone.utc)
        feed._last_tick_time["RELIANCE"] = now
        feed._backfill_gap(now)
        assert len(received) == 1
        assert received[0].event_type == "TICK"
        assert received[0].payload["quote"].symbol == "RELIANCE"
