"""Upstox IPO management.

API: GET /v2/ipo — list IPOs (open/upcoming/closed)
"""

from __future__ import annotations

from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


class UpstoxIPO:
    """IPO management for Upstox.

    Usage::

        ipo = UpstoxIPO(client=upstox_client)
        ipos = ipo.get_ipos(status="open")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_ipos(self, status: str = "open") -> list[dict[str, Any]]:
        """List IPOs filtered by status (open, upcoming, closed)."""
        data = self._client.get(f"/v2/ipo?status={status}")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []


__all__ = ["UpstoxIPO"]
