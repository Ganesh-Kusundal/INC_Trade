"""Dhan IP management — configure and manage authorized IP addresses.

API: GET /ip — get authorized IPs
     PUT /ip — update IP whitelist
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IpEntry:
    """An authorized IP address entry."""

    ip_address: str = ""
    ip_type: str = ""  # PRIMARY or SECONDARY

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IpEntry:
        return cls(
            ip_address=str(data.get("ipAddress", "")),
            ip_type=str(data.get("ipType", "")),
        )


class DhanIpManagement:
    """IP whitelist management for Dhan.

    Usage::

        ip_mgmt = DhanIpManagement(client=dhan_client)
        ips = ip_mgmt.get_ips()
        ip_mgmt.add_ip("1.2.3.4", ip_type="PRIMARY")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_ips(self) -> list[IpEntry]:
        """Get all authorized IP addresses."""
        data = self._client.get("/ip")
        items = data.get("data", []) if isinstance(data, dict) else []
        if isinstance(items, list):
            return [IpEntry.from_dict(item) for item in items if isinstance(item, dict)]
        return []

    def add_ip(self, ip_address: str, ip_type: str = "PRIMARY") -> dict[str, Any]:
        """Add an IP to the whitelist."""
        payload = {
            "dhanClientId": self._client.client_id,
            "ipAddress": ip_address,
            "ipType": ip_type,
        }
        logger.info("dhan_ip_add", ip=ip_address, ip_type=ip_type)
        return self._client.put("/ip", json=payload)


__all__ = ["DhanIpManagement", "IpEntry"]
