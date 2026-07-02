"""Upstox broker adapter — Trade_XV2 implementation.

The full ``UpstoxBroker`` facade lives in :mod:`brokers.upstox.broker` (P12).
This package re-exports it for ``from brokers.upstox import UpstoxBroker``.
"""

from __future__ import annotations

from typing import Any

from .auth.config import UpstoxConnectionSettings, UpstoxSettingsLoader
from .broker import UpstoxBroker as _UpstoxBroker
from .factory import UpstoxBrokerFactory
from .gateway import UpstoxBrokerGateway


class UpstoxBroker:
    """Upstox broker facade.

    Thin wrapper that instantiates the full :class:`brokers.upstox.broker.UpstoxBroker`
    facade (with all 20+ adapters wired) from the resolved settings.
    """

    def __new__(cls, settings: Any | None = None, **kwargs: Any) -> _UpstoxBroker:
        if settings is None:
            try:
                settings = UpstoxSettingsLoader.from_env()
            except ValueError:
                settings = UpstoxConnectionSettings(client_id="placeholder")
        return _UpstoxBroker(settings=settings, **kwargs)


__all__ = [
    "UpstoxBroker",
    "UpstoxBrokerFactory",
    "UpstoxBrokerGateway",
    "UpstoxConnectionSettings",
    "UpstoxSettingsLoader",
]
