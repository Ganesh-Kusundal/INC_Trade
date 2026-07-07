"""Canonical enums for the broker SDK domain layer.

Single source of truth for all enumerated types.  No external dependencies.
"""

from __future__ import annotations

from enum import Enum


class Exchange(str, Enum):
    """Supported exchanges."""

    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    MCX = "MCX"
    INDEX = "INDEX"


class AssetClass(str, Enum):
    """Asset classification — replaces the old ``InstrumentType``.

    Values are singular (``FUTURE`` not ``FUTURES``) to match the v2
    architecture where each instrument has exactly one asset class.
    """

    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    INDEX = "INDEX"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"
    CRYPTO = "CRYPTO"
    ETF = "ETF"
    SPOT = "SPOT"


class OptionType(str, Enum):
    """Option right (call/put)."""

    CALL = "CALL"
    PUT = "PUT"


class Side(str, Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order lifecycle states.

    PENDING is the initial state before the broker acknowledges the order.
    """

    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class OrderType(str, Enum):
    """Order pricing type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class ProductType(str, Enum):
    """Order product code (intraday, delivery, margin)."""

    CNC = "CNC"
    INTRADAY = "INTRADAY"
    MARGIN = "MARGIN"
    MTF = "MTF"


class Validity(str, Enum):
    """Order validity period."""

    DAY = "DAY"
    IOC = "IOC"


class InstrumentType(str, Enum):
    """Legacy instrument type classification (used by instrument resolvers)."""

    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    INDEX = "INDEX"
    COMMODITY = "COMMODITY"
    CURRENCY = "CURRENCY"


__all__ = [
    "AssetClass",
    "Exchange",
    "OptionType",
    "OrderStatus",
    "OrderType",
    "ProductType",
    "Side",
    "Validity",
    "InstrumentType",
]
