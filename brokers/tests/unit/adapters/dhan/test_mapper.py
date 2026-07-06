"""Tests for brokers.adapters.dhan.mapper — Dhan DTO → domain entity mapper."""

from __future__ import annotations

from decimal import Decimal

from inc_trade.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)

from brokers.adapters.dhan.mapper import (
    _normalize_exchange,
    map_balance,
    map_depth,
    map_holding,
    map_order,
    map_order_response,
    map_position,
    map_quote,
    map_trade,
)


# ---------------------------------------------------------------------------
# map_order
# ---------------------------------------------------------------------------
class TestMapOrder:
    def test_valid_buy_order(self):
        data = {
            "orderId": "12345",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": 1,
            "quantity": 10,
            "filledQty": 5,
            "price": 2500.0,
            "triggerPrice": 2480.0,
            "orderType": 2,
            "productType": "CNC",
            "orderStatus": "OPEN",
        }
        order = map_order(data)
        assert order.order_id == "12345"
        assert order.symbol == "RELIANCE"
        assert order.exchange == "NSE"
        assert order.side == Side.BUY
        assert order.quantity == 10
        assert order.filled_quantity == 5
        assert order.price == Decimal("2500")
        assert order.trigger_price == Decimal("2480")
        assert order.order_type == OrderType.LIMIT
        assert order.product_type == ProductType.DELIVERY
        assert order.status == OrderStatus.OPEN

    def test_valid_sell_order(self):
        data = {
            "orderId": "99999",
            "transactionType": 2,
            "orderType": 1,
            "productType": "INTRADAY",
            "orderStatus": "FILLED",
        }
        order = map_order(data)
        assert order.side == Side.SELL
        assert order.order_type == OrderType.MARKET
        assert order.product_type == ProductType.INTRADAY
        assert order.status == OrderStatus.FILLED

    def test_missing_fields_defaults(self):
        order = map_order({})
        assert order.order_id == ""
        assert order.symbol == ""
        assert order.exchange == ""
        assert order.side == Side.BUY
        assert order.quantity == 0
        assert order.filled_quantity == 0
        assert order.price == Decimal("0")
        assert order.trigger_price == Decimal("0")
        assert order.order_type == OrderType.MARKET
        assert order.product_type == ProductType.INTRADAY
        assert order.status == OrderStatus.PENDING

    def test_status_mapping_pending(self):
        assert map_order({"orderStatus": "PENDING"}).status == OrderStatus.PENDING

    def test_status_mapping_open(self):
        assert map_order({"orderStatus": "OPEN"}).status == OrderStatus.OPEN

    def test_status_mapping_partial(self):
        assert map_order({"orderStatus": "PARTIAL"}).status == OrderStatus.PARTIALLY_FILLED

    def test_status_mapping_filled(self):
        assert map_order({"orderStatus": "FILLED"}).status == OrderStatus.FILLED

    def test_status_mapping_cancelled(self):
        assert map_order({"orderStatus": "CANCELLED"}).status == OrderStatus.CANCELLED

    def test_status_mapping_cancel(self):
        assert map_order({"orderStatus": "CANCEL"}).status == OrderStatus.CANCELLED

    def test_status_mapping_rejected(self):
        assert map_order({"orderStatus": "REJECTED"}).status == OrderStatus.REJECTED

    def test_status_mapping_invalid(self):
        assert map_order({"orderStatus": "INVALID"}).status == OrderStatus.REJECTED

    def test_status_unknown_falls_back_to_pending(self):
        assert map_order({"orderStatus": "SOME_UNKNOWN"}).status == OrderStatus.PENDING

    def test_side_mapping_buy(self):
        assert map_order({"transactionType": 1}).side == Side.BUY

    def test_side_mapping_sell(self):
        assert map_order({"transactionType": 2}).side == Side.SELL

    def test_side_mapping_unknown_defaults_to_buy(self):
        assert map_order({"transactionType": 99}).side == Side.BUY

    def test_order_type_market(self):
        assert map_order({"orderType": 1}).order_type == OrderType.MARKET

    def test_order_type_limit(self):
        assert map_order({"orderType": 2}).order_type == OrderType.LIMIT

    def test_order_type_stop_loss(self):
        assert map_order({"orderType": 3}).order_type == OrderType.STOP_LOSS

    def test_order_type_stop_loss_market(self):
        assert map_order({"orderType": 4}).order_type == OrderType.STOP_LOSS_MARKET

    def test_order_type_unknown_defaults_to_market(self):
        assert map_order({"orderType": 99}).order_type == OrderType.MARKET

    def test_product_mapping_intraday(self):
        assert map_order({"productType": "INTRADAY"}).product_type == ProductType.INTRADAY

    def test_product_mapping_margin(self):
        assert map_order({"productType": "MARGIN"}).product_type == ProductType.DELIVERY

    def test_product_mapping_cnc(self):
        assert map_order({"productType": "CNC"}).product_type == ProductType.DELIVERY

    def test_product_mapping_unknown_defaults_to_intraday(self):
        assert map_order({"productType": "UNKNOWN"}).product_type == ProductType.INTRADAY

    def test_validity_always_day(self):
        order = map_order({})
        assert order.validity == Validity.DAY

    def test_reject_reason_populates_message(self):
        data = {"rejectReason": "Margin insufficient"}
        order = map_order(data)
        assert order.message == "Margin insufficient"


