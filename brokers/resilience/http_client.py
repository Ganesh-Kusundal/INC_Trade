"""Base HTTP client with integrated resilience patterns.

Provides a unified foundation for all broker adapters to handle Rate Limits,
Circuit Breakers, and Retries uniformly.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import requests

from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    RateLimitError,
)
from brokers.resilience.circuit_breaker import CircuitBreaker
from brokers.resilience.rate_limiter import TokenBucketRateLimiter
from brokers.resilience.retry import RetryPolicy

try:
    from brokers.infrastructure.ssl_hardening import create_pinned_session
except ImportError:
    create_pinned_session = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class BaseResilientHttpClient(ABC):
    def __init__(
        self,
        rate_limits: dict[str, float],
        timeout: float = 10.0,
    ):
        self._timeout = timeout
        if create_pinned_session is not None:
            self._session = create_pinned_session()
        else:
            self._session = requests.Session()

        self._rate_limiters: dict[str, TokenBucketRateLimiter] = {}
        for endpoint, rate in rate_limits.items():
            self._rate_limiters[endpoint] = TokenBucketRateLimiter(
                rate_per_second=rate, capacity=max(int(rate), 1)
            )

        self._circuit_breakers = {
            "read": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0),
            "write": CircuitBreaker(failure_threshold=3, recovery_timeout=60.0),
            "admin": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0),
        }

        self._retry = RetryPolicy(
            max_retries=3,
            base_delay_ms=500,
            max_delay_ms=5000,
            retryable_exceptions=(requests.exceptions.RequestException, BrokerServerError),
        )

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        return self._request("GET", endpoint, params=params)

    def post(self, endpoint: str, json: dict | None = None) -> dict:
        return self._request("POST", endpoint, json=json)

    def put(self, endpoint: str, json: dict | None = None) -> dict:
        return self._request("PUT", endpoint, json=json)

    def delete(self, endpoint: str, params: dict | None = None) -> dict:
        return self._request("DELETE", endpoint, params=params)

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict:
        category = self._categorize(endpoint)
        cb = self._circuit_breakers.get(category, self._circuit_breakers["admin"])

        self._apply_rate_limit(endpoint)

        def _do_request() -> dict:
            url = self._build_url(endpoint)
            resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
            return self._handle_response(resp)

        try:
            return cb.call(
                lambda: self._retry.call(_do_request),
                ignored_exceptions=(AuthenticationError, RateLimitError, BrokerError),
            )
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

    def close(self) -> None:
        self._session.close()

    @abstractmethod
    def _categorize(self, endpoint: str) -> str:
        """Categorize endpoint into 'read', 'write', or 'admin' for circuit breakers."""

    @abstractmethod
    def _build_url(self, endpoint: str) -> str:
        """Resolve endpoint to absolute URL."""

    @abstractmethod
    def _handle_response(self, resp: requests.Response) -> dict:
        """Parse response, mapping HTTP errors to domain exceptions."""
