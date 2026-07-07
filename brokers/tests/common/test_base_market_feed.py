"""Tests for BaseMarketFeed invariants + shared behavior."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokers.common.streaming.base_market_feed import BaseMarketFeed
from brokers.infrastructure.streaming.subscription import (
    InstrumentKey,
    StreamMode,
)


# ── Concrete subclass used across tests ──────────────────────────────────────


class _DummyMarketFeed(BaseMarketFeed):
    """Concrete subclass with synthetic broker state — no real HTTP."""

    BROKER_ID: ClassVar[str] = "dummy"
    MAX_INSTRUMENTS: ClassVar[int] = 3

    def __init__(self, *, on_tick=None, on_health_change=None) -> None:
        super().__init__(on_tick=on_tick, on_health_change=on_health_change)
        self._tracked: dict[str, InstrumentKey] = {}

    async def _resolve_url_and_headers(self):
        return ("wss://dummy.test/", {"X-Token": "dummy"})

    async def _connect_ws(self, url, extra_headers=None):
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=b"{}")
        mock_ws.close = AsyncMock()
        mock_ws.is_connected = True
        return mock_ws

    def _track_subscribe(self, instrument_key, mode):
        if len(self._tracked) >= self.MAX_INSTRUMENTS:
            raise ValueError(f"Max {self.MAX_INSTRUMENTS} instruments")
        self._tracked[instrument_key.security_id] = instrument_key

    def _track_unsubscribe(self, instrument_key):
        self._tracked.pop(instrument_key.security_id, None)

    def _build_plan(self):
        from brokers.infrastructure.streaming.subscription import SubscriptionPlan
        return SubscriptionPlan(
            instruments=frozenset(self._tracked.values()),
            mode=self._mode,
        )

    async def _send_subscription(self, transport, plan):
        pass

    def _decode_message(self, raw):
        return []


def _key(sid: str, symbol: str = "X") -> InstrumentKey:
    return InstrumentKey(symbol=symbol, exchange="NSE", security_id=sid)


# ── Constructor validation ────────────────────────────────────────────────────


class TestBaseMarketFeedInit:
    def test_succeeds_when_broker_id_set(self) -> None:
        f = _DummyMarketFeed()
        assert f.BROKER_ID == "dummy"
        assert f.MAX_INSTRUMENTS == 3

    def test_missing_broker_id_raises(self) -> None:
        class _Blank(_DummyMarketFeed):
            BROKER_ID: ClassVar[str] = ""

        with pytest.raises(ValueError, match="must define BROKER_ID"):
            _Blank()


# ── is_running / health / mode pre-start ──────────────────────────────────────


class TestBaseMarketFeedPreStart:
    def test_is_running_false_before_start(self) -> None:
        f = _DummyMarketFeed()
        assert f.is_running is False

    def test_health_default_before_start(self) -> None:
        from brokers.infrastructure.streaming.stream_health import StreamHealth
        f = _DummyMarketFeed()
        assert isinstance(f.health, StreamHealth)

    def test_default_mode_is_quote(self) -> None:
        f = _DummyMarketFeed()
        assert f.mode == StreamMode.QUOTE

    @pytest.mark.asyncio
    async def test_subscribe_before_start_raises(self) -> None:
        f = _DummyMarketFeed()
        with pytest.raises(RuntimeError, match="not started"):
            await f.subscribe(_key("O1"))

    def test_unsubscribe_before_start_is_safe(self) -> None:
        f = _DummyMarketFeed()
        # Does not raise even though orchestrator is None
        import asyncio
        asyncio.run(f.unsubscribe(_key("O1")))


# ── Subscript tracking + limit enforcement ──────────────────────────────────


class TestBaseMarketFeedTracking:
    def test_track_subscribe_appends(self) -> None:
        f = _DummyMarketFeed()
        f._track_subscribe(_key("O1"), StreamMode.LTP)
        f._track_subscribe(_key("O2"), StreamMode.LTP)
        assert "O1" in f._tracked
        assert "O2" in f._tracked

    def test_track_subscribe_enforces_max(self) -> None:
        f = _DummyMarketFeed()
        f._track_subscribe(_key("O1"), StreamMode.LTP)
        f._track_subscribe(_key("O2"), StreamMode.LTP)
        f._track_subscribe(_key("O3"), StreamMode.LTP)
        with pytest.raises(ValueError, match="Max 3 instruments"):
            f._track_subscribe(_key("O4"), StreamMode.LTP)

    def test_track_unsubscribe_removes(self) -> None:
        f = _DummyMarketFeed()
        f._track_subscribe(_key("O1"), StreamMode.LTP)
        f._track_unsubscribe(_key("O1"))
        assert "O1" not in f._tracked

    def test_track_unsubscribe_missing_is_safe(self) -> None:
        f = _DummyMarketFeed()
        f._track_unsubscribe(_key("O1"))  # No-op


# ── Build plan reflects tracked state ─────────────────────────────────────────


class TestBaseMarketFeedBuildPlan:
    def test_plan_empty_when_nothing_tracked(self) -> None:
        f = _DummyMarketFeed()
        plan = f._build_plan()
        assert plan.instruments == frozenset()
        assert plan.mode == StreamMode.QUOTE

    def test_plan_includes_tracked_instruments(self) -> None:
        f = _DummyMarketFeed()
        f._track_subscribe(_key("O1"), StreamMode.LTP)
        f._track_subscribe(_key("O2"), StreamMode.QUOTE)
        plan = f._build_plan()
        assert len(plan.instruments) == 2
        sids = {k.security_id for k in plan.instruments}
        assert sids == {"O1", "O2"}


# ── Orchestrator wiring ──────────────────────────────────────────────────────


class TestBaseMarketFeedWiring:
    @pytest.mark.asyncio
    async def test_start_streams_to_orchestrator(self) -> None:
        f = _DummyMarketFeed()
        mock_orch = AsyncMock()
        mock_orch.is_running = True
        mock_orch.set_callbacks = MagicMock()
        mock_orch.start = AsyncMock()
        mock_orch.add_tick_queue = MagicMock(return_value="mock_queue")
        mock_orch.update_plan = AsyncMock()

        from brokers.common.streaming.base_market_feed import StreamOrchestrator
        with patch.object(
            StreamOrchestrator, "__init__", return_value=None
        ):
            # Use AsyncMock.full on StreamOrchestrator to avoid __init__
            with patch(
                "brokers.common.streaming.base_market_feed.StreamOrchestrator",
                return_value=mock_orch,
            ):
                await f.start()

        assert f._orchestrator is mock_orch
        mock_orch.set_callbacks.assert_called_once()
        mock_orch.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_tears_down_orchestrator(self) -> None:
        f = _DummyMarketFeed()
        mock_orch = AsyncMock()
        mock_orch.stop = AsyncMock()
        f._orchestrator = mock_orch

        await f.stop()
        mock_orch.stop.assert_awaited_once()
        assert f._orchestrator is None


# ── Real-subtype smoke tests ────────────────────────────────────────────────


class TestRealSubtypes:
    def test_dhan_market_feed_inherits_base(self) -> None:
        from brokers.dhan.streaming.market_feed import DhanMarketFeed
        # Without subclassing dance, just check class identity:
        assert issubclass(DhanMarketFeed, BaseMarketFeed)
        assert DhanMarketFeed.BROKER_ID == "dhan"
        assert DhanMarketFeed.MAX_INSTRUMENTS == 1000

    def test_upstox_market_feed_inherits_base(self) -> None:
        from brokers.upstox.streaming.market_feed import UpstoxMarketFeed
        assert issubclass(UpstoxMarketFeed, BaseMarketFeed)
        assert UpstoxMarketFeed.BROKER_ID == "upstox"
        assert UpstoxMarketFeed.MAX_INSTRUMENTS == 5000
