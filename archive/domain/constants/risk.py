"""Risk management and capital constants.

All constants governing risk thresholds, position limits, exposure caps,
and phantom capital defaults.
"""

from __future__ import annotations

from decimal import Decimal

# ── Risk / capital ─────────────────────────────────────────────────────────

#: Daily-loss cap (percent) — RiskManager default.
RISK_DAILY_LOSS_PERCENT: float = 5.0

#: Per-position exposure cap (percent) — RiskManager default.
RISK_POSITION_PERCENT: float = 20.0

#: Gross exposure cap (percent of capital) — RiskManager default.
RISK_GROSS_PERCENT: float = 100.0

#: Loss-based circuit breaker threshold (percent of capital).
RISK_LOSS_CIRCUIT_BREAKER_PERCENT: float = 2.0

#: Cooldown period after circuit breaker trips (seconds).
RISK_LOSS_CB_COOLDOWN_SECONDS: int = 1800  # 30 minutes

#: Rolling loss window for the loss-based circuit breaker (seconds).
RISK_LOSS_CB_WINDOW_SECONDS: int = 86400  # 24 hours

#: Safety multiplier for margin check (20% buffer for intraday price movement).
RISK_MARGIN_SAFETY_MULTIPLIER: float = 1.2

#: Phantom capital (INR) used when ``capital_fn`` is not configured. This
#: MUST be replaced with a real capital source before live trading; the
#: production-readiness check fails closed if the operator
#: leaves ``RISK_FAIL_OPEN=1`` set.
PHANTOM_CAPITAL_INR: Decimal = Decimal("1_000_000")

#: High-notional INR threshold above which Dhan order placement logs
#: a warning. Dhan's "kill switch" advisory is on a similar value but
#: is governed by the broker, not by us.
DHAN_NOTIONAL_WARNING_INR: Decimal = Decimal("50_000")

__all__ = [
    "DHAN_NOTIONAL_WARNING_INR",
    "PHANTOM_CAPITAL_INR",
    "RISK_DAILY_LOSS_PERCENT",
    "RISK_GROSS_PERCENT",
    "RISK_LOSS_CB_COOLDOWN_SECONDS",
    "RISK_LOSS_CB_WINDOW_SECONDS",
    "RISK_LOSS_CIRCUIT_BREAKER_PERCENT",
    "RISK_MARGIN_SAFETY_MULTIPLIER",
    "RISK_POSITION_PERCENT",
]
