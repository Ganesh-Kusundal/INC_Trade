"""Upstox exit_all — closes all open positions.

Calls ``POST /v3/order/exit-all`` to exit all open positions across segments.
This is the proper V3 endpoint for bulk position exit.
"""
from __future__ import annotations
import asyncio
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxExitAll:
    """Exit all open positions using the V3 API."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    async def execute(self) -> dict[str, Any]:
        """Exit all open positions.

        Calls POST /v3/order/exit-all to close all open positions.
        """
        logger.info("upstox_exit_all_positions")
        return await asyncio.to_thread(
            self._client.post, "/v3/order/exit-all"
        )


__all__ = ["UpstoxExitAll"]
