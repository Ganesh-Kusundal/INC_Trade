"""Capability surface manifest — SSOT for broker → gateway capability coverage.

Each :class:`CapabilitySurface` records how a feature is implemented at the
broker layer and whether it is exposed via the gateway.

This is a simplified version of the full manifest. The full archive version
tracked CLI/REST exposure per surface; this version focuses on the
broker-layer implementation status and gateway method mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Capability(str, Enum):
    """Broker capability identifiers.

    Used to tag which broker features are supported and which
    gateway methods map to them.
    """

    MARKET_DATA = "MARKET_DATA"
    HISTORICAL_DATA = "HISTORICAL_DATA"
    DEPTH = "DEPTH"
    DEPTH_30 = "DEPTH_30"
    OPTIONS_CHAIN = "OPTIONS_CHAIN"
    FUTURES = "FUTURES"
    OPTION_GREEKS = "OPTION_GREEKS"
    WEBSOCKET = "WEBSOCKET"
    ORDER_COMMAND = "ORDER_COMMAND"
    ORDER_QUERY = "ORDER_QUERY"
    HISTORICAL_TRADES = "HISTORICAL_TRADES"
    PORTFOLIO = "PORTFOLIO"
    INSTRUMENTS = "INSTRUMENTS"
    INSTRUMENT_SEARCH = "INSTRUMENT_SEARCH"
    ALERTS = "ALERTS"
    MARGIN = "MARGIN"
    EXIT_ALL = "EXIT_ALL"
    STATIC_IP = "STATIC_IP"
    GTT_ORDER = "GTT_ORDER"
    COVER_ORDER = "COVER_ORDER"
    SLICE_ORDER = "SLICE_ORDER"
    KILL_SWITCH = "KILL_SWITCH"
    IPO = "IPO"
    MUTUAL_FUNDS = "MUTUAL_FUNDS"
    PAYMENTS = "PAYMENTS"
    FUNDAMENTALS = "FUNDAMENTALS"
    NEWS = "NEWS"
    MARKET_STATUS = "MARKET_STATUS"
    ORDER_STREAM = "ORDER_STREAM"
    PORTFOLIO_STREAM = "PORTFOLIO_STREAM"
    IDEMPOTENCY = "IDEMPOTENCY"
    MULTI_ORDER = "MULTI_ORDER"
    SESSION_RISK = "SESSION_RISK"
    SMARTLIST = "SMARTLIST"
    FII_DII = "FII_DII"
    OI_PCR_MAXPAIN = "OI_PCR_MAXPAIN"
    MARKET_INTELLIGENCE = "MARKET_INTELLIGENCE"
    LEVEL2_MARKET_DATA = "LEVEL2_MARKET_DATA"
    TSL = "TSL"
    MTF = "MTF"
    WEBHOOKS = "WEBHOOKS"
    AMO_ORDER = "AMO_ORDER"
    ORDER_SLICING = "ORDER_SLICING"
    GLOBAL_MARKETS = "GLOBAL_MARKETS"
    VOLATILITY_INDEX = "VOLATILITY_INDEX"


Tier = Literal["core", "extended", "broker_only"]
Severity = Literal["P0", "P1", "P2", "P3"]


@dataclass(frozen=True)
class BrokerMethodRef:
    """Broker-layer method reference."""

    dhan: str | None = None
    upstox: str | None = None
    dhan_gateway: bool = True
    upstox_gateway: bool = True
    upstox_known_gap: str | None = None


@dataclass(frozen=True)
class CapabilitySurface:
    """One auditable capability surface."""

    id: str
    capability: Capability | None
    gateway_method: str | None
    abc_required: bool = False
    extended_only: bool = False
    broker: BrokerMethodRef = field(default_factory=BrokerMethodRef)
    tier: Tier = "core"
    broker_only_reason: str | None = None
    severity_if_gap: Severity = "P2"
    notes: str = ""


# ── Core capability surfaces ─────────────────────────────────────────────

CAPABILITY_SURFACES: tuple[CapabilitySurface, ...] = (
    # Market data
    CapabilitySurface(
        id="market_data.history",
        capability=Capability.HISTORICAL_DATA,
        gateway_method="history",
        abc_required=True,
        broker=BrokerMethodRef(dhan="historical.get_historical", upstox="historical.fetch_candles"),
    ),
    CapabilitySurface(
        id="market_data.quote",
        capability=Capability.MARKET_DATA,
        gateway_method="quote",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_quote", upstox="market_data.get_quote"),
    ),
    CapabilitySurface(
        id="market_data.ltp",
        capability=Capability.MARKET_DATA,
        gateway_method="ltp",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_ltp", upstox="market_data.get_ltp"),
    ),
    CapabilitySurface(
        id="market_data.depth",
        capability=Capability.DEPTH,
        gateway_method="depth",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_depth", upstox="market_data.get_depth"),
    ),
    CapabilitySurface(
        id="derivatives.option_chain",
        capability=Capability.OPTIONS_CHAIN,
        gateway_method="option_chain",
        abc_required=True,
        broker=BrokerMethodRef(dhan="options.get_option_chain", upstox="options.get_option_chain"),
    ),
    CapabilitySurface(
        id="derivatives.future_chain",
        capability=Capability.FUTURES,
        gateway_method="future_chain",
        abc_required=True,
        broker=BrokerMethodRef(dhan="futures.get_contracts", upstox="futures.get_contracts"),
    ),
    CapabilitySurface(
        id="streaming.websocket",
        capability=Capability.WEBSOCKET,
        gateway_method="stream",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_feed.subscribe", upstox="market_data_v3.subscribe"),
    ),
    # Orders
    CapabilitySurface(
        id="orders.place",
        capability=Capability.ORDER_COMMAND,
        gateway_method="place_order",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.place_order", upstox="order_command.place_order"),
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="orders.cancel",
        capability=Capability.ORDER_COMMAND,
        gateway_method="cancel_order",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.cancel_order", upstox="order_command.cancel_order"),
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="orders.modify",
        capability=Capability.ORDER_COMMAND,
        gateway_method="modify_order",
        broker=BrokerMethodRef(dhan="orders.modify_order", upstox="order_command.modify_order"),
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="orders.query_orderbook",
        capability=Capability.ORDER_QUERY,
        gateway_method="get_orderbook",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.get_orderbook", upstox="order_query.get_order_list"),
    ),
    CapabilitySurface(
        id="orders.query_trades",
        capability=Capability.HISTORICAL_TRADES,
        gateway_method="get_trade_book",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.get_trade_book", upstox="order_query.get_trades"),
    ),
    # Portfolio
    CapabilitySurface(
        id="portfolio.positions",
        capability=Capability.PORTFOLIO,
        gateway_method="positions",
        abc_required=True,
        broker=BrokerMethodRef(dhan="portfolio.get_positions", upstox="portfolio.get_positions"),
    ),
    CapabilitySurface(
        id="portfolio.holdings",
        capability=Capability.PORTFOLIO,
        gateway_method="holdings",
        abc_required=True,
        broker=BrokerMethodRef(dhan="portfolio.get_holdings", upstox="portfolio.get_holdings"),
    ),
    CapabilitySurface(
        id="portfolio.funds",
        capability=Capability.PORTFOLIO,
        gateway_method="funds",
        abc_required=True,
        broker=BrokerMethodRef(dhan="portfolio.get_balance", upstox="portfolio.get_balance"),
    ),
    # Instruments
    CapabilitySurface(
        id="instruments.search",
        capability=Capability.INSTRUMENT_SEARCH,
        gateway_method="search",
        abc_required=True,
        broker=BrokerMethodRef(dhan="resolver", upstox="instrument_resolver.search"),
    ),
    CapabilitySurface(
        id="instruments.load",
        capability=Capability.INSTRUMENTS,
        gateway_method="load_instruments",
        abc_required=True,
        broker=BrokerMethodRef(dhan="load_instruments", upstox="instrument_loader.load"),
        tier="broker_only",
    ),
    # Extended Dhan
    CapabilitySurface(
        id="extended.super_orders",
        capability=None,
        gateway_method="extended.place_super_order",
        extended_only=True,
        broker=BrokerMethodRef(dhan="super_orders.place_super_order", upstox=None),
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.forever_orders",
        capability=Capability.GTT_ORDER,
        gateway_method="extended.place_forever_order",
        extended_only=True,
        broker=BrokerMethodRef(dhan="forever_orders.place_forever_order", upstox="gtt.place_forever_order"),
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.conditional_triggers",
        capability=Capability.ALERTS,
        gateway_method="extended.place_conditional_trigger",
        extended_only=True,
        broker=BrokerMethodRef(dhan="conditional_triggers.place_trigger", upstox="gtt.place_alert"),
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.margin",
        capability=Capability.MARGIN,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan="margin.calculate", upstox="margin.calculate_margin"),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.exit_all",
        capability=Capability.EXIT_ALL,
        gateway_method="extended.exit_all",
        extended_only=True,
        broker=BrokerMethodRef(dhan="exit_all.exit_all", upstox="exit_all.exit_all"),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.ledger",
        capability=None,
        gateway_method="extended.get_ledger",
        extended_only=True,
        broker=BrokerMethodRef(dhan="ledger.get_ledger", upstox=None),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.edis",
        capability=None,
        gateway_method="extended.authorize_edis",
        extended_only=True,
        broker=BrokerMethodRef(dhan="edis.authorize_edis", upstox=None),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.ip_management",
        capability=Capability.STATIC_IP,
        gateway_method="extended.set_ip",
        extended_only=True,
        broker=BrokerMethodRef(dhan="ip_management.set_ip", upstox="static_ip.set_static_ip"),
        tier="extended",
    ),
    # Extended Upstox
    CapabilitySurface(
        id="extended.gtt_order",
        capability=Capability.GTT_ORDER,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="gtt.place_gtt_order"),
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.cover_order",
        capability=Capability.COVER_ORDER,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="cover.place_cover_order"),
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.slice_order",
        capability=Capability.SLICE_ORDER,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan="orders.place_slice_order", upstox="slice.place_slice_order"),
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.ipo",
        capability=Capability.IPO,
        gateway_method="extended.get_ipos",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="ipo.get_ipos"),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.mutual_funds",
        capability=Capability.MUTUAL_FUNDS,
        gateway_method="extended.place_mutual_fund_order",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="mutual_funds.place_order"),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.payments",
        capability=Capability.PAYMENTS,
        gateway_method="extended.initiate_payout",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="payments.initiate_payout"),
        tier="extended",
    ),
    CapabilitySurface(
        id="extended.fundamentals",
        capability=Capability.FUNDAMENTALS,
        gateway_method="extended.get_pnl",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="fundamentals.get_pnl"),
        tier="extended",
    ),
    # Broker-only capabilities
    CapabilitySurface(
        id="capability.news",
        capability=Capability.NEWS,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="news.get_news"),
        tier="extended",
    ),
    CapabilitySurface(
        id="capability.market_status",
        capability=Capability.MARKET_STATUS,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="market_status.get_market_status"),
        tier="broker_only",
    ),
    CapabilitySurface(
        id="capability.order_stream",
        capability=Capability.ORDER_STREAM,
        gateway_method=None,
        broker=BrokerMethodRef(dhan="order_stream.connect", upstox=None),
        tier="extended",
    ),
    CapabilitySurface(
        id="capability.market_intelligence",
        capability=Capability.MARKET_INTELLIGENCE,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_snapshot"),
        tier="broker_only",
    ),
    CapabilitySurface(
        id="capability.fii_dii",
        capability=Capability.FII_DII,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_fii_flow"),
        tier="broker_only",
    ),
    CapabilitySurface(
        id="capability.oi_pcr_maxpain",
        capability=Capability.OI_PCR_MAXPAIN,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_pcr"),
        tier="extended",
    ),
)


# ── Lookup helpers ──────────────────────────────────────────────────────


def all_surfaces() -> tuple[CapabilitySurface, ...]:
    """Return all registered capability surfaces."""
    return CAPABILITY_SURFACES


def surface_by_id(surface_id: str) -> CapabilitySurface | None:
    """Lookup a surface by id."""
    for s in CAPABILITY_SURFACES:
        if s.id == surface_id:
            return s
    return None


def surfaces_for_capability(cap: Capability) -> list[CapabilitySurface]:
    """Return all surfaces mapped to a capability enum value."""
    return [s for s in CAPABILITY_SURFACES if s.capability == cap]


def broker_only_capabilities() -> frozenset[Capability]:
    """Capabilities explicitly marked broker_only on their primary surface."""
    result: set[Capability] = set()
    for s in CAPABILITY_SURFACES:
        if s.capability is not None and s.tier == "broker_only":
            result.add(s.capability)
    return frozenset(result)


def mapped_capability_values() -> frozenset[Capability]:
    """Capability enum values referenced by at least one surface."""
    return frozenset(s.capability for s in CAPABILITY_SURFACES if s.capability is not None)


__all__ = [
    "CAPABILITY_SURFACES",
    "BrokerMethodRef",
    "Capability",
    "CapabilitySurface",
    "all_surfaces",
    "broker_only_capabilities",
    "mapped_capability_values",
    "surface_by_id",
    "surfaces_for_capability",
]
