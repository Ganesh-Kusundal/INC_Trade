"""Trade history pagination parity tests."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.adapters.dhan.orders import DhanOrders


def test_get_trade_history_pagination():
    client = MagicMock()
    client.client_id = "cid"
    client.get.return_value = {
        "data": [
            {
                "tradeId": "TRD001",
                "orderId": "ORD001",
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "transactionType": "BUY",
                "tradedQty": 10,
                "tradedPrice": 2449.75,
            }
        ]
    }
    resolver = MagicMock()
    orders = DhanOrders(client, resolver)
    trades = orders.get_trade_history("2026-01-01", "2026-01-31", page=2)
    assert len(trades) == 1
    assert trades[0].trade_id == "TRD001"
    assert trades[0].price == Decimal("2449.75")
    called_path = client.get.call_args[0][0]
    assert "/trades/2026-01-01/2026-01-31/2" in called_path


def test_get_trade_book_alias():
    client = MagicMock()
    client.client_id = "cid"
    client.get.return_value = {"data": []}
    orders = DhanOrders(client, MagicMock())
    assert orders.get_trade_book() == []
