"""Extended domain model tests — deep coverage of value objects, aggregates, and instruments."""

from datetime import date
from decimal import Decimal

import pytest
from tradex.domain.account import Account, AccountProfile, FundLimits
from tradex.domain.enums import (
    Exchange,
    ExchangeSegment,
    InstrumentType,
    OptionType,
    OrderStatus,
    OrderType,
    PositionType,
    ProductType,
    Side,
)
from tradex.domain.execution import Order, Trade
from tradex.domain.instruments import (
    BUILTIN_INSTRUMENTS,
    Equity,
    Future,
    Index,
    Instrument,
    Option,
)
from tradex.domain.mapping import InstrumentMapper
from tradex.domain.market_data import (
    OHLCV,
    OptionChain,
    OptionQuote,
    OptionStrike,
    Quote,
)
from tradex.domain.portfolio import Holding, Portfolio, Position
from tradex.domain.value_objects import (
    DateRange,
    ExpiryDate,
    InstrumentKey,
    Money,
    Price,
    Quantity,
    SecurityID,
    TickSize,
)

# ============================================================
# Money
# ============================================================


class TestMoneyExtended:
    def test_add_inr(self):
        a = Money(Decimal("500.75"), "INR")
        b = Money(Decimal("250.25"), "INR")
        assert (a + b).amount == Decimal("751.00")

    def test_sub(self):
        a = Money(Decimal("1000"), "INR")
        b = Money(Decimal("333.33"), "INR")
        assert (a - b).amount == Decimal("666.67")

    def test_mul_int(self):
        m = Money(Decimal("50"), "INR")
        assert (m * 4).amount == Decimal("200.00")

    def test_mul_decimal(self):
        m = Money(Decimal("100"), "INR")
        assert (m * Decimal("1.5")).amount == Decimal("150.00")

    def test_mul_float(self):
        m = Money(Decimal("100"), "INR")
        assert (m * 2.5).amount == Decimal("250.00")

    def test_comparison_lt(self):
        assert Money(Decimal("10")) < Money(Decimal("20"))

    def test_comparison_le(self):
        assert Money(Decimal("10")) <= Money(Decimal("10"))
        assert Money(Decimal("10")) <= Money(Decimal("20"))

    def test_comparison_gt(self):
        assert Money(Decimal("20")) > Money(Decimal("10"))

    def test_comparison_ge(self):
        assert Money(Decimal("20")) >= Money(Decimal("20"))

    def test_currency_mismatch_add(self):
        with pytest.raises(ValueError, match="Cannot add"):
            Money(Decimal("100"), "INR") + Money(Decimal("50"), "USD")

    def test_currency_mismatch_sub(self):
        with pytest.raises(ValueError, match="Cannot subtract"):
            Money(Decimal("100"), "INR") - Money(Decimal("50"), "USD")

    def test_currency_mismatch_lt(self):
        with pytest.raises(ValueError, match="Cannot compare"):
            Money(Decimal("100"), "INR") < Money(Decimal("50"), "USD")

    def test_zero_inr(self):
        z = Money.zero()
        assert z.amount == Decimal("0")
        assert z.currency == "INR"

    def test_zero_usd(self):
        z = Money.zero("USD")
        assert z.currency == "USD"

    def test_is_positive_negative(self):
        assert Money(Decimal("1.00")).is_positive
        assert not Money(Decimal("-1.00")).is_positive
        assert Money(Decimal("-1.00")).is_negative
        assert not Money(Decimal("1.00")).is_negative
        assert not Money(Decimal("0.00")).is_positive
        assert not Money(Decimal("0.00")).is_negative

    def test_to_paise(self):
        assert Money(Decimal("123.45")).to_paise() == 12345

    def test_str_inr(self):
        s = str(Money(Decimal("1234.56"), "INR"))
        assert "₹" in s
        assert "1,234.56" in s

    def test_str_usd(self):
        s = str(Money(Decimal("100.00"), "USD"))
        assert "USD" in s
        assert "100.00" in s

    def test_rounding(self):
        m = Money(Decimal("100.006"))
        assert m.amount == Decimal("100.01")

    def test_negative_amount(self):
        m = Money(Decimal("-50.50"))
        assert m.amount == Decimal("-50.50")


# ============================================================
# Price
# ============================================================


