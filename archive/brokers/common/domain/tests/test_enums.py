"""Tests for domain.enums — canonical trading enum invariants."""

from __future__ import annotations

from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity


class TestSide:
    def test_buy_value(self):
        assert Side.BUY == "BUY"

    def test_sell_value(self):
        assert Side.SELL == "SELL"

    def test_is_str_enum(self):
        assert isinstance(Side.BUY, str)

    def test_only_two_sides(self):
        assert len(Side) == 2


class TestOrderStatus:
    def test_all_statuses_exist(self):
        expected = {"OPEN", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "PARTIALLY_CANCELLED", "REJECTED", "EXPIRED", "UNKNOWN"}
        assert {s.value for s in OrderStatus} == expected

    def test_terminal_statuses(self):
        assert OrderStatus.FILLED.is_terminal
        assert OrderStatus.CANCELLED.is_terminal
        assert OrderStatus.PARTIALLY_CANCELLED.is_terminal
        assert OrderStatus.REJECTED.is_terminal
        assert OrderStatus.EXPIRED.is_terminal

    def test_non_terminal_statuses(self):
        assert not OrderStatus.OPEN.is_terminal
        assert not OrderStatus.PARTIALLY_FILLED.is_terminal
        assert not OrderStatus.UNKNOWN.is_terminal

    def test_normalize_delegates_to_registry(self):
        result = OrderStatus.normalize("FILLED")
        assert result == OrderStatus.FILLED

    def test_normalize_complete_maps_to_filled(self):
        assert OrderStatus.normalize("COMPLETE") == OrderStatus.FILLED

    def test_normalize_executed_maps_to_filled(self):
        assert OrderStatus.normalize("EXECUTED") == OrderStatus.FILLED

    def test_normalize_unknown_for_garbage(self):
        assert OrderStatus.normalize("XYZ_GARBAGE_STATUS") == OrderStatus.UNKNOWN

    def test_normalize_empty_string_returns_unknown(self):
        assert OrderStatus.normalize("") == OrderStatus.UNKNOWN

    def test_is_str_enum(self):
        assert isinstance(OrderStatus.FILLED, str)


class TestOrderType:
    def test_all_types(self):
        assert OrderType.LIMIT == "LIMIT"
        assert OrderType.MARKET == "MARKET"
        assert OrderType.STOP_LOSS == "STOP_LOSS"
        assert OrderType.STOP_LOSS_MARKET == "STOP_LOSS_MARKET"

    def test_count(self):
        assert len(OrderType) == 4


class TestProductType:
    def test_all_types(self):
        assert ProductType.CNC == "CNC"
        assert ProductType.INTRADAY == "INTRADAY"
        assert ProductType.MARGIN == "MARGIN"
        assert ProductType.MTF == "MTF"


class TestValidity:
    def test_day(self):
        assert Validity.DAY == "DAY"

    def test_ioc(self):
        assert Validity.IOC == "IOC"
