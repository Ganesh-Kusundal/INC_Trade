"""Dhan extension data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class SuperOrderLeg:
    leg_name: str
    transaction_type: str = ""
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_status: str = ""
    trailing_jump: Decimal | None = None


@dataclass(frozen=True)
class SuperOrder:
    order_id: str
    correlation_id: str | None = None
    transaction_type: str = ""
    exchange_segment: str = ""
    product_type: str = ""
    order_type: str = ""
    security_id: str = ""
    quantity: int = 0
    price: Decimal = Decimal("0")
    target_price: Decimal = Decimal("0")
    stop_loss_price: Decimal = Decimal("0")
    trailing_jump: Decimal = Decimal("0")
    order_status: str = ""
    trading_symbol: str = ""
    leg_details: list[SuperOrderLeg] = field(default_factory=list)


@dataclass(frozen=True)
class MarginResponse:
    total_margin: Decimal
    order_margin: Decimal
    exposure_margin: Decimal
    available_margin: Decimal | None = None
    span_margin: Decimal | None = None


@dataclass(frozen=True)
class ForeverOrder:
    order_id: str
    order_status: str
    order_flag: str
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