class TestPriceExtended:
    def test_tick_05(self):
        p = Price(Decimal("100.12"), Decimal("0.05"))
        assert p.value == Decimal("100.10")

    def test_tick_01(self):
        p = Price(Decimal("100.17"), Decimal("0.01"))
        assert p.value == Decimal("100.17")

    def test_tick_0025(self):
        p = Price(Decimal("82.337"), Decimal("0.0025"))
        # 82.337 / 0.0025 = 32934.8, quantized = 32935, * 0.0025 = 82.3375
        assert p.value == Decimal("82.3375")

    def test_tick_1(self):
        p = Price(Decimal("100.7"), Decimal("1"))
        assert p.value == Decimal("101")

    def test_from_float(self):
        p = Price.from_float(100.03, 0.05)
        assert p.value == Decimal("100.05")

    def test_as_float(self):
        assert Price(Decimal("99.50")).as_float == 99.5

    def test_comparison(self):
        assert Price(Decimal("100")) < Price(Decimal("200"))
        assert Price(Decimal("200")) > Price(Decimal("100"))
        assert Price(Decimal("100")) <= Price(Decimal("100"))
        assert Price(Decimal("100")) >= Price(Decimal("100"))

    def test_str(self):
        assert str(Price(Decimal("2500.50"))) == "2500.50"


# ============================================================
# Quantity
# ============================================================


class TestQuantityExtended:
    def test_lot_validation_pass(self):
        q = Quantity(150, 15)
        assert q.lots == 10

    def test_lot_validation_fail(self):
        with pytest.raises(ValueError, match="not a multiple"):
            Quantity(13, 15)

    def test_from_lots(self):
        q = Quantity.from_lots(3, 15)
        assert q.value == 45
        assert q.lots == 3

    def test_add_same_lot(self):
        a = Quantity(50, 10)
        b = Quantity(30, 10)
        assert (a + b).value == 80

    def test_add_diff_lot_raises(self):
        with pytest.raises(ValueError, match="different lot sizes"):
            Quantity(50, 10) + Quantity(50, 25)

    def test_sub_same_lot(self):
        a = Quantity(50, 10)
        b = Quantity(30, 10)
        assert (a - b).value == 20

    def test_sub_diff_lot_raises(self):
        with pytest.raises(ValueError, match="different lot sizes"):
            Quantity(50, 10) - Quantity(50, 25)

    def test_lot_size_1(self):
        q = Quantity(7, 1)
        assert q.lots == 7

    def test_str(self):
        assert str(Quantity(105, 15)) == "105"


# ============================================================
# DateRange
# ============================================================


class TestDateRangeExtended:
    def test_same_day(self):
        d = date(2024, 6, 15)
        dr = DateRange(d, d)
        assert dr.days == 1

    def test_one_week(self):
        dr = DateRange(date(2024, 1, 1), date(2024, 1, 7))
        assert dr.days == 7

    def test_contains_boundary_start(self):
        dr = DateRange(date(2024, 1, 10), date(2024, 1, 20))
        assert dr.contains(date(2024, 1, 10))

    def test_contains_boundary_end(self):
        dr = DateRange(date(2024, 1, 10), date(2024, 1, 20))
        assert dr.contains(date(2024, 1, 20))

    def test_not_contains_before(self):
        dr = DateRange(date(2024, 1, 10), date(2024, 1, 20))
        assert not dr.contains(date(2024, 1, 9))

    def test_not_contains_after(self):
        dr = DateRange(date(2024, 1, 10), date(2024, 1, 20))
        assert not dr.contains(date(2024, 1, 21))

    def test_today(self):
        dr = DateRange.today()
        assert dr.start == dr.end
        assert dr.days == 1

    def test_last_days_30(self):
        dr = DateRange.last_days(30)
        assert dr.days == 31  # inclusive

    def test_invalid_start_after_end(self):
        with pytest.raises(ValueError, match="after end"):
            DateRange(date(2024, 12, 31), date(2024, 1, 1))


# ============================================================
# SecurityID & InstrumentKey
# ============================================================


class TestSecurityID:
    def test_str(self):
        sid = SecurityID("2885", Exchange.NSE)
        assert str(sid) == "2885"

    def test_default_exchange(self):
        sid = SecurityID("123")
        assert sid.exchange == Exchange.UNKNOWN


class TestInstrumentKeyExtended:
    def test_equity_key(self):
        key = InstrumentKey(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.EQUITY,
        )
        s = str(key)
        assert "RELIANCE" in s
        assert "NSE" in s
        assert "EQUITY" in s

    def test_option_key_full(self):
        key = InstrumentKey(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.OPTIDX,
            expiry=date(2025, 3, 27),
            strike=Decimal("24500"),
            option_type=OptionType.PUT,
        )
        s = str(key)
        assert "NIFTY" in s
        assert "OPTIDX" in s
        assert "24500" in s
        assert "PUT" in s
        assert "2025-03-27" in s


# ============================================================
# ExpiryDate & TickSize
# ============================================================


class TestExpiryDate:
    def test_weekly(self):
        ed = ExpiryDate(date(2024, 3, 28), "W")
        assert ed.is_weekly
        assert not ed.is_monthly

    def test_monthly(self):
        ed = ExpiryDate(date(2024, 3, 28), "M")
        assert ed.is_monthly
        assert not ed.is_weekly

    def test_none_flag(self):
        ed = ExpiryDate(date(2024, 3, 28))
        assert not ed.is_weekly
        assert not ed.is_monthly


