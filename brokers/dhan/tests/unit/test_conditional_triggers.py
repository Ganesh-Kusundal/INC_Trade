"""Unit tests for ConditionalTriggersAdapter."""

from decimal import Decimal

import pytest

from brokers.dhan.conditional_triggers import ConditionalTriggersAdapter
from brokers.dhan.domain import ConditionalTriggerRequest


def test_place_conditional_trigger_price_above(fake_client, resolver):
    """Verify PRICE_WITH_VALUE + CROSSING_UP."""
    fake_client.set_response("POST", "/alerts/orders", {"data": {"alertId": "CT123456"}})
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    request = ConditionalTriggerRequest(
        symbol="RELIANCE",
        exchange="NSE",
        comparison_type="PRICE_WITH_VALUE",
        operator="CROSSING_UP",
        comparing_value=Decimal("2500.00"),
        exp_date="2026-12-31",
    )
    trigger = adapter.place_trigger(request)

    payloads = fake_client.calls_for("POST", "/alerts/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["dhanClientId"] == "TEST_CLIENT"
    assert payload["securityId"] == "2885"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["comparisonType"] == "PRICE_WITH_VALUE"
    assert payload["operator"] == "CROSSING_UP"
    assert payload["comparingValue"] == 2500.00
    assert trigger.alert_id == "CT123456"


def test_place_conditional_trigger_price_below(fake_client, resolver):
    """Verify PRICE_WITH_VALUE + CROSSING_DOWN."""
    fake_client.set_response("POST", "/alerts/orders", {"data": {"alertId": "CT789012"}})
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    request = ConditionalTriggerRequest(
        symbol="RELIANCE",
        exchange="NSE",
        comparison_type="PRICE_WITH_VALUE",
        operator="CROSSING_DOWN",
        comparing_value=Decimal("2400.00"),
        exp_date="2026-12-31",
    )
    adapter.place_trigger(request)

    payloads = fake_client.calls_for("POST", "/alerts/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["operator"] == "CROSSING_DOWN"
    assert payload["comparingValue"] == 2400.00


def test_place_conditional_trigger_with_orders(fake_client, resolver):
    """Verify orders array in payload."""
    fake_client.set_response(
        "POST",
        "/alerts/orders",
        {
            "data": {
                "alertId": "CT345678",
                "orders": [
                    {
                        "transactionType": "BUY",
                        "orderType": "LIMIT",
                        "price": 2500.0,
                        "quantity": 10,
                    }
                ],
            }
        },
    )
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    request = ConditionalTriggerRequest(
        symbol="RELIANCE",
        exchange="NSE",
        comparison_type="PRICE_WITH_VALUE",
        operator="CROSSING_UP",
        comparing_value=Decimal("2500.00"),
        exp_date="2026-12-31",
        orders=[
            {
                "transactionType": "BUY",
                "orderType": "LIMIT",
                "price": 2500.0,
                "quantity": 10,
            }
        ],
    )
    trigger = adapter.place_trigger(request)

    payloads = fake_client.calls_for("POST", "/alerts/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert "orders" in payload
    assert len(payload["orders"]) == 1
    assert trigger.alert_id == "CT345678"


def test_modify_conditional_trigger(fake_client, resolver):
    """Verify PUT /alerts/orders/{alertId}."""
    fake_client.set_response(
        "PUT",
        "/alerts/orders/CT123456",
        {
            "data": {
                "alertId": "CT123456",
                "alertStatus": "ACTIVE",
                "comparisonType": "PRICE_WITH_VALUE",
                "operator": "CROSSING_UP",
                "comparingValue": 2550.0,
            }
        },
    )
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    request = ConditionalTriggerRequest(
        symbol="RELIANCE",
        exchange="NSE",
        comparison_type="PRICE_WITH_VALUE",
        operator="CROSSING_UP",
        comparing_value=Decimal("2550.00"),
        exp_date="2026-12-31",
    )
    trigger = adapter.modify_trigger("CT123456", request)

    payloads = fake_client.calls_for("PUT", "/alerts/orders/CT123456")
    assert len(payloads) == 1
    assert trigger.alert_id == "CT123456"
    assert trigger.comparing_value == Decimal("2550.00")


def test_delete_conditional_trigger(fake_client, resolver):
    """Verify DELETE /alerts/orders/{alertId}."""
    fake_client.set_response("DELETE", "/alerts/orders/CT123456", {"status": "success"})
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    result = adapter.delete_trigger("CT123456")
    assert result is True
    calls = fake_client.calls_for("DELETE", "/alerts/orders/CT123456")
    assert len(calls) == 1


def test_get_conditional_trigger_by_id(fake_client, resolver):
    """Verify GET /alerts/orders/{alertId}."""
    fake_client.set_response(
        "GET",
        "/alerts/orders/CT123456",
        {
            "data": {
                "alertId": "CT123456",
                "alertStatus": "ACTIVE",
                "comparisonType": "PRICE_WITH_VALUE",
                "operator": "CROSSING_UP",
                "comparingValue": 2500.0,
                "expDate": "2026-12-31",
                "frequency": "ONCE",
                "orders": [],
            }
        },
    )
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    trigger = adapter.get_trigger("CT123456")
    assert trigger.alert_id == "CT123456"
    assert trigger.alert_status == "ACTIVE"
    assert trigger.comparing_value == Decimal("2500.00")


def test_get_all_conditional_triggers(fake_client, resolver):
    """Verify GET /alerts/orders."""
    fake_client.set_response(
        "GET",
        "/alerts/orders",
        {
            "data": [
                {
                    "alertId": "CT001",
                    "alertStatus": "ACTIVE",
                    "comparisonType": "PRICE_WITH_VALUE",
                    "operator": "CROSSING_UP",
                    "comparingValue": 2500.0,
                    "expDate": "2026-12-31",
                    "frequency": "ONCE",
                    "orders": [],
                },
                {
                    "alertId": "CT002",
                    "alertStatus": "TRIGGERED",
                    "comparisonType": "PRICE_WITH_VALUE",
                    "operator": "CROSSING_DOWN",
                    "comparingValue": 2400.0,
                    "expDate": "2026-12-31",
                    "frequency": "ONCE",
                    "orders": [],
                },
            ]
        },
    )
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    triggers = adapter.get_all_triggers()
    assert len(triggers) == 2
    assert triggers[0].alert_id == "CT001"
    assert triggers[1].alert_status == "TRIGGERED"


def test_place_conditional_trigger_validation(fake_client, resolver):
    """Verify comparing_value > 0."""
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    request = ConditionalTriggerRequest(
        symbol="RELIANCE",
        exchange="NSE",
        comparison_type="PRICE_WITH_VALUE",
        operator="CROSSING_UP",
        comparing_value=Decimal("-100.00"),  # Invalid
        exp_date="2026-12-31",
    )
    with pytest.raises(ValueError) as exc_info:
        adapter.place_trigger(request)
    assert "comparing_value" in str(exc_info.value).lower()


def test_place_conditional_trigger_validation_operator(fake_client, resolver):
    """Verify valid operator."""
    adapter = ConditionalTriggersAdapter(fake_client, resolver)
    request = ConditionalTriggerRequest(
        symbol="RELIANCE",
        exchange="NSE",
        comparison_type="PRICE_WITH_VALUE",
        operator="INVALID_OPERATOR",  # Invalid
        comparing_value=Decimal("2500.00"),
        exp_date="2026-12-31",
    )
    with pytest.raises(ValueError) as exc_info:
        adapter.place_trigger(request)
    assert "operator" in str(exc_info.value).lower()
