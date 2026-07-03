"""Upstox adapter configuration — rate limits and mapping tables.

REST URLs live in ``brokers.config.endpoints.Upstox`` — use ``urls.resolve_upstox_urls``.
"""

from __future__ import annotations

from brokers.domain.constants.segments import SEGMENT_TO_EXCHANGE

RATE_LIMITS = {
    "/market-quote": 10.0,
    "/orders": 25.0,
    "/portfolio": 5.0,
    "/user": 5.0,
}

READ_PREFIXES = (
    "/market-quote",
    "/portfolio",
    "/user",
    "/contracts",
)

WRITE_PREFIXES = ("/orders",)

EXCHANGE_TO_SEGMENT = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FO",
    "BFO": "BSE_FO",
    "MCX": "MCX_FO",
    "CDS": "NCD_FO",
    "BCD": "BCD_FO",
    "INDEX": "NSE_INDEX",
}

# Upstox-specific overrides for the canonical segment-to-exchange map
# (keys differ from Dhan's segment codes):
SEGMENT_TO_EXCHANGE = SEGMENT_TO_EXCHANGE.copy()
SEGMENT_TO_EXCHANGE.update(
    {
        "NSE_FO": "NFO",
        "BSE_FO": "BFO",
        "MCX_FO": "MCX",
        "NCD_FO": "CDS",
        "BCD_FO": "BCD",
        "NSE_INDEX": "INDEX",
        "NSE_COM": "MCX",
        "MCX_COMM": "MCX",
    }
)

SIDE_MAP = {"BUY": "BUY", "SELL": "SELL"}

ORDER_TYPE_MAP = {
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "STOP_LOSS": "SL",
    "STOP_LOSS_MARKET": "SL-M",
}

PRODUCT_TYPE_MAP = {
    "INTRADAY": "I",
    "DELIVERY": "D",
    "MARGIN": "D",
}

VALIDITY_MAP = {
    "DAY": "DAY",
    "IOC": "IOC",
}

INSTRUMENT_CSV_COLUMNS = {
    "symbol": "tradingsymbol",
    "name": "company",
    "exchange": "exchange",
    "segment": "segment",
    "instrument_type": "instrument",
    "lot_size": "lot_size",
    "tick_size": "tick_size",
}

_INTERVAL_MAP = {
    "1m": "minute",
    "1M": "minute",
    "1": "minute",
    "5m": "5minute",
    "5M": "5minute",
    "5": "5minute",
    "15m": "15minute",
    "15M": "15minute",
    "15": "15minute",
    "30m": "30minute",
    "30M": "30minute",
    "30": "30minute",
    "60m": "60minute",
    "60M": "60minute",
    "60": "60minute",
    "1D": "day",
    "D": "day",
    "DAY": "day",
    "1W": "week",
    "W": "week",
}

ORDER_TYPE_MAP_REVERSE = {
    "MARKET": "MARKET",
    "MKT": "MARKET",
    "LIMIT": "LIMIT",
    "LMT": "LIMIT",
    "SL": "STOP_LOSS",
    "STOP_LOSS": "STOP_LOSS",
    "SL-M": "STOP_LOSS_MARKET",
    "SLM": "STOP_LOSS_MARKET",
}
PRODUCT_MAP_REVERSE = {
    "I": "INTRADAY",
    "D": "DELIVERY",
    "MTF": "DELIVERY",
}
SIDE_MAP_REVERSE = {
    "BUY": "BUY",
    "SELL": "SELL",
}
VALIDITY_MAP_REVERSE = {
    "DAY": "DAY",
    "IOC": "IOC",
}
STATUS_MAP = {
    "OPEN": "OPEN",
    "COMPLETE": "FILLED",
    "CANCELED": "CANCELLED",
    "CANCELLED": "CANCELLED",
    "REJECTED": "REJECTED",
    "MODIFY_PENDING": "PENDING",
    "OPEN_PENDING": "PENDING",
    "TRIGGER_PENDING": "PENDING",
}
