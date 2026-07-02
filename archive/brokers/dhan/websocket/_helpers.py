"""Shared helpers for Dhan WebSocket services.

Extracted from the former monolithic ``brokers/dhan/websocket.py`` (Task 5.1).
Contains lazy SDK loaders, instrument conversion, the ``_DhanContext`` shim,
and the ``_to_decimal`` utility — all shared by the three WebSocket service
classes (``DhanMarketFeed``, ``DhanOrderStream``, ``PollingMarketFeed``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from brokers.dhan.segments import to_sdk_int

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy SDK loaders — avoid importing dhanhq at module-import time so that
# ``import brokers.dhan.gateway`` works even when the SDK is not installed.
# ---------------------------------------------------------------------------

def _sdk_market_feed_class() -> type:
    """Lazy import so ``import brokers.dhan.gateway`` does not require dhanhq at import time."""
    from dhanhq.marketfeed import MarketFeed

    return MarketFeed


def _sdk_order_update_class() -> type:
    from dhanhq.orderupdate import OrderUpdate

    return OrderUpdate


# ---------------------------------------------------------------------------
# Mode map — SDK subscription-type constants (cached at module level).
# ---------------------------------------------------------------------------

# Module-level cache for the mode map (computed once, lazily on first access).
# Avoids rebuilding the dict and re-importing MarketFeed on every call.
_MODE_MAP: dict[str, int] | None = None


def _mode_map() -> dict[str, int]:
    """Return the mode-name -> SDK constant mapping (cached at module level)."""
    global _MODE_MAP
    if _MODE_MAP is None:
        mf = _sdk_market_feed_class()
        _MODE_MAP = {
            "LTP": mf.Ticker,
            "TICKER": mf.Ticker,
            "QUOTE": mf.Quote,
            "FULL": mf.Full,
            "DEPTH": mf.Quote,  # v2 does not support Depth (19)
        }
    return _MODE_MAP


# ---------------------------------------------------------------------------
# Decimal conversion helper
# ---------------------------------------------------------------------------

def _to_decimal(value: Any, default: str = "0") -> Decimal:
    """Convert a value to Decimal, avoiding redundant conversion if already Decimal.

    Task 2.4: _transform_quote already produces Decimal values. This helper
    ensures _publish_tick does not re-convert them through str() unnecessarily,
    while still handling non-Decimal inputs from the backfill path.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# Instrument conversion
# ---------------------------------------------------------------------------

def _to_sdk_instruments(instruments: list[tuple]) -> list[tuple]:
    """Convert human-readable instruments to SDK format.

    Accepts:
        [(exchange_str, security_id_str, mode_str), ...]
        e.g. [("MCX_COMM", "466583", "LTP")]

    Returns:
        [(exchange_int, security_id_int, type_int), ...]
        e.g. [(5, 466583, 15)]
    """
    sdk_instruments = []
    # Task 1.6: resolve mode map once before the loop (was called per instrument).
    mode_map = _mode_map()
    default_mode = _sdk_market_feed_class().Ticker
    for item in instruments:
        if len(item) != 3:
            logger.warning("Skipping malformed instrument: %s", item)
            continue
        exchange, security_id, mode = item

        # Already SDK-format — pass through but keep security_id as string
        if isinstance(exchange, int) and isinstance(mode, int):
            sid_str = str(security_id)
            sdk_instruments.append((exchange, sid_str, mode))
            continue

        # Convert strings to SDK integers
        if isinstance(exchange, int):
            exch_int = exchange
        else:
            try:
                exch_int = to_sdk_int(str(exchange))
            except ValueError:
                exch_int = None
        if exch_int is None:
            logger.warning("Unknown exchange: %s", exchange)
            continue
        sid_str = str(security_id)
        mode_int = (
            mode_map.get(str(mode).upper(), default_mode)
            if isinstance(mode, str)
            else int(mode)
        )
        sdk_instruments.append((exch_int, sid_str, mode_int))
    return sdk_instruments


# ---------------------------------------------------------------------------
# Dhan SDK context shim
# ---------------------------------------------------------------------------

class _DhanContext:
    """Shim to satisfy SDK's dhan_context interface.

    Supports both static token and token provider callable.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
    ):
        self._client_id = client_id
        self._access_token = access_token or ""
        self._access_token_fn = access_token_fn

    def get_client_id(self) -> str:
        return self._client_id

    def get_access_token(self) -> str:
        if self._access_token_fn:
            try:
                return self._access_token_fn()
            except Exception as exc:
                logger.error(
                    "dhan_ws_access_token_fn_failed",
                    extra={"exception_type": type(exc).__name__, "exception_message": str(exc)},
                )
        return self._access_token

    def get_dhan_http(self):
        return None

    def update_token(self, token: str) -> None:
        """Update the static token snapshot."""
        self._access_token = token
