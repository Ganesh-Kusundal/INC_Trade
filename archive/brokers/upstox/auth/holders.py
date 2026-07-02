"""Token holder types — Static, Analytics, Extended, OAuth, Webhook.

Mirrors Trade_J ``UpstoxStaticTokenHolder``, ``UpstoxAnalyticsTokenHolder``,
and ``UpstoxTokenManager.UpstoxExtendedTokenHolder``.

Three persistent token flavours:

* **STATIC** — fixed access token; no refresh, no 3:30 AM IST fallback.
* **EXTENDED** — 1-year, read-only, no refresh.
* **ANALYTICS** — 1-year, read-only, no refresh (similar to extended).

The OAuth ``UpstoxTokenManager`` (separate file) handles the live flow with
PKCE, refresh-token grant, and a daily 3:30 AM IST expiry.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from brokers.common.auth.jwt_expiry import JwtExpiry

from .token_expiry import UpstoxTokenExpiry


@dataclass(frozen=True)
class TokenSnapshot:
    access_token: str
    refresh_token: str | None = None
    expires_at_ms: int = 0
    issued_at_ms: int = 0
    source: str = "STATIC"

    @property
    def is_expired(self) -> bool:
        if self.expires_at_ms <= 0:
            return False
        return int(time.time() * 1000) >= self.expires_at_ms


class UpstoxTokenHolder:
    """Abstract base for any bearer-token source."""

    def bearer_token(self) -> str:
        raise NotImplementedError

    def expiry_epoch_ms(self) -> int:
        return -1

    def ensure_valid(self) -> None:
        exp = self.expiry_epoch_ms()
        if exp > 0 and int(time.time() * 1000) >= exp:
            raise RuntimeError(
                f"Upstox token expired at epoch ms {exp}; regenerate from Developer Apps"
            )

    def analytics_only(self) -> bool:
        return False


class UpstoxStaticTokenHolder(UpstoxTokenHolder):
    """Fixed JWT/static access token holder.

    Mirrors Trade_J ``UpstoxStaticTokenHolder``.
    """

    def __init__(
        self,
        token: str,
        *,
        analytics_only: bool = False,
        label: str = "Upstox token",
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        if not token or not token.strip():
            raise ValueError(f"{label} must not be blank")
        self._token = token
        self._expiry = JwtExpiry.parse_expiry_epoch_ms(token)
        if self._expiry <= 0:
            self._expiry = UpstoxTokenExpiry.next_expiry_epoch_ms()
        self._analytics_only = analytics_only
        self._label = label
        self._clock = clock

    def bearer_token(self) -> str:
        return self._token

    def expiry_epoch_ms(self) -> int:
        return self._expiry

    def analytics_only(self) -> bool:
        return self._analytics_only

    def ensure_valid(self) -> None:
        if self._expiry > 0 and self._clock() >= self._expiry:
            raise RuntimeError(f"{self._label} expired at epoch ms {self._expiry}")


class UpstoxAnalyticsTokenHolder(UpstoxTokenHolder):
    """Read-only analytics token (1-year, no OAuth refresh).

    Mirrors Trade_J ``UpstoxAnalyticsTokenHolder``.
    """

    def __init__(
        self,
        token: str,
        *,
        clock: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        if not token or not token.strip():
            raise ValueError("upstox analytics token is required when analyticsOnly=true")
        self._token = token
        self._expiry = JwtExpiry.parse_expiry_epoch_ms(token)
        self._clock = clock

    def bearer_token(self) -> str:
        return self._token

    def expiry_epoch_ms(self) -> int:
        return self._expiry

    def analytics_only(self) -> bool:
        return True

    def ensure_valid(self) -> None:
        if self._expiry > 0 and self._clock() >= self._expiry:
            raise RuntimeError(
                f"Upstox analytics token expired at epoch ms {self._expiry} — "
                "regenerate from Developer Apps → Analytics tab"
            )


class UpstoxExtendedTokenHolder(UpstoxTokenHolder):
    """Read-only extended token (1-year, no refresh, multi-client only).

    Mirrors Trade_J ``UpstoxTokenManager.UpstoxExtendedTokenHolder``.
    """

    def __init__(self, token: str) -> None:
        if not token or not token.strip():
            raise ValueError("upstox extended token is required")
        self._token = token
        self._expiry = JwtExpiry.parse_expiry_epoch_ms(token)

    def bearer_token(self) -> str:
        return self._token

    def expiry_epoch_ms(self) -> int:
        return self._expiry

    def analytics_only(self) -> bool:
        return True

    def ensure_valid(self) -> None:
        if self._expiry > 0 and int(time.time() * 1000) >= self._expiry:
            raise RuntimeError(
                f"Upstox extended token expired at epoch ms {self._expiry} — "
                "regenerate from Developer Apps → Analytics tab"
            )


class ThreadSafeTokenHolder(UpstoxTokenHolder):
    """Wraps any inner holder to provide a thread-safe ``bearer_token()``.

    UpstoxTokenManager uses this to atomically swap in webhook-delivered tokens
    while readers are calling ``bearer_token()`` on the WebSocket dispatch loop.
    """

    def __init__(self, inner: UpstoxTokenHolder) -> None:
        self._inner: UpstoxTokenHolder = inner
        self._lock = threading.RLock()

    def bearer_token(self) -> str:
        with self._lock:
            return self._inner.bearer_token()

    def expiry_epoch_ms(self) -> int:
        with self._lock:
            return self._inner.expiry_epoch_ms()

    def ensure_valid(self) -> None:
        with self._lock:
            self._inner.ensure_valid()

    def analytics_only(self) -> bool:
        with self._lock:
            return self._inner.analytics_only()

    def replace(self, new_inner: UpstoxTokenHolder) -> None:
        with self._lock:
            self._inner = new_inner
