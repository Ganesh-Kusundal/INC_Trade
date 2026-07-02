"""Neutral trading DTOs for orchestrator boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class CandidateDTO:
    """Scanner output passed to execution layer."""

    symbol: str
    exchange: str
    score: Decimal
    metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    strategy_id: str = ""
    timestamp: str = ""


@dataclass(frozen=True, slots=True)
class SignalDTO:
    """Strategy signal passed to execution layer."""

    symbol: str
    exchange: str
    side: str
    signal_type: str
    confidence: Decimal
    quantity: int = 0
    price: Decimal | None = None
    entry_price: Decimal | None = None
    strategy: str = ""
    position_size_pct: Decimal = Decimal("0")
    metadata: dict[str, Any] | None = None

    @property
    def is_actionable(self) -> bool:
        return self.signal_type in (
            "BUY",
            "SELL",
            "STRONG_BUY",
            "STRONG_SELL",
            "ENTRY",
            "EXIT",
        ) and self.confidence > Decimal("0")


__all__ = ["CandidateDTO", "SignalDTO"]
