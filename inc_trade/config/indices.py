"""Broker-agnostic index symbol mapping — single source of truth for all indices.

Upstox indices have segment ``"NSE_INDEX"`` (orBoth Dhan and Upstox resolve indices differently from equities:

* **Dhan**: Indices use exchange ``"INDEX"`` and segment ``"IDX_I"``.
* **Upstox**: Indices have segment ``"NSE_INDEX"`` (or ``"BSE_INDEX"``)
  instead of ``"NSE_EQ"``.

Usage::

    from inc_trade.config.indices import is_index, dhan_index_exchange, upstox_index_segment

    if is_index(symbol):
        exchange = dhan_index_exchange(symbol)
"""

from __future__ import annotations

from dataclasses import dataclass


def _normalize(symbol: str) -> str:
    return symbol.upper().strip()


@dataclass(frozen=True)
class IndexEntry:
    """Broker-agnostic index metadata."""

    canonical_name: str
    upstox_segment: str = ""
    upstox_name: str = ""


_INDEX_MAP: dict[str, IndexEntry] = {
    "NIFTY": IndexEntry(
        canonical_name="NIFTY 50",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 50",
    ),
    "NIFTY50": IndexEntry(
        canonical_name="NIFTY 50",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 50",
    ),
    "BANKNIFTY": IndexEntry(
        canonical_name="NIFTY BANK",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Bank",
    ),
    "NIFTYBANK": IndexEntry(
        canonical_name="NIFTY BANK",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Bank",
    ),
    "FINNIFTY": IndexEntry(
        canonical_name="NIFTY FINANCIAL SERVICES",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Fin Service",
    ),
    "NIFTYFIN": IndexEntry(
        canonical_name="NIFTY FINANCIAL SERVICES",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Fin Service",
    ),
    "MIDCAPNIFTY": IndexEntry(
        canonical_name="NIFTY MIDCAP 100",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Midcap 100",
    ),
    "NIFTYMIDCAP": IndexEntry(
        canonical_name="NIFTY MIDCAP 100",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Midcap 100",
    ),
    "NIFTYIT": IndexEntry(
        canonical_name="NIFTY IT",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty IT",
    ),
    "NIFTYPHARMA": IndexEntry(
        canonical_name="NIFTY PHARMA",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Pharma",
    ),
    "NIFTYAUTO": IndexEntry(
        canonical_name="NIFTY AUTO",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Auto",
    ),
    "NIFTYFMCG": IndexEntry(
        canonical_name="NIFTY FMCG",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty FMCG",
    ),
    "NIFTYMETAL": IndexEntry(
        canonical_name="NIFTY METAL",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Metal",
    ),
    "NIFTYREALTY": IndexEntry(
        canonical_name="NIFTY REALTY",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Realty",
    ),
    "NIFTYENERGY": IndexEntry(
        canonical_name="NIFTY ENERGY",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Energy",
    ),
    "NIFTYMEDIA": IndexEntry(
        canonical_name="NIFTY MEDIA",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Media",
    ),
    "NIFTYPSB": IndexEntry(
        canonical_name="NIFTY PSU BANK",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty PSU Bank",
    ),
    "NIFTYPVTBANK": IndexEntry(
        canonical_name="NIFTY PRIVATE BANK",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Pvt Bank",
    ),
    "NIFTYCONS": IndexEntry(
        canonical_name="NIFTY CONSUMER DURABLES",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Consumer Durables",
    ),
    "NIFTYOILGAS": IndexEntry(
        canonical_name="NIFTY OIL AND GAS",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Oil and Gas",
    ),
    "NIFTYCOMM": IndexEntry(
        canonical_name="NIFTY COMMODITIES",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Commodities",
    ),
    "NIFTYIND": IndexEntry(
        canonical_name="NIFTY INDUSTRIALS",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Industrials",
    ),
    "NIFTYMNC": IndexEntry(
        canonical_name="NIFTY MNC",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty MNC",
    ),
    "NIFTYSMALL": IndexEntry(
        canonical_name="NIFTY SMALLCAP 250",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Smallcap 250",
    ),
    "NIFTYMICRO": IndexEntry(
        canonical_name="NIFTY MICROCAP 250",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Microcap 250",
    ),
    "NIFTYNEXT50": IndexEntry(
        canonical_name="NIFTY NEXT 50",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Next 50",
    ),
    "NIFTY100": IndexEntry(
        canonical_name="NIFTY 100",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 100",
    ),
    "NIFTY200": IndexEntry(
        canonical_name="NIFTY 200",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 200",
    ),
    "NIFTY500": IndexEntry(
        canonical_name="NIFTY 500",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 500",
    ),
    "VXNIFTY": IndexEntry(
        canonical_name="NIFTY VOLATILITY",
        upstox_segment="NSE_INDEX",
        upstox_name="India VIX",
    ),
    "INDIAVIX": IndexEntry(
        canonical_name="INDIA VIX",
        upstox_segment="NSE_INDEX",
        upstox_name="India VIX",
    ),
    "SENSEX": IndexEntry(
        canonical_name="SENSEX",
        upstox_segment="BSE_INDEX",
        upstox_name="SENSEX",
    ),
    "BSESENSEX": IndexEntry(
        canonical_name="SENSEX",
        upstox_segment="BSE_INDEX",
        upstox_name="SENSEX",
    ),
    "BSE100": IndexEntry(
        canonical_name="BSE 100",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 100",
    ),
    "BSE200": IndexEntry(
        canonical_name="BSE 200",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 200",
    ),
    "BSE500": IndexEntry(
        canonical_name="BSE 500",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 500",
    ),
    "BSEMIDCAP": IndexEntry(
        canonical_name="BSE MIDCAP",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE Midcap",
    ),
    "BSESMALLCAP": IndexEntry(
        canonical_name="BSE SMALLCAP",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE Smallcap",
    ),
    "DOW": IndexEntry(
        canonical_name="DOW JONES",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="DOW JONES",
    ),
    "NASDAQ": IndexEntry(
        canonical_name="NASDAQ",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="NASDAQ",
    ),
    "S&P500": IndexEntry(
        canonical_name="S&P 500",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="S&P 500",
    ),
}

INDEX_SYMBOLS: frozenset[str] = frozenset(_INDEX_MAP.keys())

INDEX_TO_FNO_EXCHANGE: dict[str, str] = {
    "NIFTY": "NFO",
    "BANKNIFTY": "NFO",
    "FINNIFTY": "NFO",
    "SENSEX": "BFO",
}


def is_index(symbol: str) -> bool:
    return _normalize(symbol) in INDEX_SYMBOLS


def get_index_entry(symbol: str) -> IndexEntry | None:
    return _INDEX_MAP.get(_normalize(symbol))


def upstox_index_segment(symbol: str) -> str | None:
    entry = _INDEX_MAP.get(_normalize(symbol))
    return entry.upstox_segment if entry else None


def index_upstox_key(symbol: str) -> str | None:
    entry = _INDEX_MAP.get(_normalize(symbol))
    if entry and entry.upstox_segment and entry.upstox_name:
        return f"{entry.upstox_segment}|{entry.upstox_name}"
    return None


def list_indices() -> list[dict[str, str]]:
    result = []
    for sym, entry in sorted(_INDEX_MAP.items()):
        result.append(
            {
                "symbol": sym,
                "name": entry.canonical_name,
                "upstox_segment": entry.upstox_segment,
            }
        )
    return result
