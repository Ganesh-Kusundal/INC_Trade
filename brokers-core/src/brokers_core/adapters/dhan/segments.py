"""Dhan segment resolution helpers — single lookup for exchange → wire segment."""

from __future__ import annotations

from brokers_core.adapters.dhan.config import DHAN_SEGMENT_RESOLVER

SEGMENT_TO_EXCHANGE = DHAN_SEGMENT_RESOLVER.segment_to_exchange


def resolve_segment(exchange: str) -> str:
    """Map user-facing exchange code to Dhan wire segment."""
    return DHAN_SEGMENT_RESOLVER.to_segment(exchange)


def resolve_exchange(segment: str) -> str:
    """Map Dhan wire segment back to user-facing exchange code."""
    return DHAN_SEGMENT_RESOLVER.to_exchange(segment)
