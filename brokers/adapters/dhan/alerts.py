"""Dhan Alerts adapter."""

from __future__ import annotations

import logging

from brokers.adapters.dhan.http import DhanHttpClient

logger = logging.getLogger(__name__)


class DhanAlerts:
    """Alerts adapter for Dhan to manage price alerts."""

    def __init__(self, client: DhanHttpClient) -> None:
        self._client = client

    def create_alert(
        self,
        symbol: str,
        price: float,
        condition: str,
        exchange_segment: str = "NSE_EQ",
    ) -> dict:
        """Create a price alert."""
        payload = {
            "tradingSymbol": symbol,
            "alertPrice": price,
            "alertCondition": condition,
            "exchangeSegment": exchange_segment,
        }
        return self._client.post("/alerts", json=payload)

    def get_alerts(self) -> list[dict]:
        """Fetch all active alerts."""
        resp = self._client.get("/alerts")
        return resp.get("data", []) if isinstance(resp, dict) else []

    def get_alert(self, alert_id: str) -> dict:
        """Fetch a specific alert by ID."""
        return self._client.get(f"/alerts/{alert_id}")

    def delete_alert(self, alert_id: str) -> dict:
        """Delete a price alert."""
        return self._client.delete(f"/alerts/{alert_id}")

    def update_alert(self, alert_id: str, price: float, condition: str) -> dict:
        """Update an existing price alert."""
        payload = {"alertPrice": price, "alertCondition": condition}
        return self._client.put(f"/alerts/{alert_id}", json=payload)
