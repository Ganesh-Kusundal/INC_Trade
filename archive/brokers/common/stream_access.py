"""StreamAccessProvider — typed protocol for WS stream access.

Both Dhan and Upstox gateways use ``getattr(self._conn, "market_feed", None)``
and similar ``getattr`` chains in their ``get_connection_status()`` and
``get_connection_metadata()`` methods to probe WebSocket connectivity.

This module provides a typed ``Protocol`` that eliminates the runtime
``getattr`` calls and makes the expected interface explicit.

Usage
-----
    from typing import Any
    from brokers.common.stream_access import StreamAccessProvider

    class MyGateway:
        def get_connection_status(self) -> dict[str, bool]:
            status: dict[str, bool] = {}
            streams = self._get_stream_access()
            status["market_feed"] = bool(streams.market_feed.is_connected)
            return status

        def _get_stream_access(self) -> StreamAccessProvider:
            return StreamAccessProvider(
                market_feed=getattr(self._conn, "market_feed", None),
                order_stream=getattr(self._conn, "order_stream", None),
            )
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HasIsConnected(Protocol):
    """Anything with an ``is_connected`` attribute (bool or callable)."""

    @property
    def is_connected(self) -> bool: ...


class _CallableIsConnected:
    """Wraps a callable ``is_connected`` as a property.

    Pre-define the class at module level instead of creating it
    dynamically in ``_ensure_isconnected`` on every call.
    """
    __slots__ = ("_fn",)

    def __init__(self, fn: Callable[[], bool]) -> None:
        self._fn = fn

    @property
    def is_connected(self) -> bool:
        return bool(self._fn())


class _NoStream:
    """Sentinel representing a missing/None stream."""

    @property
    def is_connected(self) -> bool:
        return False

    def health(self) -> Any:
        """Return an empty health dict for compatibility with get_connection_metadata()."""
        from dataclasses import dataclass

        @dataclass
        class _EmptyHealth:
            metrics: dict[str, Any] | None = None

        return _EmptyHealth(metrics=None)


_NO_STREAM = _NoStream()


class StreamAccessProvider:
    """Typed accessor for WebSocket streams on a broker connection.

    Replaces ``getattr(self._conn, "market_feed", None)`` chains in
    ``get_connection_status()`` / ``get_connection_metadata()`` methods.
    Each field lazily falls back to a no-op sentinel when the underlying
    attribute is ``None``.
    """

    def __init__(
        self,
        market_feed: Any = _NO_STREAM,
        order_stream: Any = _NO_STREAM,
        depth_20_feed: Any = _NO_STREAM,
        depth_200_feed: Any = _NO_STREAM,
        polling_feed: Any = _NO_STREAM,
        portfolio_stream: Any = _NO_STREAM,
        market_data_websocket: Any = _NO_STREAM,
        subscription_engine: Any = _NO_STREAM,
    ) -> None:
        self._market_feed = market_feed if market_feed is not None else _NO_STREAM
        self._order_stream = order_stream if order_stream is not None else _NO_STREAM
        self._depth_20_feed = depth_20_feed if depth_20_feed is not None else _NO_STREAM
        self._depth_200_feed = depth_200_feed if depth_200_feed is not None else _NO_STREAM
        self._polling_feed = polling_feed if polling_feed is not None else _NO_STREAM
        self._portfolio_stream = portfolio_stream if portfolio_stream is not None else _NO_STREAM
        self._market_data_websocket = (
            market_data_websocket if market_data_websocket is not None else _NO_STREAM
        )
        self._subscription_engine = (
            subscription_engine if subscription_engine is not None else _NO_STREAM
        )

    # ── Stream properties ──────────────────────────────────────────────

    @property
    def market_feed(self) -> HasIsConnected:
        """Dhan market data feed (SDK WebSocket)."""
        return self._ensure_isconnected(self._market_feed)

    @property
    def order_stream(self) -> HasIsConnected:
        """Dhan order update stream (SDK WebSocket)."""
        return self._ensure_isconnected(self._order_stream)

    @property
    def depth_20_feed(self) -> HasIsConnected:
        """Dhan 20-level depth feed."""
        return self._ensure_isconnected(self._depth_20_feed)

    @property
    def depth_200_feed(self) -> HasIsConnected:
        """Dhan 200-level depth feed."""
        return self._ensure_isconnected(self._depth_200_feed)

    @property
    def polling_feed(self) -> HasIsConnected:
        """Dhan polling market feed (REST fallback)."""
        return self._ensure_isconnected(self._polling_feed)

    @property
    def portfolio_stream(self) -> HasIsConnected:
        """Upstox portfolio/order stream."""
        return self._ensure_isconnected(self._portfolio_stream)

    @property
    def market_data_websocket(self) -> HasIsConnected:
        """Upstox V3 market data WebSocket."""
        return self._ensure_isconnected(self._market_data_websocket)

    @property
    def subscription_engine(self) -> HasIsConnected:
        """Dhan subscription engine (aggregate subscription state)."""
        return self._ensure_isconnected(self._subscription_engine)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_isconnected(stream: Any) -> HasIsConnected:
        """Normalize a stream object to ``HasIsConnected``.

        If *stream* has an ``is_connected`` callable, wraps it as a property.
        If *stream* is ``None`` or missing, returns the ``_NO_STREAM`` sentinel.
        """
        if stream is None:
            return _NO_STREAM
        connected = getattr(stream, "is_connected", None)
        if connected is None:
            return _NO_STREAM
        if callable(connected):
            return _CallableIsConnected(connected)
        if isinstance(connected, bool):
            return stream  # type: ignore[return-value]
        return _NO_STREAM

    def stream_health(self, stream: Any) -> dict[str, Any]:
        """Return health metrics from a stream (if available)."""
        health_fn = getattr(stream, "health", None)
        if callable(health_fn):
            try:
                result = health_fn()
                metrics = getattr(result, "metrics", None) or {}
                if isinstance(metrics, dict):
                    return metrics
            except Exception:
                pass
        return {}

    @property
    def any_connected(self) -> bool:
        """Return ``True`` if any stream is connected."""
        for attr in (
            "_market_feed",
            "_order_stream",
            "_depth_20_feed",
            "_depth_200_feed",
            "_polling_feed",
            "_portfolio_stream",
            "_market_data_websocket",
        ):
            stream = getattr(self, attr, _NO_STREAM)
            try:
                if stream is not _NO_STREAM and getattr(stream, "is_connected", False):
                    return True
            except Exception:
                continue
        return False