# ---------------------------------------------------------------------------
# map_order_response
# ---------------------------------------------------------------------------
class TestMapOrderResponse:
    def test_success_path(self):
        data = {"orderId": "12345", "orderStatus": "OPEN"}
        resp = map_order_response(data)
        assert resp.order_id == "12345"
        assert resp.success is True
        assert resp.status == OrderStatus.OPEN

    def test_fail_path_rejected(self):
        data = {"orderStatus": "REJECTED", "rejectReason": "Price out of range", "errorCode": "E100"}
        resp = map_order_response(data)
        assert resp.success is False
        assert "Price out of range" in resp.message
        assert resp.error_code == "E100"

    def test_fail_path_invalid(self):
        data = {"orderStatus": "INVALID", "rejectReason": "Bad symbol"}
        resp = map_order_response(data)
        assert resp.success is False

    def test_missing_order_id(self):
        data = {"orderStatus": "OPEN"}
        resp = map_order_response(data)
        assert resp.order_id == ""
        assert resp.success is False

    def test_pending_status(self):
        data = {"orderId": "111", "orderStatus": "PENDING"}
        resp = map_order_response(data)
        assert resp.status == OrderStatus.PENDING

    def test_filled_status(self):
        data = {"orderId": "222", "orderStatus": "FILLED"}
        resp = map_order_response(data)
        assert resp.status == OrderStatus.FILLED


# ---------------------------------------------------------------------------
# map_quote
# ---------------------------------------------------------------------------
class TestMapQuote:
    def test_valid_ohlcv(self):
        data = {
            "lastPrice": 2500.0,
            "ohlc": {"open": 2480.0, "high": 2510.0, "low": 2470.0, "close": 2490.0},
            "volume": 100000,
        }
        q = map_quote("RELIANCE", data)
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal("2500")
        assert q.open == Decimal("2480")
        assert q.high == Decimal("2510")
        assert q.low == Decimal("2470")
        assert q.close == Decimal("2490")
        assert q.volume == 100000

    def test_last_price_as_dict(self):
        data = {"last_price": {"last_price": 1500.5}}
        q = map_quote("TCS", data)
        assert q.ltp == Decimal("1500.5")

    def test_last_price_as_ltp_key_in_dict(self):
        data = {"last_price": {"ltp": 999.99}}
        q = map_quote("INFY", data)
        assert q.ltp == Decimal("999.99")

    def test_missing_fields(self):
        q = map_quote("SYM", {})
        assert q.symbol == "SYM"
        assert q.ltp == Decimal("0")
        assert q.open == Decimal("0")
        assert q.high == Decimal("0")
        assert q.low == Decimal("0")
        assert q.close == Decimal("0")
        assert q.volume == 0

    def test_empty_ohlc(self):
        data = {"lastPrice": 100, "ohlc": {}}
        q = map_quote("X", data)
        assert q.open == Decimal("0")