class TestTickSize:
    def test_nse_eq(self):
        ts = TickSize.for_segment(ExchangeSegment.NSE_EQ)
        assert ts.tick_size == Decimal("0.05")

    def test_bse_eq(self):
        ts = TickSize.for_segment(ExchangeSegment.BSE_EQ)
        assert ts.tick_size == Decimal("0.01")

    def test_nse_fno(self):
        ts = TickSize.for_segment(ExchangeSegment.NSE_FNO)
        assert ts.tick_size == Decimal("0.05")

    def test_mcx(self):
        ts = TickSize.for_segment(ExchangeSegment.MCX_COMM)
        assert ts.tick_size == Decimal("0.01")

    def test_nse_currency(self):
        ts = TickSize.for_segment(ExchangeSegment.NSE_CURRENCY)
        assert ts.tick_size == Decimal("0.0025")


# ============================================================
# Account
# ============================================================


class TestAccountExtended:
    def test_profile_from_dhan_full(self):
        data = {
            "dhanClientId": "999",
            "fullName": "Jane Doe",
            "email": "jane@test.com",
            "mobileNumber": "9876543210",
            "pan": "ABCDE1234F",
            "activeSegment": "NSE_EQ,BSE_EQ,NSE_FNO",
            "ddpi": True,
            "mtf": True,
            "dataPlan": True,
            "dataValidity": "2025-01-01",
            "tokenValidity": "2024-12-31",
        }
        p = AccountProfile.from_dhan(data)
        assert p.client_id == "999"
        assert p.name == "Jane Doe"
        assert p.email == "jane@test.com"
        assert p.pan == "ABCDE1234F"
        assert len(p.active_segments) == 3
        assert p.has_segment("NSE_FNO")
        assert not p.has_segment("MCX_COMM")
        assert p.ddpi_enabled
        assert p.mtf_enabled

    def test_profile_no_segments(self):
        p = AccountProfile()
        assert not p.can_trade
        assert p.active_segments == []

    def test_profile_empty_segment_string(self):
        data = {"dhanClientId": "123", "activeSegment": ""}
        p = AccountProfile.from_dhan(data)
        assert p.active_segments == []

    def test_can_trade_needs_all(self):
        a = Account(
            account_id="1",
            broker_name="dhan",
            connected=True,
            profile=AccountProfile(client_id="", active_segments=["NSE_EQ"]),
        )
        assert not a.can_trade  # no client_id

    def test_can_trade_needs_segment(self):
        a = Account(
            account_id="1",
            broker_name="dhan",
            connected=True,
            profile=AccountProfile(client_id="123", active_segments=[]),
        )
        assert not a.can_trade

    def test_account_str_connected(self):
        a = Account(account_id="1", broker_name="dhan", connected=True)
        assert "connected" in str(a)

    def test_account_str_disconnected(self):
        a = Account(account_id="1", broker_name="dhan", connected=False)
        assert "disconnected" in str(a)

    def test_available_balance_no_funds(self):
        a = Account(account_id="1", broker_name="dhan")
        assert a.available_balance == Decimal("0")

    def test_available_balance_with_funds(self):
        fl = FundLimits(
            available_balance=Decimal("100000"),
            collateral=Decimal("50000"),
            blocked_payout=Decimal("5000"),
        )
        a = Account(account_id="1", broker_name="dhan", fund_limits=fl)
        assert a.available_balance == Decimal("145000")

    def test_fund_limits_from_dhan_full(self):
        data = {
            "availabelBalance": 500000,
            "sodLimit": 100000,
            "collateralAmount": 200000,
            "receiveableAmount": 15000,
            "utilizedAmount": 300000,
            "blockedPayoutAmount": 10000,
            "withdrawableBalance": 490000,
        }
        fl = FundLimits.from_dhan(data)
        assert fl.available_balance == Decimal("500000")
        assert fl.sod_limit == Decimal("100000")
        assert fl.collateral == Decimal("200000")
        assert fl.receivable == Decimal("15000")
        assert fl.utilized == Decimal("300000")
        assert fl.blocked_payout == Decimal("10000")
        assert fl.withdrawable == Decimal("490000")
        assert fl.net_available == Decimal("690000")  # 500k + 200k - 10k


# ============================================================
# Holding
# ============================================================


