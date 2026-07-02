"""Tests for domain enums — the vocabulary of the trading domain."""

from __future__ import annotations

import pytest

from brokers.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


class TestSide:
    def test_values(self):
        assert Side.BUY.value == "BUY"
        assert Side.SELL.value == "SELL"

    def test_from_string(self):
        assert Side("BUY") is Side.BUY
        assert Side("SELL") is Side.SELL

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            Side("HOLD")

    def test_opposite(self):
        assert Side.BUY.opposite is Side.SELL
        assert Side.SELL.opposite is Side.BUY


class TestOrderType:
    def test_values(self):
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP_LOSS.value == "STOP_LOSS"
        assert OrderType.STOP_LOSS_MARKET.value == "STOP_LOSS_MARKET"

    def test_is_limit(self):
        assert OrderType.LIMIT.is_limit
        assert not OrderType.MARKET.is_limit

    def test_is_stop(self):
        assert OrderType.STOP_LOSS.is_stop
        assert OrderType.STOP_LOSS_MARKET.is_stop
        assert not OrderType.MARKET.is_stop


class TestOrderStatus:
    def test_lifecycle_states(self):
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.OPEN.value == "OPEN"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.PARTIALLY_CANCELLED.value == "PARTIALLY_CANCELLED"
        assert OrderStatus.EXPIRED.value == "EXPIRED"
        assert OrderStatus.REJECTED.value == "REJECTED"

    def test_is_terminal(self):
        assert OrderStatus.FILLED.is_terminal
        assert OrderStatus.CANCELLED.is_terminal
        assert OrderStatus.PARTIALLY_CANCELLED.is_terminal
        assert OrderStatus.EXPIRED.is_terminal
        assert OrderStatus.REJECTED.is_terminal
        assert not OrderStatus.PENDING.is_terminal
        assert not OrderStatus.OPEN.is_terminal

    def test_is_active(self):
        assert OrderStatus.PENDING.is_active
        assert OrderStatus.OPEN.is_active
        assert not OrderStatus.FILLED.is_active
        assert not OrderStatus.PARTIALLY_CANCELLED.is_active
        assert not OrderStatus.EXPIRED.is_active


class TestProductType:
    def test_values(self):
        assert ProductType.INTRADAY.value == "INTRADAY"
        assert ProductType.DELIVERY.value == "DELIVERY"
        assert ProductType.MARGIN.value == "MARGIN"


class TestValidity:
    def test_values(self):
        assert Validity.DAY.value == "DAY"
        assert Validity.IOC.value == "IOC"
        assert Validity.GTT.value == "GTT"
