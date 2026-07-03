"""Dhan IP Management adapter."""

from __future__ import annotations

import logging

from brokers.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)


class DhanIpManagement:
    """IP Management adapter for Dhan to handle IP whitelisting dynamically."""

    def __init__(self, client: HttpClientPort) -> None:
        self._client = client

    def whitelist_ip(self, ip_address: str) -> dict:
        """Whitelist an IP address dynamically."""
        logger.info(f"whitelisting_ip: {ip_address}")
        payload = {"ipAddress": ip_address}
        return self._client.post("/ip/whitelist", json=payload)

    def get_whitelisted_ips(self) -> list[str]:
        """Get list of whitelisted IPs."""
        resp = self._client.get("/ip/whitelist")
        return resp.get("data", []) if isinstance(resp, dict) else []

    def remove_whitelisted_ip(self, ip_address: str) -> dict:
        """Remove a whitelisted IP address."""
        logger.info(f"removing_whitelisted_ip: {ip_address}")
        return self._client.delete(f"/ip/whitelist/{ip_address}")
