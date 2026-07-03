"""Tests for DhanCompatibilityGateway and observability on DhanGateway."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from brokers.domain import MarketDepth, OrderResponse, Quote
from brokers.adapters.dhan.compat_gateway import DhanCompatibilityGateway, FutureChain
from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.options import OptionChain


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_compat_gateway_delegates_place_order(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    gw.orders.place_order = MagicMock(return_value=OrderResponse.ok("1"))  # type: ignore[method-assign]
    compat = DhanCompatibilityGateway(gw)
    resp = compat.place_order("RELIANCE", "NSE", side="BUY", quantity=1)
    gw.orders.place_order.assert_called_once()
    assert resp.success
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_gateway_observability_methods(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    status = gw.get_connection_status()
    assert "market_feed" in status
    assert "order_stream" in status
    breakers = gw.get_circuit_breaker_states()
    assert "read" in breakers
    assert gw.health()["circuit_breakers"] == breakers
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_compat_delegates_market_data_batch(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    gw.market_data.ltp_batch = MagicMock(return_value={"RELIANCE": Decimal("100")})  # type: ignore[method-assign]
    gw.market_data.quote_batch = MagicMock(  # type: ignore[method-assign]
        return_value={"RELIANCE": Quote(symbol="RELIANCE", ltp=Decimal("100"))}
    )
    compat = DhanCompatibilityGateway(gw)
    assert compat.ltp_batch(["RELIANCE"])["RELIANCE"] == Decimal("100")
    assert compat.quote_batch(["RELIANCE"])["RELIANCE"].symbol == "RELIANCE"
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_compat_history_returns_dataframe(_store, _token):
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
    compat = DhanCompatibilityGateway(gw)
    df = compat.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "oi",
        "symbol",
        "exchange",
        "timeframe",
    ]
    assert df.iloc[0]["close"] == 105.0
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_compat_stream_subscribes(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    gw.streaming.subscribe = MagicMock()  # type: ignore[method-assign]
    gw.streaming.start = MagicMock()  # type: ignore[method-assign]
    with patch.object(
        type(gw.streaming),
        "is_connected",
        new_callable=PropertyMock,
        return_value=False,
    ):
        compat = DhanCompatibilityGateway(gw)
        handle = compat.stream("RELIANCE", "NSE", on_tick=lambda _: None)
    gw.streaming.subscribe.assert_called_once_with("RELIANCE", "NSE")
    gw.streaming.start.assert_called_once()
    assert handle is gw.streaming
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
def test_compat_option_and_future_chain(_store, _token):
    gw = DhanGateway(access_token="tok", client_id="cid", auto_refresh=False)
    chain = OptionChain(
        underlying="NIFTY",
        expiry="2025-03-27",
        spot=Decimal("22000"),
        strikes=[],
    )
    gw.options.get_expiries = MagicMock(return_value=["2025-03-27"])  # type: ignore[method-assign]
    gw.options.get_option_chain = MagicMock(return_value=chain)  # type: ignore[method-assign]
    gw.futures.get_futures_chain = MagicMock(return_value=[])  # type: ignore[method-assign]
    compat = DhanCompatibilityGateway(gw)
    assert compat.option_chain("NIFTY", "NFO") is chain
    future_chain = compat.future_chain("NIFTY", "NFO")
    assert isinstance(future_chain, FutureChain)
    gw.close()


@patch("brokers.adapters.dhan.auth.DhanAuth.get_token", return_value="tok")
@patch("brokers.adapters.dhan.gateway.JsonTokenStateStore")
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
