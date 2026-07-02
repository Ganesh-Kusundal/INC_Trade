"""Broker capability and connection lifecycle enums.

Submodule of :mod:`domain.types` — imported via the re-export facade.
"""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """Capabilities a broker connection can provide."""

    MARKET_DATA = "market_data"
    ORDER_COMMAND = "order_command"
    ORDER_QUERY = "order_query"
    PORTFOLIO = "portfolio"
    OPTIONS_CHAIN = "options_chain"
    INSTRUMENTS = "instruments"
    FUTURES = "futures"
    HISTORICAL_DATA = "historical_data"
    WEBSOCKET = "websocket"
    # BRACKET_ORDER removed — not supported in Upstox v3 API (as of 2024)
    COVER_ORDER = "cover_order"
    GTT_ORDER = "gtt_order"
    SLICE_ORDER = "slice_order"
    MARGIN = "margin"
    NEWS = "news"
    SESSION_RISK = "session_risk"
    ALERTS = "alerts"
    MARKET_STATUS = "market_status"
    DEPTH = "depth"
    ORDER_STREAM = "order_stream"
    IDEMPOTENCY = "idempotency"
    MULTI_ORDER = "multi_order"
    KILL_SWITCH = "kill_switch"
    STATIC_IP = "static_ip"
    SMARTLIST = "smartlist"
    FII_DII = "fii_dii"
    OI_PCR_MAXPAIN = "oi_pcr_maxpain"
    MARKET_INTELLIGENCE = "market_intelligence"
    FUNDAMENTALS = "fundamentals"
    IPO = "ipo"
    MUTUAL_FUNDS = "mutual_funds"
    PAYMENTS = "payments"
    INSTRUMENT_SEARCH = "instrument_search"
    HISTORICAL_TRADES = "historical_trades"
    TSL = "trailing_stop_loss"
    MTF = "mtf"
    WEBHOOKS = "webhooks"
    AMO_ORDER = "amo_order"
    EXIT_ALL = "exit_all"
    PORTFOLIO_STREAM = "portfolio_stream"
    ORDER_SLICING = "order_slicing"
    DEPTH_30 = "depth_30"
    LEVEL2_MARKET_DATA = "level2_market_data"
    OPTION_GREEKS = "option_greeks"
    GLOBAL_MARKETS = "global_markets"
    VOLATILITY_INDEX = "volatility_index"


class ConnectionStatus(str, Enum):
    """Lifecycle status of a broker connection."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"

    def is_connected(self) -> bool:
        return self == ConnectionStatus.CONNECTED
