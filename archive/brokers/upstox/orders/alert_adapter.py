"""Upstox alert adapter — implements ``ConditionalAlertProvider`` port (delegates to GTT)."""

from __future__ import annotations

from brokers.common.gateway_interfaces import ConditionalAlertProvider
from brokers.upstox.orders.gtt_adapter import UpstoxGttAdapter
from domain import ConditionalAlert, ConditionalAlertRequest


class UpstoxAlertAdapter(ConditionalAlertProvider):
    def __init__(self, gtt_adapter: UpstoxGttAdapter) -> None:
        self._gtt = gtt_adapter

    def place_alert(self, request: ConditionalAlertRequest) -> str:
        return self._gtt.place_alert(request)

    def get_alert(self, alert_id: str) -> ConditionalAlert:
        return self._gtt.get_alert(alert_id)

    def list_alerts(self) -> list[ConditionalAlert]:
        return self._gtt.list_alerts()

    def delete_alert(self, alert_id: str) -> bool:
        return self._gtt.delete_alert(alert_id)
