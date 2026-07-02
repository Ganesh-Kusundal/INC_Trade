"""Canonical domain dataclasses — value objects returned by broker adapters.

This package re-exports all entities for backward compatibility::

    from domain.entities import Order, Position, Balance

The individual sub-modules are::

    domain.entities.order      — Order, OrderResponse, FieldMapping
    domain.entities.order_lifecycle — ORDER_STATUS_TRANSITIONS
    domain.entities.trade      — Trade
    domain.entities.position   — Position, Holding, PositionState, POSITION_STATE_TRANSITIONS
    domain.entities.account    — Balance, FundLimits (alias)
    domain.entities.market     — Quote, MarketDepth, DepthLevel, DepthKind, MarketTick, QuoteSnapshot
    domain.entities.options    — OptionChain, OptionStrike, OptionLeg, FutureChain, FutureContract, OptionContract
    domain.entities.instrument — Instrument
    domain.entities.alerts     — ConditionalAlert, ConditionalAlertRequest, MarketIntelligenceSnapshot, PnlExitPolicy, PnlExitResult
"""

from __future__ import annotations

# Account (FundLimits consolidated into Balance)
from domain.entities.account import (
    Balance,
    FundLimits,
)

# Alerts / PnL (frozen where applicable)
from domain.entities.alerts import (
    ConditionalAlert,
    ConditionalAlertRequest,
    MarketIntelligenceSnapshot,
    PnlExitPolicy,
    PnlExitResult,
)

# Instrument (frozen)
from domain.entities.instrument import Instrument

# Market data
from domain.entities.market import (
    DepthKind,
    DepthLevel,
    MarketDepth,
    MarketTick,
    Quote,
    QuoteSnapshot,
)

# Options / Futures
from domain.entities.options import (
    FutureChain,
    FutureContract,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionStrike,
)

# Order-related
from domain.entities.order import (
    FieldMapping,
    Order,
    OrderResponse,
)
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS

# Position / Holding
from domain.entities.position import (
    POSITION_STATE_TRANSITIONS,
    Holding,
    Position,
    PositionState,
)

# Trade
from domain.entities.trade import Trade

__all__ = [
    "ORDER_STATUS_TRANSITIONS",
    "POSITION_STATE_TRANSITIONS",
    "Balance",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "DepthKind",
    "DepthLevel",
    "FieldMapping",
    "FundLimits",
    "FutureChain",
    "FutureContract",
    "Holding",
    "Instrument",
    "MarketDepth",
    "MarketIntelligenceSnapshot",
    "MarketTick",
    "OptionChain",
    "OptionContract",
    "OptionLeg",
    "OptionStrike",
    "Order",
    "OrderResponse",
    "PnlExitPolicy",
    "PnlExitResult",
    "Position",
    "PositionState",
    "Quote",
    "QuoteSnapshot",
    "Trade",
]
