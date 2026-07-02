"""Unit tests for Upstox GTT adapter."""

from __future__ import annotations

from unittest.mock import Mock

from brokers.upstox.orders.gtt_adapter import UpstoxGttAdapter
from brokers.upstox.orders.gtt_client import UpstoxGttClient


class TestGttAdapterStubMethods:
    """Verify stub methods that return empty results due to missing Upstox list-all endpoints."""

    def setup_method(self):
        self.mock_client = Mock(spec=UpstoxGttClient)
        self.adapter = UpstoxGttAdapter(self.mock_client)

    def test_get_forever_orders_returns_empty(self):
        assert self.adapter.get_forever_orders() == []

    def test_get_gtt_orders_returns_empty(self):
        assert self.adapter.get_gtt_orders() == []

    def test_list_alerts_returns_empty(self):
        assert self.adapter.list_alerts() == []

    def test_get_forever_orders_ignores_client(self):
        self.adapter.get_forever_orders()
        self.mock_client.assert_not_called()

    def test_get_gtt_orders_ignores_client(self):
        self.adapter.get_gtt_orders()
        self.mock_client.assert_not_called()

    def test_list_alerts_ignores_client(self):
        self.adapter.list_alerts()
        self.mock_client.assert_not_called()


class TestGttAdapterCancel:
    """Test GTT cancel behavior."""

    def setup_method(self):
        self.mock_client = Mock(spec=UpstoxGttClient)
        self.adapter = UpstoxGttAdapter(self.mock_client)

    def test_cancel_gtt_success(self):
        assert self.adapter.cancel_gtt("GTT-100") is True

    def test_cancel_gtt_exception_returns_false(self):
        self.mock_client.cancel_gtt.side_effect = Exception("API error")
        assert self.adapter.cancel_gtt("GTT-100") is False

    def test_cancel_forever_order_delegates(self):
        assert self.adapter.cancel_forever_order("GTT-100") is True


class TestGttAdapterAlerts:
    """Test alert placement and deletion."""

    def setup_method(self):
        self.mock_client = Mock(spec=UpstoxGttClient)
        self.adapter = UpstoxGttAdapter(self.mock_client)

    def test_get_alert(self):
        self.mock_client.get_gtt_order_details.return_value = {"status": "ACTIVE"}
        alert = self.adapter.get_alert("ALERT-1")
        assert alert.alert_id == "ALERT-1"
        assert alert.status == "ACTIVE"

    def test_get_alert_missing_data(self):
        self.mock_client.get_gtt_order_details.return_value = {}
        alert = self.adapter.get_alert("ALERT-2")
        assert alert.alert_id == "ALERT-2"

    def test_delete_alert_delegates_to_cancel(self):
        assert self.adapter.delete_alert("ALERT-1") is True
