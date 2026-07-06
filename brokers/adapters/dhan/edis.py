"""Dhan EDIS adapter — Electronic Debit Instruction Slip for CDSL."""

from __future__ import annotations

import logging
from typing import Any

from brokers.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)


class DhanEDIS:
    """EDIS adapter for Dhan.

    Manages CDSL authorization for selling delivery positions.
    """

    def __init__(self, client: HttpClientPort) -> None:
        self._client = client

    def get_tpin_status(self) -> dict[str, Any]:
        """Check if TPIN is authorized for the day."""
        try:
            response = self._client.get("/edis/tpinStatus")
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error("Failed to check TPIN status: %s", e, exc_info=True)
            return {"error": str(e)}

    def generate_tpin(self) -> dict[str, Any]:
        """Request a new TPIN from CDSL to be sent to user's registered mobile/email."""
        try:
            response = self._client.get("/edis/generateTpin")
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error("Failed to generate TPIN: %s", e, exc_info=True)
            return {"error": str(e)}

    def get_edis_form(self, isin: str, qty: int, exchange: str = "NSE") -> dict[str, Any]:
        """Get the HTML form data required to redirect user to CDSL portal for auth."""
        try:
            response = self._client.post(
                "/edis/form",
                json={
                    "isin": isin,
                    "qty": qty,
                    "exchange": exchange,
                },
            )
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error("Failed to get EDIS form: %s", e, exc_info=True)
            return {"error": str(e)}
