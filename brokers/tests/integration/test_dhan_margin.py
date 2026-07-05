from decimal import Decimal
from unittest.mock import Mock

from brokers.adapters.dhan.extensions.margin import DhanMargin
from brokers.adapters.dhan.extensions.models import MarginResponse
from inc_trade.domain.enums import OrderType, ProductType


def test_calculate_margin():
    client = Mock()
    client.post.return_value = {
        "data": {
            "totalMargin": 50000.0,
            "orderMargin": 45000.0,
            "exposureMargin": 5000.0,
            "availableMargin": 100000.0,
        }
    }

    resolver = Mock()
    ref = Mock()
    ref.exchange_segment = "NSE_EQ"
    ref.security_id_str.return_value = "1333"
    resolver.resolve.return_value = ref

    adapter = DhanMargin(client, resolver)

    resp = adapter.calculate_margin(
        symbol="HDFC",
        exchange="NSE",
        quantity=100,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        price=Decimal("1500.50"),
    )

    assert isinstance(resp, MarginResponse)
    assert resp.total_margin == Decimal("50000")

    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    payload = kwargs["json"]

    assert payload["quantity"] == 100
    assert payload["price"] == 1500.50
    assert payload["orderType"] == 2  # LIMIT
    assert payload["productType"] == "INTRADAY"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["securityId"] == "1333"
