"""OptionGreeksStreamProvider extension interface.

Capability gate: Upstox ``option_greeks`` stream mode
Supported by: Upstox (live greeks via V3 WebSocket subscription mode)
Not supported by: Dhan (greeks are in REST option chain response, not streaming)

Combined mode cap for Upstox: 2000 instruments when option_greeks mode is active
alongside other modes.  Callers must account for combined caps from
``BrokerCapabilities.stream_limits.combined_mode_caps``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from domain.historical import InstrumentRef


@dataclass(frozen=True)
class LiveOptionGreeks:
    """Normalized live option greeks tick from broker stream.

    All standard BSM greeks plus IV and OI.
    """

    instrument: InstrumentRef
    underlying_price: Decimal
    ltp: Decimal
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    iv: Decimal | None
    open_interest: int | None
    event_time: datetime
    broker_id: str


class OptionGreeksStreamProvider(Protocol):
    """Extension interface for live streaming option greeks.

    Available only on Upstox via the ``option_greeks`` WS subscription mode.
    On Dhan, fetch option chain via the common gateway for point-in-time greeks.
    """

    async def subscribe_option_greeks(
        self,
        instruments: Sequence[InstrumentRef],
        on_greeks: object,  # Callable[[LiveOptionGreeks], Awaitable[None]]
        *,
        quota: object,
    ) -> str:
        """Subscribe to live greeks stream. Returns subscription handle ID."""
        ...

    async def unsubscribe_option_greeks(self, handle_id: str) -> None:
        """Unsubscribe and release the greeks subscription."""
        ...
