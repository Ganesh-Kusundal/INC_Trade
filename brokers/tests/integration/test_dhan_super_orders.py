import pytest
from decimal import Decimal
from unittest.mock import Mock

from brokers.adapters.dhan.extensions.super_orders import DhanSuperOrders
from brokers.domain.enums import Side


def test_place_super_order_success():
    client = Mock()
    client.post.return_value = {
        "orderId": "12345",
        "orderStatus": "PENDING",
        "transactionType": "BUY",
        "legDetails": [{"legName": "ENTRY_LEG", "orderStatus": "PENDING"}],
    }

    resolver = Mock()
    ref = Mock()
    ref.exchange_segment = "NSE_EQ"
    ref.security_id_str.return_value = "11536"
    resolver.resolve.return_value = ref

    adapter = DhanSuperOrders(client, resolver)

    order = adapter.place_super_order(
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        target_price=Decimal("2600"),
        stop_loss_price=Decimal("2400"),
        trailing_jump=Decimal("10"),
    )

    assert order.order_id == "12345"
    assert len(order.leg_details) == 1
    assert order.leg_details[0].leg_name == "ENTRY_LEG"

    # Verify payload format (especially float serialization)
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    payload = kwargs["json"]

    assert payload["price"] == 2500.0
    assert payload["targetPrice"] == 2600.0
    assert payload["stopLossPrice"] == 2400.0
    assert payload["trailingJump"] == 10.0
    assert payload["transactionType"] == 1  # 1 for BUY
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["securityId"] == "11536"


def test_super_order_validation_buy():
    adapter = DhanSuperOrders(Mock(), Mock())
    with pytest.raises(ValueError, match="target_price"):
        adapter.place_super_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
            target_price=Decimal("2400"),  # Invalid, target < entry for BUY
            stop_loss_price=Decimal("2400"),
            trailing_jump=Decimal("10"),
        )
