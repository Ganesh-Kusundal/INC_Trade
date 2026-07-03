"""Upstox HTTP client — REST API calls with resilience.

Upstox splits its API across two hosts:
- V2 (api.upstox.com): market data, portfolio, user
- HFT/V3 (api-hft.upstox.com): orders, trades

Thread-safe.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import requests

from brokers.adapters.upstox.config import (
    RATE_LIMITS,
    READ_PREFIXES,
    WRITE_PREFIXES,
)
from brokers.domain.constants.timeouts import DEFAULT_HTTP_TIMEOUT_SECONDS
from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    BrokerServerError,
    RateLimitError,
)
from brokers.infrastructure.http.resilient_client import ResilientHttpClient, TokenRefreshSignal
from brokers.infrastructure.ssl_hardening import create_pinned_session

logger = logging.getLogger(__name__)


class UpstoxHttpClient(ResilientHttpClient):
    def __init__(
        self,
        access_token: str | Callable[[], str],
        base_url_v2: str = "",
        base_url_hft: str = "",
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        token_refresh_fn: Callable[[], bool] | None = None,
    ):
        self._user_refresh_fn = token_refresh_fn
        if callable(access_token):
            self._token_provider = access_token
            initial_token = access_token()
        else:
            self._token_provider = lambda: access_token
            initial_token = access_token

        self._base_v2 = base_url_v2 or "https://api.upstox.com"
        self._base_hft = base_url_hft or "https://api-hft.upstox.com"

        # Build URL function
        def _build_url(endpoint: str) -> str:
            if endpoint.startswith("http"):
                return endpoint
            if "/v3/" in endpoint:
                return f"{self._base_hft}{endpoint}"
            return f"{self._base_v2}{endpoint}"

        # Token refresh adapter — bridges Upstox bool-returning fn to str-returning fn
        def _token_refresh_adapter() -> str | None:
            if self._user_refresh_fn is not None:
                result = self._user_refresh_fn()
                if result:
                    token = self._token_provider()
                    if token:
                        self.update_token(token)
                    return token
            return None

        super().__init__(
            rate_limits=RATE_LIMITS,
            categorize_fn=self._categorize_endpoint,
            url_builder_fn=_build_url,
            response_handler_fn=self._handle_response,
            timeout=timeout,
            session_factory=create_pinned_session,
            token_refresh_fn=_token_refresh_adapter,
        )

        self._session.headers.update(
            {
                "Authorization": f"Bearer {initial_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def update_token(self, new_token: str) -> None:
        self._session.headers["Authorization"] = f"Bearer {new_token}"
        logger.debug("http_client_token_updated")

    def _categorize_endpoint(self, endpoint: str) -> str:
        for prefix in READ_PREFIXES:
            if endpoint.startswith(prefix):
                return "read"
        for prefix in WRITE_PREFIXES:
            if endpoint.startswith(prefix):
                return "write"
        return "admin"

    def _handle_response(self, resp: requests.Response) -> dict:
        if resp.status_code in (401, 403):
            raise TokenRefreshSignal("Token expired or invalid")
        if resp.status_code == 429:
            raise RateLimitError("Rate limit exceeded", retry_after=30.0)
        if resp.status_code >= 500:
            try:
                body = resp.json()
                errors = body.get("errors", [])
                msg = errors[0].get("message", resp.text) if errors else resp.text
            except Exception:
                msg = resp.text
            raise BrokerServerError(f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code))
        if resp.status_code >= 400:
            try:
                body = resp.json()
                errors = body.get("errors", [])
                msg = errors[0].get("message", resp.text) if errors else resp.text
            except Exception:
                msg = resp.text
            raise BrokerError(f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code))
        try:
            return resp.json()
        except Exception:
            return {"data": resp.text}
