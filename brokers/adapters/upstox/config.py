"""Upstox adapter configuration — endpoints, rate limits, and mapping tables."""

from __future__ import annotations

V2_BASE = "https://api.upstox.com/v2"
HFT_BASE = "https://api-hft.upstox.com/v3"

ENDPOINTS = {
    "place_order": f"{HFT_BASE}/orders/interactive",
    "modify_order": f"{HFT_BASE}/orders/interactive",
    "cancel_order": f"{HFT_BASE}/orders/interactive/{{order_id}}",
    "order_book": f"{HFT_BASE}/orders",
    "order_details": f"{HFT_BASE}/orders/{{order_id}}",
    "trades": f"{HFT_BASE}/trades",
    "ltp": f"{V2_BASE}/market/quote/ltp",
    "quote": f"{V2_BASE}/market/quote",
    "ohlc": f"{V2_BASE}/market/quote/ohlc",
    "depth": f"{V2_BASE}/market/quote",
    "positions": f"{V2_BASE}/portfolio/short-term-positions",
    "holdings": f"{V2_BASE}/portfolio/long-term-holdings",
    "funds": f"{V2_BASE}/user/get-funds-and-margin",
    "instruments": f"{V2_BASE}/contracts/MASTER",
    "profile": f"{V2_BASE}/user/profile",
}

CONTRACT_URLS = {
    "NSE": f"{V2_BASE}/contracts/MASTER/NSE",
    "BSE": f"{V2_BASE}/contracts/MASTER/BSE",
    "NSE_FO": f"{V2_BASE}/contracts/MASTER/NSE_FO",
    "BSE_FO": f"{V2_BASE}/contracts/MASTER/BSE_FO",
    "MCX_FO": f"{V2_BASE}/contracts/MASTER/MCX_FO",
    "NCD_FO": f"{V2_BASE}/contracts/MASTER/NCD_FO",
}

RATE_LIMITS = {
    "/market/quote": 10.0,
    "/orders": 25.0,
    "/portfolio": 5.0,
    "/user": 5.0,
}

READ_PREFIXES = (
    "/market/quote",
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

SEGMENT_TO_EXCHANGE = {v: k for k, v in EXCHANGE_TO_SEGMENT.items()}
SEGMENT_TO_EXCHANGE.update(
    {
        "MCX_COMM": "MCX",
        "NSE_COM": "MCX",
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
