"""Base HTTP client — shared infrastructure for all broker REST adapters.

Provides a single ``BaseHttpClient`` that handles:
- Per-endpoint rate limiting (via ``RateLimitConfig``)
- Exponential backoff retry (500ms → 1s → 2s, capped at 5s)
- Token refresh on 401 (via ``token_refresh_fn`` callback)
- 429 rate-limit backoff (honours ``Retry-After`` header)
- Circuit breaker integration (via existing ``@circuit_breaker`` decorator)
- Request logging (via ``StructuredLogger``)

Broker-specific clients (``DhanHttpClient``, ``UpstoxHttpClient``) subclass
this and add endpoint methods (``place_order()``, ``get_ltp()``, etc.).

Usage::

    from brokers.infrastructure.http_client import BaseHttpClient
    from brokers.infrastructure.rate_config import dhan_rate_config

    client = BaseHttpClient(
        base_url="https://api.dhan.co/v2",
        headers={"client-id": "123", "access-token": "tok"},
        rate_config=dhan_rate_config(),
    )
    data = client.post("/orders", json={...})
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.rate_config import RateLimitConfig

logger = get_logger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT = 15.0
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BASE_DELAY_MS = 500
_DEFAULT_MAX_DELAY_MS = 5000


class HttpError(RuntimeError):
    """Raised on any HTTP failure that exhausts retries."""


class AuthenticationError(HttpError):
    """Raised when token refresh fails or 401 persists after refresh."""


class RateLimitError(HttpError):
    """Raised when the broker returns 429 and retries are exhausted."""


class BaseHttpClient:
    """Sync HTTP client with retry, rate limiting, and token refresh.

    Thread-safe: each request acquires per-endpoint throttle and a session lock.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        rate_config: RateLimitConfig | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        base_delay_ms: int = _DEFAULT_BASE_DELAY_MS,
        max_delay_ms: int = _DEFAULT_MAX_DELAY_MS,
        token_refresh_fn: Callable[[], str | None] | None = None,
        token_header_key: str = "access-token",
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._token_refresh_fn = token_refresh_fn
        self._token_header_key = token_header_key
        self._rate_config = rate_config or RateLimitConfig()

        self._session = session or requests.Session()
        self._session.headers.update(headers)

        self._last_request_time: dict[str, float] = {}
        self._adaptive_intervals: dict[str, float] = {}
        self._rate_lock = threading.Lock()
        self._last_refresh_time: float = 0.0
        self._refresh_cooldown: float = 60.0  # min seconds between refresh attempts

        # Circuit breaker state per category
        self._cb_failures: dict[str, int] = {"read": 0, "write": 0, "admin": 0}
        self._cb_last_failure: dict[str, float] = {"read": 0.0, "write": 0.0, "admin": 0.0}
        self._cb_state: dict[str, str] = {"read": "closed", "write": "closed", "admin": "closed"}
        self._cb_lock = threading.Lock()

        # Broker-specific identity (e.g. Dhan client_id) — set by subclass or factory
        self.client_id: str = ""

    # ── Public API ──────────────────────────────────────────────────────────

    def update_token(self, token: str) -> None:
        """Update the auth token in session headers."""
        self._session.headers[self._token_header_key] = token

    def get(self, endpoint: str) -> dict[str, Any]:
        return self._request("GET", endpoint)

    def post(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json)

    def put(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return self._request("PUT", endpoint, json=json)

    def delete(self, endpoint: str) -> dict[str, Any]:
        return self._request("DELETE", endpoint)

    def close(self) -> None:
        self._session.close()

    # ── Circuit breaker ─────────────────────────────────────────────────────

    def _cb_category(self, endpoint: str) -> str:
        return self._rate_config.categorize(endpoint)

    def _cb_check(self, category: str, reset_timeout: float = 30.0) -> bool:
        """Return True if request is allowed (circuit closed or half-open probe)."""
        with self._cb_lock:
            state = self._cb_state[category]
            if state == "closed":
                return True
            if state == "open":
                elapsed = time.monotonic() - self._cb_last_failure[category]
                if elapsed >= reset_timeout:
                    self._cb_state[category] = "half_open"
                    return True  # allow one probe
                return False
            # half_open — allow one probe
            return True

    def _cb_record_success(self, category: str) -> None:
        with self._cb_lock:
            self._cb_state[category] = "closed"
            self._cb_failures[category] = 0

    def _cb_record_failure(self, category: str, threshold: int = 5) -> None:
        with self._cb_lock:
            self._cb_failures[category] += 1
            self._cb_last_failure[category] = time.monotonic()
            if self._cb_state[category] == "half_open" or self._cb_failures[category] >= threshold:
                self._cb_state[category] = "open"

    @property
    def circuit_breaker_states(self) -> dict[str, str]:
        """Return current CB state per category (for observability)."""
        with self._cb_lock:
            return dict(self._cb_state)

    # ── Rate limiting ───────────────────────────────────────────────────────

    def _throttle(self, endpoint: str) -> None:
        """Sleep if needed to respect per-endpoint rate limits."""
        static_interval = self._rate_config.get_interval(endpoint)
        prefix = self._match_prefix(endpoint)
        adaptive_interval = self._adaptive_intervals.get(prefix, 0) if prefix else 0
        min_interval = max(static_interval, adaptive_interval)
        if min_interval <= 0:
            return
        with self._rate_lock:
            last = self._last_request_time.get(endpoint, 0.0)
            elapsed = time.monotonic() - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request_time[endpoint] = time.monotonic()

    def _match_prefix(self, endpoint: str) -> str | None:
        """Return the matching rate-limit prefix for endpoint, or None."""
        if endpoint in self._rate_config.limits:
            return endpoint
        for prefix in self._rate_config.limits:
            if endpoint.startswith(prefix):
                return prefix
        return None

    # ── Token refresh ───────────────────────────────────────────────────────

    def _try_refresh_token(self) -> bool:
        """Attempt token refresh. Returns True if successful."""
        now = time.monotonic()
        if now - self._last_refresh_time < self._refresh_cooldown:
            return False
        if self._token_refresh_fn is None:
            return False
        try:
            new_token = self._token_refresh_fn()
            if new_token:
                self._last_refresh_time = now
                self.update_token(new_token)
                logger.info("token_refreshed")
                return True
        except Exception as exc:
            logger.warning("token_refresh_failed", error=str(exc)[:200])
        return False

    # ── Core request loop ───────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
    ) -> dict[str, Any]:
        category = self._cb_category(endpoint)

        # Circuit breaker check
        if not self._cb_check(category):
            raise HttpError(f"Circuit breaker open: {method} {endpoint}")

        # Rate limit
        self._throttle(endpoint)

        url = f"{self._base_url}{endpoint}" if endpoint.startswith("/") else endpoint
        max_attempts = self._max_retries

        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._session.request(
                    method, url, json=json, timeout=self._timeout
                )
            except requests.RequestException as exc:
                self._cb_record_failure(category)
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        "http_retry",
                        method=method,
                        endpoint=endpoint,
                        attempt=attempt,
                        delay_ms=int(delay * 1000),
                    )
                    time.sleep(delay)
                    continue
                raise HttpError(f"Network error: {method} {url}: {exc}") from exc

            logger.debug(
                "http_response",
                method=method,
                endpoint=endpoint,
                status=resp.status_code,
            )

            # 401 — try token refresh once
            if resp.status_code == 401:
                if attempt == 1 and self._try_refresh_token():
                    continue
                raise AuthenticationError(
                    f"Token rejected: HTTP 401 on {method} {endpoint}"
                )

            # 429 — rate limited, back off
            if resp.status_code == 429:
                self._cb_record_failure(category)
                if attempt < max_attempts:
                    retry_after = self._parse_retry_after(resp)
                    if retry_after is not None:
                        prefix = self._match_prefix(endpoint)
                        if prefix:
                            self._adaptive_intervals[prefix] = max(
                                retry_after,
                                self._adaptive_intervals.get(prefix, 0),
                            )
                        delay = retry_after
                    else:
                        delay = self._backoff_delay(attempt)
                    logger.warning(
                        "http_rate_limited",
                        method=method,
                        endpoint=endpoint,
                        attempt=attempt,
                    )
                    time.sleep(delay)
                    continue
                raise RateLimitError(f"Rate limited: HTTP 429 on {method} {endpoint}")

            # 5xx — server error, retry
            if resp.status_code >= 500:
                self._cb_record_failure(category)
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        "http_server_error",
                        method=method,
                        endpoint=endpoint,
                        status=resp.status_code,
                        attempt=attempt,
                    )
                    time.sleep(delay)
                    continue
                raise HttpError(
                    f"Server error: HTTP {resp.status_code} on {method} {url}"
                )

            # 4xx — client error (non-401/429), raise immediately
            if resp.status_code >= 400:
                body = resp.text[:300]
                raise HttpError(
                    f"Client error: HTTP {resp.status_code} on {method} {url}: {body}"
                )

            # Success
            try:
                data = resp.json()
            except Exception as exc:
                raise HttpError(f"Invalid JSON from {method} {url}") from exc

            self._cb_record_success(category)
            return data  # type: ignore[no-any-return]

        raise HttpError(f"Request failed after {max_attempts} attempts: {method} {url}")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff: 500ms, 1s, 2s, 4s... capped at 5s."""
        delay_ms = min(
            self._base_delay_ms * (2 ** (attempt - 1)),
            self._max_delay_ms,
        )
        return delay_ms / 1000.0  # type: ignore[no-any-return]

    @staticmethod
    def _parse_retry_after(resp: Any) -> float | None:
        """Parse Retry-After header into seconds. Returns None if absent."""
        raw = resp.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return max(0.01, float(raw))
        except (ValueError, TypeError):
            return None


__all__ = [
    "BaseHttpClient",
    "HttpError",
    "AuthenticationError",
    "RateLimitError",
]
