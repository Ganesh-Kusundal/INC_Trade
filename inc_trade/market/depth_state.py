"""DepthState — mutable market depth state updated by streaming.

Tracks the order book (bids and asks) for a single instrument.
Updated by depth streaming feeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


@dataclass
class DepthLevelState:
    """A single level in the order book (mutable)."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0

    def snapshot(self) -> Any:
        """Return an immutable DepthLevel."""
        from inc_trade.domain.entities import DepthLevel

        return DepthLevel(price=self.price, quantity=self.quantity, orders=self.orders)


@dataclass
class DepthState:
    """Mutable market depth (order book) for a single instrument.

    Updated by depth streaming feeds. Provides a snapshot() method
    that returns an immutable ``MarketDepth`` domain entity.

    Attributes:
        composite_key: Canonical composite key ``{exchange}:{symbol}``.
            (Previously named ``instrument_key``; deprecated alias
            available.)
    """

    composite_key: str
    bids: list[DepthLevelState] = field(default_factory=list)
    asks: list[DepthLevelState] = field(default_factory=list)
    timestamp: datetime | None = None
    seq_no: int = 0

    @property
    def instrument_key(self) -> str:
        """Deprecated alias for :attr:`composite_key`."""
        import warnings

        warnings.warn(
            "DepthState.instrument_key is deprecated; use composite_key instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.composite_key

    def update_from_depth(
        self,
        bids: list[dict[str, Any]] | None = None,
        asks: list[dict[str, Any]] | None = None,
        timestamp: datetime | None = None,
        seq_no: int | None = None,
    ) -> None:
        """Update depth from raw bid/ask data.

        Args:
            bids: List of dicts with 'price', 'quantity', 'orders' keys.
            asks: List of dicts with 'price', 'quantity', 'orders' keys.
            timestamp: Update timestamp.
            seq_no: Monotonic sequence number.
        """
        if bids is not None:
            self.bids = [
                DepthLevelState(
                    price=Decimal(str(b.get("price", 0))),
                    quantity=int(b.get("quantity", 0)),
                    orders=int(b.get("orders", 0)),
                )
                for b in bids
            ]
        if asks is not None:
            self.asks = [
                DepthLevelState(
                    price=Decimal(str(a.get("price", 0))),
                    quantity=int(a.get("quantity", 0)),
                    orders=int(a.get("orders", 0)),
                )
                for a in asks
            ]
        if timestamp:
            self.timestamp = timestamp
        if seq_no is not None:
            self.seq_no = seq_no

    def snapshot(self) -> Any:
        """Return an immutable MarketDepth entity."""
        from inc_trade.domain.entities import MarketDepth

        exchange, _, symbol = self.composite_key.partition(":")
        return MarketDepth(
            symbol=symbol or self.composite_key,
            bids=[b.snapshot() for b in self.bids],
            asks=[a.snapshot() for a in self.asks],
            exchange=exchange or "",
            timestamp=self.timestamp,
        )

    def is_stale(self, max_age_seconds: float = 5.0) -> bool:
        """Check if depth data is stale."""
        if self.timestamp is None:
            return True
        age = (datetime.now(UTC) - self.timestamp).total_seconds()
        return age > max_age_seconds

    @property
    def best_bid(self) -> DepthLevelState | None:
        """Highest bid (best bid price)."""
        if not self.bids:
            return None
        return max(self.bids, key=lambda b: b.price)

    @property
    def best_ask(self) -> DepthLevelState | None:
        """Lowest ask (best ask price)."""
        if not self.asks:
            return None
        return min(self.asks, key=lambda a: a.price)

    @property
    def spread(self) -> Decimal:
        """Bid-ask spread."""
        bb = self.best_bid
        ba = self.best_ask
        if bb and ba and bb.price > 0 and ba.price > 0:
            return ba.price - bb.price
        return Decimal("0")
