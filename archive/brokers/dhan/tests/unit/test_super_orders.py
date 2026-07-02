"""Unit tests for SuperOrdersAdapter."""

from decimal import Decimal

import pytest

from brokers.dhan.super_orders import SuperOrdersAdapter


def test_place_super_order_payload(fake_client, resolver):
    """Verify POST /super/orders payload structure."""
    fake_client.set_response("POST", "/super/orders", {"data": {"orderId": "SO123456"}})
    adapter = SuperOrdersAdapter(fake_client, resolver)
    adapter.place_super_order(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=10,
        price=Decimal("2450.00"),
        target_price=Decimal("2500.00"),
        stop_loss_price=Decimal("2400.00"),
        trailing_jump=Decimal("5.00"),
        product_type="INTRADAY",
        order_type="LIMIT",
    )
    payloads = fake_client.calls_for("POST", "/super/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["dhanClientId"] == "TEST_CLIENT"
    assert payload["securityId"] == "2885"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["transactionType"] == "BUY"
    assert payload["orderType"] == "LIMIT"
    assert payload["productType"] == "INTRADAY"
    assert payload["quantity"] == 10
    assert payload["price"] == 2450.00
    assert payload["targetPrice"] == 2500.00
    assert payload["stopLossPrice"] == 2400.00
    assert payload["trailingJump"] == 5.00


def test_place_super_order_returns_super_order(fake_client, resolver):
    """Verify response parsing."""
    fake_client.set_response(
        "POST",
        "/super/orders",
        {
            "data": {
                "orderId": "SO789012",
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "transactionType": "BUY",
                "quantity": 10,
                "price": 2450.0,
                "targetPrice": 2500.0,
                "stopLossPrice": 2400.0,
                "trailingJump": 5.0,
                "orderStatus": "OPEN",
                "legDetails": [
                    {
                        "legName": "ENTRY_LEG",
                        "transactionType": "BUY",
                        "quantity": 10,
                        "price": 2450.0,
                        "orderStatus": "OPEN",
                    },
                    {
                        "legName": "TARGET_LEG",
                        "transactionType": "SELL",
                        "quantity": 10,
                        "price": 2500.0,
                        "orderStatus": "PENDING",
                    },
                    {
                        "legName": "STOP_LOSS_LEG",
                        "transactionType": "SELL",
                        "quantity": 10,
                        "price": 2400.0,
                        "triggerPrice": 2410.0,
                        "orderStatus": "PENDING",
                    },
                ],
            }
        },
    )
    adapter = SuperOrdersAdapter(fake_client, resolver)
    order = adapter.place_super_order(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=10,
        price=Decimal("2450.00"),
        target_price=Decimal("2500.00"),
        stop_loss_price=Decimal("2400.00"),
        trailing_jump=Decimal("5.00"),
        product_type="INTRADAY",
        order_type="LIMIT",
    )
    assert order.order_id == "SO789012"
    assert order.trading_symbol == "RELIANCE"
    assert order.exchange_segment == "NSE_EQ"
    assert order.transaction_type == "BUY"
    assert order.quantity == 10
    assert order.price == Decimal("2450.00")
    assert order.target_price == Decimal("2500.00")
    assert order.stop_loss_price == Decimal("2400.00")
    assert order.trailing_jump == Decimal("5.00")
    assert order.order_status == "OPEN"
    assert len(order.leg_details) == 3
    assert order.leg_details[0].leg_name == "ENTRY_LEG"
    assert order.leg_details[1].leg_name == "TARGET_LEG"
    assert order.leg_details[2].leg_name == "STOP_LOSS_LEG"


def test_modify_super_order_entry_leg(fake_client, resolver):
    """Verify PUT /super/orders/{id} with ENTRY_LEG."""
    fake_client.set_response(
        "PUT",
        "/super/orders/SO123456",
        {
            "data": {
                "orderId": "SO123456",
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "transactionType": "BUY",
                "quantity": 20,
                "price": 2460.0,
                "targetPrice": 2510.0,
                "stopLossPrice": 2410.0,
                "trailingJump": 5.0,
                "orderStatus": "OPEN",
                "legDetails": [],
            }
        },
    )
    adapter = SuperOrdersAdapter(fake_client, resolver)
    order = adapter.modify_super_order(
        order_id="SO123456",
        leg_name="ENTRY_LEG",
        quantity=20,
        price=Decimal("2460.00"),
    )
    payloads = fake_client.calls_for("PUT", "/super/orders/SO123456")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["legName"] == "ENTRY_LEG"
    assert payload["quantity"] == 20
    assert payload["price"] == 2460.0
    assert order.order_id == "SO123456"
    assert order.quantity == 20


def test_cancel_super_order_entry_leg(fake_client, resolver):
    """Verify DELETE /super/orders/{id}/ENTRY_LEG."""
    fake_client.set_response("DELETE", "/super/orders/SO123456/ENTRY_LEG", {"status": "success"})
    adapter = SuperOrdersAdapter(fake_client, resolver)
    result = adapter.cancel_super_order_leg("SO123456", "ENTRY_LEG")
    assert result.success is True
    assert result.order_id == "SO123456"
    calls = fake_client.calls_for("DELETE", "/super/orders/SO123456/ENTRY_LEG")
    assert len(calls) == 1


def test_cancel_super_order_target_leg(fake_client, resolver):
    """Verify DELETE with TARGET_LEG."""
    fake_client.set_response("DELETE", "/super/orders/SO123456/TARGET_LEG", {"status": "success"})
    adapter = SuperOrdersAdapter(fake_client, resolver)
    result = adapter.cancel_super_order_leg("SO123456", "TARGET_LEG")
    assert result.success is True
    assert result.order_id == "SO123456"


def test_get_super_order_list(fake_client, resolver):
    """Verify GET /super/orders parsing."""
    fake_client.set_response(
        "GET",
        "/super/orders",
        {
            "data": [
                {
                    "orderId": "SO001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 10,
                    "price": 2450.0,
                    "targetPrice": 2500.0,
                    "stopLossPrice": 2400.0,
                    "trailingJump": 5.0,
                    "orderStatus": "OPEN",
                    "legDetails": [],
                },
                {
                    "orderId": "SO002",
                    "tradingSymbol": "TCS",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "SELL",
                    "quantity": 5,
                    "price": 3900.0,
                    "targetPrice": 3850.0,
                    "stopLossPrice": 3950.0,
                    "trailingJump": 10.0,
                    "orderStatus": "CLOSED",
                    "legDetails": [],
                },
            ]
        },
    )
    adapter = SuperOrdersAdapter(fake_client, resolver)
    orders = adapter.get_super_orders()
    assert len(orders) == 2
    assert orders[0].order_id == "SO001"
    assert orders[0].trading_symbol == "RELIANCE"
    assert orders[1].order_id == "SO002"
    assert orders[1].order_status == "CLOSED"


def test_place_super_order_validation_target_buy(fake_client, resolver):
    """Verify target_price > price for BUY."""
    adapter = SuperOrdersAdapter(fake_client, resolver)
    with pytest.raises(ValueError) as exc_info:
        adapter.place_super_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            price=Decimal("2450.00"),
            target_price=Decimal("2400.00"),  # Below entry - invalid
            stop_loss_price=Decimal("2400.00"),
            trailing_jump=Decimal("5.00"),
            product_type="INTRADAY",
            order_type="LIMIT",
        )
    assert "target_price" in str(exc_info.value).lower()


