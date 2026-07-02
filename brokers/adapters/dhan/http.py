"""Dhan HTTP client — REST API calls with resilience.

Integrates rate limiting, circuit breaker, and retry into every HTTP call.
Thread-safe.
"""

from __future__ import annotations

import logging
from typing import Any

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
    RateLimitError,
)
from brokers.resilience import (
    CircuitBreaker,
    RetryPolicy,
    TokenBucketRateLimiter,
)

logger = logging.getLogger(__name__)


def _categorize(endpoint: str) -> str:
    for prefix in READ_PREFIXES:
        if endpoint.startswith(prefix):
            return "read"
    for prefix in WRITE_PREFIXES:
        if endpoint.startswith(prefix):
            return "write"
    return "admin"


class DhanHttpClient:
    def __init__(
        self,
        access_token: str,
        client_id: str,
        base_url: str = "",
        timeout: float = 10.0,
    ):
        self._access_token = access_token
        self._client_id = client_id
        self._base_url = base_url or ENDPOINTS["orders"].rsplit("/orders", 1)[0]
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "access-token": access_token,
                "client-id": client_id,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

        self._rate_limiters: dict[str, TokenBucketRateLimiter] = {}
        for endpoint, rate in RATE_LIMITS.items():
            self._rate_limiters[endpoint] = TokenBucketRateLimiter(
                rate_per_second=rate, capacity=max(int(rate), 1)
            )

        self._circuit_breakers = {
            "read": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0),
            "write": CircuitBreaker(failure_threshold=3, recovery_timeout=60.0),
            "admin": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0),
        }

        self._retry = RetryPolicy(max_retries=3, base_delay_ms=500, max_delay_ms=5000)

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json: dict | None = None) -> dict:
        return self._request("POST", endpoint, json=json)

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict:
        category = _categorize(endpoint)
        cb = self._circuit_breakers[category]

        self._apply_rate_limit(endpoint)

        def _do_request() -> dict:
            url = (
                f"{self._base_url}{endpoint}"
                if not endpoint.startswith("http")
                else endpoint
            )
            resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
            return self._handle_response(resp)

        try:
            return cb.call(lambda: self._retry.call(_do_request))
        except Exception as exc:
            if isinstance(exc, BrokerError):
                raise
            raise BrokerError(str(exc)) from exc

    def _apply_rate_limit(self, endpoint: str) -> None:
        matched = None
        for prefix, limiter in self._rate_limiters.items():
            if endpoint.startswith(prefix):
                matched = limiter
                break
        if matched:
            matched.acquire(1, timeout=5.0)

    @staticmethod
    def _handle_response(resp: requests.Response) -> dict:
        if resp.status_code == 401:
            raise AuthenticationError("Token expired or invalid")
        if resp.status_code == 429:
            raise RateLimitError("Rate limit exceeded", retry_after=30.0)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                msg = body.get("remarks", {}).get("error_msg", resp.text)
            except Exception:
                msg = resp.text
            raise BrokerError(
                f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code)
            )
        try:
            return resp.json()
        except Exception:
            return {"data": resp.text}

    def close(self) -> None:
        self._session.close()
