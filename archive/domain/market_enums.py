"""Market and instrument taxonomy enums.

Submodule of :mod:`domain.types` — imported via the re-export facade.
"""

from __future__ import annotations

from enum import Enum


class ExchangeSegment(str, Enum):
    """Exchange segments supported by the broker system.

    The values use canonical wire-format strings (e.g. "NSE_EQ") so the
    segment string in the HTTP payload matches what the broker expects.
    """

    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX = "MCXCOMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    IDX_I = "IDX_I"


class InstrumentType(str, Enum):
    """Canonical instrument type categories."""

    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"
