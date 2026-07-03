"""Dhan HTTP client — REST API calls with resilience.

Integrates rate limiting, circuit breaker, retry, and 401 auto-refresh.
Thread-safe.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import requests

from brokers.adapters.dhan.config import (
    ENDPOINTS,
    RATE_LIMITS,
    READ_PREFIXES,
    WRITE_PREFIXES,
)
from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    RateLimitError,
)
from brokers.resilience.http_client import BaseResilientHttpClient, TokenRefreshSignal

logger = logging.getLogger(__name__)


class DhanHttpClient(BaseResilientHttpClient):
    """Dhan HTTP client with automatic token refresh on 401.

    Args:
        access_token: Initial access token.
        client_id: Dhan client ID.
        base_url: Base URL for API (auto-detected if empty).
        timeout: Request timeout in seconds.
        token_refresh_fn: Optional callable to refresh the token.
        refresh_lock: Optional shared lock to prevent concurrent refresh.
        refresh_cooldown_seconds: Minimum time between token refresh attempts.
        rate_limit_backoff_seconds: Backoff time when Dhan rate limits token generation.
    """

    _REFRESH_COOLDOWN_SECONDS = 60.0
    _RATE_LIMIT_BACKOFF_SECONDS = 130.0

    def __init__(
        self,
        access_token: str,
        client_id: str,
        base_url: str = "",
        timeout: float = 10.0,
        token_refresh_fn: Callable[[], str | None] | None = None,
        refresh_lock: threading.Lock | None = None,
        refresh_cooldown_seconds: float = _REFRESH_COOLDOWN_SECONDS,
        rate_limit_backoff_seconds: float = _RATE_LIMIT_BACKOFF_SECONDS,
    ):
        super().__init__(rate_limits=RATE_LIMITS, timeout=timeout)
        self._access_token = access_token
        self._client_id = client_id
        self._base_url = base_url or ENDPOINTS["orders"].rsplit("/orders", 1)[0]
        self._token_refresh_fn = token_refresh_fn
        self._refresh_lock = refresh_lock
        self._refresh_cooldown_seconds = refresh_cooldown_seconds
        self._rate_limit_backoff_seconds = rate_limit_backoff_seconds

        self._last_refresh_time: float = 0.0
        self._refresh_backoff_until: float = 0.0
        self._adaptive_intervals: dict[str, float] = {}

        self._session.headers.update(
            {
                "access-token": access_token,
                "client-id": client_id,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    @property
    def client_id(self) -> str:
        """Public accessor for client_id."""
        return self._client_id

    @property
    def access_token(self) -> str:
        """Public accessor for current access token."""
        return self._access_token

    def update_token(self, new_token: str) -> None:
        """Update the access token in session headers.

        Called by the token broadcast system when a refresh occurs.

        Args:
            new_token: The new access token.
        """
        self._access_token = new_token
        self._session.headers["access-token"] = new_token
        logger.debug("http_client_token_updated")

    def _categorize(self, endpoint: str) -> str:
        for prefix in READ_PREFIXES:
            if endpoint.startswith(prefix):
                return "read"
        for prefix in WRITE_PREFIXES:
            if endpoint.startswith(prefix):
                return "write"
        return "admin"

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        return f"{self._base_url}{endpoint}"

    def _handle_response(self, resp: requests.Response) -> dict:
        if resp.status_code == 401:
            if self._token_refresh_fn is not None:
                new_token = self._try_refresh_token()
                if new_token:
                    self.update_token(new_token)
                    raise TokenRefreshSignal("Token refreshed, retrying request")
            raise AuthenticationError("Token expired or invalid")

        if resp.status_code == 429:
            retry_after = self._parse_retry_after(resp)
            if retry_after is not None:
                prefix = self._match_prefix(resp.url)
                key = prefix or resp.url
                self._adaptive_intervals[key] = max(
                    retry_after, self._adaptive_intervals.get(key, 0)
                )
                logger.info(
                    "http_adaptive_rate_adjust",
                    extra={"endpoint": key, "retry_after_s": round(retry_after, 3)},
                )
            raise RateLimitError("Rate limit exceeded", retry_after=retry_after)

        if resp.status_code >= 500:
            try:
                body = resp.json()
                msg = body.get("remarks", {}).get("error_msg", resp.text)
            except Exception:
                msg = resp.text
            raise BrokerServerError(
                f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code)
            )

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = {}
            msg = body.get("remarks", {}).get("error_msg", resp.text)
            error_code = body.get("remarks", {}).get("errorCode", "")
            if self._is_token_error(resp.status_code, error_code, msg):
                if self._token_refresh_fn is not None:
                    new_token = self._try_refresh_token()
                    if new_token:
                        self.update_token(new_token)
                        raise TokenRefreshSignal("Token refreshed, retrying request")
                raise AuthenticationError(f"Token rejected: {msg}")
            raise BrokerError(
                f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code)
            )

        try:
            data = resp.json()
        except Exception:
            return {"data": resp.text}

        if isinstance(data, dict) and data.get("status") == "failure":
            remarks = data.get("remarks", "unknown error")
            raise BrokerError(f"API failure: {remarks}")

        return data

    def _match_prefix(self, url: str) -> str | None:
        """Return the matching rate limit prefix for a URL, or None."""
        for prefix in RATE_LIMITS:
            if prefix in url:
                return prefix
        return None

    @staticmethod
    def _parse_retry_after(resp: requests.Response) -> float:
        """Parse Retry-After header, defaulting to 30s."""
        try:
            val = resp.headers.get("Retry-After")
            if val is not None:
                return max(0.01, float(val))
        except (ValueError, TypeError):
            pass
        return 30.0

    @staticmethod
    def _is_token_error(status_code: int, error_code: str, message: str) -> bool:
        """Check if a 4xx response indicates a token/auth error."""
        if status_code == 401:
            return True
        token_error_codes = {"DH-906", "DH-808"}
        if error_code in token_error_codes:
            return True
        msg_lower = message.lower()
        if "invalid token" in msg_lower:
            return True
        return False

    def _try_refresh_token(self) -> str | None:
        """Attempt to refresh the token, using the shared lock if available.

        Implements exponential backoff when Dhan's rate limit is hit
        ("Token can be generated once every 2 minutes").

        Returns:
            New token if successful, None otherwise.
        """
        now = time.time()

        if now < self._refresh_backoff_until:
            remaining = self._refresh_backoff_until - now
            logger.debug(
                "token_refresh_backoff",
                extra={"remaining_seconds": round(remaining, 1)},
            )
            return None

        if now - self._last_refresh_time < self._refresh_cooldown_seconds:
            logger.debug("token_refresh_skipped", extra={"reason": "cooldown_active"})
            return None

        def _do_refresh() -> str | None:
            if self._refresh_lock is not None:
                acquired = self._refresh_lock.acquire(timeout=5.0)
                if not acquired:
                    logger.debug("token_refresh_lock_timeout")
                    return None
                try:
                    return self._token_refresh_fn() if self._token_refresh_fn else None
                finally:
                    self._refresh_lock.release()
            else:
                return self._token_refresh_fn() if self._token_refresh_fn else None

        try:
            new_token = _do_refresh()
            if new_token:
                self._last_refresh_time = now
                self._refresh_backoff_until = 0.0
                logger.info("token_refreshed", extra={"client_id": self._client_id})
                return new_token
            else:
                logger.warning(
                    "token_generation_failed", extra={"reason": "returned_none"}
                )
                self._refresh_backoff_until = now + self._rate_limit_backoff_seconds
                return None
        except Exception as exc:
            error_msg = str(exc)
            if "once every 2 minutes" in error_msg or "rate limit" in error_msg.lower():
                logger.warning(
                    "dhan_token_rate_limit",
                    extra={"backoff_seconds": self._rate_limit_backoff_seconds},
                )
                self._refresh_backoff_until = now + self._rate_limit_backoff_seconds
            else:
                logger.warning("token_refresh_failed", extra={"error": error_msg})
            return None
