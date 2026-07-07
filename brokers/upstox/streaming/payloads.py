"""Upstox WebSocket JSON payload builders.

Constructs the JSON/bytes messages for subscribing/unsubscribing to market data
on the Upstox V3 WebSocket API.

Upstox V3 protocol uses JSON control messages with:
- method: "subscribe" | "unsubscribe"
- instruments: list of instrument_key strings
- mode: "ltpc" | "full" | "option_greeks"
"""

from __future__ import annotations

import json
import uuid
from typing import Any


def build_subscribe_payload(
    instruments: list[str],
    mode: str = "ltpc",
) -> dict[str, Any]:
    """Build a subscribe JSON payload for Upstox V3 WS.

    Args:
        instruments: List of instrument_key strings (e.g., "NSE_EQ|INE002A01018").
        mode: One of "ltpc", "full", "option_greeks".

    Returns:
        Dict payload ready to be JSON-encoded and sent.
    """
    return {
        "guid": str(uuid.uuid4()),
        "method": "subscribe",
        "data": {
            "instrumentKeys": instruments,
            "mode": normalize_mode(mode),
        },
    }


def build_unsubscribe_payload(
    instruments: list[str],
    mode: str = "ltpc",
) -> dict[str, Any]:
    """Build an unsubscribe JSON payload for Upstox V3 WS."""
    return {
        "guid": str(uuid.uuid4()),
        "method": "unsubscribe",
        "data": {
            "instrumentKeys": instruments,
            "mode": normalize_mode(mode),
        },
    }


def build_change_mode_payload(
    instruments: list[str],
    mode: str = "ltpc",
) -> dict[str, Any]:
    """Build a change_mode JSON payload for Upstox V3 WS."""
    return {
        "guid": str(uuid.uuid4()),
        "method": "change_mode",
        "data": {
            "instrumentKeys": instruments,
            "mode": normalize_mode(mode),
        },
    }


def encode_payload(payload: dict[str, Any]) -> bytes:
    """Encode a payload dict to UTF-8 bytes for WebSocket transmission."""
    return json.dumps(payload).encode("utf-8")


def normalize_mode(mode: str) -> str:
    """Normalize mode strings to Upstox V3 canonical forms."""
    mode = mode.lower().strip()
    if mode in ("ltp", "ltpc"):
        return "ltpc"
    if mode in ("quote", "full"):
        return "full"
    if mode in ("option_greeks", "greeks"):
        return "option_greeks"
    if mode in ("full_d30", "d30", "depth"):
        return "full_d30"
    return "ltpc"


__all__ = [
    "build_subscribe_payload",
    "build_unsubscribe_payload",
    "build_change_mode_payload",
    "encode_payload",
    "normalize_mode",
]