def test_place_super_order_validation_sl_buy(fake_client, resolver):
    """Verify stop_loss_price < price for BUY."""
    adapter = SuperOrdersAdapter(fake_client, resolver)
    with pytest.raises(ValueError) as exc_info:
        adapter.place_super_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            price=Decimal("2450.00"),
            target_price=Decimal("2500.00"),
            stop_loss_price=Decimal("2500.00"),  # Above entry - invalid
            trailing_jump=Decimal("5.00"),
            product_type="INTRADAY",
            order_type="LIMIT",
        )
    assert "stop_loss_price" in str(exc_info.value).lower()


def test_place_super_order_validation_target_sell(fake_client, resolver):
    """Verify target_price < price for SELL."""
    adapter = SuperOrdersAdapter(fake_client, resolver)
    with pytest.raises(ValueError) as exc_info:
        adapter.place_super_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="SELL",
            quantity=10,
            price=Decimal("2450.00"),
            target_price=Decimal("2500.00"),  # Above entry - invalid
            stop_loss_price=Decimal("2400.00"),
            trailing_jump=Decimal("5.00"),
            product_type="INTRADAY",
            order_type="LIMIT",
        )
    assert "target_price" in str(exc_info.value).lower()


def test_place_super_order_validation_sl_sell(fake_client, resolver):
    """Verify stop_loss_price > price for SELL."""
    adapter = SuperOrdersAdapter(fake_client, resolver)
    with pytest.raises(ValueError) as exc_info:
        adapter.place_super_order(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="SELL",
            quantity=10,
            price=Decimal("2450.00"),
            target_price=Decimal("2400.00"),
            stop_loss_price=Decimal("2400.00"),  # Below entry - invalid
            trailing_jump=Decimal("5.00"),
            product_type="INTRADAY",
            order_type="LIMIT",
        )
    assert "stop_loss_price" in str(exc_info.value).lower()
