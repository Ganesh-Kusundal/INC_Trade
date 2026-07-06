"""DepthState — mutable market depth state updated by streaming.

Tracks the order book (bids and asks) for a single instrument.
Updated by depth streaming feeds.

Performance: Uses ``__slots__`` (via ``dataclass(slots=True)``) and
in-place updates to minimize allocation on the streaming hot-path.
For 200-level depth, in-place update avoids ~400 object allocations
per tick in steady state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DepthLevelState:
    """A single level in the order book (mutable, slots-optimized)."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0

    def snapshot(self) -> Any:
        """Return an immutable DepthLevel."""
        from brokers_core.domain.entities import DepthLevel

        return DepthLevel(price=self.price, quantity=self.quantity, orders=self.orders)


@dataclass(slots=True)
class DepthState:
    """Mutable market depth (order book) for a single instrument (slots-optimized).

    Updated by depth streaming feeds. Provides a snapshot() method
    that returns an immutable ``MarketDepth`` domain entity.

    Performance: ``update_in_place()`` modifies existing DepthLevelState
    objects instead of rebuilding the list, eliminating allocations in
    steady state.

    Attributes:
        composite_key: Canonical composite key ``{exchange}:{symbol}``.
    """

    composite_key: str
    bids: list[DepthLevelState] = field(default_factory=list)
    asks: list[DepthLevelState] = field(default_factory=list)
    timestamp: datetime | None = None
    seq_no: int = 0

    def update_from_depth(
        self,
        bids: list[dict[str, Any]] | None = None,
        asks: list[dict[str, Any]] | None = None,
        timestamp: datetime | None = None,
        seq_no: int | None = None,
    ) -> None:
        """Update depth from raw bid/ask data.

        Uses in-place update to minimize allocations.

        Args:
            bids: List of dicts with 'price', 'quantity', 'orders' keys.
            asks: List of dicts with 'price', 'quantity', 'orders' keys.
            timestamp: Update timestamp.
            seq_no: Monotonic sequence number.
        """
        if bids is not None:
            self._update_levels_in_place(self.bids, bids)
        if asks is not None:
            self._update_levels_in_place(self.asks, asks)
        if timestamp:
            self.timestamp = timestamp
        if seq_no is not None:
            self.seq_no = seq_no

    def _update_levels_in_place(
        self,
        existing: list[DepthLevelState],
        new_data: list[dict[str, Any]],
    ) -> None:
        """Update existing depth levels in-place (no list rebuild).

        Only creates new DepthLevelState objects when the number of
        levels changes. In steady state (same number of levels),
        zero allocations occur.

        Args:
            existing: The existing list of DepthLevelState to update.
            new_data: New level data as list of dicts.
        """
        for i, data in enumerate(new_data):
            price = Decimal(str(data.get("price", 0)))
            quantity = int(data.get("quantity", 0))
            orders = int(data.get("orders", 0))
            if i < len(existing):
                # In-place update — no allocation
                existing[i].price = price
                existing[i].quantity = quantity
                existing[i].orders = orders
            else:
                # New level — must allocate
                existing.append(
                    DepthLevelState(
                        price=price,
                        quantity=quantity,
                        orders=orders,
                    )
                )
        # Trim if fewer levels
        del existing[len(new_data) :]

    def snapshot(self) -> Any:
        """Return an immutable MarketDepth entity."""
        from brokers_core.domain.entities import MarketDepth

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
