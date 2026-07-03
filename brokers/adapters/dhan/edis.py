"""Dhan EDIS adapter — Electronic Debit Instruction Slip for CDSL."""

from __future__ import annotations

import logging

from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver

logger = logging.getLogger(__name__)


class DhanEDIS:
    """EDIS adapter for Dhan.

    Manages CDSL authorization for selling delivery positions.
    """

    def __init__(
        self, client: DhanHttpClient, resolver: DhanInstrumentResolver
    ) -> None:
        self._client = client
        self._resolver = resolver

    def get_tpin_status(self) -> dict:
        """Check if TPIN is authorized for the day."""
        try:
            response = self._client.get("/edis/tpinStatus")
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error(f"Failed to check TPIN status: {e}")
            return {"error": str(e)}

    def generate_tpin(self) -> dict:
        """Request a new TPIN from CDSL to be sent to user's registered mobile/email."""
        try:
            response = self._client.get("/edis/generateTpin")
            return response if isinstance(response, dict) else {}
        except Exception as e:
            logger.error(f"Failed to generate TPIN: {e}")
            return {"error": str(e)}

    def get_edis_form(self, isin: str, qty: int, exchange: str = "NSE") -> dict:
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
            logger.error(f"Failed to get EDIS form: {e}")
            return {"error": str(e)}
