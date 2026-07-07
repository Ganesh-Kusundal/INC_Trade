"""Dhan streaming — async WebSocket market data and order feeds.

Provides:
- Market data feed (JSON protocol, LTP/QUOTE/DEPTH modes)
- Order update stream
- Polling fallback
- Depth feeds (20-level and 200-level with connection pooling)
"""

from __future__ import annotations
