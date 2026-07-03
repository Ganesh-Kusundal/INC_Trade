"""Shared refresh coordination for Upstox auth + HTTP client."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from brokers.resilience.token_manager import TokenManager

if TYPE_CHECKING:
    from brokers.adapters.upstox.auth.token_manager import UpstoxTokenManager


class UpstoxRefreshCoordinator:
    """Thin bridge: Upstox-specific refresh delegates cooldown to shared TokenManager."""

    def __init__(self, manager: UpstoxTokenManager) -> None:
        self._manager = manager
        self._cooldown = TokenManager(
            get_token_fn=manager.bearer_token,
            refresh_fn=lambda: (manager.force_refresh() or manager.current_token() or ""),
            cooldown_seconds=30.0,
        )
        self._lock = threading.Lock()

    def try_refresh_on_401(self) -> bool:
        with self._lock:
            refreshed = self._manager.try_refresh_on_401()
            if refreshed:
                self._cooldown.invalidate()
            return refreshed

    def bearer_token(self) -> str:
        return self._manager.bearer_token()
