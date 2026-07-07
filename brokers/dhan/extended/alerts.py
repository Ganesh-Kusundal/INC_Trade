"""Dhan alerts — create, retrieve, list, and delete custom price alerts.

API: POST /alerts — create alert
     GET /alerts — list alerts
     GET /alerts/{id} — get alert
     DELETE /alerts/{id} — delete alert
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AlertRequest:
    """Request to create a price alert."""

    security_id: str
    exchange_segment: str
    alert_name: str = ""
    comparison_type: str = "LTP_GTE"  # LTP_GTE, LTP_LTE
    alert_price: float = 0.0


@dataclass(frozen=True, slots=True)
class Alert:
    """A price alert."""

    alert_id: str = ""
    security_id: str = ""
    exchange_segment: str = ""
    alert_name: str = ""
    comparison_type: str = ""
    alert_price: float = 0.0
    status: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Alert:
        return cls(
            alert_id=str(data.get("alertId", data.get("id", ""))),
            security_id=str(data.get("securityId", "")),
            exchange_segment=str(data.get("exchangeSegment", "")),
            alert_name=str(data.get("alertName", "")),
            comparison_type=str(data.get("comparisonType", "")),
            alert_price=float(data.get("alertPrice", 0) or 0),
            status=str(data.get("status", "")),
        )


class DhanAlerts:
    """Price alert management for Dhan.

    Usage::

        alerts = DhanAlerts(client=dhan_client)
        result = alerts.create(AlertRequest(security_id="1333", ...))
        all_alerts = alerts.list_alerts()
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def create(self, request: AlertRequest) -> dict[str, Any]:
        """Create a price alert."""
        payload = {
            "dhanClientId": self._client.client_id,
            "securityId": request.security_id,
            "exchangeSegment": request.exchange_segment,
            "alertName": request.alert_name,
            "comparisonType": request.comparison_type,
            "alertPrice": str(request.alert_price),
        }
        logger.info("dhan_alert_create", security_id=request.security_id)
        return self._client.post("/alerts", json=payload)

    def list_alerts(self) -> list[Alert]:
        """Get all price alerts."""
        data = self._client.get("/alerts")
        items = data.get("data", []) if isinstance(data, dict) else []
        if isinstance(items, list):
            return [Alert.from_dict(item) for item in items if isinstance(item, dict)]
        return []

    def get_alert(self, alert_id: str) -> Alert:
        """Get a specific alert by ID."""
        data = self._client.get(f"/alerts/{alert_id}")
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return Alert.from_dict(raw if isinstance(raw, dict) else {})

    def delete(self, alert_id: str) -> dict[str, Any]:
        """Delete a price alert."""
        logger.info("dhan_alert_delete", alert_id=alert_id)
        return self._client.delete(f"/alerts/{alert_id}")


__all__ = ["DhanAlerts", "AlertRequest", "Alert"]