# ---------------------------------------------------------------------------
# map_depth
# ---------------------------------------------------------------------------
class TestMapDepth:
    def test_structured_depth_format(self):
        data = {
            "depth": {
                "buy": [
                    {"price": 2500, "quantity": 10, "orders": 2},
                    {"price": 2499, "quantity": 5, "orders": 1},
                ],
                "sell": [
                    {"price": 2501, "quantity": 8, "orders": 3},
                ],
            }
        }
        md = map_depth("RELIANCE", data)
        assert md.symbol == "RELIANCE"
        assert len(md.bids) == 2
        assert len(md.asks) == 1
        assert md.bids[0].price == Decimal("2500")
        assert md.bids[0].quantity == 10
        assert md.bids[0].orders == 2
        assert md.asks[0].price == Decimal("2501")

    def test_legacy_bid0_ask0_format(self):
        data = {
            "bids": [
                {"price": 100, "quantity": 5, "orders": 1},
                {"price": 99, "quantity": 3, "orders": 2},
            ],
            "asks": [
                {"price": 101, "quantity": 7, "orders": 1},
            ],
        }
        md = map_depth("SYM", data)
        assert len(md.bids) == 2
        assert len(md.asks) == 1
        assert md.bids[0].price == Decimal("100")
        assert md.asks[0].price == Decimal("101")

    def test_legacy_bids_asks_list_format(self):
        data = {
            "bids": [
                {"price": 500, "quantity": 20, "orders": 4},
            ],
            "asks": [
                {"price": 501, "quantity": 15, "orders": 3},
                {"price": 502, "quantity": 10, "orders": 2},
            ],
        }
        md = map_depth("SYM", data)
        assert len(md.bids) == 1
        assert len(md.asks) == 2

    def test_empty_depth(self):
        md = map_depth("SYM", {})
        assert md.bids == ()
        assert md.asks == ()

    def test_depth_not_dict_falls_to_legacy(self):
        data = {"depth": "invalid_string"}
        md = map_depth("SYM", data)
        assert md.bids == ()
        assert md.asks == ()

    def test_max_20_levels(self):
        buy_levels = [{"price": i, "quantity": i, "orders": 1} for i in range(25)]
        data = {"depth": {"buy": buy_levels, "sell": []}}
        md = map_depth("SYM", data)
        assert len(md.bids) == 20


# ---------------------------------------------------------------------------
# map_position
# ---------------------------------------------------------------------------
class TestMapPosition:
    def test_valid_data(self):
        data = {
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "netQty": 10,
            "productType": "INTRADAY",
            "avgBuyCost": 2500.0,
            "realizedProfit": 100.50,
            "unrealizedProfit": -50.25,
        }
        p = map_position(data)
        assert p.symbol == "RELIANCE"
        assert p.exchange == "NSE"
        assert p.quantity == 10
        assert p.product_type == ProductType.INTRADAY
        assert p.average_price == Decimal("2500")
        assert p.realized_pnl == Decimal("100.50")
        assert p.unrealized_pnl == Decimal("-50.25")

    def test_missing_fields(self):
        p = map_position({})
        assert p.symbol == ""
        assert p.exchange == ""
        assert p.quantity == 0
        assert p.product_type == ProductType.INTRADAY
        assert p.average_price == Decimal("0")
        assert p.realized_pnl == Decimal("0")
        assert p.unrealized_pnl == Decimal("0")

    def test_cost_price_fallback(self):
        data = {"costPrice": 1000}
        p = map_position(data)
        assert p.average_price == Decimal("1000")


# ---------------------------------------------------------------------------
# map_holding
# ---------------------------------------------------------------------------
class TestMapHolding:
    def test_valid_data(self):
        data = {
            "tradingSymbol": "TCS",
            "exchangeSegment": "BSE_EQ",
            "holdingQty": 5,
            "avgBuyPrice": 3500.0,
            "isin": "INE192A01025",
            "t1Qty": 2,
        }
        h = map_holding(data)
        assert h.symbol == "TCS"
        assert h.exchange == "BSE"
        assert h.quantity == 5
        assert h.average_price == Decimal("3500")
        assert h.isin == "INE192A01025"
        assert h.t1_quantity == 2

    def test_missing_fields(self):
        h = map_holding({})
        assert h.symbol == ""
        assert h.quantity == 0
        assert h.average_price == Decimal("0")
        assert h.isin == ""
        assert h.t1_quantity == 0

    def test_quantity_fallback(self):
        data = {"quantity": 15}
        h = map_holding(data)
        assert h.quantity == 15


