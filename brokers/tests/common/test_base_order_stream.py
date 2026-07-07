"""Tests for BaseOrderStream invariants + shared behavior."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokers.common.streaming.base_order_stream import BaseOrderStream


# ── Concrete subclass used across tests ──────────────────────────────────────


class _DummyOrderStream(BaseOrderStream):
    """Concrete subclass with synthetic broker state — no real HTTP."""

    BROKER_ID: ClassVar[str] = "dummy"

    def __init__(self, *, on_order=None, on_health_change=None) -> None:
        super().__init__(on_order=on_order, on_health_change=on_health_change)
        self.authorized_url = "wss://dummy.test/"
        self.authorized_headers: dict[str, str] | None = None

    async def _resolve_url_and_headers(self):
        return (self.authorized_url, self.authorized_headers)

    def _decode_message(self, raw):
        return []

    async def _connect_ws(self, url, extra_headers=None):
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=b"{}")
        mock_ws.close = AsyncMock()
        mock_ws.is_connected = True
        return mock_ws

    async def _subscribe(self, transport, plan):
        await self._no_op_subscribe(transport, plan)


# ── Constructor validation ────────────────────────────────────────────────────


class TestBaseOrderStreamInit:
    def test_succeeds_when_broker_id_set(self) -> None:
        s = _DummyOrderStream()
        assert s.BROKER_ID == "dummy"

    def test_missing_broker_id_raises(self) -> None:
        class _Blank(_DummyOrderStream):
            BROKER_ID: ClassVar[str] = ""

        with pytest.raises(ValueError, match="must define BROKER_ID"):
            _Blank()


# ── is_running + add_consumer before start ───────────────────────────────────


class TestBaseOrderStreamRuntime:
    def test_is_running_false_before_start(self) -> None:
        s = _DummyOrderStream()
        assert s.is_running is False

    def test_add_consumer_before_start_raises(self) -> None:
        s = _DummyOrderStream()
        with pytest.raises(RuntimeError, match="not started"):
            s.add_consumer()


# ── Orchestrator wiring (mocked StreamOrchestrator) ──────────────────────────


class TestBaseOrderStreamStart:
    @pytest.mark.asyncio
    async def test_start_streams_to_orchestrator(self) -> None:
        s = _DummyOrderStream()
        mock_orch = AsyncMock()
        mock_orch.is_running = True
        mock_orch.add_order_queue = MagicMock(return_value="mock_queue")
        mock_orch.set_callbacks = MagicMock()
        mock_orch.start = AsyncMock()

        with patch(
            "brokers.common.streaming.base_order_stream.StreamOrchestrator",
            return_value=mock_orch,
        ):
            await s.start()

        assert s._orchestrator is mock_orch
        mock_orch.set_callbacks.assert_called_once()
        mock_orch.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_tears_down_orchestrator(self) -> None:
        s = _DummyOrderStream()
        mock_orch = AsyncMock()
        mock_orch.is_running = True
        mock_orch.stop = AsyncMock()
        s._orchestrator = mock_orch

        await s.stop()
        mock_orch.stop.assert_awaited_once()
        assert s._orchestrator is None

    @pytest.mark.asyncio
    async def test_stop_is_safe_when_not_started(self) -> None:
        s = _DummyOrderStream()
        await s.stop()  # Must not raise
        assert s._orchestrator is None


# ── Canonical import-path contract (regression guard) ────────────────────────


class TestBaseOrderStreamImportPath:
    def test_base_class_is_importable_from_canonical_path(self) -> None:
        from brokers.common.streaming.base_order_stream import BaseOrderStream as cls

        assert cls is not None
        assert isinstance(cls, type)


# ── Smoke test with real subclasses ─────────────────────────────────────────


class TestRealSubclassSmoke:
    @pytest.mark.asyncio
    async def test_dhan_order_feed_construction(self) -> None:
        """DhanOrderFeed should construct without errors and expose BaseOrderStream interface."""
        from brokers.dhan.streaming.order_feed import DhanOrderFeed

        feed = DhanOrderFeed(client_id="1100", access_token="tok")
        assert isinstance(feed, BaseOrderStream)
        assert feed.BROKER_ID == "dhan"
        assert feed.is_running is False

    @pytest.mark.asyncio
    async def test_upstox_portfolio_stream_construction(self) -> None:
        from brokers.upstox.streaming.portfolio_feed import UpstoxPortfolioStream

        stream = UpstoxPortfolioStream(http_client=MagicMock())
        assert isinstance(stream, BaseOrderStream)
        assert stream.BROKER_ID == "upstox"
        assert stream.is_running is False
