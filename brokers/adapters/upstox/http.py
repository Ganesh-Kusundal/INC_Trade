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

from brokers.domain.constants.timeouts import DEFAULT_HTTP_TIMEOUT_SECONDS
from brokers.adapters.upstox.config import (
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
from brokers.infrastructure.ssl_hardening import create_pinned_session
from brokers.resilience.http_client import BaseResilientHttpClient

logger = logging.getLogger(__name__)


class UpstoxHttpClient(BaseResilientHttpClient):
    def __init__(
        self,
        access_token: str | Callable[[], str],
        base_url_v2: str = "",
        base_url_hft: str = "",
        timeout: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        token_refresh_fn: Callable[[], bool] | None = None,
    ):
        super().__init__(rate_limits=RATE_LIMITS, timeout=timeout, session_factory=create_pinned_session)
        self._token_refresh_fn = token_refresh_fn
        if callable(access_token):
            self._token_provider = access_token
            initial_token = access_token()
        else:
            self._token_provider = lambda: access_token
            initial_token = access_token

        self._base_v2 = base_url_v2 or "https://api.upstox.com"
        self._base_hft = base_url_hft or "https://api-hft.upstox.com"

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

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict:
        if self._token_provider is not None:
            try:
                token = self._token_provider()
                if token:
                    self._session.headers["Authorization"] = f"Bearer {token}"
            except Exception:
                pass
        return super()._request(method, endpoint, **kwargs)

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
        if "/v3/" in endpoint:
            return f"{self._base_hft}{endpoint}"
        return f"{self._base_v2}{endpoint}"

    def _handle_response(self, resp: requests.Response) -> dict:
        if resp.status_code in (401, 403):
            if self._token_refresh_fn is not None:
                if self._token_refresh_fn():
                    token = self._token_provider()
                    if token:
                        self.update_token(token)
                    from brokers.resilience.http_client import TokenRefreshSignal

                    raise TokenRefreshSignal("Token refreshed, retrying request")
            raise AuthenticationError("Token expired or invalid")
        if resp.status_code == 429:
            raise RateLimitError("Rate limit exceeded", retry_after=30.0)
        if resp.status_code >= 500:
            try:
                body = resp.json()
                errors = body.get("errors", [])
                msg = errors[0].get("message", resp.text) if errors else resp.text
            except Exception:
                msg = resp.text
            raise BrokerServerError(
                f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code)
            )
        if resp.status_code >= 400:
            try:
                body = resp.json()
                errors = body.get("errors", [])
                msg = errors[0].get("message", resp.text) if errors else resp.text
            except Exception:
                msg = resp.text
            raise BrokerError(
                f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code)
            )
        try:
            return resp.json()
        except Exception:
            return {"data": resp.text}
