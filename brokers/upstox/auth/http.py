"""Authenticated HTTP client for Upstox REST endpoints.

Mirrors Trade_J ``UpstoxHttpClient``: Bearer + optional ``X-Algo-Name`` header
injection. Stateless w.r.t. the algo name — supplied per call.

Now includes circuit breaker and retry patterns for resilience (RES-03, RES-04).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import requests

from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from brokers.common.resilience.rate_limiter import EndpointRateLimiter

from .config import UPSTOX_DEFAULT_RATE_PER_SECOND
from .exceptions import UpstoxApiError, UpstoxAuthError

logger = logging.getLogger(__name__)


def _categorize_upstox_url(url: str, method: str) -> str:
    """Return 'read', 'write', or 'admin' for Upstox REST URLs."""
    lower = url.lower()
    if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and "/order" in lower:
        return "write"
    if "/market-quote" in lower or "/market/" in lower or "/historical" in lower:
        return "read"
    if "/order" in lower and method.upper() == "GET":
        return "read"
    if "/portfolio" in lower or "/user/" in lower or "/login/" in lower:
        return "admin"
    return "admin"


# Backward-compat alias — use EndpointRateLimiter from common module
UpstoxRateLimiter = EndpointRateLimiter


class UpstoxHttpClient:
    """Small authenticated HTTP client for Upstox v2 / v3 / HFT endpoints."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        settings: Any,
        *,
        timeout_seconds: int = 15,
        session: requests.Session | None = None,
        rate_limiter: UpstoxRateLimiter | None = None,
        enable_circuit_breaker: bool = True,
        circuit_breaker: CircuitBreaker | None = None,
        read_circuit_breaker: CircuitBreaker | None = None,
        write_circuit_breaker: CircuitBreaker | None = None,
        admin_circuit_breaker: CircuitBreaker | None = None,
        on_auth_failure: Callable[[], bool] | None = None,
    ) -> None:
        self._token_provider = token_provider
        self._settings = settings
        self._on_auth_failure = on_auth_failure
        self._timeout_seconds = timeout_seconds
        self._rate_limiter = rate_limiter or UpstoxRateLimiter(
            rate_per_second=UPSTOX_DEFAULT_RATE_PER_SECOND,
        )
        if session is not None:
            self._session = session
        else:
            self._session = requests.Session()
            from requests.adapters import HTTPAdapter

            adapter = HTTPAdapter(
                pool_connections=getattr(settings, "pool_connections", 50),
                pool_maxsize=getattr(settings, "pool_maxsize", 100),
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

        # Resilience patterns (RES-03, RES-04)
        # Note: Retry is handled at the adapter/context level via RetryExecutor,
        # not in the HTTP client itself. See brokers.upstox.auth.context.
        self._enable_circuit_breaker = enable_circuit_breaker

        if enable_circuit_breaker:
            default_cb = circuit_breaker or CircuitBreaker(
                name="upstox_api",
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=3,
                    open_duration_ms=30_000,
                ),
            )
            self._circuit_breaker = default_cb
            self._read_circuit_breaker = read_circuit_breaker or CircuitBreaker(
                name="upstox_api_read",
                config=CircuitBreakerConfig(
                    failure_threshold=10,
                    success_threshold=3,
                    open_duration_ms=15_000,
                ),
            )
            self._write_circuit_breaker = write_circuit_breaker or CircuitBreaker(
                name="upstox_api_write",
                config=CircuitBreakerConfig(
                    failure_threshold=3,
                    success_threshold=2,
                    open_duration_ms=30_000,
                ),
            )
            self._admin_circuit_breaker = admin_circuit_breaker or CircuitBreaker(
                name="upstox_api_admin",
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=3,
                    open_duration_ms=30_000,
                ),
            )
        else:
            self._circuit_breaker = None
            self._read_circuit_breaker = None
            self._write_circuit_breaker = None
            self._admin_circuit_breaker = None

    @property
    def settings(self) -> Any:
        """Expose the underlying settings (algo_name, rest_base_url, etc.)."""
        return self._settings

    def _get_circuit_breaker(self, url: str, method: str) -> CircuitBreaker | None:
        if not self._enable_circuit_breaker:
            return None
        category = _categorize_upstox_url(url, method)
        if category == "read":
            return self._read_circuit_breaker
        if category == "write":
            return self._write_circuit_breaker
        return self._admin_circuit_breaker

    def _headers(self, algo_name: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token_provider()}",
        }
        algo = algo_name or getattr(self._settings, "algo_name", "")
        if algo:
            headers["X-Algo-Name"] = algo
        return headers

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(method="GET", url=url, params=params)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        algo_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            method="POST", url=url, json=payload, algo_name=algo_name, params=params
        )

    def put_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        algo_name: str | None = None,
    ) -> dict[str, Any]:
        return self._request(method="PUT", url=url, json=payload, algo_name=algo_name)

    def delete_json(
        self,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        algo_name: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            method="DELETE",
            url=url,
            json=payload,
            algo_name=algo_name,
            params=params,
        )

    def _request(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        algo_name: str | None = None,
    ) -> dict[str, Any]:
        # Circuit breaker: fail fast if circuit is open (category-specific)
        cb = self._get_circuit_breaker(url, method)
        if cb is not None:
            from brokers.common.resilience.circuit_breaker import CircuitState
            from brokers.common.resilience.errors import CircuitBreakerOpenError

            if cb.state == CircuitState.OPEN:
                logger.warning(
                    "Upstox API circuit breaker is open for %s %s",
                    method,
                    url,
                )
                raise CircuitBreakerOpenError(cb.name)

        try:
            result = self._execute_request(
                method=method,
                url=url,
                json=json,
                params=params,
                algo_name=algo_name,
            )
            if cb is not None:
                cb.on_success()
            return result
        except Exception:
            if cb is not None:
                cb.on_failure()
            raise

    def _execute_request(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        algo_name: str | None = None,
    ) -> dict[str, Any]:
        last_auth_error: UpstoxAuthError | None = None
        for attempt in (1, 2):
            # Rate limit by endpoint category
            if "/market-quote" in url or "/market/" in url:
                self._rate_limiter.acquire("market_data")
            elif "/order" in url:
                self._rate_limiter.acquire("order")
            elif "/portfolio" in url or "/user/" in url:
                self._rate_limiter.acquire("portfolio")
            else:
                self._rate_limiter.acquire("default")

            resp = self._session.request(
                method=method,
                url=url,
                json=json,
                params=params,
                timeout=self._timeout_seconds,
                headers=self._headers(algo_name=algo_name),
            )
            if resp.status_code >= 400:
                if resp.status_code in (401, 403):
                    last_auth_error = UpstoxAuthError(
                        f"Upstox API {method} {url} failed: HTTP {resp.status_code}",
                        resp.status_code,
                        resp.text,
                    )
                    if attempt == 1 and self._on_auth_failure is not None and self._on_auth_failure():
                        logger.info(
                            "Upstox HTTP retry after token refresh: %s %s",
                            method,
                            url,
                        )
                        continue
                    raise last_auth_error
                raise UpstoxApiError(
                    f"Upstox API {method} {url} failed: HTTP {resp.status_code}",
                    resp.status_code,
                    resp.text,
                )
            body = resp.json() if resp.text else {}
            if isinstance(body, dict) and str(body.get("status", "")).lower() in {
                "failure",
                "error",
            }:
                errors = body.get("errors")
                if isinstance(errors, list) and errors:
                    first = errors[0] if isinstance(errors[0], dict) else {}
                    message = first.get("message") or first.get("error")
                else:
                    message = (
                        body.get("message") or body.get("remarks") or "Upstox API returned failure"
                    )
                raise UpstoxApiError(str(message), resp.status_code, body)
            return body
        if last_auth_error is not None:
            raise last_auth_error
        raise UpstoxAuthError(f"Upstox API {method} {url} failed after auth retry")
