"""Dhan Depth 20 adapter — L2 Market Data via WebSocket.

Thin subclass of BinaryDepthFeed that preserves backward-compatible API for
depth-20 feeds. See archived brokers.dhan.depth_20.DhanDepth20Feed for reference.

Endpoint: wss://depth-api-feed.dhan.co/twentydepth
Max instruments: 50 per connection
Header layout: security_id at offset 4
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from brokers.config.endpoints import Dhan
from brokers.domain import MarketDepth

from brokers.adapters.dhan.depth_feed_base import BinaryDepthFeed
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.segments import resolve_segment

logger = logging.getLogger(__name__)

__all__ = ["DhanDepth20Stream"]


class DhanDepth20Stream(BinaryDepthFeed):
    """20-level market depth via WebSocket.

    Extends BinaryDepthFeed with depth-20 specific configuration.
    Maintains backward-compatible API.
    """

    name = "dhan.depth_20"
    REQUEST_CODE = 23
    DEPTH_TYPE = "DEPTH_20"
    EVENT_NAME = "DEPTH_20"

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        resolver: DhanInstrumentResolver | None = None,
        instrument: tuple[str, str] | None = None,
        event_bus: Any = None,
    ):
        super().__init__(
            client_id=client_id,
            access_token=access_token if not callable(access_token) else access_token(),
            endpoint=Dhan.WS_DEPTH_20,
            request_code=self.REQUEST_CODE,
            total_slots=20,
            subs_per_connection=50,
            depth_type="DEPTH_20",
            name=self.name,
            event_name="DEPTH_20",
            header_carries_security_id=True,
            event_bus=event_bus,
        )
        self._access_token_fn = access_token if callable(access_token) else None
        self._resolver = resolver

        if instrument:
            self.subscribe(instrument)

    # ── Backward-compatible subscribe/unsubscribe ─────────────────────────

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Subscribe using symbol+exchange (backward compatible API)."""
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = (ref.exchange_segment, ref.security_id)
                super().subscribe([key])
                logger.info(f"Depth20 subscribed to {symbol} ({exchange})")
            else:
                segment = resolve_segment(exchange)
                super().subscribe([(segment, symbol)])
        except Exception as e:
            logger.error(
                f"Depth20 failed to resolve/subscribe {symbol} on {exchange}: {e}"
            )
            segment = resolve_segment(exchange)
            super().subscribe([(segment, symbol)])

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        """Unsubscribe using symbol+exchange (backward compatible API)."""
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = (ref.exchange_segment, ref.security_id)
                super().unsubscribe([key])
                logger.info(f"Depth20 unsubscribed from {symbol} ({exchange})")
        except Exception as e:
            logger.error(
                f"Depth20 failed to resolve/unsubscribe {symbol} on {exchange}: {e}"
            )
            segment = resolve_segment(exchange)
            super().unsubscribe([(segment, symbol)])

    # ── Depth-20 specific lookup: security_id-keyed cache ─────────────────

    def latest_depth(self, security_id: int) -> MarketDepth | None:
        """Return the most-recent cached MarketDepth for security_id."""
        with self._depth_cache_lock:
            entry = self._depth_cache.get(security_id)
        if entry is None:
            return None
        return MarketDepth(
            symbol=self._sec_id_to_symbol.get(security_id, ""),
            bids=list(entry.get("bids", [])),
            asks=list(entry.get("asks", [])),
        )

    # ── Token hot-swap support ────────────────────────────────────────────

    def update_token(self, new_token: str) -> None:
        """Update token and reconnect with fresh auth."""
        if self._access_token_fn:
            # Update the cached token if we have a callable
            self._access_token = new_token
        super().update_token(new_token)
