"""Upstox HTTP client — REST API calls with resilience.

Upstox splits its API across two hosts:
- V2 (api.upstox.com): market data, portfolio, user
- HFT/V3 (api-hft.upstox.com): orders, trades

Thread-safe.
"""

from __future__ import annotations

import logging

import requests

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
from brokers.resilience.http_client import BaseResilientHttpClient

logger = logging.getLogger(__name__)


class UpstoxHttpClient(BaseResilientHttpClient):
    def __init__(
        self,
        access_token: str,
        base_url_v2: str = "",
        base_url_hft: str = "",
        timeout: float = 10.0,
    ):
        super().__init__(rate_limits=RATE_LIMITS, timeout=timeout)
        self._access_token = access_token
        self._base_v2 = base_url_v2 or "https://api.upstox.com"
        self._base_hft = base_url_hft or "https://api-hft.upstox.com"
        
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

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
        if resp.status_code == 401:
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

