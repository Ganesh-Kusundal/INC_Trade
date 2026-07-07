"""Upstox conditional alerts — place, get, list, delete price alerts.

API: POST /v2/alert/place — create alert
     GET /v2/alert — list alerts
     DELETE /v2/alert — delete alert
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxAlerts:
    """Price alert management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def place_alert(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("upstox_alert_place")
        return self._client.post("/v2/alert/place", json=payload)

    def get_alerts(self) -> list[dict[str, Any]]:
        data = self._client.get("/v2/alert")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def delete_alert(self, alert_id: str) -> dict[str, Any]:
        logger.info("upstox_alert_delete", alert_id=alert_id)
        return self._client.delete(f"/v2/alert?alert_id={alert_id}")


__all__ = ["UpstoxAlerts"]
