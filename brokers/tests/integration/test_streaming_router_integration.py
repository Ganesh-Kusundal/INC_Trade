"""Integration tests for StreamingRouter with paper broker backend.

Tests backend registration, priority sorting, subscribe/unsubscribe,
fallback behavior, and callback dispatch through the router.
"""

from __future__ import annotations

from typing import Any

import pytest
from inc_trade.market.streaming_router import StreamingBackend, StreamingRouter


class _RecordingAdapter:
    """Minimal adapter that records subscribe/unsubscribe calls for testing."""

    def __init__(self) -> None:
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[tuple[str, str]] = []
        self.disconnected = False

    def subscribe(self, key: str, exchange: str = "NSE") -> None:
        self.subscribed.append((key, exchange))

    def unsubscribe(self, key: str, exchange: str = "NSE") -> None:
        self.unsubscribed.append((key, exchange))

    def disconnect(self) -> None:
        self.disconnected = True


class _FailingAdapter:
    """Adapter that raises on subscribe — used for fallback testing."""

    def __init__(self) -> None:
        self.unsubscribed: list[tuple[str, str]] = []

    def subscribe(self, key: str, exchange: str = "NSE") -> None:
        raise ConnectionError("Backend unavailable")

    def unsubscribe(self, key: str, exchange: str = "NSE") -> None:
        self.unsubscribed.append((key, exchange))


@pytest.fixture
def router() -> StreamingRouter:
    """Create an empty StreamingRouter."""
    return StreamingRouter()


@pytest.mark.integration
class TestStreamingRouterBackendRegistration:
    """Tests for backend registration and priority sorting."""

    def test_add_backend(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        backend = StreamingBackend("ws", priority=1, adapter=adapter)
        router.add_backend(backend)
        assert router.backends == ["ws"]

    def test_priority_sorting(self, router: StreamingRouter):
        adapter1 = _RecordingAdapter()
        adapter2 = _RecordingAdapter()
        router.add_backend(StreamingBackend("polling", priority=10, adapter=adapter1))
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter2))
        # ws (priority=1) should come before polling (priority=10)
        assert router.backends == ["ws", "polling"]

    def test_remove_backend(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        assert router.remove_backend("ws") is True
        assert router.remove_backend("nonexistent") is False
        assert router.backends == []

    def test_multiple_backends_same_priority(self, router: StreamingRouter):
        a1 = _RecordingAdapter()
        a2 = _RecordingAdapter()
        router.add_backend(StreamingBackend("a", priority=5, adapter=a1))
        router.add_backend(StreamingBackend("b", priority=5, adapter=a2))
        # Both at same priority — insertion order preserved
        assert router.backends == ["a", "b"]


@pytest.mark.integration
class TestStreamingRouterSubscribeUnsubscribe:
    """Tests for subscribe/unsubscribe through backends."""

    def test_subscribe_through_primary(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        router.subscribe("NSE:RELIANCE", exchange="NSE")
        assert adapter.subscribed == [("NSE:RELIANCE", "NSE")]
        assert router.is_subscribed("NSE:RELIANCE")

    def test_subscribe_tracks_active_subscriptions(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        router.subscribe("NSE:RELIANCE")
        router.subscribe("NSE:TCS")
        assert sorted(router.active_subscriptions) == ["NSE:RELIANCE", "NSE:TCS"]

    def test_unsubscribe_removes_active_subscription(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        router.subscribe("NSE:RELIANCE")
        router.unsubscribe("NSE:RELIANCE")
        assert not router.is_subscribed("NSE:RELIANCE")

    def test_unsubscribe_calls_backend(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        router.subscribe("NSE:RELIANCE")
        router.unsubscribe("NSE:RELIANCE")
        assert ("NSE:RELIANCE", "NSE") in adapter.unsubscribed

    def test_subscribe_no_backend_raises(self, router: StreamingRouter):
        with pytest.raises(RuntimeError, match="No streaming backend available"):
            router.subscribe("NSE:RELIANCE")


@pytest.mark.integration
class TestStreamingRouterFallback:
    """Tests for fallback behavior when primary backend is unavailable."""

    def test_fallback_to_secondary(self, router: StreamingRouter):
        primary = _FailingAdapter()
        secondary = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=primary))
        router.add_backend(StreamingBackend("polling", priority=10, adapter=secondary))
        # Primary fails — should fallback to polling
        router.subscribe("NSE:RELIANCE")
        assert secondary.subscribed == [("NSE:RELIANCE", "NSE")]
        assert router.is_subscribed("NSE:RELIANCE")

    def test_all_backends_fail_raises(self, router: StreamingRouter):
        primary = _FailingAdapter()
        secondary = _FailingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=primary))
        router.add_backend(StreamingBackend("polling", priority=10, adapter=secondary))
        with pytest.raises((ConnectionError, RuntimeError)):
            router.subscribe("NSE:RELIANCE")

    def test_unavailable_backend_skipped(self, router: StreamingRouter):
        primary = _RecordingAdapter()
        secondary = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=primary, is_available=False))
        router.add_backend(StreamingBackend("polling", priority=10, adapter=secondary))
        router.subscribe("NSE:RELIANCE")
        # Primary was unavailable — secondary should handle it
        assert primary.subscribed == []
        assert secondary.subscribed == [("NSE:RELIANCE", "NSE")]