class TestHoldingExtended:
    def test_from_dhan_full(self):
        data = {
            "securityId": "2885",
            "tradingSymbol": "RELIANCE",
            "exchange": "NSE_EQ",
            "isin": "INE002A01018",
            "totalQty": 50,
            "dpQty": 30,
            "t1Qty": 10,
            "availableQty": 30,
            "collateralQty": 10,
            "avgCostPrice": 2450.50,
        }
        h = Holding.from_dhan(data)
        assert h.security_id == "2885"
        assert h.isin == "INE002A01018"
        assert h.total_quantity == 50
        assert h.dp_quantity == 30
        assert h.t1_quantity == 10
        assert h.available_quantity == 30
        assert h.collateral_quantity == 10
        assert h.average_cost_price == Decimal("2450.50")

    def test_is_sellable_nse_eq(self):
        h = Holding(security_id="1", exchange="NSE_EQ", available_quantity=10)
        assert h.is_sellable

    def test_is_sellable_bse_eq(self):
        h = Holding(security_id="1", exchange="BSE_EQ", available_quantity=10)
        assert h.is_sellable

    def test_not_sellable_zero_available(self):
        h = Holding(security_id="1", exchange="NSE_EQ", available_quantity=0)
        assert not h.is_sellable

    def test_not_sellable_wrong_exchange(self):
        h = Holding(security_id="1", exchange="NSE_FNO", available_quantity=10)
        assert not h.is_sellable


# ============================================================
# Position
# ============================================================


class TestPositionExtended:
    def test_from_dhan_long(self):
        data = {
            "securityId": "49081",
            "tradingSymbol": "NIFTY28MAR25FUT",
            "exchangeSegment": "NSE_FNO",
            "productType": "MARGIN",
            "positionType": "LONG",
            "buyAvg": 24500.0,
            "buyQty": 75,
            "sellAvg": 0,
            "sellQty": 0,
            "netQty": 75,
            "realizedProfit": 0,
            "unrealizedProfit": 1500.0,
            "drvExpiryDate": "2025-03-28",
            "drvOptionType": "CE",
            "drvStrikePrice": 24500,
        }
        p = Position.from_dhan(data)
        assert p.position_type == PositionType.LONG
        assert p.is_open
        assert p.total_pnl == Decimal("1500")
        assert p.expiry_date == "2025-03-28"

    def test_from_dhan_short(self):
        data = {
            "securityId": "49082",
            "tradingSymbol": "NIFTY28MAR25FUT",
            "positionType": "SHORT",
            "netQty": -75,
            "buyQty": 0,
            "sellQty": 75,
            "buyAvg": 0,
            "sellAvg": 24600,
        }
        p = Position.from_dhan(data)
        assert p.position_type == PositionType.SHORT
        assert p.is_open

    def test_from_dhan_closed(self):
        data = {
            "securityId": "49081",
            "positionType": "CLOSED",
            "netQty": 0,
            "buyQty": 75,
            "sellQty": 75,
            "buyAvg": 24500,
            "sellAvg": 24600,
            "realizedProfit": 7500,
        }
        p = Position.from_dhan(data)
        assert p.position_type == PositionType.CLOSED
        assert not p.is_open

    def test_notional_long(self):
        data = {
            "securityId": "49081",
            "buyAvg": 100.0,
            "buyQty": 100,
            "sellAvg": 0,
            "sellQty": 0,
            "netQty": 100,
        }
        p = Position.from_dhan(data)
        assert p.notional == Decimal("10000")

    def test_notional_with_sells(self):
        data = {
            "securityId": "49081",
            "buyAvg": 100.0,
            "buyQty": 50,
            "sellAvg": 110.0,
            "sellQty": 50,
            "netQty": 0,
        }
        p = Position.from_dhan(data)
        # weighted avg = (100*50 + 110*50) / 100 = 105, * abs(0) = 0
        assert p.notional == Decimal("0")


# ============================================================
# Portfolio
# ============================================================


class TestPortfolioExtended:
    def test_summary_fields(self):
        portfolio = Portfolio(
            account_id="123",
            holdings=[
                Holding(
                    security_id="1",
                    total_quantity=20,
                    average_cost_price=Decimal("100"),
                ),
                Holding(
                    security_id="2",
                    total_quantity=10,
                    average_cost_price=Decimal("200"),
                ),
            ],
            positions=[
                Position(
                    net_quantity=50,
                    realized_profit=Decimal("500"),
                    unrealized_profit=Decimal("-100"),
                ),
                Position(
                    net_quantity=0,
                    realized_profit=Decimal("200"),
                    unrealized_profit=Decimal("0"),
                ),
            ],
        )
        s = portfolio.summary()
        assert s["holdings_count"] == 2
        assert s["open_positions"] == 1
        assert s["total_holdings_value"] == 4000.0  # 20*100 + 10*200
        assert s["realized_pnl"] == 700.0
        assert s["unrealized_pnl"] == -100.0
        assert s["total_pnl"] == 600.0

    def test_empty_portfolio(self):
        portfolio = Portfolio(account_id="empty")
        assert portfolio.open_positions == []
        assert portfolio.closed_positions == []
        assert portfolio.total_holdings_value == Decimal("0")
        assert portfolio.total_pnl == Decimal("0")


