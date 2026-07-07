"""Upstox feed authorizer — REST calls to get WebSocket authorization URLs.

The Upstox V3 WebSocket requires a REST authorization call before connecting.
This module handles those auth calls and extracts the redirect URLs.

Upstox auth flow:
1. GET /v2/feed/market-data-feed/authorize → returns {authorized_redirect_uri: "wss://..."}
2. Connect to that URL (which includes auth token in query params)
"""

from __future__ import annotations

import asyncio
from typing import Any

from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


class UpstoxFeedAuthorizer:
    """Handles REST authorization for Upstox WebSocket connections.

    Usage::

        authorizer = UpstoxFeedAuthorizer(http_client=upstox_client)
        ws_url = await authorizer.authorize_market_data_v3()
        # ws_url = "wss://api.upstox.com/v3/feed/market-data-stream?token=..."
    """

    def __init__(self, *, http_client: Any) -> None:
        self._http_client = http_client

    async def authorize_market_data_v2(self) -> str:
        """Authorize V2 market data WebSocket and return the redirect URL.

        NOTE: currently identical to :meth:`authorize_market_data_v3` — both
        hit the V3 market-data-feed authorize endpoint. Kept for API
        compatibility; consolidate if a true V2 endpoint is required.
        """
        return await self._authorize("/v2/feed/market-data-feed/authorize")

    async def authorize_market_data_v3(self) -> str:
        """Authorize V3 market data WebSocket and return the redirect URL."""
        return await self._authorize("/v2/feed/market-data-feed/authorize")

    async def authorize_portfolio_stream(
        self,
        update_types: list[str] | None = None,
    ) -> str:
        """Authorize portfolio stream WebSocket and return the redirect URL.

        Uses the dedicated portfolio-stream authorize endpoint, NOT the
        market-data endpoint.

        Args:
            update_types: Types of updates to subscribe to.
                Defaults to ["order", "position", "holding", "gtt_order"].
        """
        if update_types is None:
            update_types = ["order", "position", "holding", "gtt_order"]

        params = ",".join(update_types)
        return await self._authorize(
            f"/v2/feed/portfolio-stream/authorize?update_types={params}"
        )

    async def _authorize(self, endpoint: str) -> str:
        """Make the authorize REST call and extract the redirect URL."""
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: self._http_client.get(endpoint)
            )
            url = self._extract_authorized_url(response)
            if not url:
                raise ValueError(f"No authorized URL in response from {endpoint}")
            logger.info("upstox_ws_authorized", endpoint=endpoint)
            return url
        except Exception as exc:
            logger.warning("upstox_ws_auth_failed", endpoint=endpoint, error=str(exc)[:200])
            raise

    @staticmethod
    def _extract_authorized_url(response: Any) -> str | None:
        """Extract the authorized redirect URL from the response."""
        if isinstance(response, dict):
            # Try V3 format first
            url = response.get("authorized_redirect_uri")
            if url:
                return str(url)
            # Try V2 format
            url = response.get("redirect_uri")
            if url:
                return str(url)
            # Nested in data
            data = response.get("data")
            if isinstance(data, dict):
                url = data.get("authorized_redirect_uri") or data.get("redirect_uri")
                if url:
                    return str(url)
        return None


__all__ = ["UpstoxFeedAuthorizer"]
