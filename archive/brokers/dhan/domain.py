"""Dhan broker domain models — Dhan-only types with silent canonical re-exports.

Canonical order/trade types resolve via ``__getattr__`` to :mod:`domain`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

import domain.entities.instrument

_CANONICAL = frozenset(
    {
        "Holding",
        "Order",
        "OrderStatus",
        "OrderType",
        "Position",
        "ProductType",
        "Side",
        "Trade",
        "Validity",
        "OrderSide",
    }
)

_ALIASES = {"OrderSide": "Side"}


def __getattr__(name: str) -> Any:
    if name in _CANONICAL:
        import domain as _domain

        return getattr(_domain, _ALIASES.get(name, name))
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Dhan-specific enums ────────────────────────────────────────────────────


class Exchange(str, Enum):
    """Dhan short exchange codes (deprecated — prefer ExchangeSegment at boundaries)."""

    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"
    INDEX = "INDEX"


class DhanInstrumentType(str, Enum):
    """Dhan instrument categories."""

    EQUITY = "EQUITY"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    COMMODITY = "COMMODITY"


# Backward compatibility aliases
InstrumentType = DhanInstrumentType


class OptionType(str, Enum):
    """Option flavour."""

    CALL = "CALL"
    PUT = "PUT"


# ── Dhan-specific dataclasses ──────────────────────────────────────────────


@dataclass(frozen=True)
class MarginRequest:
    """Request shape for margin calculation."""

    symbol: str
    exchange: str
    quantity: int
    product_type: str
    order_type: str
    price: Decimal | None = None
    trigger_price: Decimal | None = None


@dataclass(frozen=True)
class MarginResponse:
    """Response from margin calculation API."""

    total_margin: Decimal
    order_margin: Decimal
    exposure_margin: Decimal
    available_margin: Decimal | None = None
    span_margin: Decimal | None = None


@dataclass(frozen=True)
class AlertRequest:
    """Request to create a price alert."""

    symbol: str
    exchange: str
    condition: str  # LTP_CROSSES_ABOVE, LTP_CROSSES_BELOW
    trigger_price: Decimal
    valid_until: str | None = None  # YYYY-MM-DD format


@dataclass(frozen=True)
class Alert:
    """Represents a created alert."""

    alert_id: str
    symbol: str
    exchange: str
    condition: str
    trigger_price: Decimal
    active: bool
    created_at: str | None = None


@dataclass(frozen=True)
class Instrument:
    """Full instrument definition as resolved by the Dhan symbol resolver.

    Uses composition to hold a reference to the canonical domain.Instrument.
    """

    domain_instrument: 'domain.entities.instrument.Instrument'
    exchange: Exchange
    instrument_type: DhanInstrumentType
    option_type: OptionType | None = None
    sm_symbol_name: str | None = None

    @property
    def symbol(self) -> str:
        return self.domain_instrument.symbol

    @property
    def security_id(self) -> str:
        return self.domain_instrument.security_id

    @property
    def lot_size(self) -> int:
        return self.domain_instrument.lot_size

    @property
    def tick_size(self) -> Decimal:
        return self.domain_instrument.tick_size

    @property
    def name(self) -> str | None:
        return self.domain_instrument.name

    @property
    def strike_price(self) -> Decimal | None:
        return self.domain_instrument.strike_price

    @property
    def expiry(self) -> str | None:
        return self.domain_instrument.expiry

    @property
    def underlying(self) -> str | None:
        return self.domain_instrument.underlying

    @property
    def canonical_symbol(self) -> str | None:
        return self.domain_instrument.canonical_symbol

    @property
    def is_option(self) -> bool:
        return self.instrument_type == DhanInstrumentType.OPTION

    @property
    def is_future(self) -> bool:
        return self.instrument_type == DhanInstrumentType.FUTURE


# OrderSide remains available via __getattr__ deprecation shim.


@dataclass(frozen=True)
class SuperOrderLeg:
    """Individual leg of a super order (Entry, Target, Stop Loss)."""

    leg_name: str  # ENTRY_LEG, TARGET_LEG, STOP_LOSS_LEG
    transaction_type: str
    quantity: int
    price: Decimal
    trigger_price: Decimal | None = None
    order_status: str | None = None
    trailing_jump: Decimal | None = None


@dataclass(frozen=True)
class SuperOrder:
    """Super Order with Entry + Target + Stop Loss + Trailing SL."""

    order_id: str
    correlation_id: str | None
    transaction_type: str
    exchange_segment: str
    product_type: str
    order_type: str
    security_id: str
    quantity: int
    price: Decimal
    target_price: Decimal
    stop_loss_price: Decimal
    trailing_jump: Decimal
    order_status: str
    leg_details: list[SuperOrderLeg]
    trading_symbol: str | None = None
    created_time: str | None = None


# ── Forever Orders ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ForeverOrderRequest:
    """Request to place a forever order (SINGLE or OCO)."""

    symbol: str
    exchange: str
    order_flag: str  # SINGLE or OCO
    transaction_type: str
    product_type: str
    order_type: str
    quantity: int
    price: Decimal
    trigger_price: Decimal
    price1: Decimal | None = None  # OCO target price
    trigger_price1: Decimal | None = None  # OCO target trigger
    quantity1: int | None = None  # OCO target quantity
    validity: str = "DAY"
    correlation_id: str | None = None


@dataclass(frozen=True)
class ForeverOrder:
    """Forever Order (Single GTT or OCO)."""

    order_id: str
    order_status: str
    order_flag: str  # SINGLE or OCO
    transaction_type: str
    exchange_segment: str
    product_type: str
    order_type: str
    trading_symbol: str
    security_id: str
    quantity: int
    price: Decimal
    trigger_price: Decimal
    leg_name: str | None = None
    created_time: str | None = None


# ── Conditional Triggers ─────────────────────────────────────────────────


@dataclass(frozen=True)
class ConditionalTriggerRequest:
    """Request to create a conditional trigger (price-based)."""

    symbol: str
    exchange: str
    comparison_type: str  # PRICE_WITH_VALUE
    operator: str  # CROSSING_UP, CROSSING_DOWN, GREATER_THAN, LESS_THAN
    comparing_value: Decimal
    exp_date: str  # YYYY-MM-DD
    frequency: str = "ONCE"
    orders: list[dict] | None = None  # Orders to execute when triggered
    user_note: str | None = None


@dataclass(frozen=True)
class ConditionalTrigger:
    """Conditional trigger order."""

    alert_id: str
    alert_status: str
    comparison_type: str
    exchange_segment: str
    security_id: str
    operator: str
    comparing_value: Decimal
    exp_date: str
    frequency: str
    orders: list[dict]
    created_time: str | None = None
    triggered_time: str | None = None
    last_price: Decimal | None = None
    user_note: str | None = None


# ── Ledger ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerEntry:
    """Ledger entry for account transactions."""

    narration: str
    voucher_date: str
    exchange: str
    voucher_description: str
    voucher_number: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


# ── User Profile ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UserProfile:
    """User profile information."""

    token_valid: bool
    active_segments: list[str]
    ddpi_status: str
    mtf_enabled: bool
    data_api_subscription: str
    user_configurations: dict[str, Any]


# ── IP Management ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IPConfig:
    """IP configuration for static IP whitelisting."""

    ip_address: str
    ip_type: str  # PRIMARY or SECONDARY
    status: str


# ── Exit All ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExitAllResponse:
    """Response from exit all operation."""

    positions_closed: int
    orders_cancelled: int
    success: bool
    message: str
