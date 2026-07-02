"""Broker-agnostic default values.

All broker adapters (Dhan, Upstox, Paper) must import these defaults rather
than hardcoding the same string or integer literal. This eliminates shotgun
surgery — changing a platform-wide default requires editing one file.

Market data defaults
--------------------
DEFAULT_EXCHANGE               Default equity exchange (NSE)
DEFAULT_DERIVATIVES_EXCHANGE   Default derivatives exchange (NFO)
DEFAULT_LOOKBACK_DAYS          Default historical lookback period
DEFAULT_TIMEFRAME              Default candle interval (1D)

Order defaults
--------------
DEFAULT_SIDE                   Default transaction side (BUY)
DEFAULT_ORDER_TYPE             Default order type (MARKET)
DEFAULT_PRODUCT_TYPE           Default product type (INTRADAY)
DEFAULT_VALIDITY               Default order validity (DAY)

Stream defaults
---------------
DEFAULT_STREAM_MODE            Default WebSocket subscription mode (LTP)
DEFAULT_DEPTH_TYPE             Default market depth type (DEPTH_5)
"""

from __future__ import annotations

from typing import Final

# ── Market data ──────────────────────────────────────────────────────────────

DEFAULT_EXCHANGE: Final[str] = "NSE"
DEFAULT_DERIVATIVES_EXCHANGE: Final[str] = "NFO"
DEFAULT_LOOKBACK_DAYS: Final[int] = 90
DEFAULT_TIMEFRAME: Final[str] = "1D"

# ── Orders ──────────────────────────────────────────────────────────────────

DEFAULT_SIDE: Final[str] = "BUY"
DEFAULT_ORDER_TYPE: Final[str] = "MARKET"
DEFAULT_PRODUCT_TYPE: Final[str] = "INTRADAY"
DEFAULT_VALIDITY: Final[str] = "DAY"

# ── Streaming ────────────────────────────────────────────────────────────────

DEFAULT_STREAM_MODE: Final[str] = "LTP"
DEFAULT_DEPTH_TYPE: Final[str] = "DEPTH_5"
