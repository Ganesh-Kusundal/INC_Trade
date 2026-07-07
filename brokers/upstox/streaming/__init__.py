"""Upstox streaming — async WebSocket market data and portfolio feeds.

Provides:
- V3 market data feed (protobuf binary protocol)
- Portfolio stream (JSON order/position updates)
- Feed authorizer (REST auth for WS connections)
- Subscription manager (plan-based limits)
"""

from __future__ import annotations
