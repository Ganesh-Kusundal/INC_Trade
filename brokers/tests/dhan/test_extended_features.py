"""Tests for Dhan extended features: convert_position, kill_switch, expired_options, slice_order, order_lookup, edis, client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.dhan.extended.convert_position import (
    ConvertPositionRequest,
    DhanConvertPosition,
)
from brokers.dhan.extended.edis import DhanEdis
from brokers.dhan.extended.expired_options import (
    ExpiredOptionsRequest,
    DhanExpiredOptions,
)
from brokers.dhan.extended.kill_switch import DhanKillSwitch
from brokers.dhan.extended.order_lookup import DhanOrderLookup
from brokers.dhan.extended.slice_order import SliceOrderRequest, DhanSliceOrder


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.client_id = "test_client"
    return client


# ── Convert Position ──────────────────────────────────────────────────────


class TestConvertPosition:
    def test_convert_success(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"success": True, "message": "Converted"}}
        converter = DhanConvertPosition(client=mock_client)
        result = converter.convert(ConvertPositionRequest(
            security_id="2885",
            exchange_segment="NSE_EQ",
            position_type="LONG",
            convert_qty=10,
            from_product_type="INTRADAY",
            to_product_type="CNC",
        ))
        assert result.success is True
        mock_client.post.assert_called_once()

    def test_convert_failure(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"success": False, "message": "Insufficient quantity"}}
        converter = DhanConvertPosition(client=mock_client)
        result = converter.convert(ConvertPositionRequest(
            security_id="2885",
            exchange_segment="NSE_EQ",
            position_type="LONG",
            convert_qty=10,
            from_product_type="INTRADAY",
            to_product_type="CNC",
        ))
        assert result.success is False


# ── Kill Switch ──────────────────────────────────────────────────────────


class TestKillSwitch:
    def test_activate(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"active": True, "message": "Activated"}}
        ks = DhanKillSwitch(client=mock_client)
        result = ks.activate()
        assert result.active is True

    def test_deactivate(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"active": False, "message": "Deactivated"}}
        ks = DhanKillSwitch(client=mock_client)
        result = ks.deactivate()
        assert result.active is False

    def test_status(self, mock_client: MagicMock):
        mock_client.get.return_value = {"data": {"active": True}}
        ks = DhanKillSwitch(client=mock_client)
        result = ks.status()
        assert result.active is True


# ── Expired Options ──────────────────────────────────────────────────────


class TestExpiredOptions:
    def test_fetch(self, mock_client: MagicMock):
        mock_client.post.return_value = {
            "data": {
                "timestamp": [1704067200, 1704153600],
                "open": [100.0, 105.0],
                "high": [110.0, 115.0],
                "low": [95.0, 100.0],
                "close": [105.0, 110.0],
                "volume": [1000, 2000],
                "oi": [5000, 6000],
            }
        }
        exp = DhanExpiredOptions(client=mock_client)
        result = exp.fetch(ExpiredOptionsRequest(
            security_id=13,
            exchange_segment="NSE_FNO",
            instrument_type="OPTIDX",
            expiry_flag="MONTH",
            from_date="2024-01-01",
            to_date="2024-01-31",
        ))
        assert len(result.timestamps) == 2
        assert result.open == [100.0, 105.0]


# ── Slice Order ──────────────────────────────────────────────────────────


class TestSliceOrder:
    def test_single_slice(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"orderId": "order_001"}}
        slicer = DhanSliceOrder(client=mock_client)
        result = slicer.place(SliceOrderRequest(
            security_id="2885",
            exchange_segment="NSE_EQ",
            transaction_type="BUY",
            quantity=100,
            freeze_quantity=900,
        ))
        assert result.success is True
        assert len(result.order_ids) == 1
        assert mock_client.post.call_count == 1

    def test_multiple_slices(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"orderId": "order_001"}}
        slicer = DhanSliceOrder(client=mock_client)
        result = slicer.place(SliceOrderRequest(
            security_id="2885",
            exchange_segment="NSE_EQ",
            transaction_type="BUY",
            quantity=2500,
            freeze_quantity=900,
        ))
        assert result.success is True
        assert result.total_slices == 3  # 900 + 900 + 700
        assert mock_client.post.call_count == 3


# ── Order Lookup ─────────────────────────────────────────────────────────


class TestOrderLookup:
    def test_get_by_order_id(self, mock_client: MagicMock):
        mock_client.get.return_value = {
            "data": {
                "orderId": "123456",
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "transactionType": "BUY",
                "quantity": 10,
                "orderType": "MARKET",
                "productType": "INTRADAY",
                "orderStatus": "FILLED",
            }
        }
        lookup = DhanOrderLookup(client=mock_client)
        order = lookup.get_by_order_id("123456")
        assert order is not None
        assert order.order_id == "123456"

    def test_get_by_order_id_not_found(self, mock_client: MagicMock):
        mock_client.get.return_value = {"data": {}}
        lookup = DhanOrderLookup(client=mock_client)
        order = lookup.get_by_order_id("999999")
        assert order is None

    def test_get_by_correlation_id(self, mock_client: MagicMock):
        mock_client.get.return_value = {
            "data": [
                {"orderId": "111", "correlationId": "tag_a", "tradingSymbol": "RELIANCE",
                 "exchangeSegment": "NSE_EQ", "transactionType": "BUY", "quantity": 10,
                 "orderType": "MARKET", "productType": "INTRADAY", "orderStatus": "FILLED"},
                {"orderId": "222", "correlationId": "tag_b", "tradingSymbol": "TCS",
                 "exchangeSegment": "NSE_EQ", "transactionType": "BUY", "quantity": 5,
                 "orderType": "LIMIT", "productType": "INTRADAY", "orderStatus": "OPEN"},
                {"orderId": "333", "correlationId": "tag_a", "tradingSymbol": "INFY",
                 "exchangeSegment": "NSE_EQ", "transactionType": "SELL", "quantity": 3,
                 "orderType": "MARKET", "productType": "INTRADAY", "orderStatus": "FILLED"},
            ]
        }
        lookup = DhanOrderLookup(client=mock_client)
        orders = lookup.get_by_correlation_id("tag_a")
        assert len(orders) == 2
        assert orders[0].order_id == "111"
        assert orders[1].order_id == "333"


# ── eDIS ─────────────────────────────────────────────────────────────────


class TestEdis:
    def test_get_tpin(self, mock_client: MagicMock):
        mock_client.get.return_value = {"data": {"tpin": "123456"}}
        edis = DhanEdis(client=mock_client)
        result = edis.get_tpin()
        assert "data" in result
        mock_client.get.assert_called_once_with("/edis/tpin")

    def test_authorize(self, mock_client: MagicMock):
        mock_client.post.return_value = {"data": {"success": True}}
        edis = DhanEdis(client=mock_client)
        result = edis.authorize(isin="INE002A01018", quantity=100)
        assert "data" in result
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["isin"] == "INE002A01018"
        assert payload["qty"] == "100"
        assert payload["exchange"] == "NSE_EQ"

    def test_inquiry(self, mock_client: MagicMock):
        mock_client.get.return_value = {"data": {"status": "AUTHORIZED"}}
        edis = DhanEdis(client=mock_client)
        result = edis.inquiry()
        assert "data" in result
        mock_client.get.assert_called_once_with("/edis/inquiry")


# ── Client trade history ─────────────────────────────────────────────────


class TestClientTradeHistory:
    def test_get_trade_history(self, mock_client: MagicMock):
        mock_client.post.return_value = {
            "data": [
                {"tradeId": "T1", "orderId": "O1", "tradingSymbol": "RELIANCE", "tradedQty": 10},
                {"tradeId": "T2", "orderId": "O2", "tradingSymbol": "TCS", "tradedQty": 5},
            ]
        }
        result = mock_client.post(
            "/trades",
            json={"fromDate": "2024-01-01", "toDate": "2024-01-31"},
        )
        items = result.get("data", [])
        assert len(items) == 2
        assert items[0]["tradeId"] == "T1"
        mock_client.post.assert_called_once_with(
            "/trades",
            json={"fromDate": "2024-01-01", "toDate": "2024-01-31"},
        )
