"""Capability surface manifest — SSOT for broker → gateway → CLI → REST coverage.

Each :class:`CapabilitySurface` records how a feature is implemented at the
broker layer and whether it is exposed on CLI and REST surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from domain.capabilities import Capability

DataSource = Literal["live_broker", "datalake", "oms", "none", "mixed"]
Tier = Literal["core", "extended", "broker_only"]
Severity = Literal["P0", "P1", "P2", "P3"]
ExposureStatus = Literal["exposed", "gap", "broker_only", "partial", "mismatch"]


@dataclass(frozen=True)
class CliExposure:
    """CLI command that exercises a capability."""

    command: str
    module: str


@dataclass(frozen=True)
class RestExposure:
    """REST route that exercises a capability."""

    method: str
    path: str
    module: str
    data_source: DataSource


@dataclass(frozen=True)
class BrokerMethodRef:
    """Broker-layer method reference (connection-relative or module path)."""

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
    cli: tuple[CliExposure, ...] = ()
    rest: tuple[RestExposure, ...] = ()
    cli_data_source: DataSource = "live_broker"
    tier: Tier = "core"
    broker_only_reason: str | None = None
    severity_if_gap: Severity = "P2"
    notes: str = ""


# ── MarketDataGateway ABC methods (core tier) ─────────────────────────────

CAPABILITY_SURFACES: tuple[CapabilitySurface, ...] = (
    CapabilitySurface(
        id="market_data.history",
        capability=Capability.HISTORICAL_DATA,
        gateway_method="history",
        abc_required=True,
        broker=BrokerMethodRef(dhan="historical.get_historical", upstox="historical.fetch_candles"),
        cli=(
            CliExposure("historical", "cli/commands/market_handlers.py"),
            CliExposure("history", "cli/commands/market_handlers.py"),
        ),
        rest=(
            RestExposure("GET", "/api/v1/market/candles", "api/routers/market.py", "datalake"),
            RestExposure(
                "GET", "/api/v1/live/candles", "api/routers/live/market.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
        notes="Dual API: datalake candles + /live/candles broker history",
    ),
    CapabilitySurface(
        id="market_data.quote",
        capability=Capability.MARKET_DATA,
        gateway_method="quote",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_quote", upstox="market_data.get_quote"),
        cli=(CliExposure("quote", "cli/commands/market_handlers.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/market/quote/{symbol}", "api/routers/market.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/live/quote/{symbol}", "api/routers/live/market.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="market_data.ltp",
        capability=Capability.MARKET_DATA,
        gateway_method="ltp",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_ltp", upstox="market_data.get_ltp"),
        cli=(),
        rest=(
            RestExposure(
                "GET", "/api/v1/live/ltp/{symbol}", "api/routers/live/market.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="core",
        severity_if_gap="P2",
        notes="No dedicated CLI/REST; used internally by dashboard/validate",
    ),
    CapabilitySurface(
        id="market_data.depth",
        capability=Capability.DEPTH,
        gateway_method="depth",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_depth", upstox="market_data.get_depth"),
        cli=(CliExposure("depth", "cli/commands/market_handlers.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/live/depth/{symbol}", "api/routers/live/market.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="derivatives.option_chain",
        capability=Capability.OPTIONS_CHAIN,
        gateway_method="option_chain",
        abc_required=True,
        broker=BrokerMethodRef(dhan="options.get_option_chain", upstox="options.get_option_chain"),
        cli=(CliExposure("option-chain", "cli/commands/market_handlers.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/options/chain/{underlying}", "api/routers/options.py", "datalake"
            ),
            RestExposure(
                "GET",
                "/api/v1/live/options/chain/{underlying}",
                "api/routers/live/derivatives.py",
                "live_broker",
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="derivatives.future_chain",
        capability=Capability.FUTURES,
        gateway_method="future_chain",
        abc_required=True,
        broker=BrokerMethodRef(
            dhan="futures.get_contracts",
            upstox="futures.get_contracts",
        ),
        cli=(CliExposure("futures", "cli/commands/market_handlers.py"),),
        rest=(
            RestExposure(
                "GET",
                "/api/v1/live/futures/chain/{underlying}",
                "api/routers/live/derivatives.py",
                "live_broker",
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="streaming.websocket",
        capability=Capability.WEBSOCKET,
        gateway_method="stream",
        abc_required=True,
        broker=BrokerMethodRef(
            dhan="market_feed.subscribe",
            upstox="market_data_websocket.subscribe",
        ),
        cli=(
            CliExposure("stream", "cli/commands/market.py"),
            CliExposure("websocket", "cli/commands/websocket.py"),
        ),
        rest=(
            RestExposure("WS", "/ws/market", "api/ws/market.py", "live_broker"),
            RestExposure("WS", "/ws/market/{symbol}", "api/ws/market.py", "live_broker"),
        ),
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="batch.ltp_batch",
        capability=Capability.MARKET_DATA,
        gateway_method="ltp_batch",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_batch_ltp", upstox="market_data.get_ltp"),
        cli=(),
        rest=(),
        tier="broker_only",
        broker_only_reason="Batch API used internally; no user-facing surface",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="batch.quote_batch",
        capability=Capability.MARKET_DATA,
        gateway_method="quote_batch",
        abc_required=True,
        broker=BrokerMethodRef(dhan="market_data.get_batch_quote", upstox="market_data.get_quote"),
        cli=(),
        rest=(),
        tier="broker_only",
        broker_only_reason="Batch API used internally",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="batch.history_batch",
        capability=Capability.HISTORICAL_DATA,
        gateway_method="history_batch",
        abc_required=True,
        broker=BrokerMethodRef(
            dhan="historical.get_historical", upstox="historical.fetch_history_batch"
        ),
        cli=(),
        rest=(),
        tier="broker_only",
        broker_only_reason="Batch API used internally",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="orders.place",
        capability=Capability.ORDER_COMMAND,
        gateway_method="place_order",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.place_order", upstox="order_command.place_order"),
        cli=(
            CliExposure("place-order", "cli/commands/order_placement.py"),
            CliExposure("place-orders", "cli/commands/order_placement.py"),
            CliExposure("bracket-order", "cli/commands/order_composition.py"),
            CliExposure("oco-order", "cli/commands/order_composition.py"),
            CliExposure("basket-order", "cli/commands/order_composition.py"),
        ),
        rest=(RestExposure("POST", "/api/v1/orders", "api/routers/orders.py", "live_broker"),),
        cli_data_source="oms",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="orders.cancel",
        capability=Capability.ORDER_COMMAND,
        gateway_method="cancel_order",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.cancel_order", upstox="order_command.cancel_order"),
        cli=(CliExposure("cancel-order", "cli/commands/order_placement.py"),),
        rest=(
            RestExposure(
                "DELETE", "/api/v1/orders/{order_id}", "api/routers/orders.py", "live_broker"
            ),
        ),
        cli_data_source="oms",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="orders.modify",
        capability=Capability.ORDER_COMMAND,
        gateway_method="modify_order",
        abc_required=False,
        broker=BrokerMethodRef(dhan="orders.modify_order", upstox="order_command.modify_order"),
        cli=(CliExposure("modify-order", "cli/commands/order_placement.py"),),
        rest=(
            RestExposure(
                "PUT", "/api/v1/orders/{order_id}", "api/routers/orders.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="orders.query_orderbook",
        capability=Capability.ORDER_QUERY,
        gateway_method="get_orderbook",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.get_orderbook", upstox="order_query.get_order_list"),
        cli=(
            CliExposure("orders", "cli/commands/oms.py"),
            CliExposure("oms", "cli/commands/oms.py"),
        ),
        rest=(
            RestExposure("GET", "/api/v1/orders", "api/routers/orders.py", "oms"),
            RestExposure("GET", "/api/v1/orders/{order_id}", "api/routers/orders.py", "oms"),
            RestExposure("GET", "/api/v1/live/orders", "api/routers/live/orders.py", "live_broker"),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
        notes="REST OMS routes coexist with /live/orders broker orderbook",
    ),
    CapabilitySurface(
        id="orders.query_trades",
        capability=Capability.HISTORICAL_TRADES,
        gateway_method="get_trade_book",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.get_trade_book", upstox="order_query.get_trades"),
        cli=(CliExposure("trades", "cli/commands/oms.py"),),
        rest=(
            RestExposure("GET", "/api/v1/orders/trades", "api/routers/orders.py", "oms"),
            RestExposure("GET", "/api/v1/orders/tradebook", "api/routers/orders.py", "oms"),
            RestExposure("GET", "/api/v1/live/trades", "api/routers/live/orders.py", "live_broker"),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="portfolio.positions",
        capability=Capability.PORTFOLIO,
        gateway_method="positions",
        abc_required=True,
        broker=BrokerMethodRef(dhan="portfolio.get_positions", upstox="portfolio.get_positions"),
        cli=(CliExposure("positions", "cli/commands/portfolio.py"),),
        rest=(
            RestExposure("GET", "/api/v1/portfolio/positions", "api/routers/portfolio.py", "oms"),
            RestExposure(
                "GET", "/api/v1/live/positions", "api/routers/live/portfolio.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="portfolio.holdings",
        capability=Capability.PORTFOLIO,
        gateway_method="holdings",
        abc_required=True,
        broker=BrokerMethodRef(dhan="portfolio.get_holdings", upstox="portfolio.get_holdings"),
        cli=(CliExposure("holdings", "cli/commands/portfolio.py"),),
        rest=(
            RestExposure("GET", "/api/v1/portfolio/holdings", "api/routers/portfolio.py", "oms"),
            RestExposure(
                "GET", "/api/v1/live/holdings", "api/routers/live/portfolio.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="portfolio.funds",
        capability=Capability.PORTFOLIO,
        gateway_method="funds",
        abc_required=True,
        broker=BrokerMethodRef(dhan="portfolio.get_balance", upstox="portfolio.get_balance"),
        cli=(
            CliExposure("account", "cli/commands/account.py"),
            CliExposure("funds", "cli/commands/account.py"),
        ),
        rest=(
            RestExposure(
                "GET", "/api/v1/live/funds", "api/routers/live/portfolio.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="portfolio.trades_alias",
        capability=Capability.HISTORICAL_TRADES,
        gateway_method="trades",
        abc_required=True,
        broker=BrokerMethodRef(dhan="orders.get_trade_book", upstox="order_query.get_trades"),
        cli=(CliExposure("trades", "cli/commands/oms.py"),),
        rest=(),
        tier="core",
        severity_if_gap="P3",
        notes="Alias for get_trade_book on gateway ABC",
    ),
    CapabilitySurface(
        id="instruments.search",
        capability=Capability.INSTRUMENT_SEARCH,
        gateway_method="search",
        abc_required=True,
        broker=BrokerMethodRef(dhan="resolver", upstox="instrument_resolver.search"),
        cli=(
            CliExposure("search", "cli/commands/search.py"),
            CliExposure("instruments lookup", "cli/commands/instruments.py"),
        ),
        rest=(RestExposure("GET", "/api/v1/symbols/search", "api/routers/symbols.py", "datalake"),),
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="instruments.load",
        capability=Capability.INSTRUMENTS,
        gateway_method="load_instruments",
        abc_required=True,
        broker=BrokerMethodRef(dhan="load_instruments", upstox="instrument_loader.load"),
        cli=(CliExposure("instruments stats", "cli/commands/instruments.py"),),
        rest=(),
        tier="broker_only",
        broker_only_reason="Startup/bootstrap only",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="lifecycle.capabilities",
        capability=None,
        gateway_method="capabilities",
        abc_required=True,
        broker=BrokerMethodRef(dhan_gateway=True, upstox_gateway=True),
        cli=(CliExposure("doctor", "cli/commands/doctor/strategies/active_broker.py"),),
        rest=(),
        tier="broker_only",
        broker_only_reason="Metadata; doctor reports flags",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="lifecycle.describe",
        capability=None,
        gateway_method="describe",
        abc_required=True,
        broker=BrokerMethodRef(dhan_gateway=True, upstox_gateway=True),
        cli=(CliExposure("broker", "cli/commands/broker.py"),),
        rest=(),
        tier="broker_only",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="lifecycle.close",
        capability=None,
        gateway_method="close",
        abc_required=True,
        broker=BrokerMethodRef(dhan="close", upstox="disconnect"),
        cli=(),
        rest=(),
        tier="broker_only",
        broker_only_reason="Lifecycle teardown",
        severity_if_gap="P3",
    ),
    # ── Extended Dhan ─────────────────────────────────────────────────────
    CapabilitySurface(
        id="extended.user_profile",
        capability=None,
        gateway_method="extended.get_user_profile",
        extended_only=True,
        broker=BrokerMethodRef(dhan="user_profile.get_profile", upstox="portfolio.get_profile"),
        cli=(CliExposure("profile", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/live/profile", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="extended.super_orders",
        capability=None,
        gateway_method="extended.place_super_order",
        extended_only=True,
        broker=BrokerMethodRef(dhan="super_orders.place_super_order", upstox=None),
        cli=(CliExposure("super-order", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/orders/super", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.forever_orders",
        capability=None,
        gateway_method="extended.place_forever_order",
        extended_only=True,
        broker=BrokerMethodRef(
            dhan="forever_orders.place_forever_order", upstox="gtt.place_forever_order"
        ),
        cli=(CliExposure("forever-order", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/orders/forever", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.conditional_triggers",
        capability=Capability.ALERTS,
        gateway_method="extended.place_conditional_trigger",
        extended_only=True,
        broker=BrokerMethodRef(dhan="conditional_triggers.place_trigger", upstox="gtt.place_alert"),
        cli=(CliExposure("trigger", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/alerts/trigger", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.margin",
        capability=Capability.MARGIN,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan="margin.calculate", upstox="margin.calculate_margin"),
        cli=(CliExposure("margin", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST",
                "/api/v1/live/margin/calculate",
                "api/routers/live/extended.py",
                "live_broker",
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.exit_all",
        capability=Capability.EXIT_ALL,
        gateway_method="extended.exit_all",
        extended_only=True,
        broker=BrokerMethodRef(dhan="exit_all.exit_all", upstox="exit_all.exit_all"),
        cli=(CliExposure("exit-all", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST",
                "/api/v1/live/orders/exit-all",
                "api/routers/live/extended.py",
                "live_broker",
            ),
            RestExposure("POST", "/api/v1/portfolio/square-off", "api/routers/portfolio.py", "oms"),
        ),
        cli_data_source="live_broker",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.ledger",
        capability=None,
        gateway_method="extended.get_ledger",
        extended_only=True,
        broker=BrokerMethodRef(dhan="ledger.get_ledger", upstox="portfolio.get_ledger"),
        cli=(CliExposure("ledger", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/live/ledger", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="extended.edis",
        capability=None,
        gateway_method="extended.authorize_edis",
        extended_only=True,
        broker=BrokerMethodRef(dhan="edis.authorize_edis", upstox=None),
        cli=(CliExposure("edis", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/edis/authorize", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="extended.ip_management",
        capability=Capability.STATIC_IP,
        gateway_method="extended.set_ip",
        extended_only=True,
        broker=BrokerMethodRef(dhan="ip_management.set_ip", upstox="static_ip.set_static_ip"),
        cli=(CliExposure("ip", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure("GET", "/api/v1/live/ip", "api/routers/live/extended.py", "live_broker"),
            RestExposure("POST", "/api/v1/live/ip", "api/routers/live/extended.py", "live_broker"),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    # ── Extended Upstox ───────────────────────────────────────────────────
    CapabilitySurface(
        id="extended.gtt_order",
        capability=Capability.GTT_ORDER,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="gtt.place_gtt_order"),
        cli=(CliExposure("gtt-order", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/orders/gtt", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.cover_order",
        capability=Capability.COVER_ORDER,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="cover.place_cover_order"),
        cli=(CliExposure("cover-order", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/orders/cover", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.slice_order",
        capability=Capability.SLICE_ORDER,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan="orders.place_slice_order", upstox="slice.place_slice_order"),
        cli=(CliExposure("slice-order", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST", "/api/v1/live/orders/slice", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="extended.kill_switch_broker",
        capability=Capability.KILL_SWITCH,
        gateway_method=None,
        extended_only=True,
        broker=BrokerMethodRef(dhan="orders.kill_switch", upstox="kill_switch.set_status"),
        cli=(CliExposure("risk kill-switch", "cli/commands/risk_controls.py"),),
        rest=(RestExposure("POST", "/api/v1/risk/kill-switch", "api/routers/risk.py", "oms"),),
        cli_data_source="oms",
        severity_if_gap="P1",
        notes="CLI/REST use OMS kill-switch, not broker-native kill switch",
    ),
    CapabilitySurface(
        id="extended.ipo",
        capability=Capability.IPO,
        gateway_method="extended.get_ipos",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="ipo.get_ipos"),
        cli=(CliExposure("ipo", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure("GET", "/api/v1/live/ipo", "api/routers/live/extended.py", "live_broker"),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="extended.mutual_funds",
        capability=Capability.MUTUAL_FUNDS,
        gateway_method="extended.place_mutual_fund_order",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="mutual_funds.place_order"),
        cli=(CliExposure("mf", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/live/mutual-funds", "api/routers/live/extended.py", "live_broker"
            ),
            RestExposure(
                "POST", "/api/v1/live/mutual-funds", "api/routers/live/extended.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="extended.payments",
        capability=Capability.PAYMENTS,
        gateway_method="extended.initiate_payout",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="payments.initiate_payout"),
        cli=(CliExposure("payout", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "POST",
                "/api/v1/live/payments/payout",
                "api/routers/live/extended.py",
                "live_broker",
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="extended.fundamentals",
        capability=Capability.FUNDAMENTALS,
        gateway_method="extended.get_pnl",
        extended_only=True,
        broker=BrokerMethodRef(dhan=None, upstox="fundamentals.get_pnl"),
        cli=(CliExposure("fundamentals", "cli/commands/extended_orders.py"),),
        rest=(
            RestExposure(
                "GET",
                "/api/v1/live/fundamentals/{isin}",
                "api/routers/live/extended.py",
                "live_broker",
            ),
        ),
        cli_data_source="live_broker",
        tier="extended",
        broker_only_reason="Upstox fundamentals API",
        severity_if_gap="P3",
    ),
    # ── Capability enum broker-only entries ───────────────────────────────
    CapabilitySurface(
        id="capability.news",
        capability=Capability.NEWS,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="news.get_news"),
        cli=(CliExposure("news", "cli/commands/news.py"),),
        rest=(),
        tier="extended",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="capability.market_status",
        capability=Capability.MARKET_STATUS,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="market_status.get_market_status"),
        tier="broker_only",
        broker_only_reason="Upstox adapter only",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.order_stream",
        capability=Capability.ORDER_STREAM,
        gateway_method=None,
        broker=BrokerMethodRef(dhan="order_stream.connect", upstox=None),
        cli=(CliExposure("websocket", "cli/commands/websocket.py"),),
        rest=(),
        tier="extended",
        severity_if_gap="P2",
        notes="CLI reports connection status only",
    ),
    CapabilitySurface(
        id="capability.idempotency",
        capability=Capability.IDEMPOTENCY,
        gateway_method=None,
        broker=BrokerMethodRef(dhan="orders", upstox="idempotency_cache"),
        tier="broker_only",
        broker_only_reason="Internal OMS/broker cache",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.multi_order",
        capability=Capability.MULTI_ORDER,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="order_client.place_multi_order"),
        cli=(CliExposure("place-orders", "cli/commands/order_placement.py"),),
        rest=(),
        tier="extended",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="capability.session_risk",
        capability=Capability.SESSION_RISK,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="risk_manager"),
        cli=(
            CliExposure("risk status", "cli/commands/risk_controls.py"),
            CliExposure("oms", "cli/commands/oms.py"),
        ),
        rest=(RestExposure("GET", "/api/v1/risk/state", "api/routers/risk.py", "oms"),),
        cli_data_source="oms",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="capability.smartlist",
        capability=Capability.SMARTLIST,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_smartlist"),
        tier="broker_only",
        broker_only_reason="Upstox intelligence adapter",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.fii_dii",
        capability=Capability.FII_DII,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_fii_flow"),
        tier="broker_only",
        broker_only_reason="Upstox intelligence adapter",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.oi_pcr_maxpain",
        capability=Capability.OI_PCR_MAXPAIN,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_pcr"),
        cli=(),
        rest=(
            RestExposure(
                "GET", "/api/v1/options/pcr/{underlying}", "api/routers/options.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/options/max-pain/{underlying}", "api/routers/options.py", "datalake"
            ),
            RestExposure(
                "GET",
                "/api/v1/options/volume-profile/{underlying}",
                "api/routers/options.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="capability.market_intelligence",
        capability=Capability.MARKET_INTELLIGENCE,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="intelligence.get_snapshot"),
        tier="broker_only",
        broker_only_reason="Upstox intelligence bundle",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.tsl",
        capability=Capability.TSL,
        gateway_method=None,
        tier="broker_only",
        broker_only_reason="Not implemented at broker layer",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.mtf",
        capability=Capability.MTF,
        gateway_method=None,
        tier="broker_only",
        broker_only_reason="Product type only; no dedicated surface",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.webhooks",
        capability=Capability.WEBHOOKS,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="feed_authorizer"),
        tier="broker_only",
        broker_only_reason="Upstox feed authorizer internal",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.amo_order",
        capability=Capability.AMO_ORDER,
        gateway_method="place_order",
        broker=BrokerMethodRef(dhan="orders.place_order", upstox="order_command.place_order"),
        tier="broker_only",
        broker_only_reason="AMO flag on standard place_order",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.portfolio_stream",
        capability=Capability.PORTFOLIO_STREAM,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="portfolio_stream"),
        tier="broker_only",
        severity_if_gap="P3",
        notes="UpstoxPortfolioStream wired on broker init and lifecycle",
    ),
    CapabilitySurface(
        id="capability.order_slicing",
        capability=Capability.ORDER_SLICING,
        gateway_method=None,
        broker=BrokerMethodRef(dhan="orders.place_slice_order", upstox="slice.place_slice_order"),
        tier="broker_only",
        broker_only_reason="Same as slice_order",
        severity_if_gap="P1",
    ),
    CapabilitySurface(
        id="capability.depth_30",
        capability=Capability.DEPTH_30,
        gateway_method="depth",
        broker=BrokerMethodRef(dhan="market_data.get_depth", upstox="market_data.get_depth"),
        cli=(CliExposure("depth", "cli/commands/market_handlers.py"),),
        tier="broker_only",
        broker_only_reason="Uses generic depth endpoint",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.level2_market_data",
        capability=Capability.LEVEL2_MARKET_DATA,
        gateway_method="depth_20",
        broker=BrokerMethodRef(dhan="depth_20_feed.subscribe", upstox=None),
        tier="extended",
        broker_only_reason="Dhan depth_20/200 feeds — no CLI command",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="capability.option_greeks",
        capability=Capability.OPTION_GREEKS,
        gateway_method=None,
        broker=BrokerMethodRef(dhan=None, upstox="market_data_v3.get_option_greeks_v3"),
        cli=(CliExposure("option-chain", "cli/commands/market.py"),),
        rest=(
            RestExposure(
                "GET",
                "/api/v1/options/iv-surface/{underlying}",
                "api/routers/options.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="capability.global_markets",
        capability=Capability.GLOBAL_MARKETS,
        gateway_method=None,
        tier="broker_only",
        broker_only_reason="Not implemented",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="capability.volatility_index",
        capability=Capability.VOLATILITY_INDEX,
        gateway_method=None,
        tier="broker_only",
        broker_only_reason="Not implemented",
        severity_if_gap="P3",
    ),
    # ── Monitoring / health (no broker capability) ────────────────────────
    CapabilitySurface(
        id="monitoring.api_health",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("doctor", "cli/commands/doctor/__init__.py"),),
        rest=(
            RestExposure("GET", "/api/v1/health", "api/routers/health.py", "none"),
            RestExposure("GET", "/api/v1/health/readyz", "api/routers/health.py", "none"),
            RestExposure("GET", "/api/v1/health/metrics", "api/routers/health.py", "oms"),
            RestExposure(
                "GET", "/api/v1/health/metrics/prometheus", "api/routers/health.py", "none"
            ),
        ),
        tier="core",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="monitoring.live_broker_health",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("doctor", "cli/commands/doctor/__init__.py"),),
        rest=(
            RestExposure("GET", "/api/v1/live/health", "api/routers/live/health.py", "live_broker"),
            RestExposure("GET", "/api/v1/live/readyz", "api/routers/live/health.py", "live_broker"),
            RestExposure(
                "GET", "/api/v1/live/capabilities", "api/routers/live/health.py", "live_broker"
            ),
        ),
        cli_data_source="live_broker",
        tier="core",
        severity_if_gap="P2",
    ),
    # ── API-only surfaces (no Capability enum) ────────────────────────────
    CapabilitySurface(
        id="api.scanner",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("analytics scan", "cli/commands/analytics_scanner.py"),),
        rest=(
            RestExposure("GET", "/api/v1/scanner/results", "api/routers/scanner.py", "datalake"),
            RestExposure(
                "GET", "/api/v1/scanner/top-candidates", "api/routers/scanner.py", "datalake"
            ),
            RestExposure("GET", "/api/v1/scanner/snapshots", "api/routers/scanner.py", "datalake"),
            RestExposure("POST", "/api/v1/scanner/run", "api/routers/scanner.py", "mixed"),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="api.backtest",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("analytics backtest", "cli/commands/analytics_backtest.py"),),
        rest=(
            RestExposure("POST", "/api/v1/backtest/run", "api/routers/backtest.py", "datalake"),
            RestExposure(
                "GET",
                "/api/v1/backtest/results/{backtest_id}",
                "api/routers/backtest.py",
                "datalake",
            ),
            RestExposure(
                "GET", "/api/v1/backtest/comparison/{run_id}", "api/routers/backtest.py", "datalake"
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="api.replay",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("analytics replay", "cli/commands/analytics_replay.py"),),
        rest=(
            RestExposure("GET", "/api/v1/replay/sessions", "api/routers/replay.py", "datalake"),
            RestExposure("POST", "/api/v1/replay/sessions", "api/routers/replay.py", "datalake"),
            RestExposure(
                "GET", "/api/v1/replay/sessions/{session_id}", "api/routers/replay.py", "datalake"
            ),
            RestExposure(
                "POST",
                "/api/v1/replay/sessions/{session_id}/play",
                "api/routers/replay.py",
                "datalake",
            ),
            RestExposure(
                "POST",
                "/api/v1/replay/sessions/{session_id}/pause",
                "api/routers/replay.py",
                "datalake",
            ),
            RestExposure(
                "POST",
                "/api/v1/replay/sessions/{session_id}/stop",
                "api/routers/replay.py",
                "datalake",
            ),
            RestExposure(
                "POST",
                "/api/v1/replay/sessions/{session_id}/speed",
                "api/routers/replay.py",
                "datalake",
            ),
            RestExposure(
                "POST",
                "/api/v1/replay/sessions/{session_id}/seek",
                "api/routers/replay.py",
                "datalake",
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="api.analytics",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("analytics breadth", "cli/commands/analytics.py"),),
        rest=(
            RestExposure(
                "GET", "/api/v1/analytics/market-breadth", "api/routers/analytics.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/analytics/indicators", "api/routers/analytics.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/scanner/snapshots", "api/routers/scanner.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/scanner/top-candidates", "api/routers/scanner.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/analytics/relative-strength", "api/routers/analytics.py", "datalake"
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
    CapabilitySurface(
        id="api.portfolio_summary",
        capability=Capability.PORTFOLIO,
        gateway_method=None,
        cli=(CliExposure("oms", "cli/commands/oms.py"),),
        rest=(
            RestExposure("GET", "/api/v1/portfolio/summary", "api/routers/portfolio.py", "oms"),
            RestExposure("GET", "/api/v1/portfolio/pnl", "api/routers/portfolio.py", "oms"),
        ),
        cli_data_source="live_broker",
        tier="extended",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="api.symbols",
        capability=Capability.INSTRUMENTS,
        gateway_method=None,
        cli=(CliExposure("instrument", "cli/commands/instrument_info.py"),),
        rest=(
            RestExposure("GET", "/api/v1/symbols/{symbol}", "api/routers/symbols.py", "datalake"),
            RestExposure(
                "GET", "/api/v1/symbols/universe/{name}", "api/routers/symbols.py", "datalake"
            ),
        ),
        tier="core",
        severity_if_gap="P2",
    ),
    CapabilitySurface(
        id="api.strategy",
        capability=None,
        gateway_method=None,
        cli=(CliExposure("analytics strategies", "cli/commands/analytics_strategies.py"),),
        rest=(
            RestExposure("GET", "/api/v1/strategy/signals", "api/routers/strategy.py", "datalake"),
            RestExposure(
                "GET", "/api/v1/strategy/candidates", "api/routers/strategy.py", "datalake"
            ),
            RestExposure(
                "GET", "/api/v1/analytics/strategies", "api/routers/analytics.py", "datalake"
            ),
            RestExposure(
                "POST", "/api/v1/analytics/strategies/run", "api/routers/analytics.py", "datalake"
            ),
        ),
        tier="extended",
        severity_if_gap="P3",
    ),
)


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


def abc_gateway_methods() -> frozenset[str]:
    """Abstract methods required by MarketDataGateway ABC."""
    return frozenset(
        {
            "history",
            "quote",
            "ltp",
            "depth",
            "option_chain",
            "future_chain",
            "stream",
            "ltp_batch",
            "quote_batch",
            "history_batch",
            "place_order",
            "cancel_order",
            "get_orderbook",
            "get_trade_book",
            "positions",
            "holdings",
            "funds",
            "trades",
            "search",
            "load_instruments",
            "capabilities",
            "describe",
            "close",
        }
    )


def all_capability_enum_values() -> frozenset[Capability]:
    """All domain Capability enum members."""
    return frozenset(Capability)


def mapped_capability_values() -> frozenset[Capability]:
    """Capability enum values referenced by at least one surface."""
    return frozenset(s.capability for s in CAPABILITY_SURFACES if s.capability is not None)


def broker_only_capabilities() -> frozenset[Capability]:
    """Capabilities explicitly marked broker_only on their primary surface."""
    result: set[Capability] = set()
    for s in CAPABILITY_SURFACES:
        if s.capability is not None and s.tier == "broker_only":
            result.add(s.capability)
    return frozenset(result)


def classify_exposure(surface: CapabilitySurface) -> ExposureStatus:
    """Classify whether a surface is fully exposed across layers."""
    if surface.tier == "broker_only" or surface.broker_only_reason:
        return "broker_only"
    has_cli = bool(surface.cli)
    has_rest = bool(surface.rest)
    if has_cli and has_rest:
        cli_src = surface.cli_data_source
        rest_sources = {r.data_source for r in surface.rest}
        if cli_src == "live_broker" and rest_sources <= {"datalake", "oms"}:
            return "mismatch"
        return "exposed"
    if has_cli or has_rest:
        return "partial"
    if surface.broker.dhan or surface.broker.upstox:
        return "gap"
    return "broker_only"


__all__ = [
    "CAPABILITY_SURFACES",
    "BrokerMethodRef",
    "CapabilitySurface",
    "CliExposure",
    "DataSource",
    "ExposureStatus",
    "RestExposure",
    "Severity",
    "Tier",
    "abc_gateway_methods",
    "all_capability_enum_values",
    "all_surfaces",
    "broker_only_capabilities",
    "classify_exposure",
    "mapped_capability_values",
    "surface_by_id",
    "surfaces_for_capability",
]
