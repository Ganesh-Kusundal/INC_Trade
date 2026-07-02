"""Sync HTTP client for Dhan REST API with token refresh, retry, and logging."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitState
from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter
from brokers.dhan.config import DhanResilienceConfig, DEFAULT_CONFIG
from brokers.dhan.exceptions import AuthenticationError, DhanError, RateLimitError
from brokers.dhan.metrics import (
    dhan_errors_total,
    dhan_request_duration_seconds,
    dhan_request_total,
)
from brokers.dhan.resilience.rate_limiter import DhanRateLimiterMetrics
from config.endpoints import Dhan

logger = logging.getLogger(__name__)

# Default base URL — imported from central endpoint registry.
_DEFAULT_BASE_URL = Dhan.REST_BASE

# Default configuration - kept for backwards compatibility
# When no config is provided, these defaults are used
_DEFAULT_RESILIENCE_CONFIG = DEFAULT_CONFIG

# Legacy constants - kept for backwards compatibility with existing code
# These are now derived from DEFAULT_CONFIG but can be overridden
_RATE_LIMITS = DEFAULT_CONFIG.rate_limit.limits
_MAX_RETRIES = DEFAULT_CONFIG.retry.max_retries
_BASE_DELAY_MS = DEFAULT_CONFIG.retry.base_delay_ms
_MAX_DELAY_MS = DEFAULT_CONFIG.retry.max_delay_ms
_REFRESH_COOLDOWN_SECONDS = DEFAULT_CONFIG.token.refresh_cooldown_seconds
_RATE_LIMIT_BACKOFF_SECONDS = DEFAULT_CONFIG.token.rate_limit_backoff_seconds


# ── Endpoint categorization for circuit-breaker isolation (A1) ────────────
#
# Previously a single `CircuitBreaker("dhan-api")` protected every endpoint.
# That meant a storm of failed historical-data reads (or option-chain calls)
# would OPEN the breaker and block order placement. Phase A / A1 splits the
# breaker into three categories so a failure in one class cannot take down
# another:
#
#   READ   — market data; no user state change.  Most bursty, most likely
#            to hit rate limits; failure here must NOT block orders.
#   WRITE  — order placement, modification, cancellation. User money is on
#            the line. The most sensitive category; opened quickly.
#   ADMIN  — account state queries (positions/holdings/funds/orderbook/
#            tradebook), broker auth (token refresh), kill switch. Default
#            category for unrecognised endpoints.
#
# Endpoints are matched by `endpoint.startswith(prefix)` so `/charts/historical`
# matches the prefix `/charts/`. Unknown endpoints default to ADMIN.
# These are now derived from DEFAULT_CONFIG but kept for backwards compatibility
_READ_CB_PREFIXES = DEFAULT_CONFIG.circuit_breaker.read_prefixes
_WRITE_CB_PREFIXES = DEFAULT_CONFIG.circuit_breaker.write_prefixes
# Note: /traderbook and /trades are intentionally NOT in the write list.
# They are account-state reads; the categorization defaults them to
# "admin" so they share the admin CB with /positions, /holdings,
# /fundlimit, /traderbook. This keeps the orderbook failure mode
# isolated from order placement.


def _categorize_endpoint(endpoint: str, config: DhanResilienceConfig | None = None) -> str:
    """Return one of 'read', 'write', or 'admin' for an endpoint path.

    Used by ``DhanHttpClient._get_circuit_breaker`` to route failures to
    the category-specific circuit breaker.

    Args:
        endpoint: The API endpoint path.
        config: Optional configuration to use. If None, uses DEFAULT_CONFIG.
    """
    if config is None:
        config = DEFAULT_CONFIG
    
    for prefix in config.circuit_breaker.write_prefixes:
        if endpoint.startswith(prefix):
            return "write"
    for prefix in config.circuit_breaker.read_prefixes:
        if endpoint.startswith(prefix):
            return "read"
    return "admin"


# Circuit-breaker categories (read/write/admin) differ from token-bucket
# names (market_data/orders/admin). Map before acquire().
# Derived from DEFAULT_CONFIG for backwards compatibility
_RL_BUCKET_MAP = DEFAULT_CONFIG.rate_limit.bucket_map


def _rate_limit_bucket(endpoint: str, config: DhanResilienceConfig | None = None) -> str:
    """Return the MultiBucketRateLimiter category for *endpoint*.

    Args:
        endpoint: The API endpoint path.
        config: Optional configuration to use. If None, uses DEFAULT_CONFIG.
    """
    if config is None:
        config = DEFAULT_CONFIG
    category = _categorize_endpoint(endpoint, config)
    return config.rate_limit.bucket_map.get(category, "admin")


class DhanHttpClient:
    """Sync HTTP client with auth injection, token refresh, retry, and rate limiting."""

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
        session: requests.Session | None = None,
        # Standardized resilience parameters (from Dhan resilience package)
        _rate_limiter: MultiBucketRateLimiter | None = None,
        _circuit_breakers: dict[str, CircuitBreaker] | None = None,
        # Configuration: if provided, overrides hardcoded defaults
        config: DhanResilienceConfig | None = None,
    ) -> None:
        self.client_id = client_id
        self.access_token = access_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._token_refresh_fn = token_refresh_fn
        self._enable_retry = enable_retry
        
        # Store the configuration
        self._config = config if config is not None else DEFAULT_CONFIG
        
        # Backwards-compat: a single ``circuit_breaker`` is used for any
        # category whose specific CB was not provided. This keeps every
        # existing test fixture working unchanged.
        self._circuit_breaker = circuit_breaker
        self._read_circuit_breaker = read_circuit_breaker or circuit_breaker
        self._write_circuit_breaker = write_circuit_breaker or circuit_breaker
        self._admin_circuit_breaker = admin_circuit_breaker or circuit_breaker

        # Standardized resilience patterns (Task 6.2)
        # _rate_limiter: Token bucket rate limiter from Dhan resilience package
        self._rate_limiter = _rate_limiter
        # _circuit_breakers: Dict of all circuit breakers for observability
        # Keys: 'orders', 'market_data', 'portfolio', 'admin'
        self._circuit_breakers = _circuit_breakers or {}
        # Metrics collector for rate limiter observability
        self._rate_metrics = DhanRateLimiterMetrics()

        # Use provided session (from connection pool) or create own
        if session is not None:
            self._session = session
        else:
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                }
            )

        self._session.headers.update(
            {
                "client-id": client_id,
                "access-token": access_token,
            }
        )
        self._last_request_time: dict[str, float] = {}
        self._adaptive_intervals: dict[str, float] = {}
        self._rate_lock = threading.Lock()
        self._last_refresh_time: float = 0.0

    def _get_circuit_breaker(self, endpoint: str) -> CircuitBreaker | None:
        """Return the circuit breaker that protects ``endpoint``.

        Routes to the category-specific CB if one was supplied;
        otherwise falls back to the single ``circuit_breaker`` argument
        (backwards-compat path).
        """
        category = _categorize_endpoint(endpoint, self._config)
        if category == "read":
            return self._read_circuit_breaker
        if category == "write":
            return self._write_circuit_breaker
        return self._admin_circuit_breaker

    def update_token(self, access_token: str) -> None:
        self.access_token = access_token
        self._session.headers["access-token"] = access_token

    def post(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json)

    def get(self, endpoint: str) -> dict[str, Any]:
        return self._request("GET", endpoint)

    def put(self, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        return self._request("PUT", endpoint, json=json)

    def delete(self, endpoint: str) -> dict[str, Any]:
        return self._request("DELETE", endpoint)

    def _throttle(self, endpoint: str) -> None:
        # Use config-based rate limits
        static_interval = self._match_rate_limit(endpoint, self._config.rate_limit.limits)
        adaptive_interval = self._match_rate_limit(endpoint, self._adaptive_intervals)
        min_interval = max(static_interval, adaptive_interval)
        if min_interval <= 0:
            return
        with self._rate_lock:
            last = self._last_request_time.get(endpoint, 0.0)
            elapsed = time.time() - last
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            self._last_request_time[endpoint] = time.time()

    def _acquire_rate_limit_token(self, endpoint: str, timeout: float = 5.0) -> bool:
        """Acquire a rate limit token if rate limiter is configured.

        Uses the token bucket rate limiter from the Dhan resilience package.
        Falls back to allowing the request if no rate limiter is configured.

        Args:
            endpoint: The API endpoint being called.
            timeout: Maximum time to wait for a token (seconds).

        Returns:
            True if token acquired or no rate limiter, False if timed out.
        """
        if self._rate_limiter is None:
            return True  # No rate limiter configured, allow request

        category = _rate_limit_bucket(endpoint, self._config)
        try:
            acquired = self._rate_limiter.acquire(category, tokens=1, timeout=timeout)
            if acquired:
                self._rate_metrics.record_request(category)
            else:
                self._rate_metrics.record_rejection(category)
                logger.warning(
                    "rate_limit_timeout",
                    extra={
                        "endpoint": endpoint,
                        "category": category,
                        "timeout_s": timeout,
                    },
                )
            return acquired
        except ValueError as exc:
            # Unknown category — allow request but log warning
            logger.warning(
                "rate_limit_unknown_category",
                extra={"endpoint": endpoint, "category": category, "error": str(exc)},
            )
            return True

    @staticmethod
    def _match_rate_limit(endpoint: str, limits: dict[str, float]) -> float:
        """Match endpoint against rate limit keys using prefix matching."""
        if endpoint in limits:
            return limits[endpoint]
        for prefix, interval in limits.items():
            if endpoint.startswith(prefix):
                return interval
        return 0

    @staticmethod
    def _match_prefix(endpoint: str, limits: dict[str, float]) -> str | None:
        """Return the matching prefix key for endpoint, or None."""
        if endpoint in limits:
            return endpoint
        for prefix in limits:
            if endpoint.startswith(prefix):
                return prefix
        return None

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

    def _try_refresh_token(self) -> bool:
        """Attempt token refresh. Returns True if successful.

        Implements exponential backoff when Dhan's rate limit is hit
        ("Token can be generated once every 2 minutes").
        """
        now = time.time()

        # Check if we're in backoff period due to rate limiting
        if hasattr(self, "_refresh_backoff_until") and now < self._refresh_backoff_until:
            remaining = self._refresh_backoff_until - now
            logger.debug("token_refresh_backoff", extra={"remaining_seconds": round(remaining, 1)})
            return False

        # Standard cooldown check
        if now - self._last_refresh_time < self._config.token.refresh_cooldown_seconds:
            logger.debug("token_refresh_skipped", extra={"reason": "cooldown_active"})
            return False

        if self._token_refresh_fn is None:
            return False
        try:
            new_token = self._token_refresh_fn()
            if new_token:
                self._last_refresh_time = now
                self.update_token(new_token)
                # Clear any backoff state on success
                if hasattr(self, "_refresh_backoff_until"):
                    delattr(self, "_refresh_backoff_until")
                logger.info("token_refreshed", extra={"client_id": self.client_id})
                return True
            else:
                # Token generation returned None - likely rate limited
                # Check response body for rate limit message
                logger.warning("token_generation_failed", extra={"reason": "returned_none"})
                # Set backoff to prevent rapid retries
                self._refresh_backoff_until = now + self._config.token.rate_limit_backoff_seconds
                return False
        except Exception as exc:
            error_msg = str(exc)
            # Detect Dhan's rate limit error
            if "once every 2 minutes" in error_msg or "rate limit" in error_msg.lower():
                logger.warning(
                    "dhan_token_rate_limit", 
                    extra={"backoff_seconds": self._config.token.rate_limit_backoff_seconds}
                )
                self._refresh_backoff_until = now + self._config.token.rate_limit_backoff_seconds
            else:
                logger.warning("token_refresh_failed", extra={"error": error_msg})
        return False

    def _send_raw_http(self, method: str, url: str, json: dict | None) -> requests.Response:
        """Execute a single HTTP request and convert network errors to DhanError.

        This is a thin wrapper around ``session.request`` that:
        * Records circuit-breaker failures on network errors.
        * Converts ``requests.RequestException`` → ``DhanError`` so callers
          only need to catch one exception type.

        All retry logic (network-level, application-level) lives in the
        outer ``_request`` loop — this method performs exactly **one**
        HTTP attempt.

        Raises:
            DhanError: On any network failure.
            requests.Response: On successful HTTP exchange (any status code).
        """
        cb = self._get_circuit_breaker(
            url.replace(self._base_url, "") if url.startswith(self._base_url) else url
        )
        try:
            return self._session.request(method, url, json=json, timeout=self._timeout)
        except requests.RequestException as exc:
            if cb:
                cb.on_failure()
            raise DhanError(f"HTTP {method} {url} failed: {exc}") from exc

    def _request(self, method: str, endpoint: str, json: dict | None = None) -> dict[str, Any]:
        # Circuit breaker check — fast-fail if the category-specific
        # breaker for this endpoint is OPEN. The split (read / write /
        # admin) is what stops a read-side failure storm from blocking
        # order placement. See PRODUCTION_CERTIFICATION_REPORT §B1.
        cb = self._get_circuit_breaker(endpoint)
        if cb and cb.state == CircuitState.OPEN and not cb.allow_request():
            raise DhanError(f"Circuit breaker open: {method} {endpoint}")

        # Rate limit token acquisition (enforced, not just defined)
        if not self._acquire_rate_limit_token(endpoint):
            raise DhanError(f"Rate limit timeout: {method} {endpoint}")

        self._throttle(endpoint)
        url = f"{self._base_url}{endpoint}" if endpoint.startswith("/") else endpoint

        max_attempts = self._config.retry.max_retries if self._enable_retry else 1
        last_exc: Exception | None = None

        _start = time.monotonic()
        dhan_request_total.inc()
        try:
          for attempt in range(1, max_attempts + 1):
            try:
                # Always route through _send_raw_http so that
                # requests.RequestException is converted to DhanError
                # regardless of whether retry is enabled.  The outer
                # loop owns all retry logic (network + application).
                resp = self._send_raw_http(method, url, json)
            except DhanError as exc:
                last_exc = exc
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
                    logger.warning(
                        "http_retry",
                        extra={
                            "method": method,
                            "endpoint": endpoint,
                            "attempt": attempt,
                            "delay_ms": int(delay * 1000),
                        },
                    )
                    time.sleep(delay)
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
                if attempt == 1 and self._try_refresh_token():
                    logger.info(
                        "http_retry_after_refresh", extra={"method": method, "endpoint": endpoint}
                    )
                    continue  # retry with new token
                raise AuthenticationError(f"Token rejected: HTTP 401 on {method} {endpoint}")

            # 429 — rate limited, back off and retry
            if resp.status_code == 429:
                if attempt < max_attempts:
                    retry_after = self._parse_retry_after(resp)
                    if retry_after is not None:
                        delay = retry_after
                        prefix = self._match_prefix(endpoint, self._config.rate_limit.limits)
                        key = prefix or endpoint
                        self._adaptive_intervals[key] = max(
                            delay, self._adaptive_intervals.get(key, 0)
                        )
                        logger.info(
                            "http_adaptive_rate_adjust",
                            extra={
                                "endpoint": key,
                                "retry_after_s": round(delay, 3),
                            },
                        )
                    else:
                        delay = self._backoff_delay(attempt)
                    logger.warning(
                        "http_rate_limited_retry",
                        extra={
                            "method": method,
                            "endpoint": endpoint,
                            "attempt": attempt,
                            "delay_ms": int(delay * 1000),
                        },
                    )
                    time.sleep(delay)
                    continue
                raise RateLimitError(f"Rate limited: HTTP 429 on {method} {endpoint}")

            # 5xx — server error, retry
            if resp.status_code >= 500:
                if cb:
                    cb.on_failure()
                if attempt < max_attempts:
                    delay = self._backoff_delay(attempt)
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
                    time.sleep(delay)
                    continue
                body = resp.text[:200]
                raise DhanError(f"Dhan API {method} {url} failed: HTTP {resp.status_code} — {body}")

            # 4xx — check for Dhan-specific token errors (DH-906/DH-808 returned as 400)
            if resp.status_code >= 400:
                body = resp.text[:300]
                # Dhan returns invalid token as HTTP 400 with DH-906 or DH-808
                if resp.status_code == 400 and (
                    "DH-906" in body or "DH-808" in body or "Invalid Token" in body
                ):
                    if attempt == 1 and self._try_refresh_token():
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

            # Success
            try:
                data = resp.json()
            except Exception as exc:
                raise DhanError(f"Invalid JSON from {method} {url}") from exc

            if isinstance(data, dict) and data.get("status") == "failure":
                remarks = data.get("remarks", "unknown error")
                if cb:
                    cb.on_failure()
                raise DhanError(f"API failure: {remarks}")

            if cb:
                cb.on_success()
            return data

          # Should not reach here, but just in case
          if last_exc:
              raise last_exc
          raise DhanError(f"Request failed after {max_attempts} attempts: {method} {url}")
        except Exception:
            dhan_errors_total.inc()
            raise
        finally:
            dhan_request_duration_seconds.observe(time.monotonic() - _start)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff: 500ms, 1s, 2s, 4s... capped at 5s."""
        delay_ms = min(
            self._config.retry.base_delay_ms * (2 ** (attempt - 1)), 
            self._config.retry.max_delay_ms
        )
        return delay_ms / 1000.0

    def close(self) -> None:
        self._session.close()
