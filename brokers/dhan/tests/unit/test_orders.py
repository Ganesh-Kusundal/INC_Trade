"""Unit tests for OrdersAdapter."""

from decimal import Decimal

import pytest

from brokers.common.dtos import BrokerOrderPayload
from brokers.dhan.domain import Exchange
from brokers.dhan.orders import OrdersAdapter
from domain import OrderStatus, Side
from infrastructure.event_bus import EventBus


def test_place_order_payload(fake_client, resolver):
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD123456"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    adapter.place_order(
        BrokerOrderPayload(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=10,
            order_type="MARKET",
            product_type="INTRADAY",
        )
    )
    payloads = fake_client.calls_for("POST", "/orders")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["dhanClientId"] == "TEST_CLIENT"
    assert payload["securityId"] == "2885"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["transactionType"] == "BUY"
    assert payload["orderType"] == "MARKET"
    assert payload["productType"] == "INTRADAY"
    assert payload["validity"] == "DAY"
    assert payload["quantity"] == 10


def test_place_order_returns_order(fake_client, resolver):
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD789012"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    order = adapter.place_order(
        BrokerOrderPayload(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=5,
        )
    )
    assert order.order_id == "ORD789012"
    assert order.symbol == "RELIANCE"
    assert order.status == OrderStatus.OPEN


def test_cancel_order(fake_client, resolver):
    fake_client.set_response("DELETE", "/orders/ORD123456", {"status": "success"})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    result = adapter.cancel_order("ORD123456")
    assert result.success is True
    assert result.order_id == "ORD123456"
    # Verify the correct endpoint was called
    assert fake_client.calls_for("DELETE", "/orders/ORD123456") is not None


def test_cancel_order_broker_error(fake_client, resolver):
    """When the broker returns a non-success status, the adapter must
    return a structured failure — not treat any dict as success."""
    fake_client.set_response(
        "DELETE",
        "/orders/ORD123456",
        {"status": "error", "errorCode": "DH-906", "errorMessage": "Invalid token"},
    )
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    result = adapter.cancel_order("ORD123456")
    assert result.success is False
    assert result.error_code == "DH-906"
    assert "Invalid token" in result.message


def test_get_orderbook_parsing(fake_client, resolver):
    fake_client.set_response(
        "GET",
        "/orders",
        {
            "data": [
                {
                    "orderId": "ORD001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 10,
                    "filledQty": 10,
                    "price": 2450.0,
                    "averagePrice": 2449.5,
                    "orderStatus": "COMPLETE",
                },
                {
                    "orderId": "ORD002",
                    "tradingSymbol": "NIFTY",
                    "exchangeSegment": "NSE_FNO",
                    "transactionType": "SELL",
                    "quantity": 75,
                    "filledQty": 0,
                    "price": 24600.0,
                    "averagePrice": None,
                    "orderStatus": "OPEN",
                },
            ]
        },
    )
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    orders = adapter.get_orderbook()
    assert len(orders) == 2

    first = orders[0]
    assert first.order_id == "ORD001"
    assert first.symbol == "RELIANCE"
    assert first.exchange == Exchange.NSE
    assert first.side == Side.BUY
    assert first.quantity == 10
    assert first.filled_quantity == 10
    assert first.price == Decimal("2450.0")
    assert first.average_price == Decimal("2449.5")
    assert first.status == OrderStatus.FILLED

    second = orders[1]
    assert second.order_id == "ORD002"
    assert second.side == Side.SELL
    assert second.status == OrderStatus.OPEN


def test_get_trade_book_parsing(fake_client, resolver):
    fake_client.set_response(
        "GET",
        "/trades",
        {
            "data": [
                {
                    "tradeId": "TRD001",
                    "orderId": "ORD001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "tradedQty": 10,
                    "tradedPrice": 2449.75,
                },
                {
                    "tradeId": "TRD002",
                    "orderId": "ORD002",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "SELL",
                    "tradedQty": 5,
                    "tradedPrice": 2460.0,
                },
            ]
        },
    )
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    trades = adapter.get_trade_book()
    assert len(trades) == 2

    first = trades[0]
    assert first.trade_id == "TRD001"
    assert first.order_id == "ORD001"
    assert first.symbol == "RELIANCE"
    assert first.exchange == Exchange.NSE
    assert first.side == Side.BUY
    assert first.quantity == 10
    assert first.price == Decimal("2449.75")

    second = trades[1]
    assert second.trade_id == "TRD002"
    assert second.side == Side.SELL
    assert second.quantity == 5
    assert second.price == Decimal("2460.0")


def test_kill_switch_url(fake_client, resolver):
    fake_client.set_response("POST", "/killswitch?killSwitchStatus=ACTIVATE", {"status": "success"})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    result = adapter.kill_switch(enable=True)
    assert result is True
    # Verify the exact URL with query param was used
    calls = fake_client.calls_for("POST", "/killswitch?killSwitchStatus=ACTIVATE")
    assert len(calls) == 1


def test_place_order_publishes_event(fake_client, resolver):
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD123"}})
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))
    adapter = OrdersAdapter(fake_client, resolver, event_bus=bus, allow_live_orders=True)
    adapter.place_order(
        BrokerOrderPayload(symbol="RELIANCE", exchange="NSE", transaction_type="BUY", quantity=1)
    )
    assert len(received) == 1
    assert received[0].payload["order"].order_id == "ORD123"


