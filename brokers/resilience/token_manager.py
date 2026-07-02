"""Token manager — auth token refresh with cooldown.

Manages token lifecycle: tracks expiry, prevents rapid refresh
attempts (cooldown), and provides thread-safe token access.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class TokenManager:
    def __init__(
        self,
        get_token_fn: Callable[[], str],
        refresh_fn: Callable[[], str] | None = None,
        cooldown_seconds: float = 30.0,
        ttl_seconds: float = 86400.0,
    ):
        self._get_token = get_token_fn
        self._refresh = refresh_fn
        self._cooldown = cooldown_seconds
        self._ttl = ttl_seconds
        self._token: str = ""
        self._obtained_at: float = 0.0
        self._last_refresh_attempt: float = 0.0
        self._lock = threading.Lock()

    @property
    def token(self) -> str:
        with self._lock:
            if not self._token or self._is_expired():
                self._token = self._get_token()
                self._obtained_at = time.monotonic()
            return self._token

    @property
    def is_expired(self) -> bool:
        with self._lock:
            return self._is_expired()

    def refresh(self) -> str:
        if self._refresh is None:
            return self.token

        with self._lock:
            now = time.monotonic()
            if now - self._last_refresh_attempt < self._cooldown:
                logger.debug("token_refresh_cooldown_active")
                return self._token
            self._last_refresh_attempt = now

        new_token = self._refresh()
        with self._lock:
            self._token = new_token
            self._obtained_at = time.monotonic()
        logger.info("token_refreshed")
        return new_token

    def invalidate(self) -> None:
        with self._lock:
            self._token = ""
            self._obtained_at = 0.0

    def _is_expired(self) -> bool:
        if not self._token:
            return True
        return time.monotonic() - self._obtained_at > self._ttl
