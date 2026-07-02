"""Upstox V3 Protobuf WebSocket feed (binary).

Mirrors Trade_J ``UpstoxWebSocketMultiplexer``, ``UpstoxFeedAuthorizer``,
``UpstoxMarketInfoParser``, ``UpstoxMarketSubscription``, ``UpstoxPortfolioStreamParser``.

The wire protocol uses Protobuf-encoded binary frames. The official Upstox
proto is shipped in :mod:`brokers.upstox.websocket.proto`; the generated
Python stubs are at :mod:`brokers.upstox.websocket.proto.market_feed_pb2`.
"""

from __future__ import annotations
