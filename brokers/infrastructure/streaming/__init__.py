"""Common streaming infrastructure — async-first WebSocket lifecycle management.

Provides:
- Stream health models (transport, subscription, freshness states)
- Subscription plan (SSOT for required instruments)
- Queue-based AsyncIterator for StreamingPort compliance
- StreamOrchestrator for reconnection, heartbeat, and fan-out
- AsyncTransport protocol for WebSocket abstraction
"""

from __future__ import annotations
