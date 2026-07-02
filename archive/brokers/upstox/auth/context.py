"""Shared DI container for Upstox adapters.

Mirrors Trade_J ``UpstoxBrokerConnectionFactory`` — wires all adapters from
the resolved settings + token manager + HTTP client.

Tested contract:

* ``UpstoxAdapterContext(settings=..., token_provider=...)`` constructs a
  context exposing ``settings``, ``token_provider()``, ``url_resolver``,
  ``http_client``, ``oauth_client``, and ``token_manager``.
* ``ctx.make_retry_executor(category)`` returns a ``RetryExecutor`` tuned for
  the given rate-limit bucket (``orders``, ``quotes``, ``data``, or any
  unknown category which falls back to a safe default).
* ``ctx.http_client.settings.algo_name`` flows through to the auth layer.
* Passing ``token_manager=...`` overrides the auto-built one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brokers.common.connection_pool import get_connection_pool

from .config import UpstoxConnectionSettings
from .http import UpstoxHttpClient
from .oauth_client import UpstoxOAuthClient
from .token_manager import UpstoxTokenManager
from .urls import UpstoxApiUrlResolver


class UpstoxAdapterContext:
    """DI container for the Upstox adapter stack."""

    def __init__(
        self,
        *,
        settings: UpstoxConnectionSettings,
        token_provider: Callable[[], str],
        token_manager: UpstoxTokenManager | None = None,
        http_session: Any | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._url_resolver = UpstoxApiUrlResolver(settings)

        # Use provided session or get from connection pool
        if http_session is None:
            pool = get_connection_pool()
            http_session = pool.get_session("upstox")

        self._oauth_client = UpstoxOAuthClient(base_url=settings.base_v2)
        self._token_manager = token_manager or UpstoxTokenManager(
            settings=settings, oauth_client=self._oauth_client
        )
        self._http_client = UpstoxHttpClient(
            token_provider=token_provider,
            settings=settings,
            session=http_session,
            on_auth_failure=self._token_manager.try_refresh_on_401,
        )

    @property
    def settings(self) -> UpstoxConnectionSettings:
        return self._settings

    @property
    def token_provider(self) -> Callable[[], str]:
        return self._token_provider

    @property
    def url_resolver(self) -> UpstoxApiUrlResolver:
        return self._url_resolver

    @property
    def http_client(self) -> UpstoxHttpClient:
        return self._http_client

    @property
    def oauth_client(self) -> UpstoxOAuthClient:
        return self._oauth_client

    @property
    def token_manager(self) -> UpstoxTokenManager:
        return self._token_manager

    def make_retry_executor(self, category: str) -> Any:
        """Build a ``RetryExecutor`` for the given rate-limit bucket.

        Categories (mirrors Trade_J):

        * ``orders``  — 3 retries, 10 RPS bucket, 30 s open duration
        * ``quotes``  — 2 retries, 1 RPS bucket, 10 s open duration
        * ``data``    — 2 retries, 5 RPS bucket, 10 s open duration
        * any other  — falls back to a safe default
        """
        from brokers.common.resilience.backoff import ExponentialBackoff
        from brokers.common.resilience.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )
        from brokers.common.resilience.rate_limiter import (
            MultiBucketRateLimiter,
            RateLimitConfig,
        )
        from brokers.common.resilience.retry import RetryConfig, RetryExecutor
        from brokers.upstox.auth.config import UPSTOX_DEFAULT_RATE_PER_SECOND

        _configs: dict[str, tuple[RetryConfig, CircuitBreakerConfig, RateLimitConfig]] = {
            "orders": (
                RetryConfig(max_attempts=3),
                CircuitBreakerConfig(failure_threshold=5, open_duration_ms=30_000),
                RateLimitConfig(
                    rate_per_second=int(UPSTOX_DEFAULT_RATE_PER_SECOND),
                    capacity=int(UPSTOX_DEFAULT_RATE_PER_SECOND),
                ),
            ),
            "quotes": (
                RetryConfig(max_attempts=2),
                CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                RateLimitConfig(rate_per_second=1, capacity=1),
            ),
            "data": (
                RetryConfig(max_attempts=2),
                CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                RateLimitConfig(rate_per_second=5, capacity=20),
            ),
        }
        retry_cfg, cb_cfg, rl_cfg = _configs.get(
            category,
            (
                RetryConfig(max_attempts=2),
                CircuitBreakerConfig(failure_threshold=3, open_duration_ms=10_000),
                RateLimitConfig(rate_per_second=5, capacity=20),
            ),
        )
        return RetryExecutor(
            config=retry_cfg,
            circuit_breaker=CircuitBreaker(f"upstox-{category}", cb_cfg),
            rate_limiter=MultiBucketRateLimiter({category: rl_cfg}),
            rate_limit_category=category,
            backoff=ExponentialBackoff(base_delay_ms=500, max_delay_ms=5000),
        )
