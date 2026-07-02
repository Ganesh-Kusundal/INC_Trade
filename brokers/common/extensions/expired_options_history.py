"""ExpiredOptionsHistoryProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_expired_options_history``
Supported by: Dhan (rolling options API — /charts/rollingoption)
Not supported by: Upstox (expired instruments client exists but is Plus-gated
                          and not exposed in public capabilities)

Dhan's rolling options API supports ATM-relative strikes and WEEK/MONTH expiry
types.  This is fundamentally different from normal historical data because the
instrument identifier changes on expiry.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domain.historical import HistoricalBar


@dataclass(frozen=True)
class RollingOptionRequest:
    """Request for rolling expired option history.

    underlying   — underlying index/equity symbol, e.g. ``"NIFTY"``.
    exchange     — exchange, e.g. ``"NFO"``.
    strike_offset — ATM-relative strike offset (0 = ATM, 1 = ATM+1, -1 = ATM-1).
    expiry_type  — ``"WEEK"`` or ``"MONTH"``.
    option_type  — ``"CE"`` or ``"PE"``.
    from_date    — start date for the rolling series.
    to_date      — end date for the rolling series.
    timeframe    — candle interval, e.g. ``"1D"``.
    request_id   — correlation ID for provenance.
    """

    underlying: str
    exchange: str
    strike_offset: int
    expiry_type: str
    option_type: str
    from_date: date
    to_date: date
    timeframe: str
    request_id: str


class ExpiredOptionsHistoryProvider(Protocol):
    """Extension interface for expired/rolling option historical data."""

    async def fetch_rolling_option_history(
        self,
        request: RollingOptionRequest,
        *,
        quota: object,
    ) -> Sequence[HistoricalBar]:
        """Fetch rolling option history stitched across expiries."""
        ...
