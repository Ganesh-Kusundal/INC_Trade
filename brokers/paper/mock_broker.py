"""MockBroker — thin legacy wrapper for backward compatibility."""

from __future__ import annotations

import random
from decimal import Decimal

from application.oms.context import TradingContext
from domain import Balance, Holding, OrderResponse, Position
from domain.constants.defaults import PAPER_INITIAL_CAPITAL

from .paper_gateway import PaperGateway


class MockBroker:
    """Thin backward-compatibility wrapper around PaperGateway.

    Exposes a ``connect()`` / ``disconnect()`` lifecycle that earlier code
    expected, while delegating everything else to a PaperGateway.
    """

    def __init__(
        self,
        initial_capital: Decimal = PAPER_INITIAL_CAPITAL,
        name: str = "paper",
        trading_context: TradingContext | None = None,
    ) -> None:
        self._name = name
        self._id = f"paper-{random.randint(1000, 9999)}"
        self._connected = False
        self._gw = PaperGateway(
            initial_capital=initial_capital,
            trading_context=trading_context,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def broker_id(self) -> str:
        return self._id

    @property
    def gateway(self) -> PaperGateway:
        return self._gw

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> bool:
        self._connected = False
        return True

    def is_connected(self) -> bool:
        return self._connected

    def place_order(self, *args, **kwargs) -> OrderResponse:
        return self._gw.place_order(*args, **kwargs)

    def cancel_order(self, order_id: str) -> bool:
        return self._gw.cancel_order(order_id)

    def get_orderbook(self) -> list[dict]:
        return self._gw.get_orderbook()

    def get_trade_book(self) -> list[dict]:
        return self._gw.get_trade_book()

    def get_positions(self) -> list[Position]:
        return self._gw.positions()

    def get_holdings(self) -> list[Holding]:
        return self._gw.holdings()

    def get_balance(self) -> Balance:
        return self._gw.funds()

    # -- Seed API for test fixtures -----------------------------------------

    def seed_orders(self, orders: list) -> None:
        self._gw.seed_orders(orders)

    def seed_trades(self, trades: list) -> None:
        self._gw.seed_trades(trades)

    def seed_positions(self, positions: dict) -> None:
        self._gw.seed_positions(positions)

    def seed_holdings(self, holdings: list) -> None:
        self._gw.seed_holdings(holdings)

    # -- ABC-aligned aliases (match MarketDataGateway interface) -------------

    def quote(self, symbol: str, exchange: str = "NSE"):
        return self._gw.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE"):
        return self._gw.ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE"):
        return self._gw.depth(symbol, exchange)

    def positions(self) -> list[Position]:
        return self._gw.positions()

    def holdings(self) -> list[Holding]:
        return self._gw.holdings()

    def funds(self) -> Balance:
        return self._gw.funds()

    def trades(self):
        return self._gw.trades()

    @property
    def portfolio(self):
        """Expose portfolio sub-object matching BrokerGateway.portfolio interface."""
        return self._gw.portfolio


# Backward-compatibility alias removed — use MockBroker directly.


def create_demo_broker(
    name: str = "dhan",
    initial_capital: Decimal = PAPER_INITIAL_CAPITAL,
) -> MockBroker:
    """Create a MockBroker pre-populated with realistic seed data.

    Provides the same orders, trades, positions, and holdings that the
    CLI's former MockBroker class used, so the TUI and CLI commands
    display meaningful data when no live broker is connected.
    """
    from datetime import datetime, timedelta, timezone

    from domain import (
        Holding,
        Order,
        OrderStatus,
        OrderType,
        Position,
        ProductType,
        Side,
        Trade,
    )

    broker = MockBroker(initial_capital=initial_capital, name=name)
    broker.connect()

    now = datetime.now(timezone.utc)
    prefix = name.upper()

    broker.seed_orders(
        [
            Order(
                order_id=f"{prefix}-ORD-101",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=10,
                filled_quantity=10,
                price=Decimal("2550.00"),
                status=OrderStatus.FILLED,
                product_type=ProductType.INTRADAY,
                avg_price=Decimal("2550.00"),
                timestamp=now - timedelta(hours=2),
            ),
            Order(
                order_id=f"{prefix}-ORD-102",
                symbol="SBIN",
                exchange="NSE",
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                quantity=50,
                filled_quantity=0,
                price=Decimal("590.00"),
                status=OrderStatus.OPEN,
                product_type=ProductType.INTRADAY,
                timestamp=now - timedelta(minutes=15),
            ),
        ]
    )

    broker.seed_trades(
        [
            Trade(
                trade_id=f"{prefix}-TRD-201",
                order_id=f"{prefix}-ORD-101",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                price=Decimal("2550.00"),
                timestamp=now - timedelta(hours=2),
            ),
        ]
    )

    broker.seed_positions(
        {
            "RELIANCE:NSE": Position(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                avg_price=Decimal("2550.00"),
                ltp=Decimal("2565.50"),
                unrealized_pnl=Decimal("155.00"),
                realized_pnl=Decimal("0.00"),
                product_type=ProductType.INTRADAY,
            ),
        }
    )

    broker.seed_holdings(
        [
            Holding(
                symbol="INFY",
                exchange="NSE",
                quantity=20,
                available_quantity=20,
                avg_price=Decimal("1420.00"),
                ltp=Decimal("1435.00"),
                pnl=Decimal("300.00"),
            ),
            Holding(
                symbol="HDFCBANK",
                exchange="NSE",
                quantity=50,
                available_quantity=50,
                avg_price=Decimal("1580.00"),
                ltp=Decimal("1565.00"),
                pnl=Decimal("-750.00"),
            ),
        ]
    )

    return broker
