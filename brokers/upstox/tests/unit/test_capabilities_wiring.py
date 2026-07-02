"""Tests for Upstox capability group wiring on :class:`UpstoxBroker`."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.capabilities import (
    InstrumentsCapability,
    MarketDataCapability,
    OrdersCapability,
    PortfolioCapability,
    StreamingCapability,
)
from domain import (
    ExchangeSegment,
    OrderResponse,
    OrderType,
    ProductType,
    Side,
    Validity,
)


@dataclass
class _Settings:
    client_id: str = "cid"
    client_secret: str = "sec"
    redirect_uri: str = "http://localhost:18080"
    access_token: str = "tok"
    auth_mode: str = "STATIC"
    environment: str = "LIVE"
    algo_name: str = ""
    allow_live_orders: bool = False
    market_protection_default: int = -1
    slice_default: bool = False
    ws_plus_plan: bool = False
    ws_auto_reconnect: bool = True
    ws_reconnect_interval_s: int = 10
    ws_reconnect_max_retries: int = 5


def _broker() -> UpstoxBroker:
    s = UpstoxConnectionSettings(
        client_id=_Settings.client_id,
        client_secret=_Settings.client_secret,
        redirect_uri=_Settings.redirect_uri,
        access_token=_Settings.access_token,
        auth_mode=_Settings.auth_mode,
        environment=_Settings.environment,
        algo_name=_Settings.algo_name,
        allow_live_orders=_Settings.allow_live_orders,
        market_protection_default=_Settings.market_protection_default,
        slice_default=_Settings.slice_default,
        ws_plus_plan=_Settings.ws_plus_plan,
        ws_auto_reconnect=_Settings.ws_auto_reconnect,
        ws_reconnect_interval_s=_Settings.ws_reconnect_interval_s,
        ws_reconnect_max_retries=_Settings.ws_reconnect_max_retries,
    )
    return UpstoxBroker(s)


def test_broker_exposes_five_capability_groups() -> None:
    broker = _broker()
    caps = broker.capabilities

    assert isinstance(caps.market_data, MarketDataCapability)
    assert isinstance(caps.orders, OrdersCapability)
    assert isinstance(caps.portfolio, PortfolioCapability)
    assert isinstance(caps.instruments, InstrumentsCapability)
    assert isinstance(caps.streaming, StreamingCapability)


def test_capability_groups_reference_same_adapters_as_broker() -> None:
    broker = _broker()
    caps = broker.capabilities

    assert caps.market_data.market_data is broker.market_data
    assert caps.market_data.options is broker.options
    assert caps.orders.order_command is broker.order_command
    assert caps.orders.order_query is broker.order_query
    assert caps.orders.slice is broker.slice
    assert caps.portfolio.portfolio is broker.portfolio
    assert caps.portfolio.margin is broker.margin
    assert caps.instruments.instrument_resolver is broker.instrument_resolver
    assert caps.instruments.instrument_loader is broker.instrument_loader
    assert caps.streaming.market_data_websocket is broker.market_data_websocket
    assert caps.streaming.feed_authorizer is broker.feed_authorizer


def test_orders_capability_place_delegates_to_order_command() -> None:
    from brokers.common.dtos import BrokerOrderPayload

    broker = _broker()
    mock_response = OrderResponse.ok(order_id="CAP-001")
    broker.order_command.place_order = MagicMock(return_value=mock_response)

    request = BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        exchange_segment=ExchangeSegment.NSE,
        transaction_type=Side.BUY,
        quantity=1,
        price=Decimal("100"),
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        correlation_id="test:cap:1",
    )
    response = broker.capabilities.orders.place(request)

    assert response is mock_response
    broker.order_command.place_order.assert_called_once_with(request)


def test_orders_capability_cancel_delegates() -> None:
    broker = _broker()
    mock_response = OrderResponse.ok(order_id="CAP-002", message="cancelled")
    broker.order_command.cancel_order = MagicMock(return_value=mock_response)

    response = broker.capabilities.orders.cancel("CAP-002")

    assert response is mock_response
    broker.order_command.cancel_order.assert_called_once_with("CAP-002")


def test_market_data_capability_quote_delegates() -> None:
    broker = _broker()
    expected = {"ltp": Decimal("100")}
    broker.market_data.get_quote = MagicMock(return_value=expected)

    result = broker.capabilities.market_data.quote("RELIANCE", "NSE")

    assert result is expected
    broker.market_data.get_quote.assert_called_once_with("RELIANCE", "NSE")
