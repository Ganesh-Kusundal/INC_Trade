"""Domain enumerations — the vocabulary of the trading domain.

These enums define the allowed values for order parameters, exchange segments,
and status tracking. They are the innermost layer with zero dependencies.
"""

from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY

    @classmethod
    def from_string(cls, value: str) -> Side:
        """Parse a side string into a Side enum, case-insensitive.

        Accepts common variations:
        - ``"BUY"``, ``"buy"``, ``"Buy"`` → ``Side.BUY``
        - ``"SELL"``, ``"sell"``, ``"Sell"`` → ``Side.SELL``

        Args:
            value: The side string to parse.

        Returns:
            The matching Side enum value.

        Raises:
            ValueError: If the string does not match any Side value.
        """
        normalized = value.upper().strip()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(
            f"Invalid side: {value!r}. Valid: {[m.value for m in cls]}"
        )


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"

    @property
    def is_limit(self) -> bool:
        return self is OrderType.LIMIT

    @property
    def is_stop(self) -> bool:
        return self in (OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET)

    @classmethod
    def from_string(cls, value: str) -> OrderType:
        """Parse an order type string into an OrderType enum, case-insensitive.

        Accepts common wire-format variations:
        - ``"MARKET"``, ``"MKT"`` → ``OrderType.MARKET``
        - ``"LIMIT"``, ``"LMT"`` → ``OrderType.LIMIT``
        - ``"STOP_LOSS"``, ``"SL"`` → ``OrderType.STOP_LOSS``
        - ``"STOP_LOSS_MARKET"``, ``"SL-M"``, ``"SLM"`` → ``OrderType.STOP_LOSS_MARKET``

        Args:
            value: The order type string to parse.

        Returns:
            The matching OrderType enum value.

        Raises:
            ValueError: If the string does not match any OrderType value.
        """
        normalized = value.upper().strip()
        # Handle common wire-format aliases
        _ALIASES: dict[str, OrderType] = {
            "MKT": cls.MARKET,
            "LMT": cls.LIMIT,
            "SL": cls.STOP_LOSS,
            "SL-M": cls.STOP_LOSS_MARKET,
            "SLM": cls.STOP_LOSS_MARKET,
            "STOPLOSS": cls.STOP_LOSS,
            "STOPLOSSMARKET": cls.STOP_LOSS_MARKET,
        }
        if normalized in _ALIASES:
            return _ALIASES[normalized]
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(
            f"Invalid order type: {value!r}. Valid: {[m.value for m in cls]}"
        )


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    PARTIALLY_CANCELLED = "PARTIALLY_CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"

    @property
    def is_terminal(self) -> bool:
        return self in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.PARTIALLY_CANCELLED,
            OrderStatus.EXPIRED,
            OrderStatus.REJECTED,
        )

    @property
    def is_active(self) -> bool:
        return self in (
            OrderStatus.PENDING,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        )


class ProductType(str, Enum):
    INTRADAY = "INTRADAY"
    DELIVERY = "DELIVERY"
    MARGIN = "MARGIN"


class Validity(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    GTT = "GTT"


class AuthMode(str, Enum):
    STATIC = "STATIC"
    TOTP = "TOTP"
    OAUTH = "OAUTH"
    INTERACTIVE = "INTERACTIVE"
    EXTENDED = "EXTENDED"
    WEBHOOK = "WEBHOOK"

    @property
    def supports_refresh(self) -> bool:
        return self in (AuthMode.OAUTH, AuthMode.TOTP, AuthMode.INTERACTIVE)

    @property
    def is_long_lived(self) -> bool:
        return self in (AuthMode.EXTENDED, AuthMode.STATIC)


class BrokerID(str, Enum):
    """Canonical broker identifiers — type-safe broker selection."""

    DHAN = "dhan"
    UPSTOX = "upstox"
    PAPER = "paper"

    @classmethod
    def from_string(cls, value: str) -> BrokerID:
        """Parse a broker string into a BrokerID, case-insensitive."""
        value = value.lower().strip()
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown broker: {value!r}. Valid: {[m.value for m in cls]}")

    def to_string(self) -> str:
        return self.value
