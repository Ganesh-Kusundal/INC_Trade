"""Upstox kill switch adapter — implements ``KillSwitchPort``."""

from __future__ import annotations

from typing import Any

from brokers.common.gateway_interfaces import KillSwitchPort
from brokers.upstox.kill_switch.client import UpstoxKillSwitchClient


class UpstoxKillSwitchAdapter(KillSwitchPort):
    def __init__(self, client: UpstoxKillSwitchClient) -> None:
        self._client = client

    def get_status(self) -> dict[str, Any]:
        return self._client.get_status()

    def set_status(self, updates: list[dict[str, str]]) -> dict[str, Any]:
        return self._client.set_status(updates)
