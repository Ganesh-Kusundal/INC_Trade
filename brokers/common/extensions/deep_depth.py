"""DeepDepthProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_depth_20_ws``
Supported by: Dhan (native depth-20 WS at 50 symbols/conn, depth-200 at 1 sym/conn)
Not supported by: Upstox (REST depth only via get_depth_snapshot)

Dhan depth-20 is NSE-segment only.  Depth-200 requires one connection per symbol.
Callers must respect connection budget from ``BrokerCapabilities.stream_limits``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.entities.market import DepthLevel
from domain.historical import InstrumentRef


class DepthKind(str):
    """Depth kind constants — preserved on DepthSnapshot to avoid information loss."""

    REST_5 = "REST_5"
    WS_20 = "WS_20"
    WS_200 = "WS_200"
    REST_FULL = "REST_FULL"


@dataclass(frozen=True)
class DepthSnapshot:
    """Normalized market depth with explicit kind metadata.

    ``depth_kind`` preserves whether this came from a 5-level REST response
    or a 20/200-level streaming response so consumers can make informed decisions
    about the precision of their order-book models.
    """

    instrument: InstrumentRef
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    depth_kind: str  # DepthKind constant
    event_time: datetime
    broker_id: str

    @property
    def bid_levels(self) -> int:
        return len(self.bids)

    @property
    def ask_levels(self) -> int:
        return len(self.asks)


class DeepDepthProvider(Protocol):
    """Extension interface for streaming 20-level or 200-level market depth.

    Only available on Dhan.  Upstox callers must use ``get_depth_snapshot()``
    on ``CommonBrokerGateway`` which returns REST_5 or REST_FULL via V2 API.
    """

    async def subscribe_depth_20(
        self,
        instruments: Sequence[InstrumentRef],
        on_depth: object,  # Callable[[DepthSnapshot], Awaitable[None]]
        *,
        quota: object,
    ) -> str:
        """Subscribe to 20-level depth streaming.

        Returns a subscription handle ID.  Max 50 instruments per connection.
        NSE segment only.
        """
        ...

    async def subscribe_depth_200(
        self,
        instrument: InstrumentRef,
        on_depth: object,
        *,
        quota: object,
    ) -> str:
        """Subscribe to 200-level depth streaming for a single instrument.

        One connection per instrument — check connection budget before subscribing.
        """
        ...

    async def unsubscribe_depth(self, handle_id: str) -> None:
        """Unsubscribe and release the depth connection."""
        ...
