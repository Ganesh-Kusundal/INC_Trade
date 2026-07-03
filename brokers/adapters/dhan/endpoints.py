"""Canonical Dhan REST endpoint paths — single source for adapter HTTP calls."""

from __future__ import annotations

from brokers.config.endpoints import Dhan

REST_BASE = Dhan.REST_BASE

ENDPOINTS: dict[str, str] = {
    "generate_token": Dhan.GENERATE_TOKEN_URL,
    "orders": f"{REST_BASE}{Dhan.ORDERS}",
    "order_by_id": f"{REST_BASE}{Dhan.ORDERS}/{{order_id}}",
    "modify_order": f"{REST_BASE}{Dhan.ORDERS}",
    "cancel_order": f"{REST_BASE}{Dhan.ORDERS}/{{order_id}}",
    "orderbook": f"{REST_BASE}{Dhan.ORDERS}",
    "tradebook": f"{REST_BASE}/tradebook",
    "trade_history": f"{REST_BASE}/trades/{{from_date}}/{{to_date}}/{{page}}",
    "positions": f"{REST_BASE}/positions",
    "holdings": f"{REST_BASE}/holdings",
    "fund_limit": f"{REST_BASE}/fundlimit",
    "quote": f"{REST_BASE}{Dhan.MARKETFEED_QUOTE}",
    "ltp": f"{REST_BASE}{Dhan.MARKETFEED_LTP}",
    "ohlc": f"{REST_BASE}{Dhan.MARKETFEED_OHLC}",
    "option_chain": f"{REST_BASE}{Dhan.OPTION_CHAIN}",
    "historical": f"{REST_BASE}{Dhan.CHARTS_HISTORICAL}",
    "instruments": Dhan.INSTRUMENT_CSV,
    "slice_order": f"{REST_BASE}/orders/slice",
    "kill_switch": f"{REST_BASE}{Dhan.KILL_SWITCH}",
}