@pytest.mark.integration
class TestStreamingRouterCallbackDispatch:
    """Tests for callback registration and dispatch."""

    def test_callback_invoked_on_dispatch(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        received: list[Any] = []
        router.subscribe("NSE:RELIANCE", callback=lambda data: received.append(data))
        router.dispatch_tick("NSE:RELIANCE", {"ltp": 2500})
        assert received == [{"ltp": 2500}]

    def test_multiple_callbacks_per_key(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        received1: list[Any] = []
        received2: list[Any] = []
        router.subscribe("NSE:RELIANCE", callback=lambda d: received1.append(d))
        router.subscribe("NSE:RELIANCE", callback=lambda d: received2.append(d))
        router.dispatch_tick("NSE:RELIANCE", 42)
        assert received1 == [42]
        assert received2 == [42]

    def test_callback_not_invoked_for_unsubscribed_key(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        received: list[Any] = []
        cb = lambda data: received.append(data)
        router.subscribe("NSE:RELIANCE", callback=cb)
        # Unsubscribe with the same callback reference to remove it
        router.unsubscribe("NSE:RELIANCE", callback=cb)
        router.dispatch_tick("NSE:RELIANCE", 42)
        assert received == []  # No dispatch after unsubscribe

    def test_callback_error_does_not_raise(self, router: StreamingRouter):
        """A callback that raises should not propagate the exception."""
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))

        def broken(_data: Any) -> None:
            raise ValueError("callback error")

        router.subscribe("NSE:RELIANCE", callback=broken)
        # This should not raise — the error is caught and logged
        router.dispatch_tick("NSE:RELIANCE", 42)

    def test_callback_with_fallback_backend(self, router: StreamingRouter):
        primary = _FailingAdapter()
        secondary = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=primary))
        router.add_backend(StreamingBackend("polling", priority=10, adapter=secondary))
        received: list[Any] = []
        router.subscribe("NSE:RELIANCE", callback=lambda d: received.append(d))
        router.dispatch_tick("NSE:RELIANCE", "tick-data")
        assert received == ["tick-data"]


@pytest.mark.integration
class TestStreamingRouterLifecycle:
    """Tests for lifecycle methods (disconnect_all, clear)."""

    def test_disconnect_all(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        router.subscribe("NSE:RELIANCE")
        router.disconnect_all()
        assert adapter.disconnected
        assert router.active_subscriptions == []

    def test_clear(self, router: StreamingRouter):
        adapter = _RecordingAdapter()
        router.add_backend(StreamingBackend("ws", priority=1, adapter=adapter))
        router.subscribe("NSE:RELIANCE")
        router.clear()
        assert router.backends == []
        assert router.active_subscriptions == []
