"""Dhan eDIS — TPIN generation and stock authorization.

API: GET /edis/tpin — generate TPIN
     POST /edis/authorize — authorize stock transfer
"""

from __future__ import annotations

from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


class DhanEdis:
    """eDIS (electronic Delivery Instruction Slip) authorization for Dhan.

    Usage::

        edis = DhanEdis(client=dhan_client)
        tpin = edis.get_tpin()
        result = edis.authorize(isin="INE002A01018", quantity=100, exchange="NSE_EQ")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_tpin(self) -> dict[str, Any]:
        """Generate a TPIN for eDIS authorization."""
        logger.info("dhan_edis_get_tpin")
        return self._client.get("/edis/tpin")

    def authorize(
        self,
        isin: str,
        quantity: int,
        exchange: str = "NSE_EQ",
    ) -> dict[str, Any]:
        """Authorize stock transfer via eDIS."""
        payload = {
            "dhanClientId": self._client.client_id,
            "isin": isin,
            "qty": str(quantity),
            "exchange": exchange,
        }
        logger.info("dhan_edis_authorize", isin=isin, qty=quantity)
        return self._client.post("/edis/authorize", json=payload)


__all__ = ["DhanEdis"]
