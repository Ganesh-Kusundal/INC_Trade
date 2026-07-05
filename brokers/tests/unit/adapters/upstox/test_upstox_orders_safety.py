"""Unit tests for Upstox order safety guards."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.adapters.upstox.orders import UpstoxOrders
from inc_trade.config.endpoints import Upstox
from inc_trade.domain import Order, OrderResponse
from inc_trade.domain.enums import OrderStatus, Side
from inc_trade.utils.idempotency_cache import TypedIdempotencyCache as InMemoryIdempotencyCache


def _orders(client=None, **kwargs) -> UpstoxOrders:
    return UpstoxOrders(client or MagicMock(), Upstox.production(), **kwargs)


class TestOrderSafetyGuards:
    def test_analytics_only_blocks_place(self):
        orders = _orders(analytics_only=True)
        resp = orders.place_order("RELIANCE", "NSE", Side.BUY, 1)
        assert not resp.success
        assert resp.error_code == "ANALYTICS_ONLY"

    def test_correlation_id_idempotency(self):
        client = MagicMock()
        client.post.return_value = {
            "status": "success",
            "data": {"order_id": "123"},
        }
        cache = InMemoryIdempotencyCache[OrderResponse]()
        orders = UpstoxOrders(client, Upstox.production(), idempotency_cache=cache)

        r1 = orders.place_order("RELIANCE", "NSE", Side.BUY, 1, correlation_id="corr-1")
        r2 = orders.place_order("RELIANCE", "NSE", Side.BUY, 1, correlation_id="corr-1")
        assert r1.success
        assert r2 is r1 or r2.order_id == r1.order_id
        assert client.post.call_count == 1

    def test_cancel_already_executed(self):
        client = MagicMock()
        client.delete.return_value = {"status": "success"}
        client.get.return_value = {
            "data": {
                "order_id": "99",
                "status": "complete",
                "trading_symbol": "RELIANCE",
                "transaction_type": "BUY",
                "quantity": 1,
            }
        }
        orders = UpstoxOrders(client, Upstox.production())
        orders.get_order = MagicMock(
            return_value=Order(
                order_id="99",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=1,
                status=OrderStatus.FILLED,
            )
        )
        resp = orders.cancel_order("99")
        assert not resp.success
        assert resp.error_code == "ALREADY_EXECUTED"
