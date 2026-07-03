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
    "/marketfeed/quote": 1.0,  # 1 req/s
    "/marketfeed/ltp": 0.15,  # ~6.7 req/s (documented 10 req/s)
    "/marketfeed/ohlc": 0.15,  # ~6.7 req/s (documented 10 req/s)
    "/optionchain": 0.35,  # ~2.9 req/s (documented 3 req/s)
    "/charts/": 0.15,  # ~6.7 req/s (documented 10 req/s)
    "/orders": 0.04,  # 25 req/s
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

# Maps user-facing exchange names → Dhan API wire segment codes (used in order/chart payloads).
# These segment codes are what Dhan's REST API expects in fields like "exchangeSegment".
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

# Dhan's master CSV (api-scrip-master.csv) uses plain exchange codes in SEM_EXM_EXCH_ID:
# "NSE", "BSE", "MCX" — NOT the segment codes above.
# This map translates CSV exchange codes → API wire segment codes for the resolver.
CSV_EXCHANGE_TO_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",   # equity; FNO rows are still under "NSE" but instrument type distinguishes them
    "BSE": "BSE_EQ",
    "MCX": "MCX_COMM",
    "CDS": "NSE_CD",
    "NDX": "IDX_I",
}

# For FNO/derivatives in the CSV, the exchange is still "NSE" or "BSE" but the instrument
# name tells us it's a derivative. We use this to override the segment assignment.
INSTRUMENT_TO_SEGMENT: dict[str, str] = {
    "OPTIDX": "NSE_FNO",
    "OPTSTK": "NSE_FNO",
    "FUTIDX": "NSE_FNO",
    "FUTSTK": "NSE_FNO",
    "FUTCOM": "MCX_COMM",
    "OPTFUT": "MCX_COMM",
    "OPTCOM": "MCX_COMM",
    "FUTCUR": "NSE_CD",
    "OPTCUR": "NSE_CD",
}

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
