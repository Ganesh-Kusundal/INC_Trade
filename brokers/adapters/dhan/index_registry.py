"""Dhan-specific index registry — owns Dhan-internal security IDs.

Architecture:
    DhanIndexRegistry replaces the old ``config.indices`` security IDs.
    All Dhan-specific identity lives in the adapter layer, never in
    ``brokers/config/``.

    This ensures Clean Architecture compliance: configuration is
    broker-agnostic; broker-internal details are encapsulated in the adapter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DhanIndexEntry:
    """Dhan-internal index metadata."""

    security_id: str
    dhan_exchange: str = "INDEX"
    dhan_segment: str = "IDX_I"


_DHAN_INDEX_MAP: dict[str, DhanIndexEntry] = {
    "NIFTY": DhanIndexEntry(security_id="13"),
    "NIFTY50": DhanIndexEntry(security_id="13"),
    "BANKNIFTY": DhanIndexEntry(security_id="25"),
    "NIFTYBANK": DhanIndexEntry(security_id="25"),
    "FINNIFTY": DhanIndexEntry(security_id="27"),
    "NIFTYFIN": DhanIndexEntry(security_id="27"),
    "MIDCAPNIFTY": DhanIndexEntry(security_id=""),
    "NIFTYMIDCAP": DhanIndexEntry(security_id=""),
    "NIFTYIT": DhanIndexEntry(security_id=""),
    "NIFTYPHARMA": DhanIndexEntry(security_id=""),
    "NIFTYAUTO": DhanIndexEntry(security_id=""),
    "NIFTYFMCG": DhanIndexEntry(security_id=""),
    "NIFTYMETAL": DhanIndexEntry(security_id=""),
    "NIFTYREALTY": DhanIndexEntry(security_id=""),
    "NIFTYENERGY": DhanIndexEntry(security_id=""),
    "NIFTYMEDIA": DhanIndexEntry(security_id=""),
    "NIFTYPSB": DhanIndexEntry(security_id=""),
    "NIFTYPVTBANK": DhanIndexEntry(security_id=""),
    "NIFTYCONS": DhanIndexEntry(security_id=""),
    "NIFTYOILGAS": DhanIndexEntry(security_id=""),
    "NIFTYCOMM": DhanIndexEntry(security_id=""),
    "NIFTYIND": DhanIndexEntry(security_id=""),
    "NIFTYMNC": DhanIndexEntry(security_id=""),
    "NIFTYSMALL": DhanIndexEntry(security_id=""),
    "NIFTYMICRO": DhanIndexEntry(security_id=""),
    "NIFTYNEXT50": DhanIndexEntry(security_id=""),
    "NIFTY100": DhanIndexEntry(security_id=""),
    "NIFTY200": DhanIndexEntry(security_id=""),
    "NIFTY500": DhanIndexEntry(security_id=""),
    "VXNIFTY": DhanIndexEntry(security_id=""),
    "INDIAVIX": DhanIndexEntry(security_id=""),
    "SENSEX": DhanIndexEntry(security_id=""),
    "BSESENSEX": DhanIndexEntry(security_id=""),
    "BSE100": DhanIndexEntry(security_id=""),
    "BSE200": DhanIndexEntry(security_id=""),
    "BSE500": DhanIndexEntry(security_id=""),
    "BSEMIDCAP": DhanIndexEntry(security_id=""),
    "BSESMALLCAP": DhanIndexEntry(security_id=""),
    "DOW": DhanIndexEntry(security_id=""),
    "NASDAQ": DhanIndexEntry(security_id=""),
    "S&P500": DhanIndexEntry(security_id=""),
}


class DhanIndexRegistry:
    """O(1) lookup of Dhan-specific index metadata."""

    @staticmethod
    def lookup(symbol: str) -> DhanIndexEntry | None:
        """Look up Dhan index metadata by symbol (case-insensitive)."""
        return _DHAN_INDEX_MAP.get(symbol.upper().strip())

    @staticmethod
    def security_id(symbol: str) -> str | None:
        """Get Dhan security ID for an index symbol."""
        entry = _DHAN_INDEX_MAP.get(symbol.upper().strip())
        return entry.security_id if entry else None

    @staticmethod
    def exchange(symbol: str) -> str:
        """Get Dhan exchange segment for an index."""
        entry = _DHAN_INDEX_MAP.get(symbol.upper().strip())
        return entry.dhan_exchange if entry else "INDEX"

    @staticmethod
    def segment(symbol: str) -> str:
        """Get Dhan exchange segment for an index."""
        entry = _DHAN_INDEX_MAP.get(symbol.upper().strip())
        return entry.dhan_segment if entry else "IDX_I"
