"""Shared WebSocket infrastructure — reconnect strategy, backfill coordinator.

This package provides broker-agnostic building blocks for WebSocket
connections. Both Dhan and Upstox adapters use these classes to avoid
duplicating reconnect backoff, heartbeat monitoring, and backfill gap
logic.

Usage
-----
    from brokers.common.websocket.reconnect import ReconnectStrategy
    from brokers.common.websocket.backfill import BackfillCoordinator
"""

from brokers.common.websocket.reconnect import ReconnectStrategy
from brokers.common.websocket.backfill import BackfillCoordinator

__all__ = ["ReconnectStrategy", "BackfillCoordinator"]
