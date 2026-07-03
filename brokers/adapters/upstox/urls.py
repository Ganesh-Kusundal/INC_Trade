"""Resolve Upstox URL registry for an environment."""

from __future__ import annotations

from brokers.config.endpoints import Upstox, _UpstoxUrls


def resolve_upstox_urls(environment: str = "LIVE") -> _UpstoxUrls:
    if environment.upper() == "SANDBOX":
        return Upstox.sandbox()
    return Upstox.production()
