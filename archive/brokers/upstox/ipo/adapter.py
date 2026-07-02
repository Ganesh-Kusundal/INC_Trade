"""Upstox IPO adapter."""

from __future__ import annotations

from typing import Any

from brokers.upstox.ipo.client import UpstoxIpoClient


class UpstoxIpoAdapter:
    def __init__(self, client: UpstoxIpoClient) -> None:
        self._client = client

    def get_ipos(self, status: str = "open") -> list[dict[str, Any]]:
        return self._client.get_ipo_data(status=status)