# ============================================================
# Order
# ============================================================


class TestOrderExtended:
    def test_from_dhan_all_statuses(self):
        for status_str, expected in [
            ("PENDING", OrderStatus.PENDING),
            ("PLACED", OrderStatus.PLACED),
            ("ACCEPTED", OrderStatus.ACCEPTED),
            ("OPEN", OrderStatus.OPEN),
            ("PART_TRADED", OrderStatus.PART_TRADED),
            ("TRADED", OrderStatus.TRADED),
            ("CANCELLED", OrderStatus.CANCELLED),
            ("REJECTED", OrderStatus.REJECTED),
            ("EXPIRED", OrderStatus.EXPIRED),
            ("TRIGGER_PENDING", OrderStatus.TRIGGER_PENDING),
        ]:
            data = {
                "orderId": f"order_{status_str}",
                "orderStatus": status_str,
                "transactionType": "BUY",
                "orderType": "LIMIT",
                "productType": "INTRADAY",
                "quantity": 10,
                "price": 100,
            }
            order = Order.from_dhan(data)
            assert order.status == expected

    def test_from_dhan_sell_order(self):
        data = {
            "orderId": "100",
            "transactionType": "SELL",
            "orderType": "MARKET",
            "productType": "CNC",
            "quantity": 5,
            "orderStatus": "PLACED",
        }
        order = Order.from_dhan(data)
        assert order.side == Side.SELL
        assert order.order_type == OrderType.MARKET
        assert order.product_type == ProductType.CNC

    def test_fill_partial(self):
        order = Order(
            order_id="100",
            quantity=100,
            price=Decimal("50"),
            status=OrderStatus.OPEN,
        )
        order.fill(30, Decimal("51"))
        assert order.filled_quantity == 30
        assert order.pending_quantity == 70
        assert order.status == OrderStatus.PART_TRADED

    def test_fill_complete(self):
        order = Order(
            order_id="100",
            quantity=100,
            price=Decimal("50"),
            status=OrderStatus.OPEN,
        )
        order.fill(100, Decimal("50"))
        assert order.filled_quantity == 100
        assert order.pending_quantity == 0
        assert order.status == OrderStatus.TRADED
        assert order.is_filled
        assert order.is_complete

    def test_fill_average_price(self):
        order = Order(
            order_id="100",
            quantity=100,
            price=Decimal("50"),
            status=OrderStatus.OPEN,
        )
        order.fill(50, Decimal("100"))
        order.fill(50, Decimal("200"))
        # avg = (100*50 + 200*50) / 100 = 150
        assert order.average_price == Decimal("150.00")

    def test_fill_first_fill_avg(self):
        order = Order(order_id="100", quantity=10, status=OrderStatus.OPEN)
        order.fill(5, Decimal("100"))
        assert order.average_price == Decimal("100.00")

    def test_is_complete_terminal_states(self):
        for status in [
            OrderStatus.TRADED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        ]:
            order = Order(order_id="1", status=status)
            assert order.is_complete, f"Expected is_complete for {status}"

    def test_is_active_states(self):
        for status in [
            OrderStatus.PENDING,
            OrderStatus.PLACED,
            OrderStatus.ACCEPTED,
            OrderStatus.OPEN,
            OrderStatus.PART_TRADED,
            OrderStatus.TRIGGER_PENDING,
        ]:
            order = Order(order_id="1", status=status)
            assert order.is_active, f"Expected is_active for {status}"

    def test_notional(self):
        order = Order(quantity=100, price=Decimal("250.50"))
        assert order.notional == Decimal("25050.00")

    def test_summary_format(self):
        order = Order(
            order_id="X123",
            trading_symbol="TCS",
            side=Side.SELL,
            order_type=OrderType.STOP_LOSS_MARKET,
            product_type=ProductType.MARGIN,
            quantity=25,
            price=Decimal("3500"),
            trigger_price=Decimal("3450"),
            status=OrderStatus.OPEN,
            filled_quantity=10,
            tag="my_tag",
        )
        s = order.summary()
        assert s["order_id"] == "X123"
        assert s["symbol"] == "TCS"
        assert s["side"] == "SELL"
        assert s["type"] == "STOP_LOSS_MARKET"
        assert s["product"] == "MARGIN"
        assert s["quantity"] == 25
        assert s["trigger_price"] == 3450.0
        assert s["filled"] == 10
        assert s["tag"] == "my_tag"

    def test_summary_fallback_symbol(self):
        order = Order(order_id="Y", security_id="SEC123")
        s = order.summary()
        assert s["symbol"] == "SEC123"


# ============================================================
# Trade
# ============================================================


