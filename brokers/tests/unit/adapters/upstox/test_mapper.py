"""Tests for brokers.adapters.upstox.mapper — Upstox DTO → domain entity mapping."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.adapters.upstox.mapper import (
    map_balance,
    map_depth,
    map_holding,
    map_order,
    map_order_response,
    map_position,
    map_quote,
    map_trade,
    unwrap_data,
)
from inc_trade.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)


class TestMapOrder:
    """Tests for map_order — Upstox order dict → Order entity."""

    def test_valid_buy_order(self):
        data = {
            "order_id": "12345",
            "trading_symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 2500.0,
            "order_type": "MARKET",
            "product": "I",
            "status": "OPEN",
        }
        order = map_order(data)
        assert order.order_id == "12345"
        assert order.symbol == "RELIANCE"
        assert order.exchange == "NSE"
        assert order.side == Side.BUY
        assert order.quantity == 10
        assert order.price == Decimal("2500.0")
        assert order.order_type == OrderType.MARKET
        assert order.product_type == ProductType.INTRADAY
        assert order.status == OrderStatus.OPEN

    def test_valid_sell_order(self):
        data = {
            "order_id": "67890",
            "trading_symbol": "TCS",
            "exchange": "NSE",
            "transaction_type": "SELL",
            "quantity": 5,
            "price": 3500.0,
            "order_type": "LIMIT",
            "product": "D",
            "status": "COMPLETE",
        }
        order = map_order(data)
        assert order.side == Side.SELL
        assert order.order_type == OrderType.LIMIT
        assert order.product_type == ProductType.DELIVERY
        assert order.status == OrderStatus.FILLED

    def test_status_mapping_open(self):
        data = {"order_id": "1", "status": "OPEN"}
        assert map_order(data).status == OrderStatus.OPEN

    def test_status_mapping_complete(self):
        data = {"order_id": "2", "status": "COMPLETE"}
        assert map_order(data).status == OrderStatus.FILLED

    def test_status_mapping_canceled(self):
        data = {"order_id": "3", "status": "CANCELED"}
        assert map_order(data).status == OrderStatus.CANCELLED

    def test_status_mapping_rejected(self):
        data = {"order_id": "4", "status": "REJECTED"}
        assert map_order(data).status == OrderStatus.REJECTED

    def test_status_mapping_modify_pending(self):
        data = {"order_id": "5", "status": "MODIFY_PENDING"}
        assert map_order(data).status == OrderStatus.PENDING

    def test_status_mapping_open_pending(self):
        data = {"order_id": "6", "status": "OPEN_PENDING"}
        assert map_order(data).status == OrderStatus.PENDING

    def test_status_mapping_trigger_pending(self):
        data = {"order_id": "7", "status": "TRIGGER_PENDING"}
        assert map_order(data).status == OrderStatus.PENDING

    def test_side_mapping_buy(self):
        data = {"order_id": "1", "transaction_type": "BUY"}
        assert map_order(data).side == Side.BUY

    def test_side_mapping_sell(self):
        data = {"order_id": "1", "transaction_type": "SELL"}
        assert map_order(data).side == Side.SELL

    def test_order_type_market(self):
        data = {"order_id": "1", "order_type": "MARKET"}
        assert map_order(data).order_type == OrderType.MARKET

    def test_order_type_mkt(self):
        data = {"order_id": "1", "order_type": "MKT"}
        assert map_order(data).order_type == OrderType.MARKET

    def test_order_type_limit(self):
        data = {"order_id": "1", "order_type": "LIMIT"}
        assert map_order(data).order_type == OrderType.LIMIT

    def test_order_type_lmt(self):
        data = {"order_id": "1", "order_type": "LMT"}
        assert map_order(data).order_type == OrderType.LIMIT

    def test_order_type_sl(self):
        data = {"order_id": "1", "order_type": "SL"}
        assert map_order(data).order_type == OrderType.STOP_LOSS

    def test_order_type_stop_loss(self):
        data = {"order_id": "1", "order_type": "STOP_LOSS"}
        assert map_order(data).order_type == OrderType.STOP_LOSS

    def test_order_type_slm(self):
        data = {"order_id": "1", "order_type": "SLM"}
        assert map_order(data).order_type == OrderType.STOP_LOSS_MARKET

    def test_order_type_sl_dash_m(self):
        data = {"order_id": "1", "order_type": "SL-M"}
        assert map_order(data).order_type == OrderType.STOP_LOSS_MARKET

    def test_product_intraday(self):
        data = {"order_id": "1", "product": "I"}
        assert map_order(data).product_type == ProductType.INTRADAY

    def test_product_delivery(self):
        data = {"order_id": "1", "product": "D"}
        assert map_order(data).product_type == ProductType.DELIVERY

    def test_product_mtf(self):
        data = {"order_id": "1", "product": "MTF"}
        assert map_order(data).product_type == ProductType.DELIVERY

    def test_validity_day(self):
        data = {"order_id": "1", "validity": "DAY"}
        assert map_order(data).validity == Validity.DAY

    def test_validity_ioc(self):
        data = {"order_id": "1", "validity": "IOC"}
        assert map_order(data).validity == Validity.IOC

    def test_missing_fields_defaults(self):
        order = map_order({})
        assert order.order_id == ""
        assert order.symbol == ""
        assert order.exchange == ""
        assert order.side == Side.BUY
        assert order.quantity == 0
        assert order.price == Decimal("0")
        assert order.order_type == OrderType.MARKET
        assert order.product_type == ProductType.INTRADAY
        assert order.validity == Validity.DAY
        assert order.status == OrderStatus.OPEN
        assert order.message == ""

    def test_filled_quantity(self):
        data = {"order_id": "1", "filled_quantity": 5}
        assert map_order(data).filled_quantity == 5

    def test_trigger_price(self):
        data = {"order_id": "1", "trigger_price": 2400.0}
        assert map_order(data).trigger_price == Decimal("2400.0")

    def test_status_message(self):
        data = {"order_id": "1", "status_message": "Placed successfully"}
        assert map_order(data).message == "Placed successfully"

    def test_symbol_fallback(self):
        data = {"order_id": "1", "symbol": "INFY"}
        assert map_order(data).symbol == "INFY"


class TestMapOrderResponse:
    """Tests for map_order_response — Upstox response → OrderResponse entity."""

    def test_success_path(self):
        data = {"data": {"order_id": "ORD123"}}
        resp = map_order_response(data)
        assert resp.success is True
        assert resp.order_id == "ORD123"
        assert resp.status == OrderStatus.OPEN

    def test_failure_with_errors_list(self):
        data = {"errors": [{"message": "Insufficient margin"}]}
        resp = map_order_response(data)
        assert resp.success is False
        assert resp.message == "Insufficient margin"

    def test_failure_with_string_error(self):
        data = {"errors": ["Some error"]}
        resp = map_order_response(data)
        assert resp.success is False
        assert resp.message == "Some error"

    def test_missing_order_id(self):
        data = {"data": {}}
        resp = map_order_response(data)
        assert resp.success is False
        assert "no order_id" in resp.message.lower()

    def test_non_dict_response(self):
        resp = map_order_response("invalid")
        assert resp.success is False
        assert resp.message == "Order failed: unexpected response"

    def test_data_without_inner_dict(self):
        data = {"order_id": "ORD456"}
        resp = map_order_response(data)
        assert resp.success is True
        assert resp.order_id == "ORD456"

    def test_empty_errors_list(self):
        data = {"data": {"order_id": "ORD789"}, "errors": []}
        resp = map_order_response(data)
        assert resp.success is True
        assert resp.order_id == "ORD789"


class TestMapQuote:
    """Tests for map_quote — Upstox quote dict → Quote entity."""

    def test_valid_ohlcv_data(self):
        data = {
            "last_price": 2500.50,
            "ohlc": {"open": 2480.0, "high": 2510.0, "low": 2470.0, "close": 2490.0},
            "volume": 123456,
        }
        quote = map_quote("RELIANCE", data)
        assert quote.symbol == "RELIANCE"
        assert quote.ltp == Decimal("2500.50")
        assert quote.open == Decimal("2480.0")
        assert quote.high == Decimal("2510.0")
        assert quote.low == Decimal("2470.0")
        assert quote.close == Decimal("2490.0")
        assert quote.volume == 123456

    def test_missing_fields(self):
        data = {}
        quote = map_quote("TCS", data)
        assert quote.symbol == "TCS"
        assert quote.ltp == Decimal("0")
        assert quote.open == Decimal("0")
        assert quote.high == Decimal("0")
        assert quote.low == Decimal("0")
        assert quote.close == Decimal("0")
        assert quote.volume == 0


class TestMapDepth:
    """Tests for map_depth — Upstox depth dict → MarketDepth entity."""

    def test_structured_depth(self):
        data = {
            "depth": {
                "buy": [
                    {"price": 2500.0, "quantity": 10, "orders": 2},
                    {"price": 2499.0, "quantity": 5, "orders": 1},
                ],
                "sell": [
                    {"price": 2501.0, "quantity": 8, "orders": 3},
                    {"price": 2502.0, "quantity": 12, "orders": 4},
                ],
            }
        }
        depth = map_depth("RELIANCE", data)
        assert depth.symbol == "RELIANCE"
        assert len(depth.bids) == 2
        assert len(depth.asks) == 2
        assert depth.bids[0].price == Decimal("2500.0")
        assert depth.bids[0].quantity == 10
        assert depth.bids[0].orders == 2
        assert depth.asks[0].price == Decimal("2501.0")
        assert depth.asks[0].quantity == 8
        assert depth.asks[0].orders == 3

    def test_empty_depth(self):
        data = {}
        depth = map_depth("TCS", data)
        assert depth.symbol == "TCS"
        assert len(depth.bids) == 0
        assert len(depth.asks) == 0

    def test_non_dict_depth(self):
        data = {"depth": "invalid"}
        depth = map_depth("INFY", data)
        assert len(depth.bids) == 0
        assert len(depth.asks) == 0


class TestMapPosition:
    """Tests for map_position — Upstox position dict → Position entity."""

    def test_valid_data(self):
        data = {
            "trading_symbol": "RELIANCE",
            "exchange": "NSE",
            "net_quantity": 10,
            "product": "I",
            "buy_average_price": 2500.0,
            "realised": 150.0,
            "unrealised": -50.0,
        }
        pos = map_position(data)
        assert pos.symbol == "RELIANCE"
        assert pos.exchange == "NSE"
        assert pos.quantity == 10
        assert pos.product_type == ProductType.INTRADAY
        assert pos.average_price == Decimal("2500.0")
        assert pos.realized_pnl == Decimal("150.0")
        assert pos.unrealized_pnl == Decimal("-50.0")

    def test_missing_fields_defaults(self):
        pos = map_position({})
        assert pos.symbol == ""
        assert pos.exchange == ""
        assert pos.quantity == 0
        assert pos.product_type == ProductType.INTRADAY
        assert pos.average_price == Decimal("0")
        assert pos.realized_pnl == Decimal("0")
        assert pos.unrealized_pnl == Decimal("0")

    def test_symbol_fallback(self):
        data = {"symbol": "TCS"}
        assert map_position(data).symbol == "TCS"

    def test_quantity_fallback(self):
        data = {"quantity": 20}
        assert map_position(data).quantity == 20

    def test_average_price_fallback(self):
        data = {"average_price": 3500.0}
        assert map_position(data).average_price == Decimal("3500.0")


class TestMapHolding:
    """Tests for map_holding — Upstox holding dict → Holding entity."""

    def test_valid_data(self):
        data = {
            "trading_symbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 10,
            "average_price": 2500.0,
            "isin": "INE002A01018",
            "t1_quantity": 5,
        }
        holding = map_holding(data)
        assert holding.symbol == "RELIANCE"
        assert holding.exchange == "NSE"
        assert holding.quantity == 10
        assert holding.average_price == Decimal("2500.0")
        assert holding.isin == "INE002A01018"
        assert holding.t1_quantity == 5

    def test_missing_fields_defaults(self):
        holding = map_holding({})
        assert holding.symbol == ""
        assert holding.exchange == ""
        assert holding.quantity == 0
        assert holding.average_price == Decimal("0")
        assert holding.isin == ""
        assert holding.t1_quantity == 0

    def test_symbol_fallback(self):
        data = {"symbol": "TCS"}
        assert map_holding(data).symbol == "TCS"


class TestMapBalance:
    """Tests for map_balance — Upstox balance dict → Balance entity."""

    def test_valid_data(self):
        data = {
            "equity": {
                "available_margin": 50000.0,
                "used_margin": 10000.0,
                "net_margin": 40000.0,
            }
        }
        balance = map_balance(data)
        assert balance.available_cash == Decimal("50000.0")
        assert balance.utilized_margin == Decimal("10000.0")
        assert balance.total_margin == Decimal("40000.0")

    def test_nested_data_structure(self):
        data = {
            "data": {
                "equity": {
                    "available_margin": 75000.0,
                    "used_margin": 25000.0,
                    "net_margin": 50000.0,
                }
            }
        }
        balance = map_balance(data)
        assert balance.available_cash == Decimal("75000.0")
        assert balance.utilized_margin == Decimal("25000.0")
        assert balance.total_margin == Decimal("50000.0")

    def test_missing_fields_defaults(self):
        balance = map_balance({})
        assert balance.available_cash == Decimal("0")
        assert balance.utilized_margin == Decimal("0")
        assert balance.total_margin == Decimal("0")

    def test_data_without_equity(self):
        data = {"data": "invalid"}
        balance = map_balance(data)
        assert balance.available_cash == Decimal("0")

    def test_available_cash_fallback(self):
        data = {"equity": {"available_cash": 60000.0}}
        balance = map_balance(data)
        assert balance.available_cash == Decimal("60000.0")

    def test_net_fallback(self):
        data = {"equity": {"available_margin": 50000.0, "net": 30000.0}}
        balance = map_balance(data)
        assert balance.total_margin == Decimal("30000.0")


class TestMapTrade:
    """Tests for map_trade — Upstox trade dict → Trade entity."""

    def test_valid_data(self):
        data = {
            "trade_id": "TRD123",
            "order_id": "ORD456",
            "trading_symbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "quantity": 10,
            "average_price": 2500.0,
        }
        trade = map_trade(data)
        assert trade.trade_id == "TRD123"
        assert trade.order_id == "ORD456"
        assert trade.symbol == "RELIANCE"
        assert trade.exchange == "NSE"
        assert trade.side == Side.BUY
        assert trade.quantity == 10
        assert trade.price == Decimal("2500.0")

    def test_missing_fields_defaults(self):
        trade = map_trade({})
        assert trade.trade_id == ""
        assert trade.order_id == ""
        assert trade.symbol == ""
        assert trade.exchange == ""
        assert trade.side == Side.BUY
        assert trade.quantity == 0
        assert trade.price == Decimal("0")

    def test_symbol_fallback(self):
        data = {"symbol": "TCS"}
        assert map_trade(data).symbol == "TCS"

    def test_quantity_fallback(self):
        data = {"traded_quantity": 15}
        assert map_trade(data).quantity == 15

    def test_price_fallback(self):
        data = {"price": 3500.0}
        assert map_trade(data).price == Decimal("3500.0")


class TestUnwrapData:
    """Tests for unwrap_data — extract 'data' field from Upstox response."""

    def test_data_present(self):
        response = {"data": {"key": "value"}}
        result = unwrap_data(response)
        assert result == {"key": "value"}

    def test_data_missing(self):
        response = {"status": "ok"}
        result = unwrap_data(response)
        assert result == []

    def test_non_dict_response(self):
        result = unwrap_data("invalid")
        assert result == []

    def test_custom_default_none_becomes_empty_list(self):
        response = {"status": "ok"}
        result = unwrap_data(response, default=None)
        assert result == []

    def test_custom_default_string(self):
        response = {"status": "ok"}
        result = unwrap_data(response, default="fallback")
        assert result == "fallback"

    def test_data_is_list(self):
        response = {"data": [1, 2, 3]}
        result = unwrap_data(response)
        assert result == [1, 2, 3]

    def test_data_is_string(self):
        response = {"data": "order_placed"}
        result = unwrap_data(response)
        assert result == "order_placed"
