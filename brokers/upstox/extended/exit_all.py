"""Upstox exit all — close all positions via kill switch.

Uses the Upstox kill switch to deactivate all segments,
effectively closing all open positions.
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxExitAll:
    """Exit all positions for Upstox (via kill switch)."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def execute(self) -> dict[str, Any]:
        """Deactivate all segments to exit all positions."""
        logger.info("upstox_exit_all_execute")
        return self._client.put("/v2/kill-switch", json={"active": True})


__all__ = ["UpstoxExitAll"]
