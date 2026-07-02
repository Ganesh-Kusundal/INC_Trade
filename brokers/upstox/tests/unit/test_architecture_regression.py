"""Regression tests for Upstox WebSocket architecture hardening.

Covers the 3 architecture fixes:
1. Callback dedup + stream lock in gateway.stream()
2. unstream() unregistration with listener removal
3. Cache eviction (_last_tick_time) on unsubscribe
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from brokers.upstox.gateway import UpstoxBrokerGateway
from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer


def _fake_authorizer() -> UpstoxFeedAuthorizer:
    http = MagicMock()
    http.get_json.return_value = {"data": {"authorized_redirect_uri": "wss://x"}}
    urls = MagicMock()
    urls.feed_authorize_v3_url.return_value = "https://x/authorize"
    return UpstoxFeedAuthorizer(http, urls)


def _make_multiplexer() -> UpstoxMarketDataV3Multiplexer:
    return UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())


def _make_gateway_with_mock_broker() -> UpstoxBrokerGateway:
    broker = MagicMock()
    ws = _make_multiplexer()
    broker.market_data_websocket = ws
    broker.instrument_resolver = MagicMock()
    broker.instrument_resolver.resolve.return_value = None
    return UpstoxBrokerGateway(broker)


# ── Fix 1: Callback dedup + stream lock ─────────────────────────────────────


class TestUpstoxStreamCallbackDedup:
    def test_stream_registry_initialized(self):
        """Gateway must have _stream_registry and _stream_lock on construction."""
        gw = _make_gateway_with_mock_broker()
        assert hasattr(gw, "_stream_registry")
        assert isinstance(gw._stream_registry, dict)
        assert hasattr(gw, "_stream_lock")
        assert isinstance(gw._stream_lock, type(threading.Lock()))

    def test_same_callback_not_registered_twice(self):
        """Calling stream() with the same on_tick for the same instrument must dedup."""
        gw = _make_gateway_with_mock_broker()
        ws = gw._broker.market_data_websocket
        ws._connected = True  # Avoid connect path

        def my_tick(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        initial_count = len(ws._listeners)

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        assert len(ws._listeners) == initial_count  # No new listener added

    def test_different_callbacks_both_registered(self):
        """Different on_tick callbacks for the same symbol should both register."""
        gw = _make_gateway_with_mock_broker()
        ws = gw._broker.market_data_websocket
        ws._connected = True

        def tick_a(q):
            pass

        def tick_b(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.stream("RELIANCE", "NSE", on_tick=tick_b)

        # The key is constructed as f"{segment_to_wire(exchange)}|{symbol}"
        # segment_to_wire("NSE") returns "NSE"
        inst_key = "NSE_EQ|RELIANCE"
        assert len(gw._stream_registry[inst_key]) == 2


# ── Fix 2: unstream() unregistration ────────────────────────────────────────


class TestUpstoxUnstream:
    def test_unstream_removes_specific_callback(self):
        """unstream() with on_tick removes only that callback."""
        gw = _make_gateway_with_mock_broker()
        ws = gw._broker.market_data_websocket
        ws._connected = True

        def tick_a(q):
            pass

        def tick_b(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.stream("RELIANCE", "NSE", on_tick=tick_b)
        gw.unstream("RELIANCE", "NSE", on_tick=tick_a)

        inst_key = "NSE_EQ|RELIANCE"
        remaining = gw._stream_registry.get(inst_key, [])
        assert len(remaining) == 1
        assert remaining[0][0] is tick_b

    def test_unstream_all_removes_everything(self):
        """unstream() without on_tick removes ALL callbacks and registry entry."""
        gw = _make_gateway_with_mock_broker()
        ws = gw._broker.market_data_websocket
        ws._connected = True

        def tick_a(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=tick_a)
        gw.unstream("RELIANCE", "NSE")

        inst_key = "NSE_EQ|RELIANCE"
        assert inst_key not in gw._stream_registry

    def test_unstream_removes_listener_from_multiplexer(self):
        """unstream() must call ws.remove_listener() for the wrapped listener."""
        gw = _make_gateway_with_mock_broker()
        ws = gw._broker.market_data_websocket
        ws._connected = True

        def my_tick(q):
            pass

        gw.stream("RELIANCE", "NSE", on_tick=my_tick)
        assert len(ws._listeners) == 1

        gw.unstream("RELIANCE", "NSE", on_tick=my_tick)
        assert len(ws._listeners) == 0

    def test_unstream_nonexistent_is_noop(self):
        """unstream() for an instrument never streamed should not raise."""
        gw = _make_gateway_with_mock_broker()
        gw.unstream("NONEXISTENT", "NSE")  # Should not raise


# ── Fix 3: Cache eviction on unsubscribe ────────────────────────────────────


class TestUpstoxCacheEviction:
    def test_last_tick_time_evicted_on_unsubscribe(self):
        """unsubscribe() must remove _last_tick_time entries."""
        mux = _make_multiplexer()
        key = "NSE_EQ|INE002A01018"

        from datetime import datetime, timezone

        mux._last_tick_time[key] = datetime.now(timezone.utc)
        mux._subscribed.add(key)

        mux.unsubscribe([key])

        assert key not in mux._last_tick_time
        assert key not in mux._subscribed

    def test_unsubscribe_multiple_keys_evicts_all(self):
        """unsubscribe() with multiple keys must evict all their cache entries."""
        mux = _make_multiplexer()
        keys = ["NSE_EQ|INE002A01018", "NSE_EQ|INE062A01020", "NSE_FNO|12345"]

        from datetime import datetime, timezone

        for k in keys:
            mux._last_tick_time[k] = datetime.now(timezone.utc)
            mux._subscribed.add(k)

        mux.unsubscribe(keys)

        for k in keys:
            assert k not in mux._last_tick_time
            assert k not in mux._subscribed

    def test_unsubscribe_nonexistent_key_is_noop(self):
        """unsubscribe() for a key never subscribed should not raise."""
        mux = _make_multiplexer()
        mux.unsubscribe(["NONEXISTENT_KEY"])  # Should not raise

    def test_subscribed_set_cleaned_on_unsubscribe(self):
        """_subscribed set must not retain unsubscribed keys."""
        mux = _make_multiplexer()
        key = "NSE_EQ|INE002A01018"
        mux._subscribed.add(key)

        mux.unsubscribe([key])

        assert key not in mux._subscribed


# ── Subscription manager dedup (pre-existing, guarded by regression) ────────


class TestUpstoxSubscriptionManagerRegression:
    def test_subscribe_same_key_same_mode_is_noop(self):
        """Subscribing the same key in the same mode must not increase count."""
        from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionManager

        mgr = UpstoxV3SubscriptionManager()
        mgr.subscribe(["NSE_EQ|INE002A01018"], "ltpc")
        count_before = mgr.ltpc_count()

        mgr.subscribe(["NSE_EQ|INE002A01018"], "ltpc")
        assert mgr.ltpc_count() == count_before

    def test_subscribe_mode_change_moves_key(self):
        """Changing a key's mode must remove it from old mode and add to new."""
        from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionManager

        mgr = UpstoxV3SubscriptionManager()
        key = "NSE_EQ|INE002A01018"
        mgr.subscribe([key], "ltpc")
        assert mgr.ltpc_count() == 1

        mgr.subscribe([key], "full")
        assert mgr.ltpc_count() == 0
        assert mgr.full_count() == 1

    def test_unsubscribe_removes_from_manager(self):
        """unsubscribe() must remove the key from the manager."""
        from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionManager

        mgr = UpstoxV3SubscriptionManager()
        key = "NSE_EQ|INE002A01018"
        mgr.subscribe([key], "ltpc")
        mgr.unsubscribe([key])

        assert mgr.ltpc_count() == 0
        assert mgr.total_subscriptions() == 0

    def test_limit_enforcement_raises(self):
        """Exceeding per-mode limit must raise SubscriptionLimitExceeded."""
        from brokers.upstox.websocket.v3_subscription_manager import (
            SubscriptionLimitExceededError,
            UpstoxV3SubscriptionLimits,
            UpstoxV3SubscriptionManager,
        )

        limits = UpstoxV3SubscriptionLimits(d30_individual=2)
        mgr = UpstoxV3SubscriptionManager(limits=limits)

        mgr.subscribe(["K1", "K2"], "full_d30")
        with pytest.raises(SubscriptionLimitExceededError):
            mgr.subscribe(["K3"], "full_d30")


