"""Dhan HTTP client — REST API calls with resilience.

Integrates rate limiting, circuit breaker, and retry into every HTTP call.
Thread-safe.
"""

from __future__ import annotations

import logging

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
    BrokerServerError,
    RateLimitError,
)
from brokers.resilience.http_client import BaseResilientHttpClient

logger = logging.getLogger(__name__)


class DhanHttpClient(BaseResilientHttpClient):
    def __init__(
        self,
        access_token: str,
        client_id: str,
        base_url: str = "",
        timeout: float = 10.0,
    ):
        super().__init__(rate_limits=RATE_LIMITS, timeout=timeout)
        self._access_token = access_token
        self._client_id = client_id
        self._base_url = base_url or ENDPOINTS["orders"].rsplit("/orders", 1)[0]
        
        self._session.headers.update(
            {
                "access-token": access_token,
                "client-id": client_id,
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
        return f"{self._base_url}{endpoint}"

    def _handle_response(self, resp: requests.Response) -> dict:
        if resp.status_code == 401:
            raise AuthenticationError("Token expired or invalid")
        if resp.status_code == 429:
            raise RateLimitError("Rate limit exceeded", retry_after=30.0)
        if resp.status_code >= 500:
            try:
                body = resp.json()
                msg = body.get("remarks", {}).get("error_msg", resp.text)
            except Exception:
                msg = resp.text
            raise BrokerServerError(
                f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code)
            )
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

