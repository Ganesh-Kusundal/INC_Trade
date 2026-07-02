"""Tests for enhanced AlertsAdapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.dhan.alerts import AlertsAdapter
from brokers.dhan.domain import Alert, AlertRequest


class TestAlertsDomain:
    """Test alerts domain types."""

    def test_alert_request_creation(self):
        """AlertRequest should create successfully."""
        req = AlertRequest(
            symbol="RELIANCE",
            exchange="NSE",
            condition="LTP_CROSSES_ABOVE",
            trigger_price=Decimal("2500.00"),
        )
        assert req.symbol == "RELIANCE"
        assert req.trigger_price == Decimal("2500.00")

    def test_alert_creation(self):
        """Alert should create successfully."""
        alert = Alert(
            alert_id="ALERT_123",
            symbol="RELIANCE",
            exchange="NSE",
            condition="LTP_CROSSES_ABOVE",
            trigger_price=Decimal("2500.00"),
            active=True,
        )
        assert alert.alert_id == "ALERT_123"
        assert alert.active is True


class TestAlertsAdapter:
    """Test alerts adapter functionality."""

    def test_place_alert_success(self, fake_client, resolver):
        """Should create alert and return Alert."""
        fake_client.set_response(
            "POST",
            "/alerts",
            {
                "data": {
                    "alertId": "ALERT_001",
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "condition": "LTP_CROSSES_ABOVE",
                    "triggerPrice": 2500.0,
                    "status": "ACTIVE",
                }
            },
        )

        adapter = AlertsAdapter(fake_client, resolver)
        result = adapter.place(
            AlertRequest(
                symbol="RELIANCE",
                exchange="NSE",
                condition="LTP_CROSSES_ABOVE",
                trigger_price=Decimal("2500.00"),
            )
        )

        assert isinstance(result, Alert)
        assert result.alert_id == "ALERT_001"
        assert result.active is True
        assert result.trigger_price == Decimal("2500.00")

    def test_place_alert_validation_negative_price(self, fake_client, resolver):
        """Should reject negative trigger price."""
        adapter = AlertsAdapter(fake_client, resolver)

        with pytest.raises(ValueError, match="Trigger price must be positive"):
            adapter.place(
                AlertRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    condition="LTP_CROSSES_ABOVE",
                    trigger_price=Decimal("-100"),
                )
            )

    def test_place_alert_validation_invalid_condition(self, fake_client, resolver):
        """Should reject invalid condition."""
        adapter = AlertsAdapter(fake_client, resolver)

        with pytest.raises(ValueError, match="Invalid condition"):
            adapter.place(
                AlertRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    condition="INVALID_CONDITION",
                    trigger_price=Decimal("2500.00"),
                )
            )

    def test_get_alert_success(self, fake_client, resolver):
        """Should retrieve alert by ID."""
        fake_client.set_response(
            "GET",
            "/alerts/ALERT_001",
            {
                "data": {
                    "alertId": "ALERT_001",
                    "symbol": "RELIANCE",
                    "condition": "LTP_CROSSES_ABOVE",
                    "triggerPrice": 2500.0,
                    "status": "ACTIVE",
                }
            },
        )

        adapter = AlertsAdapter(fake_client, resolver)
        alert = adapter.get("ALERT_001")

        assert alert.alert_id == "ALERT_001"
        assert alert.condition == "LTP_CROSSES_ABOVE"

    def test_list_alerts_success(self, fake_client, resolver):
        """Should list all alerts."""
        fake_client.set_response(
            "GET",
            "/alerts",
            {
                "data": [
                    {
                        "alertId": "ALERT_001",
                        "symbol": "RELIANCE",
                        "triggerPrice": 2500.0,
                        "status": "ACTIVE",
                    },
                    {
                        "alertId": "ALERT_002",
                        "symbol": "TCS",
                        "triggerPrice": 3500.0,
                        "status": "ACTIVE",
                    },
                ]
            },
        )

        adapter = AlertsAdapter(fake_client, resolver)
        alerts = adapter.list_all()

        assert len(alerts) == 2
        assert alerts[0].alert_id == "ALERT_001"
        assert alerts[1].alert_id == "ALERT_002"

    def test_delete_alert_success(self, fake_client, resolver):
        """Should delete alert successfully."""
        fake_client.set_response("DELETE", "/alerts/ALERT_001", {"success": True})

        adapter = AlertsAdapter(fake_client, resolver)
        result = adapter.delete("ALERT_001")

        assert result is True
