"""Contract tests — StreamingRouter contract.

Verifies priority-based backend selection, fallback on failure,
subscribe/unsubscribe lifecycle, callback dispatch, and cleanup.
"""

from __future__ import annotations

from typing import Any

import pytest
from brokers.market.streaming_router import StreamingBackend, StreamingRouter


class _MockAdapter:
    """Adapter stub that tracks calls."""

    def __init__(self) -> None:
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[tuple[str, str]] = []
        self.disconnected = False
        self.stopped = False

    def subscribe(self, key: str, exchange: str) -> None:
        self.subscribed.append((key, exchange))

    def unsubscribe(self, key: str, exchange: str) -> None:
        self.unsubscribed.append((key, exchange))

    def disconnect(self) -> None:
        self.disconnected = True

    def stop(self) -> None:
        self.stopped = True


class _FailingAdapter:
    """Adapter that raises on subscribe to trigger fallback."""

    def subscribe(self, key: str, exchange: str) -> None:
        msg = f"subscribe failed for {key}"
        raise RuntimeError(msg)

    def unsubscribe(self, key: str, exchange: str) -> None:
        pass

    def disconnect(self) -> None:
        pass


class StreamingRouterContractTests:
    """Mixin-style contract tests for StreamingRouter."""

    def test_priority_based_backend_selection(self, router: StreamingRouter) -> None:
        """Lower priority number = higher priority; should be selected first."""
        primary = _MockAdapter()
        fallback = _MockAdapter()
        router.add_backend(StreamingBackend("primary", 0, primary))
        router.add_backend(StreamingBackend("fallback", 1, fallback))

        router.subscribe("NSE:RELIANCE", "NSE")

        assert ("NSE:RELIANCE", "NSE") in primary.subscribed
        assert ("NSE:RELIANCE", "NSE") not in fallback.subscribed

    def test_backends_listed_in_priority_order(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("low", 10, _MockAdapter()))
        router.add_backend(StreamingBackend("high", 0, _MockAdapter()))
        router.add_backend(StreamingBackend("mid", 5, _MockAdapter()))

        assert router.backends == ["high", "mid", "low"]

    def test_primary_failure_falls_back(self, router: StreamingRouter) -> None:
        """When primary raises, the next available backend is used."""
        failing = _FailingAdapter()
        backup = _MockAdapter()
        router.add_backend(StreamingBackend("primary", 0, failing))
        router.add_backend(StreamingBackend("backup", 1, backup))

        router.subscribe("NSE:TCS", "NSE")

        assert ("NSE:TCS", "NSE") in backup.subscribed

    def test_no_available_backend_raises(self, router: StreamingRouter) -> None:
        with pytest.raises(RuntimeError, match="No streaming backend available"):
            router.subscribe("NSE:HINDUNILVR", "NSE")

    def test_subscribe_adds_to_active_subscriptions(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        router.subscribe("NSE:RELIANCE", "NSE")

        assert router.is_subscribed("NSE:RELIANCE")
        assert "NSE:RELIANCE" in router.active_subscriptions

    def test_unsubscribe_removes_active_subscription(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        router.subscribe("NSE:RELIANCE", "NSE")
        router.unsubscribe("NSE:RELIANCE", "NSE")

        assert not router.is_subscribed("NSE:RELIANCE")

    def test_unsubscribe_calls_backend_unsubscribe(self, router: StreamingRouter) -> None:
        adapter = _MockAdapter()
        router.add_backend(StreamingBackend("ws", 0, adapter))
        router.subscribe("NSE:RELIANCE", "NSE")
        router.unsubscribe("NSE:RELIANCE", "NSE")

        assert ("NSE:RELIANCE", "NSE") in adapter.unsubscribed

    def test_dispatch_tick_calls_registered_callback(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        received: list[Any] = []

        def cb(data: Any) -> None:
            received.append(data)

        router.subscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.dispatch_tick("NSE:RELIANCE", {"price": 2500})

        assert len(received) == 1
        assert received[0] == {"price": 2500}

    def test_multiple_callbacks_per_key(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        received1: list[Any] = []
        received2: list[Any] = []

        def cb1(data: Any) -> None:
            received1.append(data)

        def cb2(data: Any) -> None:
            received2.append(data)

        router.subscribe("NSE:RELIANCE", "NSE", callback=cb1)
        router.subscribe("NSE:RELIANCE", "NSE", callback=cb2)
        router.dispatch_tick("NSE:RELIANCE", 100.0)

        assert len(received1) == 1
        assert len(received2) == 1

    def test_dispatch_tick_skips_unsubscribed_callback(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        received: list[Any] = []

        def cb(data: Any) -> None:
            received.append(data)

        router.subscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.unsubscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.dispatch_tick("NSE:RELIANCE", 100.0)

        assert len(received) == 0

    def test_disconnect_all_cleans_up(self, router: StreamingRouter) -> None:
        adapter1 = _MockAdapter()
        adapter2 = _MockAdapter()
        router.add_backend(StreamingBackend("ws1", 0, adapter1))
        router.add_backend(StreamingBackend("ws2", 1, adapter2))
        router.subscribe("NSE:RELIANCE", "NSE")

        router.disconnect_all()

        assert adapter1.disconnected
        assert adapter1.stopped
        assert adapter2.disconnected
        assert adapter2.stopped
        assert router.active_subscriptions == []

    def test_clear_removes_all_backends(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        router.subscribe("NSE:RELIANCE", "NSE")
        router.clear()

        assert router.active_subscriptions == []
        assert router.backends == []

    def test_add_backend_sorts_by_priority(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("a", 5, _MockAdapter()))
        router.add_backend(StreamingBackend("b", 1, _MockAdapter()))
        router.add_backend(StreamingBackend("c", 3, _MockAdapter()))

        assert router.backends == ["b", "c", "a"]

    def test_remove_backend(self, router: StreamingRouter) -> None:
        router.add_backend(StreamingBackend("ws", 0, _MockAdapter()))
        assert router.remove_backend("ws") is True
        assert router.backends == []

    def test_remove_backend_not_found(self, router: StreamingRouter) -> None:
        assert router.remove_backend("nonexistent") is False


@pytest.mark.contract
class TestStreamingRouterContractConformance:
    """Base test class — override ``router`` fixture for concrete instances."""

    @pytest.fixture
    def router(self) -> StreamingRouter:
        return StreamingRouter()

    def test_priority_based_backend_selection(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_priority_based_backend_selection(router)

    def test_backends_listed_in_priority_order(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_backends_listed_in_priority_order(router)

    def test_primary_failure_falls_back(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_primary_failure_falls_back(router)

    def test_no_available_backend_raises(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_no_available_backend_raises(router)

    def test_subscribe_adds_to_active_subscriptions(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_subscribe_adds_to_active_subscriptions(router)

    def test_unsubscribe_removes_active_subscription(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_unsubscribe_removes_active_subscription(router)

    def test_unsubscribe_calls_backend_unsubscribe(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_unsubscribe_calls_backend_unsubscribe(router)

    def test_dispatch_tick_calls_registered_callback(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_dispatch_tick_calls_registered_callback(router)

    def test_multiple_callbacks_per_key(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_multiple_callbacks_per_key(router)

    def test_dispatch_tick_skips_unsubscribed_callback(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_dispatch_tick_skips_unsubscribed_callback(router)

    def test_disconnect_all_cleans_up(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_disconnect_all_cleans_up(router)

    def test_clear_removes_all_backends(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_clear_removes_all_backends(router)

    def test_add_backend_sorts_by_priority(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_add_backend_sorts_by_priority(router)

    def test_remove_backend(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_remove_backend(router)

    def test_remove_backend_not_found(self, router: StreamingRouter) -> None:
        StreamingRouterContractTests().test_remove_backend_not_found(router)
