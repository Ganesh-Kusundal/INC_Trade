"""Base HTTP client with integrated resilience patterns.

Provides a unified foundation for all broker adapters to handle Rate Limits,
Circuit Breakers, and Retries uniformly.
"""

from __future__ import annotations

import logging
import urllib.parse
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import requests

from inc_trade.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    RateLimitError,
)
from inc_trade.resilience.circuit_breaker import CircuitBreaker
from inc_trade.resilience.rate_limiter import TokenBucketRateLimiter
from inc_trade.resilience.retry import RetryPolicy

logger = logging.getLogger(__name__)


class TokenRefreshSignal(Exception):
    """Internal signal that token was refreshed and request should be retried."""


class ResilientHttpClient:
    def __init__(
        self,
        rate_limits: dict[str, float],
        categorize_fn: Callable[[str], str],
        url_builder_fn: Callable[[str], str],
        response_handler_fn: Callable[[requests.Response], dict[str, Any]],
        timeout: float = 10.0,
        session_factory: Callable[[], requests.Session] | None = None,
        token_refresh_fn: Callable[[], str | None] | None = None,
        client_id: str = "",
    ):
        self._client_id = client_id
        self._timeout = timeout
        self._session = session_factory() if session_factory else requests.Session()
        self._categorize_fn = categorize_fn
        self._url_builder_fn = url_builder_fn
        self._response_handler_fn = response_handler_fn
        self._token_refresh_fn = token_refresh_fn

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
            retryable_exceptions=(
                requests.exceptions.RequestException,
                BrokerServerError,
                RateLimitError,
            ),
        )

    @property
    def session(self) -> requests.Session:
        return self._session

    @property
    def _read_breaker(self) -> CircuitBreaker:
        return self._circuit_breakers["read"]

    @_read_breaker.setter
    def _read_breaker(self, val: CircuitBreaker) -> None:
        self._circuit_breakers["read"] = val

    @property
    def _write_breaker(self) -> CircuitBreaker:
        return self._circuit_breakers["write"]

    @_write_breaker.setter
    def _write_breaker(self, val: CircuitBreaker) -> None:
        self._circuit_breakers["write"] = val

    @property
    def client_id(self) -> str:
        return self._client_id

    def get(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params, **kwargs)

    def post(self, endpoint: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._request("POST", endpoint, json=json, **kwargs)

    def put(self, endpoint: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._request("PUT", endpoint, json=json, **kwargs)

    def delete(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._request("DELETE", endpoint, params=params, **kwargs)
        
    def update_token(self, new_token: str) -> None:
        if "access-token" in self._session.headers:
            self._session.headers["access-token"] = new_token
        elif "Authorization" in self._session.headers:
            self._session.headers["Authorization"] = f"Bearer {new_token}"
        else:
            # Default to Authorization if neither exists
            self._session.headers["Authorization"] = f"Bearer {new_token}"

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        category = self._categorize_fn(endpoint)
        cb = self._circuit_breakers.get(category, self._circuit_breakers["admin"])

        self._apply_rate_limit(endpoint)

        def _do_request() -> dict[str, Any]:
            url = self._url_builder_fn(endpoint)
            resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
            return self._response_handler_fn(resp)

        try:
            return dict(cb.call(
                lambda: self._retry.call(_do_request),
                ignored_exceptions=(AuthenticationError, RateLimitError, BrokerError),
            ))
        except TokenRefreshSignal:
            logger.debug("token_refreshed_retrying", extra={"endpoint": endpoint})
            
            if hasattr(self, "_token_refresh_fn") and self._token_refresh_fn:
                try:
                    new_token = self._token_refresh_fn()
                    if new_token:
                        self.update_token(new_token)
                except Exception as exc:
                    logger.warning("token_refresh_failed", extra={"error": str(exc)})
                    
            try:
                return dict(cb.call(
                    lambda: self._retry.call(_do_request),
                    ignored_exceptions=(AuthenticationError, RateLimitError, BrokerError),
                ))
            except Exception as exc:
                if isinstance(exc, BrokerError):
                    raise
                raise BrokerError(str(exc)) from exc
        except Exception as exc:
            if isinstance(exc, BrokerError):
                raise
            raise BrokerError(str(exc)) from exc

    def _apply_rate_limit(self, endpoint: str) -> None:
        path = urllib.parse.urlparse(endpoint).path
        matched = None
        for prefix, limiter in self._rate_limiters.items():
            if path.startswith(prefix):
                matched = limiter
                break
        if matched:
            matched.acquire(1, timeout=5.0)

    def close(self) -> None:
        self._session.close()

    def circuit_breaker_states(self) -> dict[str, int]:
        """Map breaker states to ints: 0=CLOSED, 1=OPEN, 2=HALF_OPEN."""
        from inc_trade.resilience.circuit_breaker import CircuitState

        mapping = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }
        return {
            name: mapping[breaker.state]
            for name, breaker in self._circuit_breakers.items()
        }
