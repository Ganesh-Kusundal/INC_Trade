"""Tests for domain model."""

from datetime import date
from decimal import Decimal

import pytest
from tradex.domain.account import Account, AccountProfile, FundLimits
from tradex.domain.enums import (
    Exchange,
    InstrumentType,
    OptionType,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
)
from tradex.domain.execution import Order
from tradex.domain.instruments import (
    BUILTIN_INSTRUMENTS,
    Equity,
    Option,
)
from tradex.domain.market_data import (
    DepthLevel,
    MarketDepth,
    OptionChain,
    OptionQuote,
    OptionStrike,
    Quote,
)
from tradex.domain.portfolio import Holding, Portfolio, Position
from tradex.domain.value_objects import DateRange, InstrumentKey, Money, Price, Quantity

# --- Value Object Tests ---


class TestMoney:
    def test_creation(self):
        m = Money(Decimal("100.50"))
        assert m.amount == Decimal("100.50")
        assert m.currency == "INR"

    def test_from_float(self):
        m = Money(100.50)
        assert m.amount == Decimal("100.50")

    def test_addition(self):
        m1 = Money(Decimal("100"))
        m2 = Money(Decimal("50"))
        result = m1 + m2
        assert result.amount == Decimal("150")

    def test_subtraction(self):
        m1 = Money(Decimal("100"))
        m2 = Money(Decimal("30"))
        result = m1 - m2
        assert result.amount == Decimal("70")

    def test_multiplication(self):
        m = Money(Decimal("100"))
        result = m * 3
        assert result.amount == Decimal("300")

    def test_zero(self):
        m = Money.zero()
        assert m.amount == Decimal("0")

    def test_str(self):
        m = Money(Decimal("1000.50"))
        assert "1,000.50" in str(m)

    def test_comparison(self):
        assert Money(Decimal("100")) < Money(Decimal("200"))
        assert Money(Decimal("200")) > Money(Decimal("100"))
        assert Money(Decimal("100")) == Money(Decimal("100"))


class TestPrice:
    def test_tick_alignment(self):
        p = Price(Decimal("100.12"), Decimal("0.05"))
        assert p.value == Decimal("100.10")  # Rounded to nearest 0.05

    def test_from_float(self):
        p = Price.from_float(100.12, 0.05)
        assert p.value == Decimal("100.10")

    def test_as_float(self):
        p = Price(Decimal("100.50"))
        assert p.as_float == 100.5


class TestQuantity:
    def test_creation(self):
        q = Quantity(100, 10)
        assert q.value == 100
        assert q.lots == 10

    def test_invalid_lot(self):
        with pytest.raises(ValueError):
            Quantity(105, 10)

    def test_from_lots(self):
        q = Quantity.from_lots(5, 10)
        assert q.value == 50


class TestDateRange:
    def test_creation(self):
        dr = DateRange(date(2024, 1, 1), date(2024, 1, 31))
        assert dr.days == 31

    def test_invalid_range(self):
        with pytest.raises(ValueError):
            DateRange(date(2024, 1, 31), date(2024, 1, 1))

    def test_contains(self):
        dr = DateRange(date(2024, 1, 1), date(2024, 1, 31))
        assert dr.contains(date(2024, 1, 15))
        assert not dr.contains(date(2024, 2, 1))


class TestInstrumentKey:
    def test_str(self):
        key = InstrumentKey(
            symbol="NIFTY",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.OPTIDX,
            expiry=date(2024, 3, 28),
            strike=Decimal("24000"),
            option_type=OptionType.CALL,
        )
        s = str(key)
        assert "NIFTY" in s
        assert "OPTIDX" in s
        assert "CALL" in s


# --- Account Tests ---


class TestAccount:
    def test_fund_limits(self):
        data = {
            "availabelBalance": 100000,
            "sodLimit": 0,
            "collateralAmount": 50000,
            "utilizedAmount": 30000,
            "blockedPayoutAmount": 5000,
            "withdrawableBalance": 95000,
        }
        fl = FundLimits.from_dhan(data)
        assert fl.available_balance == Decimal("100000")
        assert fl.net_available == Decimal("145000")  # 100000 + 50000 - 5000

    def test_account_profile(self):
        data = {
            "dhanClientId": "123",
            "fullName": "Test User",
            "activeSegment": "NSE_EQ,BSE_EQ",
            "dataPlan": True,
        }
        profile = AccountProfile.from_dhan(data)
        assert profile.client_id == "123"
        assert profile.has_segment("NSE_EQ")
        assert not profile.has_segment("MCX_COMM")

    def test_account(self):
        account = Account(
            account_id="123",
            broker_name="dhan",
            connected=True,
            profile=AccountProfile(client_id="123", active_segments=["NSE_EQ"]),
        )
        assert account.can_trade
        assert account.has_segment("NSE_EQ")


# --- Portfolio Tests ---


