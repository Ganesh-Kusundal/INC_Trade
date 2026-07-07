"""Shared HTTP client for all Dhan API calls.

Centralizes connection management, authentication headers,
and response handling into a single reusable client.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from tradex.broker.auth import AuthManager
from tradex.providers.dhan.config import DhanConfig
from tradex.core.errors import map_provider_error
from tradex.core.logging_config import get_logger

logger = get_logger("providers.dhan.http_client")


class DhanHTTPClient:
    """Shared async HTTP client for all Dhan API calls.

    Eliminates per-request client creation. Handles automatic
    header refresh and standardised response/error handling.
    """

    def __init__(self, config: DhanConfig, auth_manager: AuthManager) -> None:
        self._config = config
        self._auth = auth_manager
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Create the shared httpx client."""
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._config.timeout,
            headers=self._build_headers(),
        )
        logger.info("dhan_http_client_connected", base_url=self._config.base_url)

    async def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated request with automatic header refresh."""
        if not self._client:
            await self.connect()

        # Refresh headers in case token was refreshed
        self._client.headers.update(self._build_headers())  # type: ignore[union-attr]

        client_fn = getattr(self._client, method.lower())
        response = await client_fn(path, **kwargs)
        return self._handle_response(response, path)

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a GET request."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a POST request."""
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a PUT request."""
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a DELETE request."""
        return await self.request("DELETE", path, **kwargs)

    async def close(self) -> None:
        """Close the shared client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("dhan_http_client_closed")

    @property
    def is_connected(self) -> bool:
        """Whether the underlying httpx client has been created."""
        return self._client is not None

    def _build_headers(self) -> dict[str, str]:
        """Build request headers with current auth token."""
        # Prefer the auth_manager token (may have been refreshed);
        # fall back to the config token for initial requests before
        # the auth provider has called set_token().
        token = self._config.access_token
        if self._auth.is_authenticated:
            token = self._auth.access_token
        return {
            "Content-Type": "application/json",
            "access-token": token,
            "client-id": self._config.client_id,
        }

    def _handle_response(self, response: httpx.Response, path: str) -> dict[str, Any]:
        """Parse response and raise on error status."""
        data = response.json()
        if data.get("status") == "success":
            return data

        remarks = data.get("remarks", {})
        raise map_provider_error(
            code=remarks.get("error_code", ""),
            message=remarks.get("error_message", f"Request failed: {path}"),
            provider="dhan",
            http_status=response.status_code,
            raw_response=data,
        )
