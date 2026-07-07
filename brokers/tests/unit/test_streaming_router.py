"""Unit tests for StreamingRouter — backend selection, fallback, lifecycle."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from brokers.domain.entities import Quote
from brokers.market.streaming_router import StreamingBackend, StreamingRouter


class TestStreamingRouter:
    """StreamingRouter backend management and routing."""

    def _make_ws_adapter(self) -> MagicMock:
        adapter = MagicMock()
        adapter.subscribe = MagicMock()
        adapter.unsubscribe = MagicMock()
        adapter.disconnect = MagicMock()
        return adapter

    def _make_polling_adapter(self) -> MagicMock:
        adapter = MagicMock()
        adapter.subscribe = MagicMock()
        adapter.unsubscribe = MagicMock()
        adapter.disconnect = MagicMock()
        return adapter

    def _make_router(self, adapter: MagicMock | None = None) -> StreamingRouter:
        router = StreamingRouter()
        ws = adapter or self._make_ws_adapter()
        router.add_backend(
            StreamingBackend(
                name="websocket",
                priority=1,
                adapter=ws,
                is_available=True,
            )
        )
        return router

    # ── Backend Management ────────────────────────────────────────────

    def test_add_backend_sorted_by_priority(self) -> None:
        router = StreamingRouter()
        ws = self._make_ws_adapter()
        polling = self._make_polling_adapter()
        router.add_backend(StreamingBackend(name="polling", priority=10, adapter=polling))
        router.add_backend(StreamingBackend(name="websocket", priority=1, adapter=ws))
        assert router.backends == ["websocket", "polling"]

    def test_remove_backend_by_name(self) -> None:
        router = self._make_router()
        assert router.remove_backend("websocket") is True
        assert router.backends == []

    def test_remove_backend_unknown_returns_false(self) -> None:
        router = self._make_router()
        assert router.remove_backend("nonexistent") is False

    def test_backends_property_returns_names(self) -> None:
        router = self._make_router()
        assert router.backends == ["websocket"]

    # ── Subscribe Routing ─────────────────────────────────────────────

    def test_route_subscribe_to_correct_adapter(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        router.subscribe("NSE:RELIANCE", "NSE")
        ws.subscribe.assert_called_once_with("NSE:RELIANCE", "NSE")
        assert router.is_subscribed("NSE:RELIANCE")

    def test_route_subscribe_to_multiple_keys(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        router.subscribe("NSE:RELIANCE", "NSE")
        router.subscribe("NSE:TCS", "NSE")
        assert ws.subscribe.call_count == 2
        active = router.active_subscriptions
        assert len(active) == 2
        assert "NSE:RELIANCE" in active
        assert "NSE:TCS" in active

    def test_route_subscribe_raises_when_no_backend(self) -> None:
        router = StreamingRouter()  # No backends
        with pytest.raises(RuntimeError, match="No streaming backend available"):
            router.subscribe("NSE:RELIANCE", "NSE")

    # ── Unsubscribe Routing ───────────────────────────────────────────

    def test_route_unsubscribe_to_correct_adapter(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        router.subscribe("NSE:RELIANCE", "NSE")
        router.unsubscribe("NSE:RELIANCE", "NSE")
        ws.unsubscribe.assert_called_once_with("NSE:RELIANCE", "NSE")
        assert not router.is_subscribed("NSE:RELIANCE")

    def test_unsubscribe_unknown_key_does_not_raise(self) -> None:
        router = self._make_router()
        router.unsubscribe("nonexistent:key")  # Should not raise

    def test_unsubscribe_cleans_up_all_backends(self) -> None:
        ws = self._make_ws_adapter()
        polling = self._make_polling_adapter()
        router = StreamingRouter()
        router.add_backend(
            StreamingBackend(name="websocket", priority=1, adapter=ws, is_available=True)
        )
        router.add_backend(
            StreamingBackend(name="polling", priority=10, adapter=polling, is_available=True)
        )
        router.subscribe("NSE:RELIANCE", "NSE")
        router.unsubscribe("NSE:RELIANCE", "NSE")
        # Should attempt unsubscribe on all backends
        ws.unsubscribe.assert_called()
        polling.unsubscribe.assert_called()

    # ── Fallback ──────────────────────────────────────────────────────

    def test_polling_fallback_when_websocket_not_available(self) -> None:
        ws = self._make_ws_adapter()
        polling = self._make_polling_adapter()
        router = StreamingRouter()
        router.add_backend(
            StreamingBackend(
                name="websocket",
                priority=1,
                adapter=ws,
                is_available=False,  # WebSocket unavailable
            )
        )
        router.add_backend(
            StreamingBackend(
                name="polling",
                priority=10,
                adapter=polling,
                is_available=True,  # Polling available as fallback
            )
        )
        router.subscribe("NSE:RELIANCE", "NSE")
        # WebSocket should NOT have been called
        ws.subscribe.assert_not_called()
        # Polling should have been used
        polling.subscribe.assert_called_once_with("NSE:RELIANCE", "NSE")
        assert router.is_subscribed("NSE:RELIANCE")

    def test_fallback_on_adapter_failure(self) -> None:
        ws = self._make_ws_adapter()
        ws.subscribe.side_effect = ConnectionError("ws down")
        polling = self._make_polling_adapter()
        router = StreamingRouter()
        router.add_backend(
            StreamingBackend(name="websocket", priority=1, adapter=ws, is_available=True)
        )
        router.add_backend(
            StreamingBackend(name="polling", priority=10, adapter=polling, is_available=True)
        )
        # Should fall back to polling after ws failure
        router.subscribe("NSE:RELIANCE", "NSE")
        polling.subscribe.assert_called_once_with("NSE:RELIANCE", "NSE")
        assert router.is_subscribed("NSE:RELIANCE")

    def test_fallback_raises_when_no_fallback_available(self) -> None:
        ws = self._make_ws_adapter()
        ws.subscribe.side_effect = ConnectionError("ws down")
        router = StreamingRouter()
        router.add_backend(
            StreamingBackend(name="websocket", priority=1, adapter=ws, is_available=True)
        )
        # Only one backend and it fails — should raise
        with pytest.raises(ConnectionError):
            router.subscribe("NSE:RELIANCE", "NSE")

    # ── Lifecycle ─────────────────────────────────────────────────────

    def test_disconnect_all_disconnects_all_backends(self) -> None:
        ws = self._make_ws_adapter()
        polling = self._make_polling_adapter()
        router = StreamingRouter()
        router.add_backend(
            StreamingBackend(name="websocket", priority=1, adapter=ws, is_available=True)
        )
        router.add_backend(
            StreamingBackend(name="polling", priority=10, adapter=polling, is_available=True)
        )
        router.subscribe("NSE:RELIANCE", "NSE")
        router.disconnect_all()
        ws.disconnect.assert_called_once()
        polling.disconnect.assert_called_once()
        assert router.active_subscriptions == []

    def test_clear_removes_all_backends_and_subscriptions(self) -> None:
        router = self._make_router()
        router.subscribe("NSE:RELIANCE", "NSE")
        router.clear()
        assert router.backends == []
        assert router.active_subscriptions == []

    # ── Active Subscriptions Tracking ─────────────────────────────────

    def test_active_subscriptions_after_subscribe(self) -> None:
        router = self._make_router()
        router.subscribe("NSE:RELIANCE", "NSE")
        active = router.active_subscriptions
        assert "NSE:RELIANCE" in active

    def test_active_subscriptions_after_unsubscribe(self) -> None:
        router = self._make_router()
        router.subscribe("NSE:RELIANCE", "NSE")
        router.unsubscribe("NSE:RELIANCE", "NSE")
        assert not router.is_subscribed("NSE:RELIANCE")

    def test_is_subscribed_returns_false_for_unknown_key(self) -> None:
        router = self._make_router()
        assert not router.is_subscribed("unknown:key")

    # ── Callback Dispatch ──────────────────────────────────────────────

    def test_subscribe_stores_callback_for_dispatch(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        received: list[Quote] = []

        def cb(tick: Quote) -> None:
            received.append(tick)

        quote = Quote(symbol="RELIANCE", ltp=Decimal("2500"), exchange="NSE")
        router.subscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.dispatch_tick("NSE:RELIANCE", quote)

        assert len(received) == 1
        assert received[0].ltp == Decimal("2500")

    def test_dispatch_tick_multiple_callbacks(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        received1: list[Quote] = []
        received2: list[Quote] = []

        def cb1(tick: Quote) -> None:
            received1.append(tick)

        def cb2(tick: Quote) -> None:
            received2.append(tick)

        quote = Quote(symbol="RELIANCE", ltp=Decimal("2500"), exchange="NSE")
        router.subscribe("NSE:RELIANCE", "NSE", callback=cb1)
        router.subscribe("NSE:RELIANCE", "NSE", callback=cb2)
        router.dispatch_tick("NSE:RELIANCE", quote)

        assert len(received1) == 1
        assert len(received2) == 1

    def test_dispatch_tick_only_calls_registered_key(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        received: list[Quote] = []

        def cb(tick: Quote) -> None:
            received.append(tick)

        router.subscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.dispatch_tick("NSE:TCS", Quote(symbol="TCS", ltp=Decimal("1000"), exchange="NSE"))

        assert len(received) == 0  # TCS dispatch should not call RELIANCE callback

    def test_dispatch_tick_no_callbacks_does_not_raise(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        router.dispatch_tick("NSE:RELIANCE", {"ltp": 2500})  # No callbacks registered

    def test_unsubscribe_removes_callback(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        received: list[Quote] = []

        def cb(tick: Quote) -> None:
            received.append(tick)

        quote = Quote(symbol="RELIANCE", ltp=Decimal("2500"), exchange="NSE")
        router.subscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.unsubscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.dispatch_tick("NSE:RELIANCE", quote)

        assert len(received) == 0  # Callback should have been removed

    def test_disconnect_all_clears_callbacks(self) -> None:
        ws = self._make_ws_adapter()
        router = self._make_router(ws)
        received: list[Quote] = []

        def cb(tick: Quote) -> None:
            received.append(tick)

        router.subscribe("NSE:RELIANCE", "NSE", callback=cb)
        router.disconnect_all()
        router.dispatch_tick(
            "NSE:RELIANCE", Quote(symbol="RELIANCE", ltp=Decimal("2500"), exchange="NSE")
        )

        assert len(received) == 0  # Callbacks cleared after disconnect_all
