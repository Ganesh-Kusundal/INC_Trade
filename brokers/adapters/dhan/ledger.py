"""Dhan Ledger adapter — Transaction history."""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.ports.http_client_port import HttpClientPort

logger = logging.getLogger(__name__)


class DhanLedger:
    """Ledger adapter for Dhan.

    Fetches transaction history and ledger statements.
    """

    def __init__(self, client: HttpClientPort) -> None:
        self._client = client

    def get_ledger(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Fetch ledger statement for a date range.

        Parameters
        ----------
        from_date : str
            Start date in YYYY-MM-DD.
        to_date : str
            End date in YYYY-MM-DD.

        Returns
        -------
        list[dict]
            List of ledger entries.
        """
        try:
            response = self._client.get(f"/ledger?fromDate={from_date}&toDate={to_date}")
            if not isinstance(response, dict):
                logger.warning("Unexpected ledger response type")
                return []

            data = response.get("data", [])
            if not isinstance(data, list):
                logger.warning("Ledger data is not a list")
                return []

            return data
        except Exception as e:
            logger.error("Failed to fetch ledger: %s", e, exc_info=True)
            return []
