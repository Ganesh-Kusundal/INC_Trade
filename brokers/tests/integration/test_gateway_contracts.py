from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.upstox.gateway import UpstoxGateway


def test_dhan_gateway_implements_ports():
    gateway = DhanGateway(access_token="test", client_id="test")

    # We check that the properties exist and their return types are subclasses/implementations of ports
    # In Python, protocols can be checked with isinstance if runtime_checkable is used,
    # but we can also just check that the required methods are present.

    assert hasattr(gateway, "orders")
    assert hasattr(gateway.orders, "place_order")

    assert hasattr(gateway, "market_data")
    assert hasattr(gateway.market_data, "quote")

    assert hasattr(gateway, "portfolio")
    assert hasattr(gateway.portfolio, "positions")

    assert hasattr(gateway, "instruments")
    assert hasattr(gateway.instruments, "resolve")

    assert hasattr(gateway, "historical")
    assert hasattr(gateway.historical, "get_historical_candles")


def test_upstox_gateway_implements_ports():
    gateway = UpstoxGateway(access_token="test")

    assert hasattr(gateway, "orders")
    assert hasattr(gateway.orders, "place_order")

    assert hasattr(gateway, "market_data")
    assert hasattr(gateway.market_data, "quote")

    assert hasattr(gateway, "portfolio")
    assert hasattr(gateway.portfolio, "positions")

    assert hasattr(gateway, "instruments")
    assert hasattr(gateway.instruments, "resolve")

    assert hasattr(gateway, "historical")
    assert hasattr(gateway.historical, "get_historical_candles")
