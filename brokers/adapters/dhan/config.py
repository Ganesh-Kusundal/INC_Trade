"""Dhan adapter configuration — endpoints and rate limits."""

from __future__ import annotations


REST_BASE = "https://api.dhan.co/v2"

ENDPOINTS = {
    "generate_token": "https://auth.dhan.co/app/generateAccessToken",
    "orders": f"{REST_BASE}/orders",
    "order_by_id": f"{REST_BASE}/orders/{{order_id}}",
    "modify_order": f"{REST_BASE}/orders",
    "cancel_order": f"{REST_BASE}/orders/{{order_id}}",
    "orderbook": f"{REST_BASE}/orders",
    "tradebook": f"{REST_BASE}/tradebook",
    "positions": f"{REST_BASE}/positions",
    "holdings": f"{REST_BASE}/holdings",
    "fund_limit": f"{REST_BASE}/fundlimit",
    "quote": f"{REST_BASE}/marketfeed/quote",
    "ltp": f"{REST_BASE}/marketfeed/ltp",
    "ohlc": f"{REST_BASE}/marketfeed/ohlc",
    "option_chain": f"{REST_BASE}/optionchain",
    "historical": f"{REST_BASE}/charts/historical",
    "instruments": "https://images.dhan.co/api-data/api-scrip-master.csv",
    "slice_order": f"{REST_BASE}/orders/slice",
}

RATE_LIMITS = {
    "/marketfeed/quote": 1.0,
    "/marketfeed/ltp": 10.0,
    "/marketfeed/ohlc": 10.0,
    "/optionchain": 3.0,
    "/charts/": 10.0,
    "/orders": 25.0,
}

READ_PREFIXES = (
    "/marketfeed/ltp",
    "/marketfeed/quote",
    "/marketfeed/ohlc",
    "/charts/",
    "/optionchain",
)

WRITE_PREFIXES = (
    "/orders",
    "/killswitch",
    "/sliceorder",
)

EXCHANGE_MAP = {
    "NSE": "NSE_EQ",
    "NFO": "NSE_FNO",
    "BSE": "BSE_EQ",
    "BFO": "BSE_FNO",
    "MCX": "MCX_COMM",
    "CUR": "NSE_CD",
    "INDEX": "IDX_I",
}

SEGMENT_TO_EXCHANGE: dict[str, str] = {v: k for k, v in EXCHANGE_MAP.items()}

DHAN_SEGMENTS: frozenset[str] = frozenset(
    {"NSE_EQ", "BSE_EQ", "NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CD", "IDX_I"}
)

DERIVATIVE_SEGMENTS: frozenset[str] = frozenset(
    {"NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CD"}
)

INSTRUMENT_TYPE_MAP: dict[str, str] = {
    "EQUITY": "EQUITY",
    "INDEX": "EQUITY",
    "OPTIDX": "OPTIDX",
    "OPTSTK": "OPTSTK",
    "FUTIDX": "FUTIDX",
    "FUTSTK": "FUTSTK",
    "FUTCOM": "FUTCOM",
    "OPTCUR": "OPTCUR",
    "OPTFUT": "OPTFUT",
    "OPTCOM": "OPTCOM",
    "FUTCUR": "FUTCUR",
}

SIDE_MAP = {"BUY": 1, "SELL": 2}
ORDER_TYPE_MAP = {"MARKET": 1, "LIMIT": 2, "STOP_LOSS": 3, "STOP_LOSS_MARKET": 4}
PRODUCT_TYPE_MAP = {"INTRADAY": "INTRADAY", "DELIVERY": "MARGIN", "MARGIN": "MARGIN"}
VALIDITY_MAP = {"DAY": "DAY", "IOC": "IOC", "GTT": "GTT"}
