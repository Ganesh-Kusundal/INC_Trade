"""Risk manager and event bus parity tests for DhanOrders."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.domain import RiskCheckRequest, RiskCheckResult
from brokers.domain.enums import Side
from brokers.infrastructure.event_bus import EventBus

from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.adapters.dhan.orders import DhanOrders


def _equity_ref() -> DhanInstrumentRef:
    return DhanInstrumentRef(
        symbol="RELIANCE",
        security_id="2885",
        exchange_segment="NSE_EQ",
    )


class _BlockingRiskManager:
    def get_status(self) -> dict[str, str]:
        return {}

    def is_kill_switch_active(self) -> bool:
        return False

    def check_order(self, order_request: RiskCheckRequest) -> RiskCheckResult:
        return RiskCheckResult(allowed=False, reason="max exposure exceeded")


def test_place_order_publishes_event():
    client = MagicMock()
    client.client_id = "cid"
    client.post.return_value = {"orderId": "ORD123", "orderStatus": "OPEN"}
    resolver = MagicMock()
    resolver.resolve.return_value = _equity_ref()
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))
    orders = DhanOrders(client, resolver, event_bus=bus)
    resp = orders.place_order("RELIANCE", "NSE", Side.BUY, 1, correlation_id="c1")
    assert resp.success
    assert len(received) == 1
    assert received[0].order.order_id == "ORD123"


def test_place_order_idempotency_does_not_publish_duplicate():
    client = MagicMock()
    client.client_id = "cid"
    client.post.return_value = {"orderId": "ORD123", "orderStatus": "OPEN"}
    resolver = MagicMock()
    resolver.resolve.return_value = _equity_ref()
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))
    orders = DhanOrders(client, resolver, event_bus=bus)
    orders.place_order("RELIANCE", "NSE", Side.BUY, 1, correlation_id="c1")
    orders.place_order("RELIANCE", "NSE", Side.BUY, 1, correlation_id="c1")
    assert client.post.call_count == 1
    assert len(received) == 1


def test_risk_manager_blocks_order():
    client = MagicMock()
    client.client_id = "cid"
    resolver = MagicMock()
    resolver.resolve.return_value = _equity_ref()
    orders = DhanOrders(
        client,
        resolver,
        risk_manager=_BlockingRiskManager(),
    )
    resp = orders.place_order(
        "RELIANCE",
        "NSE",
        Side.BUY,
        1,
        price=Decimal("2500"),
        correlation_id="risk-1",
    )
    assert not resp.success
    assert "Risk check failed" in resp.message
    client.post.assert_not_called()
