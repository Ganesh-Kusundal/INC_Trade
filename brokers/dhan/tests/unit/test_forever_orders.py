"""Unit tests for ForeverOrdersAdapter."""

from decimal import Decimal

import pytest

from brokers.dhan.domain import ForeverOrderRequest
from brokers.dhan.forever_orders import ForeverOrdersAdapter


def test_place_forever_order_single(fake_client, resolver):
    """Verify SINGLE mode payload."""
    fake_client.set_response("POST", "/forever/orders", {"data": {"orderId": "FO123456"}})
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    request = ForeverOrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        order_flag="SINGLE",
        transaction_type="BUY",
        product_type="CNC",
        order_type="LIMIT",
        quantity=10,
        price=Decimal("2450.00"),
        trigger_price=Decimal("2460.00"),
    )
    order = adapter.place_forever_order(request)

    payloads = fake_client.calls_for("POST", "/forever/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["dhanClientId"] == "TEST_CLIENT"
    assert payload["securityId"] == "2885"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["orderFlag"] == "SINGLE"
    assert payload["transactionType"] == "BUY"
    assert payload["productType"] == "CNC"
    assert payload["orderType"] == "LIMIT"
    assert payload["quantity"] == 10
    assert payload["price"] == 2450.00
    assert payload["triggerPrice"] == 2460.00
    assert order.order_id == "FO123456"


def test_place_forever_order_oco(fake_client, resolver):
    """Verify OCO mode with price1/trigger_price1/quantity1."""
    fake_client.set_response(
        "POST",
        "/forever/orders",
        {
            "data": {
                "orderId": "FO789012",
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "orderFlag": "OCO",
                "transactionType": "BUY",
                "quantity": 10,
                "price": 2450.0,
                "triggerPrice": 2460.0,
                "orderStatus": "OPEN",
            }
        },
    )
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    request = ForeverOrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        order_flag="OCO",
        transaction_type="BUY",
        product_type="CNC",
        order_type="LIMIT",
        quantity=10,
        price=Decimal("2450.00"),
        trigger_price=Decimal("2460.00"),
        price1=Decimal("2500.00"),
        trigger_price1=Decimal("2490.00"),
        quantity1=10,
    )
    order = adapter.place_forever_order(request)

    payloads = fake_client.calls_for("POST", "/forever/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["orderFlag"] == "OCO"
    assert payload["price1"] == 2500.00
    assert payload["triggerPrice1"] == 2490.00
    assert payload["quantity1"] == 10
    assert order.order_id == "FO789012"


def test_modify_forever_order(fake_client, resolver):
    """Verify PUT /forever/orders/{id}."""
    fake_client.set_response(
        "PUT",
        "/forever/orders/FO123456",
        {
            "data": {
                "orderId": "FO123456",
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "orderFlag": "SINGLE",
                "transactionType": "BUY",
                "quantity": 20,
                "price": 2470.0,
                "triggerPrice": 2480.0,
                "orderStatus": "OPEN",
            }
        },
    )
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    request = ForeverOrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        order_flag="SINGLE",
        transaction_type="BUY",
        product_type="CNC",
        order_type="LIMIT",
        quantity=20,
        price=Decimal("2470.00"),
        trigger_price=Decimal("2480.00"),
    )
    order = adapter.modify_forever_order("FO123456", request)

    payloads = fake_client.calls_for("PUT", "/forever/orders/FO123456")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["quantity"] == 20
    assert payload["price"] == 2470.00
    assert order.order_id == "FO123456"
    assert order.quantity == 20


def test_cancel_forever_order(fake_client, resolver):
    """Verify DELETE /forever/orders/{id}."""
    fake_client.set_response("DELETE", "/forever/orders/FO123456", {"status": "success"})
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    result = adapter.cancel_forever_order("FO123456")
    assert result.success is True
    assert result.order_id == "FO123456"
    calls = fake_client.calls_for("DELETE", "/forever/orders/FO123456")
    assert len(calls) == 1


def test_get_all_forever_orders(fake_client, resolver):
    """Verify GET /forever/all."""
    fake_client.set_response(
        "GET",
        "/forever/all",
        {
            "data": [
                {
                    "orderId": "FO001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "orderFlag": "SINGLE",
                    "transactionType": "BUY",
                    "quantity": 10,
                    "price": 2450.0,
                    "triggerPrice": 2460.0,
                    "orderStatus": "OPEN",
                },
                {
                    "orderId": "FO002",
                    "tradingSymbol": "TCS",
                    "exchangeSegment": "NSE_EQ",
                    "orderFlag": "OCO",
                    "transactionType": "SELL",
                    "quantity": 5,
                    "price": 3900.0,
                    "triggerPrice": 3890.0,
                    "orderStatus": "CLOSED",
                },
            ]
        },
    )
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    orders = adapter.get_all_forever_orders()
    assert len(orders) == 2
    assert orders[0].order_id == "FO001"
    assert orders[0].trading_symbol == "RELIANCE"
    assert orders[1].order_id == "FO002"
    assert orders[1].order_status == "CLOSED"


def test_place_forever_order_validation_oco(fake_client, resolver):
    """Verify OCO requires price1, trigger_price1, quantity1."""
    adapter = ForeverOrdersAdapter(fake_client, resolver)
    request = ForeverOrderRequest(
        symbol="RELIANCE",
        exchange="NSE",
        order_flag="OCO",
        transaction_type="BUY",
        product_type="CNC",
        order_type="LIMIT",
        quantity=10,
        price=Decimal("2450.00"),
        trigger_price=Decimal("2460.00"),
        # Missing price1, trigger_price1, quantity1
    )
    with pytest.raises(ValueError) as exc_info:
        adapter.place_forever_order(request)
    assert "OCO" in str(exc_info.value)
