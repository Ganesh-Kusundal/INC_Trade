"""Dhan reconciliation models — drift detection and reporting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DriftSeverity = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(slots=True)
class DriftItem:
    """Canonical reconciliation drift entry."""

    kind: str
    severity: DriftSeverity
    symbol: str = ""
    details: str = ""
    payload: dict | None = None


@dataclass(slots=True)
class ReconciliationReport:
    """Reconciliation report produced after comparing local OMS vs broker state."""

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
