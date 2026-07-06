"""Dhan segment resolution helpers — single lookup for exchange → wire segment."""

from __future__ import annotations

from inc_trade.domain.constants.segments import SEGMENT_TO_EXCHANGE as _BASE_SEGMENT_TO_EXCHANGE

from brokers.adapters.dhan.config import EXCHANGE_MAP

SEGMENT_TO_EXCHANGE: dict[str, str] = {
    **_BASE_SEGMENT_TO_EXCHANGE,
    "NSE_CD": "CUR",
    "IDX_I": "INDEX",
}


def resolve_segment(exchange: str) -> str:
    """Map user-facing exchange code to Dhan wire segment."""
    return EXCHANGE_MAP.get(exchange.strip().upper(), exchange.strip().upper())


def resolve_exchange(segment: str) -> str:
    """Map Dhan wire segment back to user-facing exchange code."""
    return SEGMENT_TO_EXCHANGE.get(segment.strip().upper(), segment.strip().upper())
