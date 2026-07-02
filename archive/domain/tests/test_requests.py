"""Tests for domain.requests — canonical order input models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from domain.requests import (
    HistoricalCandle,
    ModifyOrderRequest,
    OrderPreview,
    OrderRequest,
    SliceOrderRequest,
)
from domain.types import OrderType, ProductType, Side, Validity


class TestOrderRequest:
    def test_defaults(self):
        r = OrderRequest()
        assert r.exchange == "NSE"
        assert r.transaction_type == Side.BUY
        assert r.quantity == 0
        assert r.order_type == OrderType.MARKET
        assert r.product_type == ProductType.INTRADAY
        assert r.validity == Validity.DAY
        assert r.slice is False

    def test_custom_values(self):
        r = OrderRequest(
            symbol="TCS",
            exchange="BSE",
            transaction_type=Side.SELL,
            quantity=50,
            price=Decimal("3500"),
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
        )
        assert r.symbol == "TCS"
        assert r.exchange == "BSE"
        assert r.transaction_type == Side.SELL
        assert r.quantity == 50
        assert r.price == Decimal("3500")
        assert r.product_type == ProductType.CNC

    def test_is_frozen(self):
        r = OrderRequest()
        with pytest.raises(FrozenInstanceError):
            r.symbol = "INFY"


class TestModifyOrderRequest:
    def test_requires_order_id(self):
        r = ModifyOrderRequest(order_id="O-123")
        assert r.order_id == "O-123"
        assert r.quantity is None
        assert r.price is None

    def test_partial_update(self):
        r = ModifyOrderRequest(order_id="O-123", quantity=100, price=Decimal("2500"))
        assert r.quantity == 100
        assert r.price == Decimal("2500")
        assert r.trigger_price is None


class TestSliceOrderRequest:
    def test_defaults(self):
        r = SliceOrderRequest()
        assert r.exchange == "NSE"
        assert r.side == Side.BUY
        assert r.order_type == OrderType.MARKET

    def test_custom(self):
        r = SliceOrderRequest(symbol="RELIANCE", quantity=500, side=Side.SELL)
        assert r.symbol == "RELIANCE"
        assert r.quantity == 500
        assert r.side == Side.SELL


class TestOrderPreview:
    def test_default_invalid(self):
        p = OrderPreview()
        assert p.valid is False
        assert p.errors == []
        assert p.warnings == []

    def test_with_errors(self):
        p = OrderPreview(valid=False, errors=["Insufficient margin"])
        assert not p.valid
        assert len(p.errors) == 1


class TestHistoricalCandle:
    def test_defaults(self):
        c = HistoricalCandle()
        assert c.exchange == "NSE"
        assert c.volume == 0
        assert c.timeframe == "1D"

    def test_custom(self):
        from datetime import datetime, timezone

        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        c = HistoricalCandle(
            timestamp=ts,
            symbol="NIFTY",
            open=Decimal("20000"),
            high=Decimal("20100"),
            low=Decimal("19900"),
            close=Decimal("20050"),
            volume=1000000,
        )
        assert c.close == Decimal("20050")
        assert c.volume == 1000000
