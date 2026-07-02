"""DhanAsyncHttpClient — async HTTP client for Dhan REST API with non-blocking I/O.

Uses ``httpx.AsyncClient`` instead of the synchronous ``requests.Session`` used
by :class:`~brokers.dhan.http_client.DhanHttpClient`.  All retry back-offs and
rate-limit waits use ``asyncio.sleep()`` so they never block the event loop.

Intended for event-loop-based composition roots and async workflows that need
to issue Dhan API calls without tying up a thread-pool worker.

Usage::

    from brokers.dhan.async_http_client import DhanAsyncHttpClient

    async with DhanAsyncHttpClient(
        client_id="...",
        access_token="...",
    ) as client:
        data = await client.get("/fundlimit")
        resp = await client.post("/orders", json={...})

Design
------
Mirrors the sync :class:`DhanHttpClient` interface and shares its:
- Endpoint categorization (read / write / admin circuit breakers)
- Rate limit profiles and token-bucket throttling
- Token refresh via callable
- Prometheus metrics

The only difference is that all blocking calls (``time.sleep()``) are replaced
with ``asyncio.sleep()`` and the HTTP transport uses ``httpx.AsyncClient``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx

from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitState
from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter
from brokers.dhan.exceptions import AuthenticationError, DhanError, RateLimitError
from brokers.dhan.metrics import (
    dhan_errors_total,
    dhan_request_duration_seconds,
    dhan_request_total,
)
from brokers.dhan.http_client import (
    _BACKOFF_DELAY,
    _MAX_DELAY_MS,
    _MAX_RETRIES,
    _RATE_LIMIT_BACKOFF_SECONDS,
    _REFRESH_COOLDOWN_SECONDS,
    _categorize_endpoint,
    _rate_limit_bucket,
)
from brokers.dhan.http_client import _match_rate_limit as _match_static_rate_limit
from brokers.dhan.http_client import _parse_retry_after
from config.endpoints import Dhan

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = Dhan.REST_BASE


class DhanAsyncHttpClient:
    """Async HTTP client with auth injection, token refresh, retry, and rate limiting.

    Designed as an async drop-in for :class:`DhanHttpClient` in event-loop-based
    composition roots.  Shares the same endpoint categorization, rate-limit
    buckets, and circuit-breaker configuration.

    Use as an async context manager to ensure the underlying ``httpx.AsyncClient``
    is properly closed::

        async with DhanAsyncHttpClient(client_id="...", access_token="...") as client:
            ...

    Or call ``await client.aclose()`` explicitly.
    """

    def __init__(
        self,
        client_id: str,
        access_token: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 15.0,
        token_refresh_fn: Callable[[], str] | None = None,
        enable_retry: bool = True,
        circuit_breaker: CircuitBreaker | None = None,
        read_circuit_breaker: CircuitBreaker | None = None,
        write_circuit_breaker: CircuitBreaker | None = None,
        admin_circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: MultiBucketRateLimiter | None = None,
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
    ):
        self.client_id = client_id
        self.access_token = access_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._token_refresh_fn = token_refresh_fn
        self._enable_retry = enable_retry

        # Circuit breakers — same category split as sync client
        self._circuit_breaker = circuit_breaker
        self._read_circuit_breaker = read_circuit_breaker or circuit_breaker
        self._write_circuit_breaker = write_circuit_breaker or circuit_breaker
        self._admin_circuit_breaker = admin_circuit_breaker or circuit_breaker

        # Rate limiter — uses async acquire
        self._rate_limiter = rate_limiter
        self._circuit_breakers = circuit_breakers or {}

        # HTTP client — created lazily so the context manager is optional
        self._client: httpx.AsyncClient | None = None

        # Per-endpoint adaptive intervals (updated on 429)
        self._adaptive_intervals: dict[str, float] = {}

        self._last_refresh_time: float = 0.0
        self._refresh_backoff_until: float = 0.0

    # ── Context manager support ──────────────────────────────────────────

    async def __aenter__(self) -> DhanAsyncHttpClient:
        self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        """Create the underlying AsyncClient if it does not exist yet."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "client-id": self.client_id,
                    "access-token": self.access_token,
                },
            )
        return self._client

    # ── Token management ─────────────────────────────────────────────────

    def update_token(self, access_token: str) -> None:
        """Update the access token used for API authentication."""
        self.access_token = access_token
        if self._client is not None:
            self._client.headers["access-token"] = access_token

    # ── HTTP method shortcuts ────────────────────────────────────────────

    async def post(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return await self._request("POST", endpoint, json=json)

    async def get(self, endpoint: str) -> dict[str, Any]:
        return await self._request("GET", endpoint)

    async def put(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return await self._request("PUT", endpoint, json=json)

    async def delete(self, endpoint: str) -> dict[str, Any]:
        return await self._request("DELETE", endpoint)

    # ── Core request pipeline ────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with circuit-breaker, rate-limiter, and retry."""
        client = self._ensure_client()

        # Circuit breaker check — fast-fail if the category-specific
        # breaker for this endpoint is OPEN.
        cb = self._get_circuit_breaker(endpoint)
        if cb is not None and cb.state == CircuitState.OPEN and not cb.allow_request():
            raise DhanError(f"Circuit breaker open: {method} {endpoint}")

        # Rate limit token acquisition (async)
        if not await self._acquire_rate_limit_token(endpoint):
            raise DhanError(f"Rate limit timeout: {method} {endpoint}")

        # Throttle — wait for per-endpoint minimum interval
        await self._throttle(endpoint)

        url = f"{self._base_url}{endpoint}" if endpoint.startswith("/") else endpoint
        max_attempts = _MAX_RETRIES if self._enable_retry else 1
        last_exc: Exception | None = None

        _start = __import__("time").monotonic()
        dhan_request_total.inc()
        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await self._send_raw_http(method, url, json)
                except DhanError as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        delay = _backoff_delay(attempt)
                        logger.warning(
                            "http_retry",
                            extra={
                                "method": method,
                                "endpoint": endpoint,
                                "attempt": attempt,
                                "delay_ms": int(delay * 1000),
                            },
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise last_exc

                logger.debug(
                    "http_response",
                    extra={
                        "method": method,
                        "endpoint": endpoint,
                        "status": resp.status_code,
                    },
                )

                # 401 — try token refresh
                if resp.status_code == 401:
                    if attempt == 1 and await self._try_refresh_token():
                        logger.info(
                            "http_retry_after_refresh",
                            extra={"method": method, "endpoint": endpoint},
                        )
                        continue
                    raise AuthenticationError(f"Token rejected: HTTP 401 on {method} {endpoint}")

                # 429 — rate limited, back off and retry
                if resp.status_code == 429:
                    if attempt < max_attempts:
                        retry_after = _parse_retry_after(resp)
                        if retry_after is not None:
                            delay = retry_after
                            prefix = _match_prefix(endpoint)
                            key = prefix or endpoint
                            self._adaptive_intervals[key] = max(
                                delay, self._adaptive_intervals.get(key, 0)
                            )
                            logger.info(
                                "http_adaptive_rate_adjust",
                                extra={"endpoint": key, "retry_after_s": round(delay, 3)},
                            )
                        else:
                            delay = _backoff_delay(attempt)
                        logger.warning(
                            "http_rate_limited_retry",
                            extra={
                                "method": method,
                                "endpoint": endpoint,
                                "attempt": attempt,
                                "delay_ms": int(delay * 1000),
                            },
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise RateLimitError(f"Rate limited: HTTP 429 on {method} {endpoint}")

                # 5xx — server error, retry
                if resp.status_code >= 500:
                    if cb is not None:
                        cb.on_failure()
                    if attempt < max_attempts:
                        delay = _backoff_delay(attempt)
                        logger.warning(
                            "http_server_error_retry",
                            extra={
                                "method": method,
                                "endpoint": endpoint,
                                "status": resp.status_code,
                                "attempt": attempt,
                                "delay_ms": int(delay * 1000),
                            },
                        )
                        await asyncio.sleep(delay)
                        continue
                    body = resp.text[:200]
                    raise DhanError(f"Dhan API {method} {url} failed: HTTP {resp.status_code} — {body}")

                # 4xx — check for Dhan-specific token errors (DH-906/DH-808 returned as 400)
                if resp.status_code >= 400:
                    body = resp.text[:300]
                    if resp.status_code == 400 and (
                        "DH-906" in body or "DH-808" in body or "Invalid Token" in body
                    ):
                        if attempt == 1 and await self._try_refresh_token():
                            logger.info(
                                "http_retry_after_token_refresh",
                                extra={"method": method, "endpoint": endpoint},
                            )
                            continue
                        raise AuthenticationError(f"Token rejected: DH-906 on {method} {endpoint}")
                    logger.warning(
                        "http_client_error",
                        extra={
                            "method": method,
                            "endpoint": endpoint,
                            "status": resp.status_code,
                            "body": body,
                        },
                    )
                    raise DhanError(f"Dhan API {method} {url} failed: HTTP {resp.status_code} — {body}")

                # Success path
                try:
                    data = resp.json()
                except Exception as exc:
                    raise DhanError(f"Invalid JSON from {method} {url}") from exc

                if isinstance(data, dict) and data.get("status") == "failure":
                    remarks = data.get("remarks", "unknown error")
                    if cb is not None:
                        cb.on_failure()
                    raise DhanError(f"API failure: {remarks}")

                if cb is not None:
                    cb.on_success()
                return data

            if last_exc:
                raise last_exc
            raise DhanError(f"Request failed after {max_attempts} attempts: {method} {url}")
        except Exception:
            dhan_errors_total.inc()
            raise
        finally:
            dhan_request_duration_seconds.observe(__import__("time").monotonic() - _start)

    async def _send_raw_http(
        self,
        method: str,
        url: str,
        json: dict | None,
    ) -> httpx.Response:
        """Execute a single HTTP request.  Converts network errors to DhanError."""
        cb = self._get_circuit_breaker(
            url.replace(self._base_url, "") if url.startswith(self._base_url) else url
        )
        try:
            client = self._ensure_client()
            return await client.request(method, url, json=json)
        except httpx.HTTPError as exc:
            if cb is not None:
                cb.on_failure()
            raise DhanError(f"HTTP {method} {url} failed: {exc}") from exc

    # ── Rate limiting ────────────────────────────────────────────────────

    async def _throttle(self, endpoint: str) -> None:
        """Wait for the per-endpoint minimum interval."""
        static_interval = _match_static_rate_limit(endpoint)
        adaptive_interval = self._adaptive_intervals.get(endpoint, 0.0)
        min_interval = max(static_interval, adaptive_interval)
        if min_interval > 0:
            await asyncio.sleep(min_interval)

    async def _acquire_rate_limit_token(self, endpoint: str, timeout: float = 5.0) -> bool:
        """Acquire a rate limit token from the token bucket (async)."""
        if self._rate_limiter is None:
            return True
        category = _rate_limit_bucket(endpoint)
        try:
            return await self._rate_limiter.acquire_async(category, tokens=1, timeout=timeout)
        except ValueError:
            return True

    # ── Token refresh ────────────────────────────────────────────────────

    async def _try_refresh_token(self) -> bool:
        """Attempt token refresh.  Returns True on success."""
        now = __import__("time").time()

        if now < self._refresh_backoff_until:
            return False
        if now - self._last_refresh_time < _REFRESH_COOLDOWN_SECONDS:
            return False
        if self._token_refresh_fn is None:
            return False

        try:
            new_token = self._token_refresh_fn()
            if new_token:
                self._last_refresh_time = now
                self.update_token(new_token)
                self._refresh_backoff_until = 0.0
                logger.info("token_refreshed", extra={"client_id": self.client_id})
                return True
            else:
                self._refresh_backoff_until = now + _RATE_LIMIT_BACKOFF_SECONDS
                return False
        except Exception as exc:
            error_msg = str(exc)
            if "once every 2 minutes" in error_msg or "rate limit" in error_msg.lower():
                self._refresh_backoff_until = now + _RATE_LIMIT_BACKOFF_SECONDS
            else:
                logger.warning("token_refresh_failed", extra={"error": error_msg})
            return False

    # ── Circuit breaker routing ──────────────────────────────────────────

    def _get_circuit_breaker(self, endpoint: str) -> CircuitBreaker | None:
        """Return the circuit breaker for the given endpoint's category."""
        category = _categorize_endpoint(endpoint)
        if category == "read":
            return self._read_circuit_breaker
        elif category == "write":
            return self._write_circuit_breaker
        return self._admin_circuit_breaker

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ── Shared helpers (reused from sync client or inlined) ────────────────


def _match_prefix(endpoint: str) -> str | None:
    """Return the matching rate-limit prefix key for endpoint, or None."""
    from brokers.dhan.http_client import _RATE_LIMITS
    if endpoint in _RATE_LIMITS:
        return endpoint
    for prefix in _RATE_LIMITS:
        if endpoint.startswith(prefix):
            return prefix
    return None


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff: 500ms, 1s, 2s, 4s... capped at 5s."""
    from brokers.dhan.http_client import _BASE_DELAY_MS
    delay_ms = min(_BASE_DELAY_MS * (2 ** (attempt - 1)), _MAX_DELAY_MS)
    return delay_ms / 1000.0
