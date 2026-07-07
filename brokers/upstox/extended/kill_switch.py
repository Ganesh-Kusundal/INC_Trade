"""Upstox kill switch — emergency segment deactivation.

API: GET /v2/kill-switch — get status
     PUT /v2/kill-switch — set status
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxKillSwitch:
    """Kill switch management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_status(self) -> dict[str, Any]:
        data = self._client.get("/v2/kill-switch")
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]

    def set_status(self, active: bool) -> dict[str, Any]:
        logger.info("upstox_kill_switch_set", active=active)
        return self._client.put("/v2/kill-switch", json={"active": active})


__all__ = ["UpstoxKillSwitch"]
