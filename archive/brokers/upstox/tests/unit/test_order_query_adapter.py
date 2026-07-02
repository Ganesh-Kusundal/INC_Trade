"""Tests for UpstoxOrderQueryAdapter."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_query_adapter import UpstoxOrderQueryAdapter


def _make_adapter(client: UpstoxRestOrderClient | None = None):
    return UpstoxOrderQueryAdapter(
        order_client=client or MagicMock(spec=UpstoxRestOrderClient),
        instrument_resolver=MagicMock(),
    )


class TestGetOrderDataShape:
    """get_order must handle V2 list data and V3 dict data."""

    def test_data_is_list_uses_first_element(self):
        order_row = {"order_id": "O1", "status": "COMPLETED"}
        adapter = _make_adapter()
        adapter._order_client.get_order.return_value = {"data": [order_row]}

        result = adapter.get_order("O1")

        assert result is not None
        assert result.order_id == "O1"

    def test_data_is_dict_uses_directly(self):
        order_row = {"order_id": "O2", "status": "PLACED"}
        adapter = _make_adapter()
        adapter._order_client.get_order.return_value = {"data": order_row}

        result = adapter.get_order("O2")

        assert result is not None
        assert result.order_id == "O2"

    def test_data_is_empty_list_returns_none(self):
        adapter = _make_adapter()
        adapter._order_client.get_order.return_value = {"data": []}

        assert adapter.get_order("O1") is None

    def test_data_is_none_returns_none(self):
        adapter = _make_adapter()
        adapter._order_client.get_order.return_value = {"data": None}

        assert adapter.get_order("O1") is None

    def test_body_not_dict_returns_none(self):
        adapter = _make_adapter()
        adapter._order_client.get_order.return_value = "error"

        assert adapter.get_order("O1") is None

    def test_body_without_data_key_returns_none(self):
        adapter = _make_adapter()
        adapter._order_client.get_order.return_value = {"status": "error"}

        assert adapter.get_order("O1") is None


class TestGetTradesForOrder:
    """get_trades_for_order should call get_trades_by_order, not get_trades."""

    def test_calls_get_trades_by_order(self):
        adapter = _make_adapter()
        trade_row = {"trade_id": "T1", "order_id": "O1", "quantity": 5}
        adapter._order_client.get_trades_by_order.return_value = [trade_row]

        result = adapter.get_trades_for_order("O1")

        adapter._order_client.get_trades_by_order.assert_called_once_with("O1")
        assert len(result) == 1
        assert result[0].order_id == "O1"

    def test_empty_trades(self):
        adapter = _make_adapter()
        adapter._order_client.get_trades_by_order.return_value = []

        result = adapter.get_trades_for_order("O1")

        assert result == []

    def test_filters_non_dict_entries(self):
        adapter = _make_adapter()
        adapter._order_client.get_trades_by_order.return_value = [
            {"trade_id": "T1", "order_id": "O1"},
            "invalid",
            None,
        ]

        result = adapter.get_trades_for_order("O1")

        assert len(result) == 1
        assert result[0].order_id == "O1"
