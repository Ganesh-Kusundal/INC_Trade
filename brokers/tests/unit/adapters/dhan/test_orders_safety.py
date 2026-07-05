"""Unit tests for Dhan order safety — idempotency, cancel semantics, validation."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.adapters.dhan.identity import DhanInstrumentRef
from brokers.adapters.dhan.orders import DhanOrders
from inc_trade.domain import OrderResponse
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side
from inc_trade.utils.idempotency_cache import TypedIdempotencyCache


def _equity_ref(symbol: str = "RELIANCE", lot_size: int = 1) -> DhanInstrumentRef:
    return DhanInstrumentRef(
        symbol=symbol,
        security_id="2885",
        exchange_segment="NSE_EQ",
        lot_size=lot_size,
    )


def _fno_ref(symbol: str = "NIFTY", lot_size: int = 50) -> DhanInstrumentRef:
    return DhanInstrumentRef(
        symbol=symbol,
        security_id="35000",
        exchange_segment="NSE_FNO",
        lot_size=lot_size,
    )


def _orders(client=None, resolver=None, **kwargs) -> DhanOrders:
    client = client or MagicMock()
    resolver = resolver or MagicMock()
    resolver.resolve.return_value = _equity_ref()
    return DhanOrders(client, resolver, **kwargs)


class TestDhanOrderIdempotency:
    def test_correlation_id_prevents_duplicate_post(self):
        client = MagicMock()
        client.client_id = "cid"
        client.post.return_value = {"orderId": "ORD1", "orderStatus": "OPEN"}
        orders = _orders(client)

        r1 = orders.place_order("RELIANCE", "NSE", Side.BUY, 10, correlation_id="corr-abc")
        r2 = orders.place_order("RELIANCE", "NSE", Side.BUY, 10, correlation_id="corr-abc")
        assert r1.success
        assert r2.order_id == r1.order_id
        assert client.post.call_count == 1

    def test_validation_failure_not_cached(self):
        client = MagicMock()
        client.client_id = "cid"
        resolver = MagicMock()
        resolver.resolve.return_value = _fno_ref(lot_size=50)
        orders = DhanOrders(client, resolver)

        resp = orders.place_order(
            "NIFTY",
            "NFO",
            Side.BUY,
            25,
            correlation_id="corr-lot",
        )
        assert not resp.success
        assert orders.idempotency_cache.get("corr-lot") is None
        client.post.assert_not_called()

    def test_idempotency_cache_exposed(self):
        cache = TypedIdempotencyCache[OrderResponse]()
        orders = _orders(idempotency_cache=cache)
        assert orders.idempotency_cache is cache


class TestKillSwitchAndSlice:
    def test_kill_switch_posts_action(self):
        client = MagicMock()
        client.client_id = "cid"
        client.post.return_value = {"status": "success"}
        orders = _orders(client)
        assert orders.kill_switch(True) is True
        client.post.assert_called_once()
        assert "ACTIVATE" in client.post.call_args[0][0]

    def test_place_slice_order_uses_slice_endpoint(self):
        client = MagicMock()
        client.client_id = "cid"
        client.post.return_value = {"orderId": "SL1", "orderStatus": "OPEN"}
        orders = _orders(client)
        resp = orders.place_slice_order("RELIANCE", "NSE", Side.BUY, 1000, correlation_id="slice-1")
        assert resp.success
        assert "slice" in client.post.call_args[0][0]


class TestDhanCancelOrder:
    def test_cancel_uses_delete_and_parses_status(self):
        client = MagicMock()
        client.client_id = "cid"
        client.delete.return_value = {"status": "success", "message": "ok"}
        orders = _orders(client)
        orders.get_order = MagicMock(return_value=None)

        resp = orders.cancel_order("ORD99")
        assert resp.success
        client.delete.assert_called_once()
        client.post.assert_not_called()

    def test_cancel_failure_on_broker_error(self):
        client = MagicMock()
        client.delete.return_value = {
            "status": "error",
            "errorMessage": "unknown order",
            "errorCode": "DH-404",
        }
        orders = _orders(client)
        resp = orders.cancel_order("BAD")
        assert not resp.success
        assert resp.error_code == "DH-404"

    def test_cancel_race_already_filled(self):
        from inc_trade.domain import Order

        client = MagicMock()
        client.delete.return_value = {"status": "success"}
        orders = _orders(client)
        orders.get_order = MagicMock(
            return_value=Order(
                order_id="ORD1",
                symbol="R",
                exchange="NSE",
                side=Side.BUY,
                quantity=1,
                status=OrderStatus.FILLED,
            )
        )
        resp = orders.cancel_order("ORD1")
        assert not resp.success
        assert resp.error_code == "ORDER_ALREADY_FILLED"
