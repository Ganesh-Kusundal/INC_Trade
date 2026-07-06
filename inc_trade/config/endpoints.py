"""Strangler bridge — re-export endpoints registry."""
from brokers_core.config.endpoints import Dhan, Upstox, _UpstoxUrls

__all__ = ["Dhan", "Upstox", "_UpstoxUrls"]