def test_place_order_idempotency_does_not_publish_duplicate(fake_client, resolver):
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD123"}})
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))
    adapter = OrdersAdapter(fake_client, resolver, event_bus=bus, allow_live_orders=True)
    adapter.place_order(
        BrokerOrderPayload(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            correlation_id="abc",
        )
    )
    adapter.place_order(
        BrokerOrderPayload(
            symbol="RELIANCE",
            exchange="NSE",
            transaction_type="BUY",
            quantity=1,
            correlation_id="abc",
        )
    )
    assert len(received) == 1
    assert len(fake_client.calls_for("POST", "/orders")) == 1


def test_place_order_risk_check_blocks_order(fake_client, resolver):
    from decimal import Decimal

    from application.oms.position_manager import PositionManager
    from application.oms.risk_manager import RiskConfig, RiskManager

    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD123"}})
    position_manager = PositionManager()
    risk = RiskManager(
        position_manager, RiskConfig(max_position_pct=Decimal("1")), lambda: Decimal("100000")
    )
    adapter = OrdersAdapter(fake_client, resolver, risk_manager=risk, allow_live_orders=True)

    with pytest.raises(Exception) as exc_info:
        adapter.place_order(
            BrokerOrderPayload(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1000,
                price=Decimal("100"),
                order_type="LIMIT",
            )
        )
    assert "Risk check failed" in str(exc_info.value)
    assert len(fake_client.calls_for("POST", "/orders")) == 0


def test_place_order_transport_only_does_not_bypass_risk_check(fake_client, resolver):
    """transport_only field has been removed — this test verifies that
    risk checks are always enforced regardless of any transport flags."""
    from decimal import Decimal

    from application.oms.position_manager import PositionManager
    from application.oms.risk_manager import RiskConfig, RiskManager

    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD123"}})
    position_manager = PositionManager()
    risk = RiskManager(
        position_manager,
        RiskConfig(max_position_pct=Decimal("1")),
        lambda: Decimal("100000"),
    )
    adapter = OrdersAdapter(fake_client, resolver, risk_manager=risk, allow_live_orders=True)

    with pytest.raises(Exception) as exc_info:
        adapter.place_order(
            BrokerOrderPayload(
                symbol="RELIANCE",
                exchange="NSE",
                transaction_type="BUY",
                quantity=1000,
                price=Decimal("100"),
                order_type="LIMIT",
            )
        )
    assert "Risk check failed" in str(exc_info.value)
    assert len(fake_client.calls_for("POST", "/orders")) == 0
    """Verify POST /sliceorder payload (same as regular order)."""
    fake_client.set_response("POST", "/sliceorder", {"data": {"orderId": "SLICE123"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    order = adapter.place_slice_order(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        quantity=1000,  # Large order for slicing
        order_type="LIMIT",
        price=Decimal("2450.00"),
        product_type="INTRADAY",
    )
    payloads = fake_client.calls_for("POST", "/sliceorder")
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["dhanClientId"] == "TEST_CLIENT"
    assert payload["securityId"] == "2885"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["quantity"] == 1000
    assert order.order_id == "SLICE123"


def test_get_trade_history_payload(fake_client, resolver):
    """Verify GET /trades/{from}/{to}/{page}."""
    fake_client.set_response(
        "GET",
        "/trades/2026-01-01/2026-01-31/0",
        {
            "data": [
                {
                    "tradeId": "TRD001",
                    "orderId": "ORD001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "tradedQty": 10,
                    "tradedPrice": 2449.75,
                },
            ]
        },
    )
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    trades = adapter.get_trade_history("2026-01-01", "2026-01-31", page=0)

    calls = fake_client.calls_for("GET", "/trades/2026-01-01/2026-01-31/0")
    assert calls is not None
    assert len(trades) == 1
    assert trades[0].trade_id == "TRD001"
    assert trades[0].symbol == "RELIANCE"


def test_get_trade_history_parsing(fake_client, resolver):
    """Verify response parsing to list[Trade]."""
    fake_client.set_response(
        "GET",
        "/trades/2026-01-01/2026-01-31/0",
        {
            "data": [
                {
                    "tradeId": "TRD001",
                    "orderId": "ORD001",
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "tradedQty": 10,
                    "tradedPrice": 2449.75,
                },
                {
                    "tradeId": "TRD002",
                    "orderId": "ORD002",
                    "tradingSymbol": "TCS",
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "SELL",
                    "tradedQty": 5,
                    "tradedPrice": 3900.00,
                },
            ]
        },
    )
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    trades = adapter.get_trade_history("2026-01-01", "2026-01-31")

    assert len(trades) == 2
    assert trades[0].quantity == 10
    assert trades[0].price == Decimal("2449.75")
    assert trades[1].side == Side.SELL


def test_get_trade_history_pagination(fake_client, resolver):
    """Verify page parameter handling."""
    fake_client.set_response("GET", "/trades/2026-01-01/2026-01-31/2", {"data": []})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    trades = adapter.get_trade_history("2026-01-01", "2026-01-31", page=2)

    calls = fake_client.calls_for("GET", "/trades/2026-01-01/2026-01-31/2")
    assert calls is not None
    assert len(trades) == 0
