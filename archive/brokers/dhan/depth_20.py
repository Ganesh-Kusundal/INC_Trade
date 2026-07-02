"""20-level market depth WebSocket feed for Dhan.

Plan §7.1 refactor: the binary-packet / reconnect / lifecycle machinery is
shared with ``DhanDepth200Feed`` via :class:`BinaryDepthFeed` (in
``brokers.dhan.depth_feed_base``). This module keeps ``DhanDepth20Feed``
as a thin subclass so callers and tests that import
``brokers.dhan.depth_20.DhanDepth20Feed`` keep working unchanged.

Endpoint: wss://depth-api-feed.dhan.co/twentydepth
Max instruments: 50 per connection
Header layout: security_id at offset 4 (see ``BinaryDepthFeed.header_carries_security_id``)
"""

from __future__ import annotations

from brokers.dhan.depth_feed_base import BinaryDepthFeed
from domain import MarketDepth
from infrastructure.event_bus import EventBus

__all__ = ["DhanDepth20Feed"]


class DhanDepth20Feed(BinaryDepthFeed):
    """20-level market depth via WebSocket.

    The class attributes ``MAX_INSTRUMENTS``, ``TOTAL_DEPTH_PACKETS``,
    ``ENDPOINT``, ``REQUEST_CODE``, ``HEADER_SIZE``, ``DEPTH_LEVEL_SIZE``,
    ``BID_RESPONSE_CODE``, ``ASK_RESPONSE_CODE`` are inherited from
    :class:`BinaryDepthFeed` and remain accessible for backward compat.
    """

    # Class-level constants (also set by BinaryDepthFeed.__init__; redefined
    # here so legacy code that introspects them on the class itself still works).
    name = "dhan.depth_20"
    ENDPOINT = ""
    MAX_INSTRUMENTS = 50
    TOTAL_DEPTH_PACKETS = 20
    REQUEST_CODE = 23  # Full Market Depth
    HEADER_SIZE = 12
    DEPTH_LEVEL_SIZE = 16
    BID_RESPONSE_CODE = 41
    ASK_RESPONSE_CODE = 51

    def __init__(
        self,
        client_id: str,
        access_token: str,
        instruments: list[tuple[str, str]] | None = None,
        event_bus: EventBus | None = None,
    ):
        from config.endpoints import Dhan as _DhanEndpoints

        super().__init__(
            client_id=client_id,
            access_token=access_token,
            endpoint=_DhanEndpoints.WS_DEPTH_20,
            request_code=self.REQUEST_CODE,
            total_slots=20,
            subs_per_connection=50,
            depth_type="DEPTH_20",
            name=self.name,
            event_name="DEPTH_20",
            header_carries_security_id=True,
            event_bus=event_bus,
        )

        # Preserve class-level ENDPOINT for introspection by callers that
        # read it off the class rather than the instance.
        if not self.ENDPOINT:
            self.ENDPOINT = _DhanEndpoints.WS_DEPTH_20
        DhanDepth20Feed.ENDPOINT = _DhanEndpoints.WS_DEPTH_20

        if instruments:
            self.subscribe(instruments)

    # ── Depth-20 specific lookup: security_id-keyed cache ─────────────────
    def latest_depth(self, security_id: int) -> MarketDepth | None:
        """Return the most-recent cached :class:`MarketDepth` for *security_id*."""
        with self._depth_cache_lock:
            entry = self._depth_cache.get(security_id)
        if entry is None:
            return None
        return MarketDepth(
            symbol=self._sec_id_to_symbol.get(security_id, ""),
            bids=list(entry.get("bids", [])),
            asks=list(entry.get("asks", [])),
            depth_type="DEPTH_20",
        )
