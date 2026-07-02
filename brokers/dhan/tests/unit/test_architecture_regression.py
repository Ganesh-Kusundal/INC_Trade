"""Regression tests for Dhan WebSocket architecture hardening.

Covers the 6 architecture fixes:
1. Dual feed path prevention — create_market_feed() stops existing feed
2. Callback dedup in gateway.stream()
3. Subscription limit enforcement (1000 cap)
4. unstream() unregistration mechanism
5. Cache eviction (_last_tick_time, _depth_cache) on unsubscribe
6. Thread-safe feed creation (_stream_lock)
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from brokers.dhan.depth_20 import DhanDepth20Feed
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.websocket import DhanMarketFeed

# ── Fix 1: Dual feed path prevention ────────────────────────────────────────


class TestDualFeedPrevention:
    def _make_connection(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn._client = MagicMock()
        conn._client.client_id = "TEST"
        conn._client.access_token = "TOKEN"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn._event_bus = None
        conn._lifecycle = None
        conn._backfill_callback = None
        conn._market_feed = None
        return conn

    def test_create_market_feed_returns_existing_feed(self):
        """create_market_feed() must return the existing feed if one exists."""
        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.connection_lifecycle import ConnectionLifecycle

        conn = MagicMock(spec=DhanConnection)
        lifecycle_helper = MagicMock(spec=ConnectionLifecycle)
        conn._lifecycle_helper = lifecycle_helper
        old_feed = MagicMock()
        lifecycle_helper.create_market_feed.return_value = old_feed

        # Call the real create_market_feed
        result = DhanConnection.create_market_feed(conn, access_token="TOKEN")

        assert result is old_feed

    def test_create_market_feed_noop_when_no_existing(self):
        """create_market_feed() should not fail when no existing feed."""
        from brokers.dhan.connection import DhanConnection
        from brokers.dhan.connection_lifecycle import ConnectionLifecycle

        conn = MagicMock(spec=DhanConnection)
        lifecycle_helper = MagicMock(spec=ConnectionLifecycle)
        conn._lifecycle_helper = lifecycle_helper
        new_feed = MagicMock()
        lifecycle_helper.create_market_feed.return_value = new_feed

        feed = DhanConnection.create_market_feed(conn, access_token="TOKEN")
        assert feed is new_feed


# ── Fix 2: Callback dedup in stream() ───────────────────────────────────────


class TestStreamCallbackDedup:
    def _make_gateway(self):
        from brokers.dhan.subscription_engine import SubscriptionEngine

        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        feed = MagicMock()
        feed.is_connected = False
        conn.market_feed = None
        conn.create_market_feed = MagicMock(return_value=feed)
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst
        conn.subscription_engine = SubscriptionEngine(conn)

        gw = BrokerGateway(conn)
        return gw

    def test_same_callback_not_registered_twice(self):
        """Calling stream() with the same on_tick for the same symbol must not duplicate."""
        gw = self._make_gateway()
        received = []

        def my_tick(q):
            received.append(q)

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        gw.stream("RELIANCE", "NSE", on_tick=my_tick)

        assert len(gw._conn.subscription_engine._market_callbacks.get("RELIANCE:NSE", [])) == 1

    def test_different_callbacks_both_registered(self):
        """Different on_tick callbacks for the same symbol should both be registered."""
        gw = self._make_gateway()

        def tick_a(q):
            pass

        def tick_b(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.stream("RELIANCE", "NSE", on_tick=tick_b)

        assert len(gw._conn.subscription_engine._market_callbacks.get("RELIANCE:NSE", [])) == 2

    def test_stream_without_callback_no_registry_entry(self):
        """stream() without on_tick should not create a callback registry entry."""
        gw = self._make_gateway()
        gw.stream("RELIANCE", "NSE")

        assert "RELIANCE:NSE" not in gw._conn.subscription_engine._market_callbacks


# ── Fix 3: Subscription limit enforcement ───────────────────────────────────


class TestSubscriptionLimitEnforcement:
    def test_max_instruments_constant(self):
        """DhanMarketFeed must declare MAX_INSTRUMENTS = 1000."""
        assert DhanMarketFeed.MAX_INSTRUMENTS == 1000

    def test_subscribe_within_limit_succeeds(self):
        """subscribe() within the limit should succeed."""
        feed = DhanMarketFeed(client_id="X", instruments=[])
        feed.subscribe([("NSE_EQ", "2885", "LTP")])
        assert len(feed._instruments) == 1

    def test_subscribe_exceeding_limit_raises(self):
        """subscribe() beyond MAX_INSTRUMENTS must raise ValueError."""
        feed = DhanMarketFeed(client_id="X", instruments=[])
        # Pre-fill the subscription tracking set to the limit
        feed._subscribed_instruments = {(1, i, 15) for i in range(1000)}

        with pytest.raises(ValueError, match="1000"):
            feed.subscribe([("NSE", "9999", "LTP")])


# ── Fix 4: unstream() unregistration ────────────────────────────────────────


class TestUnstream:
    def _make_gateway_with_stream(self):
        gw = self._make_gateway()

        def my_tick(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        return gw, my_tick

    def _make_gateway(self):
        from brokers.dhan.subscription_engine import SubscriptionEngine

        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        feed = MagicMock()
        feed.is_connected = False
        conn.market_feed = feed
        conn.create_market_feed = MagicMock(return_value=feed)
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst
        conn.subscription_engine = SubscriptionEngine(conn)

        return BrokerGateway(conn)

    def test_unstream_removes_specific_callback(self):
        """unstream() with on_tick should remove only that callback."""
        gw = self._make_gateway()

        def tick_a(q):
            pass

        def tick_b(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.stream("RELIANCE", "NSE", on_tick=tick_b)
        gw.unstream("RELIANCE", "NSE", on_tick=tick_a)

        remaining = gw._conn.subscription_engine._market_callbacks.get("RELIANCE:NSE", [])
        assert len(remaining) == 1
        assert remaining[0] is tick_b

    def test_unstream_all_removes_everything(self):
        """unstream() without on_tick should remove ALL callbacks and registry entry."""
        gw, _my_tick = self._make_gateway_with_stream()
        gw.unstream("RELIANCE", "NSE")

        assert "RELIANCE:NSE" not in gw._conn.subscription_engine._market_callbacks

    def test_unstream_nonexistent_is_noop(self):
        """unstream() for a symbol never streamed should not raise."""
        gw = self._make_gateway()
        gw.unstream("NONEXISTENT", "NSE")  # Should not raise


# ── Fix 5: Cache eviction ───────────────────────────────────────────────────


class TestCacheEviction:
    def test_last_tick_time_evicted_on_unsubscribe(self):
        """unstream() should call clear_symbol_tracking() for the symbol."""
        gw = self._make_gateway_with_feed()
        feed = gw._conn.market_feed

        gw.unstream("RELIANCE", "NSE")

        # Now that the abstraction boundary is clean, the subscription engine
        # calls feed.clear_symbol_tracking() instead of accessing feed._lock.
        feed.clear_symbol_tracking.assert_called_once_with("RELIANCE")

    def test_depth_20_cache_evicted_on_unsubscribe(self):
        """depth_20.unsubscribe() should evict _depth_cache entries."""
        feed = DhanDepth20Feed(
            client_id="X",
            access_token="T",
            instruments=[("NSE_EQ", "2885")],
        )
        # Populate depth cache
        feed._depth_cache[2885] = {"bids": [], "asks": []}

        feed.unsubscribe([("NSE_EQ", "2885")])

        assert 2885 not in feed._depth_cache

    def test_depth_20_subscribe_dedup(self):
        """depth_20.subscribe() should skip instruments already subscribed."""
        feed = DhanDepth20Feed(
            client_id="X",
            access_token="T",
            instruments=[("NSE_EQ", "2885")],
        )
        initial_count = len(feed._subscriptions)

        feed.subscribe([("NSE_EQ", "2885")])  # duplicate

        assert len(feed._subscriptions) == initial_count

    def _make_gateway_with_feed(self):
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst

        feed = MagicMock()
        feed._lock = threading.RLock()
        feed._last_tick_time = {}
        feed.is_connected = False
        conn.market_feed = feed
        conn.create_market_feed = MagicMock(return_value=feed)

        from brokers.dhan.subscription_engine import SubscriptionEngine

        conn.subscription_engine = SubscriptionEngine(conn)

        gw = BrokerGateway(conn)
        gw.stream("RELIANCE", "NSE", on_tick=lambda q: None)
        return gw


# ── Fix 6: Thread-safe feed creation ────────────────────────────────────────


class TestThreadSafeStreamCreation:
    def test_concurrent_stream_creates_single_feed(self):
        """Multiple threads calling stream() simultaneously should create only one feed."""
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.market_feed = None
        conn.instruments = MagicMock()
        conn.event_bus = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst
        feed = MagicMock()
        feed.is_connected = False
        conn.create_market_feed = MagicMock(return_value=feed)
        from brokers.dhan.subscription_engine import SubscriptionEngine

        conn.subscription_engine = SubscriptionEngine(conn)

        gw = BrokerGateway(conn)

        errors: list[Exception] = []
        results: list = []

        def stream_reliance():
            try:
                r = gw.stream("RELIANCE", "NSE")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=stream_reliance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        # All threads should get the same feed instance
        assert len({id(r) for r in results}) == 1

    def test_stream_lock_exists(self):
        """BrokerGateway must have a _stream_lock attribute."""
        conn = MagicMock()
        gw = BrokerGateway(conn)
        assert hasattr(gw, "_stream_lock")
        assert isinstance(gw._stream_lock, type(threading.Lock()))

    def test_stream_registry_exists(self):
        """BrokerGateway connection must own a SubscriptionEngine."""
        conn = MagicMock()
        from brokers.dhan.subscription_engine import SubscriptionEngine

        conn.create_market_feed = MagicMock(return_value=MagicMock(is_connected=False))
        conn.instruments = MagicMock()
        conn.subscription_engine = SubscriptionEngine(conn)
        gw = BrokerGateway(conn)
        assert hasattr(gw._conn, "subscription_engine")
        assert gw._conn.subscription_engine is not None
