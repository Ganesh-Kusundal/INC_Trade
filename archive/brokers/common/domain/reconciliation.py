"""Canonical reconciliation types — drift detection and reporting.

Used by every broker's reconciliation service to report drift between
local OMS state and broker-authoritative state.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=False)
class DriftItem:
    """Canonical reconciliation drift entry."""

    kind: str
    severity: str
    symbol: str = ""
    details: str = ""
    payload: dict | None = None


@dataclass(slots=True, frozen=False)
class ReconciliationReport:
    """Canonical reconciliation report — used by every broker adapter."""

    drift_items: list[DriftItem] = field(default_factory=list)
    broker_orders: int = 0
    broker_positions: int = 0
    orders_repaired: int = 0
    positions_repaired: int = 0
    timestamp_ms: int = 0

    @property
    def has_drift(self) -> bool:
        return len(self.drift_items) > 0

    @property
    def high_severity_count(self) -> int:
        return sum(1 for d in self.drift_items if d.severity == "HIGH")
