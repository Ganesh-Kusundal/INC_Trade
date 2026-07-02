"""Market data domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from domain.historical import InstrumentRef
from domain.provenance import DataProvenance


class DepthKind(str, Enum):
    """Describes the source and depth level of market depth data.

    REST_5   — 5-level depth from REST API (standard across all brokers).
    WS_20    — 20-level depth from WebSocket (Dhan-specific).
    WS_200   — 200-level depth from WebSocket (Dhan-specific, premium tier).
    """

    REST_5 = "REST_5"
    WS_20 = "WS_20"
    WS_200 = "WS_200"


@dataclass(slots=True, frozen=True)
class DepthLevel:
    """Single price level in market depth."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


@dataclass(slots=True, frozen=False)
class MarketDepth:
    """Canonical market depth — bid/ask ladder.

    Kept as ``frozen=False`` because ``bids``/``asks`` are mutable lists
    that are built incrementally by broker adapters.
    """

    symbol: str = ""
    bids: list[DepthLevel] | None = None
    asks: list[DepthLevel] | None = None
    timestamp: datetime | None = None
    depth_type: str = "DEPTH_5"  # DEPTH_5, DEPTH_20, DEPTH_200

    def __post_init__(self) -> None:
        if self.bids is None:
            self.bids = []
        if self.asks is None:
            self.asks = []


@dataclass(slots=True, frozen=True)
class Quote:
    """Canonical quote snapshot — returned by every broker adapter."""

    symbol: str
    ltp: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
    timestamp: datetime | None = None


@dataclass(slots=True, frozen=True)
class MarketTick:
    """Normalized market data tick — delivered by StreamOrchestrator to consumers.

    Every tick carries full provenance so consumers can trace data lineage.
    """

    instrument: InstrumentRef
    ltp: Decimal
    event_time: datetime
    provenance: DataProvenance
    volume: int = 0
    bid: Decimal | None = None
    ask: Decimal | None = None
    sequence: int | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None


@dataclass(slots=True, frozen=True)
class QuoteSnapshot:
    """Point-in-time quote snapshot with provenance — returned by gateway methods.

    Distinct from ``Quote`` which is the older model without provenance.
    New code should prefer ``QuoteSnapshot`` for multi-broker auditing.
    """

    instrument: InstrumentRef
    ltp: Decimal
    event_time: datetime
    provenance: DataProvenance
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change_pct: Decimal = Decimal("0")
    bid: Decimal | None = None
    ask: Decimal | None = None
