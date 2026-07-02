"""Observability and HTTP server constants.

All constants governing HTTP observability server configuration including
host, port, and monitoring defaults.
"""

from __future__ import annotations

# ── Observability / HTTP server ────────────────────────────────────────────

#: Default bind address for HttpObservabilityServer.
OBSERVABILITY_DEFAULT_HOST: str = "127.0.0.1"

#: Default bind port for HttpObservabilityServer.
OBSERVABILITY_DEFAULT_PORT: int = 8765

__all__ = [
    "OBSERVABILITY_DEFAULT_HOST",
    "OBSERVABILITY_DEFAULT_PORT",
]
