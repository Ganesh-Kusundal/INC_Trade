"""Upstox static IP — retrieve and configure static IP addresses.

API: GET /v2/static-ip — get static IP
     PUT /v2/static-ip — set static IP
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxStaticIp:
    """Static IP management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_static_ip(self) -> dict[str, Any]:
        data = self._client.get("/v2/static-ip")
        return data.get("data", data) if isinstance(data, dict) else {}  # type: ignore[no-any-return]

    def set_static_ip(self, ip_address: str, ip_type: str = "PRIMARY") -> dict[str, Any]:
        logger.info("upstox_static_ip_set", ip=ip_address, ip_type=ip_type)
        return self._client.put("/v2/static-ip", json={"ipAddress": ip_address, "ipType": ip_type})


__all__ = ["UpstoxStaticIp"]
