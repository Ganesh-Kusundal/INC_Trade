"""Exchange classification constants."""

from __future__ import annotations

EQUITY_EXCHANGES = frozenset({"NSE", "BSE"})
DERIVATIVE_EXCHANGES = frozenset({"NFO", "BFO", "MCX", "CDS", "BCD"})

# Default exchange values for function parameter defaults.
# Use these instead of hardcoded string literals.
DEFAULT_EQUITY_EXCHANGE = "NSE"
DEFAULT_DERIVATIVE_EXCHANGE = "NFO"
