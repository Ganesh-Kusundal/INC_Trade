"""Dhan segment adapter — wire format and SDK integer mappings.

Canonical parsing delegates to :mod:`brokers.common.core.exchange_segments`.
This module owns Dhan-specific wire strings (``MCX_COMM``) and SDK transport codes.
"""

from __future__ import annotations

from brokers.dhan.domain import Exchange
from domain.constants.market import DEFAULT_EXCHANGE_SEGMENT_FALLBACK
from domain.exchange_segments import parse_segment as _parse_segment
from domain.types import ExchangeSegment

DEFAULT_SEGMENT = DEFAULT_EXCHANGE_SEGMENT_FALLBACK

# Dhan HTTP/wire segment strings (distinct from canonical enum values).
_DHAN_WIRE: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: "NSE_EQ",
    ExchangeSegment.BSE: "BSE_EQ",
    ExchangeSegment.NSE_FNO: "NSE_FNO",
    ExchangeSegment.BSE_FNO: "BSE_FNO",
    ExchangeSegment.MCX: "MCX_COMM",
    ExchangeSegment.NSE_CURRENCY: "NSE_CURRENCY",
    ExchangeSegment.BSE_CURRENCY: "BSE_CURRENCY",
    ExchangeSegment.IDX_I: "IDX_I",
}

# Short exchange codes used in Dhan Instrument.exchange and user input.
_EXCHANGE_SHORT: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: "NSE",
    ExchangeSegment.BSE: "BSE",
    ExchangeSegment.NSE_FNO: "NFO",
    ExchangeSegment.BSE_FNO: "BFO",
    ExchangeSegment.MCX: "MCX",
    ExchangeSegment.NSE_CURRENCY: "CDS",
    ExchangeSegment.BSE_CURRENCY: "BCD",
    ExchangeSegment.IDX_I: "INDEX",
}

EXCHANGE_TO_SEGMENT: dict[str, str] = {
    short: _DHAN_WIRE[seg]
    for seg, short in _EXCHANGE_SHORT.items()
    if short in {e.value for e in Exchange}
}
EXCHANGE_TO_SEGMENT["INDEX"] = "IDX_I"

SEGMENT_TO_EXCHANGE: dict[str, str] = {
    wire: _EXCHANGE_SHORT[seg] for seg, wire in _DHAN_WIRE.items()
}
SEGMENT_TO_EXCHANGE.update(
    {
        "BSE_CURRENCY": "BCD",
        "NSE_COMM": "MCX",
    }
)

_COMPACT_SEGMENT_MAP: dict[tuple[str, str], str] = {
    ("NSE", "E"): "NSE_EQ",
    ("NSE", "D"): "NSE_FNO",
    ("NSE", "I"): "IDX_I",
    ("BSE", "E"): "BSE_EQ",
    ("BSE", "D"): "BSE_FNO",
    ("BSE", "I"): "IDX_I",
    ("MCX", "M"): "MCX_COMM",
    ("CDS", "D"): "NSE_CURRENCY",
    ("NSE", "C"): "NSE_CURRENCY",
    ("BSE", "C"): "BSE_CURRENCY",
    ("NSE", "M"): "NSE_COMM",
}

# Binary protocol numeric codes (Dhan v2 websocket)
NUMERIC_TO_SEGMENT: dict[int, str] = {
    0: "IDX_I",
    1: "NSE_EQ",
    2: "NSE_FNO",
    3: "NSE_CURRENCY",
    4: "BSE_EQ",
    5: "MCX_COMM",
    7: "BSE_CURRENCY",
    8: "BSE_FNO",
}

SEGMENT_TO_NUMERIC: dict[str, int] = {v: k for k, v in NUMERIC_TO_SEGMENT.items()}

# Dhan SDK ``MarketFeed`` exchange attribute names → integer codes (test shim).
DHAN_SDK_SEGMENT_CONSTANTS: dict[str, int] = {
    "IDX": 0,
    "NSE": 1,
    "NSE_FNO": 2,
    "NSE_CURR": 3,
    "BSE": 4,
    "MCX": 5,
    "BSE_CURR": 7,
    "BSE_FNO": 8,
}


def parse_segment(value: str | ExchangeSegment) -> ExchangeSegment | None:
    """Parse user/broker input to canonical :class:`ExchangeSegment`."""
    return _parse_segment(value)


def to_dhan_wire(segment: str | ExchangeSegment) -> str:
    """Return Dhan HTTP/wire segment string for a canonical segment."""
    parsed = _parse_segment(segment)
    if parsed is None:
        raise ValueError(f"Unknown exchange segment: {segment!r}")
    return _DHAN_WIRE[parsed]


def to_sdk_int(segment: str | ExchangeSegment) -> int:
    """Return Dhan SDK MarketFeed integer constant for a segment."""
    from dhanhq.marketfeed import MarketFeed as SDKMarketFeed

    wire = to_dhan_wire(segment)
    _sdk_map: dict[str, int] = {
        "IDX_I": SDKMarketFeed.IDX,
        "NSE_EQ": SDKMarketFeed.NSE,
        "NSE_FNO": SDKMarketFeed.NSE_FNO,
        "NSE_CURRENCY": SDKMarketFeed.NSE_CURR,
        "BSE_EQ": SDKMarketFeed.BSE,
        "MCX_COMM": SDKMarketFeed.MCX,
        "BSE_FNO": SDKMarketFeed.BSE_FNO,
        "BSE_CURRENCY": SDKMarketFeed.BSE_CURR,
    }
    sdk_int = _sdk_map.get(wire)
    if sdk_int is None:
        raise ValueError(f"No SDK mapping for Dhan wire segment: {wire!r}")
    return sdk_int


def from_sdk_int(code: int) -> ExchangeSegment:
    """Convert Dhan SDK MarketFeed integer to canonical segment."""
    wire = NUMERIC_TO_SEGMENT.get(code)
    if wire is None:
        raise ValueError(f"Unknown SDK exchange code: {code}")
    parsed = _parse_segment(wire)
    if parsed is None:
        raise ValueError(f"Unknown wire segment for SDK code {code}: {wire!r}")
    return parsed


def segment_to_exchange(segment: str, default: str = "NSE") -> Exchange:
    exch_str = SEGMENT_TO_EXCHANGE.get(segment, default)
    return Exchange(exch_str)
