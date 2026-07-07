"""Shared streaming utilities — status mapping and common helpers.

Provides functions shared across broker adapters for streaming
event normalization.
"""

from __future__ import annotations

from brokers.domain.enums import OrderStatus, Side


def map_stream_status(status: str) -> OrderStatus:
    """Map a broker-agnostic status string to OrderStatus enum.

    Handles common status strings from both Dhan and Upstox.
    """
    mapping = {
        "OPEN": OrderStatus.OPEN,
        "FILLED": OrderStatus.FILLED,
        "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
        "CANCELLED": OrderStatus.CANCELLED,
        "REJECTED": OrderStatus.REJECTED,
        "EXPIRED": OrderStatus.EXPIRED,
        "TRADED": OrderStatus.FILLED,
        "PART_TRADED": OrderStatus.PARTIALLY_FILLED,
        "TRANSIT": OrderStatus.OPEN,
        "PENDING": OrderStatus.OPEN,
        "COMPLETE": OrderStatus.FILLED,
        "MODIFIED": OrderStatus.OPEN,
    }
    return mapping.get(status.upper(), OrderStatus.UNKNOWN)


def parse_side(side_str: str | None) -> Side:
    """Parse a broker side string safely, defaulting to BUY if unknown.

    Handles None, empty string, and common variations ("BUY", "B", "SELL", "S").
    """
    if side_str and side_str.upper() in ("BUY", "B"):
        return Side.BUY
    if side_str and side_str.upper() in ("SELL", "S"):
        return Side.SELL
    return Side.BUY


__all__ = ["map_stream_status", "parse_side"]