# ---------------------------------------------------------------------------
# map_balance
# ---------------------------------------------------------------------------
class TestMapBalance:
    def test_valid_data(self):
        data = {
            "availabelBalance": 50000.0,
            "utilizedMargin": 10000.0,
            "totalMargin": 60000.0,
        }
        b = map_balance(data)
        assert b.available_cash == Decimal("50000")
        assert b.utilized_margin == Decimal("10000")
        assert b.total_margin == Decimal("60000")

    def test_missing_fields(self):
        b = map_balance({})
        assert b.available_cash == Decimal("0")
        assert b.utilized_margin == Decimal("0")
        assert b.total_margin == Decimal("0")

    def test_nested_data_data_structure(self):
        data = {"data": {"availabelBalance": 75000.0}}
        b = map_balance(data)
        assert b.available_cash == Decimal("0")

    def test_available_margin_fallback(self):
        data = {"availableMargin": 80000.0}
        b = map_balance(data)
        assert b.available_cash == Decimal("80000")


# ---------------------------------------------------------------------------
# map_trade
# ---------------------------------------------------------------------------
class TestMapTrade:
    def test_valid_data(self):
        data = {
            "tradeId": "T001",
            "orderId": "O001",
            "tradingSymbol": "INFY",
            "exchangeSegment": "NSE_EQ",
            "transactionType": 1,
            "tradedQty": 100,
            "tradedPrice": 1500.0,
        }
        t = map_trade(data)
        assert t.trade_id == "T001"
        assert t.order_id == "O001"
        assert t.symbol == "INFY"
        assert t.exchange == "NSE"
        assert t.side == Side.BUY
        assert t.quantity == 100
        assert t.price == Decimal("1500")

    def test_sell_trade(self):
        data = {"transactionType": 2, "tradedQty": 50}
        t = map_trade(data)
        assert t.side == Side.SELL
        assert t.quantity == 50

    def test_missing_fields(self):
        t = map_trade({})
        assert t.trade_id == ""
        assert t.order_id == ""
        assert t.symbol == ""
        assert t.quantity == 0
        assert t.price == Decimal("0")

    def test_trade_id_falls_back_to_order_id(self):
        data = {"orderId": "O999"}
        t = map_trade(data)
        assert t.trade_id == "O999"
        assert t.order_id == "O999"

    def test_quantity_fallback(self):
        data = {"quantity": 25}
        t = map_trade(data)
        assert t.quantity == 25

    def test_price_fallback(self):
        data = {"price": 800.50}
        t = map_trade(data)
        assert t.price == Decimal("800.50")


# ---------------------------------------------------------------------------
# _normalize_exchange
# ---------------------------------------------------------------------------
class TestNormalizeExchange:
    def test_nse_eq(self):
        assert _normalize_exchange("NSE_EQ") == "NSE"

    def test_bse_eq(self):
        assert _normalize_exchange("BSE_EQ") == "BSE"

    def test_nse_fno(self):
        assert _normalize_exchange("NSE_FNO") == "NFO"

    def test_bse_fno(self):
        assert _normalize_exchange("BSE_FNO") == "BFO"

    def test_mcx_comm(self):
        assert _normalize_exchange("MCX_COMM") == "MCX"

    def test_nse_cd(self):
        assert _normalize_exchange("NSE_CD") == "CUR"

    def test_idx_i(self):
        assert _normalize_exchange("IDX_I") == "INDEX"

    def test_unknown_returns_input(self):
        assert _normalize_exchange("UNKNOWN_SEG") == "UNKNOWN_SEG"

    def test_empty_string(self):
        assert _normalize_exchange("") == ""

    def test_lower_case_input(self):
        assert _normalize_exchange("nse_eq") == "NSE"

    def test_non_string_input(self):
        assert _normalize_exchange(123) == "123"
