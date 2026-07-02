"""IP Management adapter — static IP whitelisting management."""

from __future__ import annotations

import logging
import re

from brokers.dhan.domain import IPConfig
from brokers.dhan.exceptions import IPManagementError
from brokers.dhan.http_client import DhanHttpClient

logger = logging.getLogger(__name__)


class IPManagementAdapter:
    """Adapter for Dhan IP Management API (v2.4+)."""

    def __init__(self, client: DhanHttpClient):
        self._client = client

    def set_ip(self, ip_address: str, ip_type: str) -> dict:
        """Set a static IP address.

        Args:
            ip_address: IP address to whitelist
            ip_type: PRIMARY or SECONDARY

        Returns:
            Response dict from API

        Raises:
            ValueError: If IP format is invalid
            IPManagementError: If API call fails
        """
        if not self._is_valid_ip(ip_address):
            raise ValueError(f"Invalid IP address format: {ip_address}")

        if ip_type not in ("PRIMARY", "SECONDARY"):
            raise ValueError(f"Invalid ip_type: {ip_type}. Must be PRIMARY or SECONDARY")

        payload = {
            "ipAddress": ip_address,
            "ipType": ip_type,
        }

        try:
            data = self._client.post("/ip", json=payload)
        except Exception as exc:
            raise IPManagementError(f"Failed to set IP: {exc}") from exc

        logger.info(
            "ip_set",
            extra={
                "ip_address": ip_address,
                "ip_type": ip_type,
            },
        )
        return data

    def modify_ip(self, ip_address: str, ip_type: str) -> dict:
        """Modify an existing IP configuration.

        Args:
            ip_address: New IP address
            ip_type: PRIMARY or SECONDARY

        Returns:
            Response dict from API

        Raises:
            ValueError: If IP format is invalid
            IPManagementError: If API call fails
        """
        if not self._is_valid_ip(ip_address):
            raise ValueError(f"Invalid IP address format: {ip_address}")

        payload = {
            "ipAddress": ip_address,
            "ipType": ip_type,
        }

        try:
            data = self._client.put("/ip", json=payload)
        except Exception as exc:
            raise IPManagementError(f"Failed to modify IP: {exc}") from exc

        logger.info(
            "ip_modified",
            extra={
                "ip_address": ip_address,
                "ip_type": ip_type,
            },
        )
        return data

    def get_ip(self) -> list[IPConfig]:
        """Get all configured IP addresses.

        Returns:
            List of IPConfig objects

        Raises:
            IPManagementError: If API call fails
        """
        try:
            data = self._client.get("/ip")
        except Exception as exc:
            raise IPManagementError(f"Failed to fetch IP configuration: {exc}") from exc

        items = data.get("data", []) if isinstance(data, dict) else []
        configs = [self._parse_config(item) for item in (items if isinstance(items, list) else [])]

        logger.info("ip_configs_fetched", extra={"count": len(configs)})
        return configs

    def _is_valid_ip(self, ip: str) -> bool:
        """Validate IP address format (IPv4)."""
        pattern = re.compile(
            r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
            r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        )
        return bool(pattern.match(ip))

    def _parse_config(self, data: dict) -> IPConfig:
        """Parse IP configuration from API response."""
        return IPConfig(
            ip_address=data.get("ipAddress", ""),
            ip_type=data.get("ipType", ""),
            status=data.get("status", ""),
        )
