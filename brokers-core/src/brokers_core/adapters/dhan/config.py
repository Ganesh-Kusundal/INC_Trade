"""Dhan adapter configuration — endpoints and rate limits."""

from __future__ import annotations

from brokers_core.config.endpoints import Dhan
from brokers_core.domain.constants.segments import SEGMENT_TO_EXCHANGE, SegmentResolver

ENDPOINTS = Dhan.ENDPOINTS
REST_BASE = Dhan.REST_BASE

EQUITY_ONLY_PRODUCTS: frozenset[str] = frozenset({"DELIVERY", "CNC"})

RATE_LIMITS = {
    "/marketfeed/quote": 1.0,  # 1 req/s
    "/marketfeed/ltp": 6.67,  # ~6.7 req/s (documented 10 req/s)
    "/marketfeed/ohlc": 6.67,  # ~6.7 req/s (documented 10 req/s)
    "/optionchain": 2.85,  # ~2.9 req/s (documented 3 req/s)
    "/charts/": 6.67,  # ~6.7 req/s (documented 10 req/s)
    "/orders": 25.0,  # 25 req/s
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

# Dhan-specific overrides for the canonical segment-to-exchange map
# (keys not covered by the canonical map):
_DHAN_SEGMENT_OVERRIDES = {
    "NSE_CD": "CUR",
    "IDX_I": "INDEX",
}

DHAN_SEGMENT_RESOLVER = SegmentResolver(
    segment_to_exchange_overrides=_DHAN_SEGMENT_OVERRIDES,
    exchange_to_segment=EXCHANGE_MAP,
)

SEGMENT_TO_EXCHANGE = DHAN_SEGMENT_RESOLVER.segment_to_exchange

# Dhan's master CSV (api-scrip-master.csv) uses plain exchange codes in SEM_EXM_EXCH_ID:
# "NSE", "BSE", "MCX" — NOT the segment codes above.
# This map translates CSV exchange codes → API wire segment codes for the resolver.
CSV_EXCHANGE_TO_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",  # equity; FNO rows are still under "NSE" but instrument type distinguishes them
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

DERIVATIVE_SEGMENTS: frozenset[str] = frozenset({"NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CD"})

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

__all__ = [
    "CSV_EXCHANGE_TO_SEGMENT",
    "DERIVATIVE_SEGMENTS",
    "DHAN_SEGMENT_RESOLVER",
    "DHAN_SEGMENTS",
    "ENDPOINTS",
    "EQUITY_ONLY_PRODUCTS",
    "EXCHANGE_MAP",
    "INSTRUMENT_TO_SEGMENT",
    "INSTRUMENT_TYPE_MAP",
    "ORDER_TYPE_MAP",
    "PRODUCT_TYPE_MAP",
    "RATE_LIMITS",
    "READ_PREFIXES",
    "REST_BASE",
    "SEGMENT_TO_EXCHANGE",
    "SIDE_MAP",
    "VALIDITY_MAP",
    "WRITE_PREFIXES",
]
