"""eDIS/TPIN adapter — authorization for selling holdings."""

from __future__ import annotations

import logging
import re

from brokers.dhan.exceptions import EDISError
from brokers.dhan.http_client import DhanHttpClient

logger = logging.getLogger(__name__)


class EDISAdapter:
    """Adapter for Dhan eDIS (Electronic DISclosure) API.

    eDIS allows authorization to sell holdings without physical DIS slips.
    """

    def __init__(self, client: DhanHttpClient):
        self._client = client

    def generate_tpin(self) -> dict:
        """Generate TPIN for eDIS authorization.

        Returns:
            Response dict with TPIN details

        Raises:
            EDISError: If API call fails
        """
        try:
            data = self._client.post("/edis/tpin")
        except Exception as exc:
            raise EDISError(f"Failed to generate TPIN: {exc}") from exc

        logger.info("tpin_generated")
        return data

    def authorize_edis(self, isin: str, quantity: int, exchange: str) -> dict:
        """Authorize eDIS for selling holdings.

        Args:
            isin: ISIN of the security (e.g., INE002A01018)
            quantity: Quantity to sell
            exchange: Exchange (NSE, BSE, etc.)

        Returns:
            Response dict with authorization details

        Raises:
            ValueError: If ISIN format is invalid
            EDISError: If API call fails
        """
        if not self._is_valid_isin(isin):
            raise ValueError(f"Invalid ISIN format: {isin}")

        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")

        payload = {
            "isin": isin,
            "quantity": quantity,
            "exchange": exchange,
        }

        try:
            data = self._client.post("/edis/authorize", json=payload)
        except Exception as exc:
            raise EDISError(f"Failed to authorize eDIS: {exc}") from exc

        logger.info(
            "edis_authorized",
            extra={
                "isin": isin,
                "quantity": quantity,
                "exchange": exchange,
            },
        )
        return data

    def check_status(self, isin: str) -> dict:
        """Check eDIS authorization status.

        Args:
            isin: ISIN of the security

        Returns:
            Response dict with status details

        Raises:
            EDISError: If API call fails
        """
        try:
            data = self._client.get(f"/edis/status/{isin}")
        except Exception as exc:
            raise EDISError(f"Failed to check eDIS status: {exc}") from exc

        result = data.get("data", data)
        logger.info(
            "edis_status_checked",
            extra={
                "isin": isin,
                "status": result.get("status"),
            },
        )
        return result

    def _is_valid_isin(self, isin: str) -> bool:
        """Validate ISIN format (12 alphanumeric characters)."""
        pattern = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[A-Z0-9]{1}$")
        return bool(pattern.match(isin))