class TestTradeExtended:
    def test_from_dhan(self):
        data = {
            "tradeNo": "T5001",
            "orderId": "12345",
            "securityId": "2885",
            "tradingSymbol": "RELIANCE",
            "transactionType": "BUY",
            "quantity": 10,
            "tradedPrice": 2450.75,
            "exchangeTradeNo": "EX999",
        }
        t = Trade.from_dhan(data)
        assert t.trade_id == "T5001"
        assert t.order_id == "12345"
        assert t.security_id == "2885"
        assert t.trading_symbol == "RELIANCE"
        assert t.side == Side.BUY
        assert t.quantity == 10
        assert t.price == Decimal("2450.75")

    def test_notional(self):
        t = Trade(quantity=50, price=Decimal("100"))
        assert t.notional == Decimal("5000")


# ============================================================
# Quote & OHLCV
# ============================================================


class TestQuoteExtended:
    def test_from_dhan_quote_full(self):
        data = {
            "last_price": 2500.50,
            "average_price": 2490.00,
            "top_bid_price": 2499.00,
            "top_bid_quantity": 100,
            "top_ask_price": 2501.00,
            "top_ask_quantity": 50,
            "last_quantity": 10,
            "volume": 123456,
            "oi": 50000,
            "ohlc": {"open": 2480, "high": 2510, "low": 2470, "close": 2485},
            "upper_circuit_limit": 2750,
            "lower_circuit_limit": 2200,
            "net_change": 15.50,
        }
        q = Quote.from_dhan_quote("NSE_EQ", "2885", data)
        assert q.security_id == "2885"
        assert q.exchange == "NSE_EQ"
        assert q.last_price == Decimal("2500.50")
        assert q.average_price == Decimal("2490.00")
        assert q.bid_price == Decimal("2499.00")
        assert q.bid_quantity == 100
        assert q.ask_price == Decimal("2501.00")
        assert q.ask_quantity == 50
        assert q.volume == 123456
        assert q.open_interest == 50000
        assert q.open == Decimal("2480")
        assert q.upper_circuit == Decimal("2750")

    def test_change_pct_positive(self):
        q = Quote(last_price=Decimal("110"), close=Decimal("100"))
        assert q.change_pct == Decimal("10.00")

    def test_change_pct_negative(self):
        q = Quote(last_price=Decimal("90"), close=Decimal("100"))
        assert q.change_pct == Decimal("-10.00")

    def test_change_pct_zero_close(self):
        q = Quote(last_price=Decimal("100"), close=Decimal("0"))
        assert q.change_pct == Decimal("0")


class TestOHLCVExtended:
    def test_from_dict_with_oi(self):
        data = {
            "timestamp": [1700000000, 1700086400],
            "open": [100, 101],
            "high": [110, 112],
            "low": [95, 99],
            "close": [105, 108],
            "volume": [1000, 1200],
            "open_interest": [500, 600],
        }
        bar = OHLCV.from_dict(data, 0)
        assert bar.open == Decimal("100")
        assert bar.high == Decimal("110")
        assert bar.volume == 1000
        assert bar.open_interest == 500

    def test_from_dict_no_oi(self):
        data = {
            "timestamp": [1700000000],
            "open": [100],
            "high": [110],
            "low": [95],
            "close": [105],
            "volume": [1000],
        }
        bar = OHLCV.from_dict(data, 0)
        assert bar.open_interest is None


# ============================================================
# OptionChain
# ============================================================


