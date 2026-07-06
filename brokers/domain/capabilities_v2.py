"""Instrument-level capabilities (ADR-002).

Replaces scattered boolean flags (supports_depth_20_ws, supports_depth_200_ws)
with a unified InstrumentCapabilities frozen dataclass.

Each instrument gets capabilities at creation time via the factory,
encoding what depth levels, streaming modes, and data features it supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class InstrumentCapabilities:
    """Capabilities for a single instrument.

    Encodes broker-specific and instrument-specific features:
    - Supported depth levels (5, 20, 30, 200)
    - Streaming mode support
    - Data feature support (Greeks, OI, fundamentals)
    """

    supported_depth_levels: frozenset[int] = frozenset({5})
    supports_streaming: bool = False
    supports_depth_streaming: bool = False
    supports_oi: bool = False
    supports_greeks: bool = False
    supports_fundamentals: bool = False
    max_batch_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    lot_size: int = 1

    def supports_depth(self, levels: int) -> bool:
        """Check if a specific depth level count is supported."""
        return levels in self.supported_depth_levels

    @property
    def max_depth_levels(self) -> int:
        """Maximum supported depth levels."""
        return max(self.supported_depth_levels) if self.supported_depth_levels else 0

    # ── Factory methods for common broker configurations ──────────────

    @classmethod
    def for_dhan_equity(cls) -> InstrumentCapabilities:
        return cls(
            supported_depth_levels=frozenset({5, 20}),
            supports_streaming=True,
            supports_depth_streaming=True,
            supports_oi=False,
        )

    @classmethod
    def for_dhan_derivative(cls) -> InstrumentCapabilities:
        return cls(
            supported_depth_levels=frozenset({5, 20, 200}),
            supports_streaming=True,
            supports_depth_streaming=True,
            supports_oi=True,
            supports_greeks=True,
        )

    @classmethod
    def for_upstox_equity(cls) -> InstrumentCapabilities:
        return cls(
            supported_depth_levels=frozenset({5, 30}),
            supports_streaming=True,
            supports_depth_streaming=True,
            supports_oi=False,
        )

    @classmethod
    def for_upstox_derivative(cls) -> InstrumentCapabilities:
        return cls(
            supported_depth_levels=frozenset({5, 30}),
            supports_streaming=True,
            supports_depth_streaming=True,
            supports_oi=True,
            supports_greeks=True,
        )

    @classmethod
    def for_paper(cls) -> InstrumentCapabilities:
        return cls(
            supported_depth_levels=frozenset({5}),
            supports_streaming=False,
            supports_depth_streaming=False,
        )
