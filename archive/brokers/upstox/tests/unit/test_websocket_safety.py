"""Concurrency safety tests for Upstox WebSocket components.

Mirrors Phase 1 of the TradeXV2 concurrency hardening roadmap: listener
snapshotting, cross-thread listener mutations, and subscription-manager
synchronisation.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from unittest.mock import MagicMock

from brokers.upstox.websocket.feed_authorizer import UpstoxFeedAuthorizer
from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer
from brokers.upstox.websocket.portfolio_stream import UpstoxPortfolioStream
from brokers.upstox.websocket.v3_subscription_manager import UpstoxV3SubscriptionManager


class _FakeSocket:
    """A controllable fake WebSocket for read-loop tests."""

    def __init__(self, messages: list[Any]) -> None:
        self.messages = list(messages)
        self.closed = False
        self._idx = 0

    async def recv(self) -> Any:
        await asyncio.sleep(0)
        if self._idx >= len(self.messages):
            raise asyncio.CancelledError(" drained")
        msg = self.messages[self._idx]
        self._idx += 1
        return msg

    def close(self) -> None:
        self.closed = True


def _fake_authorizer() -> UpstoxFeedAuthorizer:
    http = MagicMock()
    http.get_json.return_value = {"data": {"authorized_redirect_uri": "wss://x"}}
    urls = MagicMock()
    urls.feed_authorize_v3_url.return_value = "https://x/authorize"
    urls.portfolio_stream_authorize_url.return_value = "https://x/portfolio"
    return UpstoxFeedAuthorizer(http, urls)


class TestUpstoxMarketDataV3MultiplexerSafety:
    def test_is_connected_reflects_socket_state(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        assert not mux.is_connected
        mux._connected = True
        mux._stopped = False
        assert mux.is_connected
        mux._stopped = True
        assert not mux.is_connected

    def test_listener_add_remove_is_thread_safe(self):
        mux = UpstoxMarketDataV3Multiplexer(authorizer=_fake_authorizer())
        listeners = [lambda _e, _p: None for _ in range(200)]
        errors: list[Exception] = []

        def add_all() -> None:
            for listener in listeners:
                try:
                    mux.add_listener(listener)
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(exc)

        def remove_all() -> None:
            for listener in listeners:
                try:
                    mux.remove_listener(listener)
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(exc)

        t_add = threading.Thread(target=add_all)
        t_remove = threading.Thread(target=remove_all)
        t_add.start()
        t_remove.start()
        t_add.join()
        t_remove.join()

        assert not errors
        # Listeners remaining should be a subset of the original set.
        assert all(listener in listeners for listener in mux._listeners)

    async def test_read_loop_snapshots_listeners(self):
        """A listener added while dispatching must not be invoked until the next snapshot."""
        mux = UpstoxMarketDataV3Multiplexer(
            authorizer=_fake_authorizer(),
            socket_factory=lambda _url: _FakeSocket(
                [
                    '{"type":"market_info","data":{}}',
                ]
            ),
        )

        first_calls: list[tuple[str, Any]] = []
        second_calls: list[tuple[str, Any]] = []

        def first(_event_type: str, payload: Any) -> None:
            first_calls.append((_event_type, payload))
            mux.add_listener(second)

        def second(_event_type: str, payload: Any) -> None:
            second_calls.append((_event_type, payload))

        mux.add_listener(first)
        await mux.connect()
        # Give the read loop time to process the single message and then stop.
        await asyncio.sleep(0.1)
        await mux.disconnect()

        assert len(first_calls) == 1
        assert len(second_calls) == 0

    async def test_listener_invoked_with_event_type_and_payload(self):
        mux = UpstoxMarketDataV3Multiplexer(
            authorizer=_fake_authorizer(),
            socket_factory=lambda _url: _FakeSocket(
                [
                    '{"type":"market_info","exchange":"NSE"}',
                ]
            ),
        )

        received: list[tuple[str, Any]] = []
        mux.add_listener(lambda event_type, payload: received.append((event_type, payload)))
        await mux.connect()
        await asyncio.sleep(0.1)
        await mux.disconnect()

        assert len(received) == 1
        event_type, payload = received[0]
        assert event_type == "market_info"
        assert payload.get("exchange") == "NSE"

    async def test_connect_awaits_coroutine_socket_factory(self):
        """Production websockets.connect returns an awaitable; connect() must await it."""

        async def factory(_url: str) -> _FakeSocket:
            return _FakeSocket(['{"type":"market_info","exchange":"NSE"}'])

        mux = UpstoxMarketDataV3Multiplexer(
            authorizer=_fake_authorizer(),
            socket_factory=factory,
        )
        await mux.connect()
        assert mux.is_connected
        assert hasattr(mux._socket, "recv")
        await mux.disconnect()

    def test_concurrent_subscribe_unsubscribe_stays_consistent(self):
        manager = UpstoxV3SubscriptionManager()
        keys = [f"NSE_EQ|INFY{i}" for i in range(100)]
        errors: list[Exception] = []

        def flipper() -> None:
            for key in keys:
                try:
                    manager.subscribe([key], "ltpc")
                    manager.unsubscribe([key])
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(exc)

        threads = [threading.Thread(target=flipper) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert manager.total_subscriptions() == 0
        assert manager.active_categories() == []
        for key in keys:
            assert manager.mode_for(key) == ""

    def test_counts_are_consistent_under_concurrent_reads(self):
        manager = UpstoxV3SubscriptionManager()
        keys = [f"NSE_EQ|INFY{i}" for i in range(50)]
        manager.subscribe(keys, "ltpc")
        results: list[int] = []

        def reader() -> None:
            for _ in range(100):
                results.append(manager.total_subscriptions())
                results.append(manager.ltpc_count())

        def writer() -> None:
            for key in keys[25:]:
                manager.unsubscribe([key])
                manager.subscribe([key], "ltpc")

        t_reader = threading.Thread(target=reader)
        t_writer = threading.Thread(target=writer)
        t_reader.start()
        t_writer.start()
        t_reader.join()
        t_writer.join()

        assert all(count >= 0 for count in results)
        assert manager.total_subscriptions() == len(keys)
        assert manager.ltpc_count() == len(keys)


class TestUpstoxPortfolioStreamSafety:
    def test_is_connected_reflects_socket_state(self):
        stream = UpstoxPortfolioStream(authorizer=_fake_authorizer())
        assert not stream.is_connected
        stream._connected = True
        stream._stopped = False
        assert stream.is_connected
        stream._stopped = True
        assert not stream.is_connected

    def test_listener_add_remove_is_thread_safe(self):
        stream = UpstoxPortfolioStream(authorizer=_fake_authorizer())
        listeners = [lambda _e, _p: None for _ in range(200)]
        errors: list[Exception] = []

        def add_all() -> None:
            for listener in listeners:
                try:
                    stream.add_listener(listener)
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(exc)

        def remove_all() -> None:
            for listener in listeners:
                try:
                    stream.remove_listener(listener)
                except Exception as exc:  # pragma: no cover - defensive
                    errors.append(exc)

        t_add = threading.Thread(target=add_all)
        t_remove = threading.Thread(target=remove_all)
        t_add.start()
        t_remove.start()
        t_add.join()
        t_remove.join()

        assert not errors
        assert all(listener in listeners for listener in stream._listeners)

    async def test_read_loop_snapshots_listeners(self):
        stream = UpstoxPortfolioStream(
            authorizer=_fake_authorizer(),
            socket_factory=lambda _url: _FakeSocket(
                [
                    '{"type":"order","data":{"id":"1"}}',
                ]
            ),
        )

        first_calls: list[tuple[str, Any]] = []
        second_calls: list[tuple[str, Any]] = []

        def first(event_type: str, payload: Any) -> None:
            first_calls.append((event_type, payload))
            stream.add_listener(second)

        def second(event_type: str, payload: Any) -> None:
            second_calls.append((event_type, payload))

        stream.add_listener(first)
        await stream.connect()
        await asyncio.sleep(0.1)
        await stream.disconnect()

        assert len(first_calls) == 1
        assert len(second_calls) == 0

    async def test_listener_invoked_with_event_type_and_payload(self):
        stream = UpstoxPortfolioStream(
            authorizer=_fake_authorizer(),
            socket_factory=lambda _url: _FakeSocket(
                [
                    '{"type":"position","data":{"symbol":"INFY"}}',
                ]
            ),
        )

        received: list[tuple[str, Any]] = []
        stream.add_listener(lambda event_type, payload: received.append((event_type, payload)))
        await stream.connect()
        await asyncio.sleep(0.1)
        await stream.disconnect()

        assert len(received) == 1
        event_type, payload = received[0]
        assert event_type == "position"
        assert payload.get("symbol") == "INFY"

    async def test_read_loop_publishes_order_event_to_event_bus(self):
        from infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        bus.subscribe("ORDER_UPDATED", lambda e: received.append(e))

        stream = UpstoxPortfolioStream(
            authorizer=_fake_authorizer(),
            socket_factory=lambda _url: _FakeSocket(
                [
                    '{"type":"order","data":{"order_id":"O1","symbol":"INFY"}}',
                ]
            ),
            event_bus=bus,
        )

        await stream.connect()
        await asyncio.sleep(0.1)
        await stream.disconnect()

        assert len(received) == 1
        assert received[0].event_type == "ORDER_UPDATED"
        order = received[0].payload["order"]
        assert order.order_id == "O1"
        assert order.symbol == "INFY"

    async def test_read_loop_publishes_incremental_trade_on_partial_fill(self):
        from infrastructure.event_bus import EventBus

        bus = EventBus()
        trades = []
        bus.subscribe("TRADE", lambda e: trades.append(e))
        stream = UpstoxPortfolioStream(
            authorizer=_fake_authorizer(),
            socket_factory=lambda _url: _FakeSocket(
                [
                    '{"type":"order","data":{"order_id":"O1","trading_symbol":"INFY","exchange":"NSE","transaction_type":"BUY","quantity":100,"filled_quantity":40,"average_price":"1500","order_type":"MARKET","product":"I","validity":"DAY","status":"open"}}',
                    '{"type":"order","data":{"order_id":"O1","trading_symbol":"INFY","exchange":"NSE","transaction_type":"BUY","quantity":100,"filled_quantity":100,"average_price":"1500","order_type":"MARKET","product":"I","validity":"DAY","status":"complete"}}',
                ]
            ),
            event_bus=bus,
        )
        await stream.connect()
        await asyncio.sleep(0.15)
        await stream.disconnect()
        assert len(trades) == 2
        assert trades[0].payload["trade"].quantity == 40
        assert trades[1].payload["trade"].quantity == 60
