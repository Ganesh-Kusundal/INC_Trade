"""Hardcoded index symbol mapping — single source of truth for all indices.

Both Dhan and Upstox resolve indices differently from equities:

* **Dhan**: Indices use exchange ``"INDEX"`` and segment ``"IDX_I"``. The Dhan
  scrip-master CSV *may* include index instruments with
  ``SEM_EXM_EXCH_ID = "IDX_I"``, but users typically query them with
  ``exchange="NSE"`` which fails because the resolver looks up by
  ``(symbol, Exchange.INDEX)`` not ``(symbol, Exchange.NSE)``.

* **Upstox**: Indices have segment ``"NSE_INDEX"`` (or ``"BSE_INDEX"``)
  instead of ``"NSE_EQ"``. The Upstox instrument JSON *does* include
  index definitions, but when a user passes ``exchange="NSE"`` the
  segment mapper returns ``"NSE_EQ"``, which won't match ``"NSE_INDEX"``.

This module provides:

* :data:`INDEX_SYMBOLS` — a frozen set of all known index symbols.
* :func:`is_index` — fast membership check.
* :func:`dhan_index_exchange` — returns ``"INDEX"`` if *symbol* is an index.
* :func:`upstox_index_segment` — returns ``"NSE_INDEX"`` (or ``"BSE_INDEX"``)
  or ``None`` if *symbol* is not a known index.
Usage::

    from config.indices import is_index, dhan_index_exchange, upstox_index_segment

    # Dhan resolver fallback
    if is_index(symbol):
        exchange = dhan_index_exchange(symbol)

    # Upstox _resolve_instrument_key
    if is_index(symbol):
        segment = upstox_index_segment(symbol)

To add a new index, simply append to :data:`_INDEX_MAP`.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.symbols import normalize_symbol


@dataclass(frozen=True)
class _IndexEntry:
    """Broker-agnostic index metadata."""

    canonical_name: str  # User-facing name (e.g. "NIFTY 50")
    dhan_exchange: str = "INDEX"  # Dhan exchange value
    dhan_segment: str = "IDX_I"  # Dhan segment code
    dhan_security_id: str | None = None  # Dhan numeric security ID for index LTP
    upstox_segment: str = ""  # Upstox segment (e.g. "NSE_INDEX")
    upstox_name: str = ""  # Upstox instrument key suffix (e.g. "Nifty 50")


# ── Master index registry ───────────────────────────────────────────────────
# Keys are the bare trading symbols users type (NIFTY, BANKNIFTY, etc.).
# Update this dictionary when adding/removing indices.

_INDEX_MAP: dict[str, _IndexEntry] = {
    # ── NSE indices ──────────────────────────────────────────────────────
    #   Dhan security IDs sourced from Dhan scrip-master CSV (IDX_I segment):
    #   https://images.dhan.co/api-data/api-scrip-master.csv
    "NIFTY": _IndexEntry(
        canonical_name="NIFTY 50",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        dhan_security_id="13",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 50",
    ),
    "NIFTY50": _IndexEntry(
        canonical_name="NIFTY 50",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        dhan_security_id="13",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 50",
    ),
    "BANKNIFTY": _IndexEntry(
        canonical_name="NIFTY BANK",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        dhan_security_id="25",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Bank",
    ),
    "NIFTYBANK": _IndexEntry(
        canonical_name="NIFTY BANK",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        dhan_security_id="25",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Bank",
    ),
    "FINNIFTY": _IndexEntry(
        canonical_name="NIFTY FINANCIAL SERVICES",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        dhan_security_id="27",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Fin Service",
    ),
    "NIFTYFIN": _IndexEntry(
        canonical_name="NIFTY FINANCIAL SERVICES",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        dhan_security_id="27",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Fin Service",
    ),
    "MIDCAPNIFTY": _IndexEntry(
        canonical_name="NIFTY MIDCAP 100",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Midcap 100",
    ),
    "NIFTYMIDCAP": _IndexEntry(
        canonical_name="NIFTY MIDCAP 100",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Midcap 100",
    ),
    "NIFTYIT": _IndexEntry(
        canonical_name="NIFTY IT",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty IT",
    ),
    "NIFTYPHARMA": _IndexEntry(
        canonical_name="NIFTY PHARMA",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Pharma",
    ),
    "NIFTYAUTO": _IndexEntry(
        canonical_name="NIFTY AUTO",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Auto",
    ),
    "NIFTYFMCG": _IndexEntry(
        canonical_name="NIFTY FMCG",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty FMCG",
    ),
    "NIFTYMETAL": _IndexEntry(
        canonical_name="NIFTY METAL",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Metal",
    ),
    "NIFTYREALTY": _IndexEntry(
        canonical_name="NIFTY REALTY",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Realty",
    ),
    "NIFTYENERGY": _IndexEntry(
        canonical_name="NIFTY ENERGY",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Energy",
    ),
    "NIFTYMEDIA": _IndexEntry(
        canonical_name="NIFTY MEDIA",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Media",
    ),
    "NIFTYPSB": _IndexEntry(
        canonical_name="NIFTY PSU BANK",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty PSU Bank",
    ),
    "NIFTYPVTBANK": _IndexEntry(
        canonical_name="NIFTY PRIVATE BANK",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Pvt Bank",
    ),
    "NIFTYCONS": _IndexEntry(
        canonical_name="NIFTY CONSUMER DURABLES",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Consumer Durables",
    ),
    "NIFTYOILGAS": _IndexEntry(
        canonical_name="NIFTY OIL AND GAS",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Oil and Gas",
    ),
    "NIFTYCOMM": _IndexEntry(
        canonical_name="NIFTY COMMODITIES",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Commodities",
    ),
    "NIFTYIND": _IndexEntry(
        canonical_name="NIFTY INDUSTRIALS",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Industrials",
    ),
    "NIFTYMNC": _IndexEntry(
        canonical_name="NIFTY MNC",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty MNC",
    ),
    "NIFTYSMALL": _IndexEntry(
        canonical_name="NIFTY SMALLCAP 250",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Smallcap 250",
    ),
    "NIFTYMICRO": _IndexEntry(
        canonical_name="NIFTY MICROCAP 250",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Microcap 250",
    ),
    "NIFTYNEXT50": _IndexEntry(
        canonical_name="NIFTY NEXT 50",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty Next 50",
    ),
    "NIFTY100": _IndexEntry(
        canonical_name="NIFTY 100",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 100",
    ),
    "NIFTY200": _IndexEntry(
        canonical_name="NIFTY 200",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 200",
    ),
    "NIFTY500": _IndexEntry(
        canonical_name="NIFTY 500",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="Nifty 500",
    ),
    "VXNIFTY": _IndexEntry(
        canonical_name="NIFTY VOLATILITY",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="India VIX",
    ),
    "INDIAVIX": _IndexEntry(
        canonical_name="INDIA VIX",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="NSE_INDEX",
        upstox_name="India VIX",
    ),
    # ── BSE indices ──────────────────────────────────────────────────────
    "SENSEX": _IndexEntry(
        canonical_name="SENSEX",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="SENSEX",
    ),
    "BSESENSEX": _IndexEntry(
        canonical_name="SENSEX",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="SENSEX",
    ),
    "BSE100": _IndexEntry(
        canonical_name="BSE 100",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 100",
    ),
    "BSE200": _IndexEntry(
        canonical_name="BSE 200",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 200",
    ),
    "BSE500": _IndexEntry(
        canonical_name="BSE 500",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE 500",
    ),
    "BSEMIDCAP": _IndexEntry(
        canonical_name="BSE MIDCAP",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE Midcap",
    ),
    "BSESMALLCAP": _IndexEntry(
        canonical_name="BSE SMALLCAP",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="BSE_INDEX",
        upstox_name="BSE Smallcap",
    ),
    # ── Global indices (Upstox only) ─────────────────────────────────────
    "DOW": _IndexEntry(
        canonical_name="DOW JONES",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="DOW JONES",
    ),
    "NASDAQ": _IndexEntry(
        canonical_name="NASDAQ",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="NASDAQ",
    ),
    "S&P500": _IndexEntry(
        canonical_name="S&P 500",
        dhan_exchange="INDEX",
        dhan_segment="IDX_I",
        upstox_segment="GLOBAL_INDEX",
        upstox_name="S&P 500",
    ),
}

# ── Frozen set for fast membership checks ───────────────────────────────────
INDEX_SYMBOLS: frozenset[str] = frozenset(_INDEX_MAP.keys())

# ── F&O exchange mapping (single source of truth) ────────────────────────────
# Maps index symbols to their F&O exchange segment. Used by both Dhan and
# Upstox gateway future_chain() methods to resolve the correct exchange.
INDEX_TO_FNO_EXCHANGE: dict[str, str] = {
    "NIFTY": "NFO",
    "BANKNIFTY": "NFO",
    "FINNIFTY": "NFO",
    "SENSEX": "BFO",
}

# ── Public helpers ──────────────────────────────────────────────────────────


def is_index(symbol: str) -> bool:
    """Check if *symbol* is a known index (case-insensitive)."""
    return normalize_symbol(symbol) in INDEX_SYMBOLS


def get_index_entry(symbol: str) -> _IndexEntry | None:
    """Return :class:`_IndexEntry` for *symbol*, or ``None`` if not an index."""
    return _INDEX_MAP.get(normalize_symbol(symbol))


def dhan_index_exchange(symbol: str) -> str | None:
    """Return Dhan exchange name (``"INDEX"``) if *symbol* is an index, else ``None``."""
    entry = _INDEX_MAP.get(normalize_symbol(symbol))
    return entry.dhan_exchange if entry else None


def upstox_index_segment(symbol: str) -> str | None:
    """Return Upstox segment (e.g. ``"NSE_INDEX"``) if *symbol* is an index, else ``None``."""
    entry = _INDEX_MAP.get(normalize_symbol(symbol))
    return entry.upstox_segment if entry else None


def index_upstox_key(symbol: str) -> str | None:
    """Return the Upstox instrument_key for *symbol* (e.g. ``\"NSE_INDEX|Nifty 50\"``)."""
    entry = _INDEX_MAP.get(normalize_symbol(symbol))
    if entry and entry.upstox_segment and entry.upstox_name:
        return f"{entry.upstox_segment}|{entry.upstox_name}"
    return None


def list_indices() -> list[dict[str, str]]:
    """Return a human-readable list of all registered indices."""
    result = []
    for sym, entry in sorted(_INDEX_MAP.items()):
        result.append(
            {
                "symbol": sym,
                "name": entry.canonical_name,
                "dhan_exchange": entry.dhan_exchange,
                "upstox_segment": entry.upstox_segment,
            }
        )
    return result