# ── Thread safety regression guards ────────────────────────────────────────


class TestUpstoxThreadSafetyRegression:
    def test_concurrent_listener_add_remove(self):
        """Concurrent add_listener/remove_listener must not corrupt state."""
        mux = _make_multiplexer()
        listeners = [lambda _e, _p: None for _ in range(100)]
        errors: list[Exception] = []

        def add_all():
            for listener in listeners:
                try:
                    mux.add_listener(listener)
                except Exception as e:
                    errors.append(e)

        def remove_all():
            for listener in listeners:
                try:
                    mux.remove_listener(listener)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=add_all)
        t2 = threading.Thread(target=remove_all)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors

    def test_concurrent_subscribe_unsubscribe(self):
        """Concurrent subscribe/unsubscribe must not corrupt subscription manager."""
        from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionManager

        mgr = UpstoxV3SubscriptionManager()
        keys = [f"NSE_EQ|{i}" for i in range(50)]
        errors: list[Exception] = []

        def sub_all():
            try:
                mgr.subscribe(keys, "ltpc")
            except Exception as e:
                errors.append(e)

        def unsub_all():
            try:
                mgr.unsubscribe(keys)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=sub_all)
        t2 = threading.Thread(target=unsub_all)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        # Final state is valid (either all subscribed or some subset)
        assert mgr.total_subscriptions() >= 0