class TestOptionChainExtended:
    def test_from_dhan_realistic(self):
        payload = {
            "data": {
                "last_price": 24500,
                "oc": {
                    "24000": {
                        "ce": {
                            "security_id": "50001",
                            "last_price": 600,
                            "oi": 10000,
                            "volume": 500,
                        },
                        "pe": {
                            "security_id": "50002",
                            "last_price": 100,
                            "oi": 15000,
                            "volume": 300,
                        },
                    },
                    "24500": {
                        "ce": {
                            "security_id": "50003",
                            "last_price": 300,
                            "oi": 8000,
                            "volume": 200,
                        },
                        "pe": {
                            "security_id": "50004",
                            "last_price": 300,
                            "oi": 8000,
                            "volume": 250,
                        },
                    },
                    "25000": {
                        "ce": {
                            "security_id": "50005",
                            "last_price": 100,
                            "oi": 5000,
                        },
                        "pe": {
                            "security_id": "50006",
                            "last_price": 600,
                            "oi": 20000,
                        },
                    },
                },
            }
        }
        chain = OptionChain.from_dhan(payload, expiry="2025-03-27")
        assert chain.spot_price == Decimal("24500")
        assert chain.expiry == "2025-03-27"
        assert len(chain.strikes) == 3

    def test_find_atm_exact(self):
        chain = OptionChain(
            spot_price=Decimal("24500"),
            strikes=[
                OptionStrike(strike=Decimal("24000")),
                OptionStrike(strike=Decimal("24500")),
                OptionStrike(strike=Decimal("25000")),
            ],
        )
        atm = chain.find_atm()
        assert atm.strike == Decimal("24500")

    def test_find_atm_closest(self):
        chain = OptionChain(
            spot_price=Decimal("24650"),
            strikes=[
                OptionStrike(strike=Decimal("24000")),
                OptionStrike(strike=Decimal("24500")),
                OptionStrike(strike=Decimal("25000")),
            ],
        )
        atm = chain.find_atm()
        assert atm.strike == Decimal("24500")

    def test_find_atm_empty(self):
        chain = OptionChain(strikes=[])
        assert chain.find_atm() is None

    def test_pcr(self):
        chain = OptionChain(
            strikes=[
                OptionStrike(
                    call=OptionQuote(open_interest=1000),
                    put=OptionQuote(open_interest=2000),
                ),
            ],
        )
        assert chain.pcr == Decimal("2")

    def test_pcr_zero_call_oi(self):
        chain = OptionChain(
            strikes=[
                OptionStrike(
                    call=OptionQuote(open_interest=0),
                    put=OptionQuote(open_interest=1000),
                ),
            ],
        )
        assert chain.pcr == Decimal("0")

    def test_total_call_oi(self):
        chain = OptionChain(
            strikes=[
                OptionStrike(call=OptionQuote(open_interest=500)),
                OptionStrike(call=OptionQuote(open_interest=300)),
            ],
        )
        assert chain.total_call_oi == 800

    def test_total_put_oi(self):
        chain = OptionChain(
            strikes=[
                OptionStrike(put=OptionQuote(open_interest=1000)),
                OptionStrike(put=OptionQuote(open_interest=2000)),
            ],
        )
        assert chain.total_put_oi == 3000

    def test_calls_and_puts_properties(self):
        chain = OptionChain(
            strikes=[
                OptionStrike(
                    call=OptionQuote(security_id="C1"),
                    put=OptionQuote(security_id="P1"),
                ),
                OptionStrike(
                    call=OptionQuote(security_id="C2"),
                    put=None,
                ),
            ],
        )
        assert len(chain.calls) == 2
        assert len(chain.puts) == 1

    def test_find_strike(self):
        chain = OptionChain(
            strikes=[
                OptionStrike(strike=Decimal("24000")),
                OptionStrike(strike=Decimal("24500")),
            ],
        )
        found = chain.find_strike(Decimal("24500"))
        assert found is not None
        assert found.strike == Decimal("24500")
        assert chain.find_strike(Decimal("23000")) is None


# ============================================================
# Instruments
# ============================================================


