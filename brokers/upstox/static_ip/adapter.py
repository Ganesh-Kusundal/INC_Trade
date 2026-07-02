"""Upstox static IP adapter — implements ``StaticIPPort``."""

from __future__ import annotations

from brokers.common.gateway_interfaces import StaticIPPort
from brokers.upstox.static_ip.client import UpstoxStaticIpClient


class UpstoxStaticIpAdapter(StaticIPPort):
    def __init__(self, client: UpstoxStaticIpClient) -> None:
        self._client = client

    def get_static_ip(self) -> dict[str, str]:
        return self._client.get_static_ip()

    def set_static_ip(self, primary: str, secondary: str | None = None) -> dict[str, str]:
        return self._client.set_static_ip(primary, secondary)
