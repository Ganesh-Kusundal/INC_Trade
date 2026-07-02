"""Named constants for domain-critical default values.

Previously these were hardcoded magic numbers scattered across the codebase
(``Decimal("100000")``, ``Decimal("10000")``, etc.). Centralising them here
gives them names and provides a single grep target for audit.

Usage::

    from domain.constants.defaults import PAPER_INITIAL_CAPITAL, RISK_FALLBACK_CAPITAL
"""

from __future__ import annotations

from decimal import Decimal


# ── Risk / capital ──────────────────────────────────────────────────────────

RISK_FALLBACK_CAPITAL: Decimal = Decimal("100000")
"""Capital returned by :class:`GatewayCapitalProvider` when the gateway is
unavailable or ``funds()`` fails. Prevents silent zero-capital risk checks."""

#: Placeholder capital used when the operator has explicitly set
#: ``RISK_FAIL_OPEN=1`` and the gateway is unavailable.  This is the
#: **fail-open** value, distinct from :data:`RISK_FALLBACK_CAPITAL` (the
#: mid-range ``100 000`` fallback used by default-safe risk checks).
#: Historically this was the only named constant and was reused for
#: both purposes, conflating "sane fallback" with "manual override".
RISK_MANUAL_FAIL_OPEN: Decimal = Decimal("1000000")

#: Legacy alias — preserved so existing imports do not break during the
#: migration window.  Deprecated; prefer :data:`RISK_MANUAL_FAIL_OPEN`
#: for the fail-open placeholder and :data:`RISK_FALLBACK_CAPITAL` for
#: the default-safe fallback.
RISK_FAIL_OPEN_THRESHOLD: Decimal = RISK_MANUAL_FAIL_OPEN


# ── Paper trading ───────────────────────────────────────────────────────────

PAPER_INITIAL_CAPITAL: Decimal = Decimal("1000000")
"""Default initial capital for :class:`~brokers.paper.PaperGateway`."""

PAPER_MAX_POSITION_PCT: Decimal = Decimal("20.0")
"""Default per-position / gross-exposure / daily-loss defaults for
unrestricted paper-trading risk config.

.. NOTE::

 This value is a **percentage** (``20.0`` == 20 %), not an INR amount or
 a multiplier. The previous value ``Decimal("10000")`` was a typo that
 implied a 10 000 % position cap, effectively disabling paper-trading risk
 checks. See ref-1 in the architectural audit.
"""


# ── Synthetic data generation (PaperGateway history) ────────────────────────

SYNTHETIC_BASE_PRICE_MIN: float = 500.0
SYNTHETIC_BASE_PRICE_RANGE: float = 4500.0
SYNTHETIC_DAILY_VOLATILITY: float = 0.02
"""Parameters for the deterministic random-walk price generator in
:meth:`PaperGateway.history`.  These produce reproducible synthetic OHLCV
data seeded from the symbol name hash."""


# ── Default timeframes / lookbacks ──────────────────────────────────────────

DEFAULT_LOOKBACK_DAYS: int = 90
DEFAULT_TIMEFRAME: str = "1D"
"""Canonical defaults used in 15+ method signatures across the codebase."""
