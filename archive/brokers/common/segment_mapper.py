"""Base segment mapper (REF-07 extraction).

Defines the common interface for broker-specific segment mappers.
Each broker adapter implements ``to_wire()`` and ``from_wire()``
with its own wire-format strings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SegmentMapper(ABC):
    """Canonical interface for exchange-segment ↔ broker-wire conversion.

    Implementations
    ---------------
    - ``brokers.dhan.segments.DhanSegmentMapper``
    - ``brokers.upstox.instruments.segment_mapper.UpstoxSegmentMapper``
    """

    @abstractmethod
    def to_wire(self, segment: Any) -> str:
        """Convert a canonical ``ExchangeSegment`` to the broker's wire string."""
        ...

    @abstractmethod
    def from_wire(self, wire: str) -> Any:
        """Convert a broker wire string to a canonical ``ExchangeSegment``."""
        ...

    @abstractmethod
    def exchange_to_wire(self, exchange: str, default: str = ...) -> str:
        """Convert a short exchange name (e.g. "NSE", "NFO") to the broker's wire segment."""
        ...