class TestPortfolio:
    def test_holding(self):
        data = {
            "securityId": "2885",
            "tradingSymbol": "RELIANCE",
            "exchange": "NSE_EQ",
            "totalQty": 10,
            "availableQty": 10,
            "avgCostPrice": 2450.0,
        }
        h = Holding.from_dhan(data)
        assert h.security_id == "2885"
        assert h.total_quantity == 10
        assert h.is_sellable

    def test_position(self):
        data = {
            "securityId": "49081",
            "tradingSymbol": "NIFTY28MAR25FUT",
            "exchangeSegment": "NSE_FNO",
            "productType": "INTRADAY",
            "positionType": "LONG",
            "buyAvg": 24500.0,
            "buyQty": 75,
            "sellAvg": 24600.0,
            "sellQty": 75,
            "netQty": 0,
            "realizedProfit": 7500.0,
            "unrealizedProfit": 0.0,
        }
        p = Position.from_dhan(data)
        assert p.security_id == "49081"
        assert not p.is_open
        assert p.total_pnl == Decimal("7500")

    def test_portfolio_summary(self):
        portfolio = Portfolio(
            account_id="123",
            holdings=[
                Holding(security_id="2885", total_quantity=10, average_cost_price=Decimal("2450")),
            ],
            positions=[
                Position(
                    net_quantity=75,
                    realized_profit=Decimal("500"),
                    unrealized_profit=Decimal("-200"),
                ),
                Position(net_quantity=0, realized_profit=Decimal("1000")),
            ],
        )
        assert len(portfolio.open_positions) == 1
        assert len(portfolio.closed_positions) == 1
        assert portfolio.total_realized_pnl == Decimal("1500")
        assert portfolio.total_unrealized_pnl == Decimal("-200")


# --- Execution Tests ---


class TestOrder:
    def test_from_dhan(self):
        data = {
            "orderId": "12345",
            "correlationID": "test_tag",
            "securityId": "2885",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "LIMIT",
            "productType": "CNC",
            "quantity": 10,
            "price": 2450.0,
            "orderStatus": "PENDING",
            "filledQty": 0,
            "pendingQty": 10,
        }
        order = Order.from_dhan(data)
        assert order.order_id == "12345"
        assert order.side == Side.BUY
        assert order.status == OrderStatus.PENDING
        assert order.is_active

    def test_fill(self):
        order = Order(
            order_id="123",
            quantity=10,
            price=Decimal("100"),
            status=OrderStatus.OPEN,
        )
        order.fill(5, Decimal("105"))
        assert order.filled_quantity == 5
        assert order.pending_quantity == 5
        assert order.status == OrderStatus.PART_TRADED

        order.fill(5, Decimal("100"))
        assert order.is_filled

    def test_summary(self):
        order = Order(
            order_id="123",
            trading_symbol="RELIANCE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            product_type=ProductType.CNC,
            quantity=10,
            price=Decimal("2450"),
            status=OrderStatus.TRADED,
        )
        s = order.summary()
        assert s["order_id"] == "123"
        assert s["side"] == "BUY"


# --- Market Data Tests ---


class TestMarketData:
    def test_quote(self):
        q = Quote(
            security_id="2885",
            last_price=Decimal("2450"),
            close=Decimal("2440"),
        )
        assert q.change_pct > 0

    def test_option_chain(self):
        chain = OptionChain(
            spot_price=Decimal("24500"),
            expiry="2024-03-28",
            strikes=[
                OptionStrike(
                    strike=Decimal("24000"),
                    call=OptionQuote(
                        security_id="111", last_price=Decimal("600"), open_interest=1000
                    ),
                    put=OptionQuote(
                        security_id="222", last_price=Decimal("100"), open_interest=2000
                    ),
                ),
                OptionStrike(
                    strike=Decimal("25000"),
                    call=OptionQuote(
                        security_id="333", last_price=Decimal("100"), open_interest=500
                    ),
                    put=OptionQuote(
                        security_id="444", last_price=Decimal("600"), open_interest=3000
                    ),
                ),
            ],
        )
        assert chain.total_call_oi == 1500
        assert chain.total_put_oi == 5000
        assert chain.pcr > 0

        atm = chain.find_atm()
        assert atm is not None
        assert atm.strike == Decimal("24000")

    def test_depth(self):
        depth = MarketDepth(
            security_id="2885",
            levels=[
                DepthLevel(
                    bid_price=Decimal("2449"),
                    bid_quantity=100,
                    ask_price=Decimal("2450"),
                    ask_quantity=50,
                ),
            ],
        )
        assert depth.total_bid_quantity == 100
        assert depth.total_ask_quantity == 50


# --- Instrument Tests ---


class TestInstruments:
    def test_builtin_instruments(self):
        assert "NIFTY" in BUILTIN_INSTRUMENTS
        assert "BANKNIFTY" in BUILTIN_INSTRUMENTS
        nifty = BUILTIN_INSTRUMENTS["NIFTY"]
        assert nifty.security_id == "13"
        assert nifty.lot_size == 50

    def test_equity(self):
        eq = Equity(security_id="2885", trading_symbol="RELIANCE")
        assert eq.instrument_type == InstrumentType.EQUITY

    def test_option(self):
        opt = Option(
            security_id="111",
            trading_symbol="NIFTY28MAR2524000CE",
            strike=Decimal("24000"),
            option_type=OptionType.CALL,
        )
        assert opt.is_call
        assert not opt.is_put
        key = opt.to_key()
        assert key.strike == Decimal("24000")