class TestInstrumentsExtended:
    def test_equity_type(self):
        eq = Equity(security_id="1", trading_symbol="TCS")
        assert eq.instrument_type == InstrumentType.EQUITY
        assert eq.display_symbol == ""

    def test_index_type_and_segment(self):
        idx = Index(security_id="13", trading_symbol="NIFTY")
        assert idx.instrument_type == InstrumentType.INDEX
        assert idx.exchange_segment == ExchangeSegment.INDEX

    def test_future_type(self):
        f = Future(security_id="100", trading_symbol="NIFTY28MAR25FUT")
        assert f.instrument_type == InstrumentType.FUTIDX

    def test_future_with_expiry(self):
        f = Future(
            security_id="100",
            trading_symbol="NIFTY28MAR25FUT",
            expiry=ExpiryDate(date(2025, 3, 28)),
        )
        key = f.to_key()
        assert key.expiry == date(2025, 3, 28)

    def test_option_call(self):
        o = Option(
            security_id="200",
            trading_symbol="NIFTY28MAR2524000CE",
            strike=Decimal("24000"),
            option_type=OptionType.CALL,
        )
        assert o.is_call
        assert not o.is_put

    def test_option_put(self):
        o = Option(
            security_id="201",
            trading_symbol="NIFTY28MAR2524000PE",
            strike=Decimal("24000"),
            option_type=OptionType.PUT,
        )
        assert o.is_put
        assert not o.is_call

    def test_option_to_key(self):
        o = Option(
            security_id="200",
            trading_symbol="NIFTY28MAR2524000CE",
            strike=Decimal("24000"),
            option_type=OptionType.CALL,
            expiry=ExpiryDate(date(2025, 3, 28)),
            instrument_type=InstrumentType.OPTIDX,
        )
        key = o.to_key()
        assert key.strike == Decimal("24000")
        assert key.option_type == OptionType.CALL
        assert key.expiry == date(2025, 3, 28)

    def test_instrument_from_dhan_master(self):
        data = {
            "SEM_SMST_SECURITY_ID": "2885",
            "SEM_TRADING_SYMBOL": "RELIANCE",
            "SEM_CUSTOM_SYMBOL": "RELIANCE EQ",
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_INSTRUMENT_NAME": "EQUITY",
            "SEM_LOT_UNITS": "1",
            "SEM_TICK_SIZE": "0.05",
            "SEM_FREEZE_QTY": "500000",
        }
        inst = Instrument.from_dhan_master(data)
        assert inst.security_id == "2885"
        assert inst.trading_symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.exchange_segment == ExchangeSegment.NSE_EQ
        assert inst.freeze_quantity == 500000

    def test_instrument_from_dhan_master_futidx(self):
        data = {
            "SEM_SMST_SECURITY_ID": "49081",
            "SEM_TRADING_SYMBOL": "NIFTY28MAR25FUT",
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_INSTRUMENT_NAME": "FUTIDX",
            "SEM_LOT_UNITS": "50",
            "SEM_TICK_SIZE": "0.05",
        }
        inst = Instrument.from_dhan_master(data)
        assert inst.instrument_type == InstrumentType.FUTIDX
        assert inst.exchange_segment == ExchangeSegment.NSE_FNO
        assert inst.lot_size == 50

    def test_instrument_from_dhan_master_optidx(self):
        data = {
            "SEM_SMST_SECURITY_ID": "50001",
            "SEM_TRADING_SYMBOL": "NIFTY28MAR2524000CE",
            "SEM_EXM_EXCH_ID": "NSE",
            "SEM_INSTRUMENT_NAME": "OPTIDX",
        }
        inst = Instrument.from_dhan_master(data)
        assert inst.instrument_type == InstrumentType.OPTIDX
        assert inst.exchange_segment == ExchangeSegment.NSE_FNO

    def test_instrument_to_key(self):
        inst = Instrument(
            security_id="1",
            trading_symbol="RELIANCE",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.EQUITY,
        )
        key = inst.to_key()
        assert key.symbol == "RELIANCE"
        assert key.exchange == Exchange.NSE

    def test_instrument_str(self):
        inst = Instrument(
            security_id="1",
            trading_symbol="RELIANCE",
            display_symbol="RELIANCE EQ",
            exchange=Exchange.NSE,
        )
        assert "RELIANCE EQ" in str(inst)
        assert "NSE" in str(inst)

    def test_instrument_str_no_display(self):
        inst = Instrument(
            security_id="1",
            trading_symbol="RELIANCE",
            exchange=Exchange.NSE,
        )
        assert "RELIANCE" in str(inst)


# ============================================================
# BUILTIN_INSTRUMENTS
# ============================================================


class TestBuiltinInstruments:
    def test_nifty(self):
        nifty = BUILTIN_INSTRUMENTS["NIFTY"]
        assert nifty.security_id == "13"
        assert nifty.lot_size == 50
        assert nifty.exchange == Exchange.INDEX

    def test_banknifty(self):
        bn = BUILTIN_INSTRUMENTS["BANKNIFTY"]
        assert bn.security_id == "25"
        assert bn.lot_size == 15

    def test_finnifty(self):
        fn = BUILTIN_INSTRUMENTS["FINNIFTY"]
        assert fn.security_id == "27"
        assert fn.lot_size == 40

    def test_midcpnifty(self):
        mcp = BUILTIN_INSTRUMENTS["MIDCPNIFTY"]
        assert mcp.security_id == "442"
        assert mcp.lot_size == 75

    def test_sensex(self):
        sx = BUILTIN_INSTRUMENTS["SENSEX"]
        assert sx.security_id == "51"
        assert sx.lot_size == 10
        assert sx.exchange == Exchange.BSE

    def test_all_are_index(self):
        for inst in BUILTIN_INSTRUMENTS.values():
            assert isinstance(inst, Index)

    def test_all_have_tick_size(self):
        for inst in BUILTIN_INSTRUMENTS.values():
            assert inst.tick_size == Decimal("0.05")


# ============================================================
# InstrumentMapper (base)
# ============================================================


class TestInstrumentMapper:
    @pytest.mark.asyncio
    async def test_load_and_resolve(self):
        mapper = InstrumentMapper("test_broker")
        rows = [
            {
                "SEM_SMST_SECURITY_ID": "2885",
                "SEM_TRADING_SYMBOL": "RELIANCE",
                "SEM_EXM_EXCH_ID": "NSE",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": "1",
                "SEM_TICK_SIZE": "0.05",
            }
        ]
        # Base _parse_row returns None, so load won't add mappings
        await mapper.load(rows)
        assert mapper.is_loaded
        assert mapper.count == 0  # base class returns None from _parse_row

    @pytest.mark.asyncio
    async def test_refresh(self):
        mapper = InstrumentMapper("test_broker")
        await mapper.load([])
        assert mapper.is_loaded
        await mapper.refresh([])
        assert mapper.is_loaded
        assert mapper.count == 0
