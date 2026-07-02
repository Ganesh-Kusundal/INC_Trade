"""Alert and PnL domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class ConditionalAlert:
    """Conditional alert state.

    Frozen for immutability.
    """

    alert_id: str = ""
    symbol: str = ""
    condition: str = ""
    status: str = "ACTIVE"


@dataclass(slots=True, frozen=True)
class ConditionalAlertRequest:
    """Request model for placing a conditional alert.

    Frozen for immutability.
    """

    symbol: str = ""
    exchange: str = "NSE"
    condition_type: str = ""
    threshold: Decimal = Decimal("0")


@dataclass(slots=True, frozen=False)
class MarketIntelligenceSnapshot:
    """One-shot aggregate of market intelligence for an underlying.

    Kept as ``frozen=False`` because ``oi_data`` is a mutable dict
    that is built incrementally.
    """

    underlying: str = ""
    pcr: Decimal = Decimal("0")
    max_pain: Decimal = Decimal("0")
    oi_data: dict = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class PnlExitPolicy:
    """Policy for PnL-based exit automation.

    Frozen for immutability.
    """

    target_pnl: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")


@dataclass(slots=True, frozen=True)
class PnlExitResult:
    """Result returned by PnL-exit automation.

    Frozen for immutability.
    """

    success: bool = False
    message: str = ""
