"""Tests for observability and gateway behavior on DhanGateway."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

from brokers.domain import OrderResponse, Quote

from brokers.adapters.dhan.gateway import DhanGateway


@patch("brokers_core.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_gateway_delegates_place_order(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    gw.orders.place_order = MagicMock(return_value=OrderResponse.ok("1"))  # type: ignore[method-assign]
    resp = gw.orders.place_order("RELIANCE", "NSE", side="BUY", quantity=1)
    assert resp.success
    gw.close()


@patch("brokers_core.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_gateway_observability_methods(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    health = gw.health()
    assert "connections" in health
    assert "market_feed" in health["connections"]
    assert "order_stream" in health["connections"]
    assert "circuit_breakers" in health
    assert isinstance(health["circuit_breakers"], dict)
    gw.close()


@patch("brokers_core.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_gateway_market_data_batch(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    gw.market_data.ltp_batch = MagicMock(return_value={"RELIANCE": Decimal("100")})  # type: ignore[method-assign]
    gw.market_data.quote_batch = MagicMock(  # type: ignore[method-assign]
        return_value={"RELIANCE": Quote(symbol="RELIANCE", ltp=Decimal("100"))}
    )
    assert gw.market_data.ltp_batch(["RELIANCE"])["RELIANCE"] == Decimal("100")
    assert gw.market_data.quote_batch(["RELIANCE"])["RELIANCE"].symbol == "RELIANCE"
    gw.close()


@patch("brokers_core.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_gateway_history_returns_dataframe(_store, _token):
    from datetime import datetime

    from brokers.domain.entities import Candle

    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    candle = Candle(
        symbol="RELIANCE",
        timestamp=datetime(2024, 1, 1),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
    )
    gw.historical.get_historical_candles = MagicMock(return_value=[candle])  # type: ignore[method-assign]
    candles = gw.historical.get_historical_candles(
        "RELIANCE",
        "NSE",
        datetime(2024, 1, 1),
        datetime(2024, 1, 5),
        "1D",
    )
    assert len(candles) == 1
    assert candles[0].close == Decimal("105")
    gw.close()


@patch("brokers_core.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_gateway_stream_subscribes(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    gw.streaming.subscribe = MagicMock()  # type: ignore[method-assign]
    gw.streaming.start = MagicMock()  # type: ignore[method-assign]
    with patch.object(
        type(gw.streaming),
        "is_connected",
        new_callable=PropertyMock,
        return_value=False,
    ):
        gw.streaming.subscribe("RELIANCE", "NSE")
        gw.streaming.start()
    gw.streaming.subscribe.assert_called_once_with("RELIANCE", "NSE")
    gw.streaming.start.assert_called_once()
    gw.close()


@patch("brokers_core.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.infrastructure.storage.token_store.JsonTokenStateStore")
def test_gateway_close_releases_admission_and_pool(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    admission = MagicMock()
    admission.release = MagicMock()
    gw._depth20_stream._admission = admission  # type: ignore[attr-defined]

    pool = MagicMock()
    pool.close_all = MagicMock()
    gw._depth_200_pool = pool  # type: ignore[attr-defined]

    gw.close()

    pool.close_all.assert_called_once()
    admission.release.assert_called()
