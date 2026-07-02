"""Upstox <-> Trade_XV2 segment mapper.

Mirrors Trade_J ``UpstoxSegmentMapper``.

Upstox segment strings (wire values) ↔ ``brokers.common.core.enums.ExchangeSegment``.
"""

from __future__ import annotations

from typing import Any

from domain import ExchangeSegment

_UPSTOX_TO_SEGMENT: dict[str, ExchangeSegment] = {
    "NSE_EQ": ExchangeSegment.NSE,
    "BSE_EQ": ExchangeSegment.BSE,
    "NSE_FO": ExchangeSegment.NSE_FNO,
    "BSE_FO": ExchangeSegment.BSE_FNO,
    "NCD_FO": ExchangeSegment.NSE_CURRENCY,
    "BCD_FO": ExchangeSegment.BSE_CURRENCY,
    "MCX_FO": ExchangeSegment.MCX,
    "MCX_COMM": ExchangeSegment.MCX,
    "NSE_COM": ExchangeSegment.MCX,
    "NSE_INDEX": ExchangeSegment.IDX_I,
    "BSE_INDEX": ExchangeSegment.IDX_I,
    "MCX_INDEX": ExchangeSegment.IDX_I,
    "GLOBAL_INDEX": ExchangeSegment.IDX_I,
    "UNKNOWN": ExchangeSegment.NSE,
}

_SEGMENT_TO_UPSTOX: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: "NSE_EQ",
    ExchangeSegment.BSE: "BSE_EQ",
    ExchangeSegment.NSE_FNO: "NSE_FO",
    ExchangeSegment.BSE_FNO: "BSE_FO",
    ExchangeSegment.NSE_CURRENCY: "NCD_FO",
    ExchangeSegment.BSE_CURRENCY: "BCD_FO",
    ExchangeSegment.MCX: "MCX_FO",
    ExchangeSegment.IDX_I: "NSE_INDEX",
}


class UpstoxSegmentMapper:
    """Bidirectional segment mapper."""

    @classmethod
    def to_safe(cls, upstox_segment: str) -> ExchangeSegment:
        if not upstox_segment:
            return ExchangeSegment.NSE
        seg = _UPSTOX_TO_SEGMENT.get(upstox_segment.upper())
        if seg is None:
            return ExchangeSegment.NSE
        return seg

    @classmethod
    def to_wire(cls, segment: Any) -> str:
        if isinstance(segment, str):
            segment_upper = segment.upper()
            if segment_upper == "NSE":
                segment = ExchangeSegment.NSE
            elif segment_upper == "BSE":
                segment = ExchangeSegment.BSE
            elif segment_upper in ("NSE_FNO", "NFO"):
                segment = ExchangeSegment.NSE_FNO
            elif segment_upper in ("BSE_FNO", "BFO"):
                segment = ExchangeSegment.BSE_FNO
            elif segment_upper == "MCX":
                segment = ExchangeSegment.MCX
            elif segment_upper == "INDEX":
                segment = ExchangeSegment.IDX_I
            else:
                for seg in ExchangeSegment:
                    if seg.name == segment_upper or seg.value == segment_upper:
                        segment = seg
                        break

        if isinstance(segment, ExchangeSegment):
            return _SEGMENT_TO_UPSTOX.get(segment, "NSE_EQ")
        if isinstance(segment, str):
            return segment.upper() or "NSE_EQ"
        return "NSE_EQ"

    @classmethod
    def all_upstox_segments(cls) -> list[str]:
        return list(_UPSTOX_TO_SEGMENT.keys())

    @classmethod
    def all_xv2_segments(cls) -> list[ExchangeSegment]:
        return list(_SEGMENT_TO_UPSTOX.keys())
