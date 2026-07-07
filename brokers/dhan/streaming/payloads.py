"""Dhan WebSocket JSON payload builders.

Constructs the JSON messages for subscribing/unsubscribing to market data
on the Dhan WebSocket API (v3).

Dhan WS protocol uses JSON messages with:
- action: "subscribe" | "unsubscribe"
- instruments: list of "exchange_segment|security_id" strings
- feedType: "ltp" | "quote" | "depth"
"""

from __future__ import annotations

import json
from typing import Any

from brokers.domain.enums import Exchange
from brokers.common import segments as _segments


# ── Exchange segment mapping ───────────────────────────────────────────────


def format_instrument_key(exchange: Exchange, security_id: str) -> str:
    """Format an instrument key for Dhan WS subscribe payload.

    Returns ``"exchange_segment|security_id"`` (e.g., ``"NSE_EQ|1333"``).
    """
    segment = _segments.dhan_segment_for(exchange)
    return f"{segment}|{security_id}"


def build_subscribe_payload(
    instruments: list[tuple[Exchange, str]],
    feed_type: str = "quote",
) -> str:
    """Build a subscribe JSON message.

    Args:
        instruments: List of (exchange, security_id) tuples.
        feed_type: One of "ltp", "quote", "depth".

    Returns:
        JSON string ready to send over WebSocket.
    """
    keys = [format_instrument_key(ex, sid) for ex, sid in instruments]
    payload: dict[str, Any] = {
        "action": "subscribe",
        "instruments": keys,
        "feedType": feed_type,
    }
    return json.dumps(payload)


def build_unsubscribe_payload(
    instruments: list[tuple[Exchange, str]],
    feed_type: str = "quote",
) -> str:
    """Build an unsubscribe JSON message."""
    keys = [format_instrument_key(ex, sid) for ex, sid in instruments]
    payload: dict[str, Any] = {
        "action": "unsubscribe",
        "instruments": keys,
        "feedType": feed_type,
    }
    return json.dumps(payload)


# ── Feed type mapping ──────────────────────────────────────────────────────

def mode_to_feed_type(mode: str) -> str:
    """Map stream mode names to Dhan feed types."""
    mapping = {
        "ltp": "ltp",
        "quote": "quote",
        "full": "depth",
        "depth": "depth",
    }
    return mapping.get(mode, "quote")


__all__ = [
    "format_instrument_key",
    "build_subscribe_payload",
    "build_unsubscribe_payload",
    "mode_to_feed_type",
]
