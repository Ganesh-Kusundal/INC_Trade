from decimal import Decimal
from unittest.mock import Mock

from brokers.adapters.dhan.extensions.forever_orders import DhanForeverOrders
from brokers.adapters.dhan.extensions.models import ForeverOrder
from inc_trade.domain.enums import Side


def test_place_forever_order_single():
    client = Mock()
    client.post.return_value = {
        "orderId": "F123",
        "orderStatus": "PENDING",
        "orderFlag": "SINGLE",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "securityId": "11536",
        "quantity": 50,
        "price": 2500.0,
        "triggerPrice": 2510.0,
    }

    resolver = Mock()
    ref = Mock()
    ref.exchange_segment = "NSE_EQ"
    ref.security_id_str.return_value = "11536"
    resolver.resolve.return_value = ref

    adapter = DhanForeverOrders(client, resolver)

    order = adapter.place_forever_order(
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": Side.BUY,
            "quantity": 50,
            "price": Decimal("2500"),
            "trigger_price": Decimal("2510"),
            "order_flag": "SINGLE",
        }
    )

    assert isinstance(order, ForeverOrder)
    assert order.order_id == "F123"
    assert order.order_flag == "SINGLE"

    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    payload = kwargs["json"]

    assert payload["quantity"] == 50
    assert payload["price"] == 2500.0
    assert payload["triggerPrice"] == 2510.0
    assert payload["orderFlag"] == "SINGLE"
    assert payload["transactionType"] == 1
