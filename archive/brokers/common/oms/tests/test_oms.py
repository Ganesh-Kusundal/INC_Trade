"""Tests for the central OMS (OrderManager + PositionManager + RiskManager)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from application.oms import (
    OrderManager,
    OrderRequest,
    PositionManager,
    RiskConfig,
    RiskManager,
)
from domain import Order, OrderStatus, OrderType, ProductType, Side, Trade
from infrastructure.event_bus import DomainEvent, EventBus, EventType


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def order_manager(bus: EventBus) -> OrderManager:
    return OrderManager(event_bus=bus)


@pytest.fixture
def position_manager(bus: EventBus) -> PositionManager:
    return PositionManager(event_bus=bus)


# ── OrderManager ───────────────────────────────────────────────────────────


def test_place_order(order_manager: OrderManager) -> None:
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 10)
    result = order_manager.place_order(req)
    assert result.success
    assert result.order is not None
    assert result.order.symbol == "RELIANCE"
    assert result.order.status == OrderStatus.OPEN


def test_place_order_idempotent_by_correlation_id(order_manager: OrderManager) -> None:
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 10, correlation_id="same-id")
    r1 = order_manager.place_order(req)
    r2 = order_manager.place_order(req)
    assert r1.order is not None
    assert r2.order is not None
    assert r1.order.order_id == r2.order.order_id


def test_concurrent_place_order_same_correlation_id(order_manager: OrderManager) -> None:
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 10, correlation_id="race-id")

    def place(_: int) -> str:
        result = order_manager.place_order(req)
        return result.order.order_id if result.order else ""

    with ThreadPoolExecutor(max_workers=20) as pool:
        order_ids = list(pool.map(place, range(50)))

    unique_ids = {oid for oid in order_ids if oid}
    assert len(unique_ids) == 1


def test_record_trade_updates_order(order_manager: OrderManager) -> None:
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 10)
    result = order_manager.place_order(req)
    order = result.order
    trade = Trade(
        trade_id="T1",
        order_id=order.order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=5,
        price=Decimal("100"),
    )
    order_manager.record_trade(trade)
    updated = order_manager.get_order(order.order_id)
    assert updated.filled_quantity == 5
    assert updated.status == OrderStatus.PARTIALLY_FILLED


def test_record_trade_fills_order(order_manager: OrderManager) -> None:
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 10)
    order = order_manager.place_order(req).order
    trade = Trade(
        trade_id="T1",
        order_id=order.order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    order_manager.record_trade(trade)
    updated = order_manager.get_order(order.order_id)
    assert updated.filled_quantity == 10
    assert updated.status == OrderStatus.FILLED


def test_cancel_order(order_manager: OrderManager) -> None:
    order = order_manager.place_order(OrderRequest("RELIANCE", "NSE", Side.BUY, 10)).order
    result = order_manager.cancel_order(order.order_id)
    assert result.success
    assert result.order.status == OrderStatus.CANCELLED


def test_cancel_filled_order_fails(order_manager: OrderManager) -> None:
    order = order_manager.place_order(OrderRequest("RELIANCE", "NSE", Side.BUY, 10)).order
    trade = Trade(
        trade_id="T1",
        order_id=order.order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    order_manager.record_trade(trade)
    result = order_manager.cancel_order(order.order_id)
    assert not result.success


# ── PositionManager ────────────────────────────────────────────────────────


def test_apply_trade_creates_position(position_manager: PositionManager) -> None:
    trade = Trade(
        trade_id="T1",
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    pos = position_manager.apply_trade(trade)
    assert pos.quantity == 10
    assert pos.avg_price == Decimal("100")


def test_apply_trade_sell_reduces_position(position_manager: PositionManager) -> None:
    position_manager.apply_trade(Trade("T1", "O1", "RELIANCE", "NSE", Side.BUY, 10, Decimal("100")))
    pos = position_manager.apply_trade(
        Trade("T2", "O2", "RELIANCE", "NSE", Side.SELL, 4, Decimal("110"))
    )
    assert pos.quantity == 6


def test_apply_trade_side_flip(position_manager: PositionManager) -> None:
    position_manager.apply_trade(Trade("T1", "O1", "RELIANCE", "NSE", Side.BUY, 10, Decimal("100")))
    pos = position_manager.apply_trade(
        Trade("T2", "O2", "RELIANCE", "NSE", Side.SELL, 15, Decimal("110"))
    )
    assert pos.quantity == -5
    assert pos.avg_price == Decimal("110")
    assert pos.realized_pnl == Decimal("100")


def test_concurrent_trades_on_same_symbol(position_manager: PositionManager) -> None:
    def buy(i: int) -> None:
        position_manager.apply_trade(
            Trade(f"T{i}", f"O{i}", "RELIANCE", "NSE", Side.BUY, 1, Decimal("100"))
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(buy, range(100)))

    pos = position_manager.get_position("RELIANCE", "NSE")
    assert pos.quantity == 100


# ── RiskManager ────────────────────────────────────────────────────────────


def test_risk_manager_allows_safe_order(position_manager: PositionManager) -> None:
    risk = RiskManager(position_manager, RiskConfig(), lambda: Decimal("100000"))
    order = _make_order("RELIANCE", "NSE", Side.BUY, 10, Decimal("100"))
    result = risk.check_order(order)
    assert result.allowed


def test_risk_manager_blocks_excessive_position(position_manager: PositionManager) -> None:
    risk = RiskManager(
        position_manager, RiskConfig(max_position_pct=Decimal("1")), lambda: Decimal("100000")
    )
    order = _make_order("RELIANCE", "NSE", Side.BUY, 1000, Decimal("100"))
    result = risk.check_order(order)
    assert not result.allowed


def test_risk_manager_kill_switch(position_manager: PositionManager) -> None:
    risk = RiskManager(position_manager, RiskConfig(), lambda: Decimal("100000"))
    risk.set_kill_switch(True)
    order = _make_order("RELIANCE", "NSE", Side.BUY, 1, Decimal("100"))
    result = risk.check_order(order)
    assert not result.allowed


def test_risk_manager_blocks_insufficient_capital(position_manager: PositionManager) -> None:
    risk = RiskManager(position_manager, RiskConfig(), lambda: Decimal("0"))
    order = _make_order("RELIANCE", "NSE", Side.BUY, 1, Decimal("100"))
    result = risk.check_order(order)
    assert not result.allowed


def test_order_manager_risk_gate_blocks_order(
    bus: EventBus, position_manager: PositionManager
) -> None:
    risk = RiskManager(
        position_manager, RiskConfig(max_position_pct=Decimal("1")), lambda: Decimal("100000")
    )
    om = OrderManager(event_bus=bus, risk_manager=risk)
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 1000, Decimal("100"))
    result = om.place_order(req)
    assert not result.success
    assert result.error is not None


def test_order_manager_risk_gate_allows_order(bus: EventBus) -> None:
    om = OrderManager(event_bus=bus)
    req = OrderRequest("RELIANCE", "NSE", Side.BUY, 1, Decimal("100"))
    result = om.place_order(req)
    assert result.success


def test_trading_context_replays_event_log(tmp_path) -> None:
    from application.oms.context import TradingContext
    from infrastructure.event_log import EventLog

    log = EventLog(events_dir=tmp_path / "events")
    bus = EventBus(event_log=log)

    # Simulate order placed and filled before restart.
    order = Order(
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        filled_quantity=10,
        price=Decimal("100"),
        avg_price=Decimal("100"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.FILLED,
    )
    trade = Trade(
        trade_id="T1",
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )
    bus.publish(
        DomainEvent.now(EventType.ORDER_UPDATED.value, {"order": order}, symbol="RELIANCE")
    )
    bus.publish(
        DomainEvent.now(EventType.TRADE.value, {"trade": trade}, symbol="RELIANCE")
    )
    log.close()

    # New context replays the log.
    ctx = TradingContext(event_log=log, replay_events=True)
    assert len(ctx.order_manager.get_orders()) == 1
    assert ctx.order_manager.get_orders()[0].order_id == "O1"
    assert ctx.position_manager.get_position("RELIANCE", "NSE").quantity == 10


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_order(symbol: str, exchange: str, side: Side, qty: int, price: Decimal) -> object:
    from domain import Order

    return Order(
        order_id="O1",
        symbol=symbol,
        exchange=exchange,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        price=price,
        product_type=ProductType.INTRADAY,
    )


# ── Reconciliation compatibility ──────────────────────────────────────────


def test_get_all_orders_returns_dicts(order_manager: OrderManager) -> None:
    """get_all_orders() must return list of dicts."""
    order_manager.place_order(OrderRequest("RELIANCE", "NSE", Side.BUY, 10))
    order_manager.place_order(OrderRequest("INFY", "NSE", Side.SELL, 5))
    result = order_manager.get_all_orders()
    assert len(result) == 2
    assert all(isinstance(o, dict) for o in result)
    assert {o["symbol"] for o in result} == {"RELIANCE", "INFY"}
    assert all("order_id" in o and "status" in o for o in result)


def test_get_positions_as_dicts_returns_dicts(position_manager: PositionManager) -> None:
    """get_positions_as_dicts() must return list of dicts."""
    position_manager.apply_trade(Trade("T1", "O1", "RELIANCE", "NSE", Side.BUY, 10, Decimal("100")))
    result = position_manager.get_positions_as_dicts()
    assert len(result) == 1
    assert isinstance(result[0], dict)
    assert result[0]["symbol"] == "RELIANCE"
    assert result[0]["quantity"] == 10


def test_upsert_position_creates_new(position_manager: PositionManager) -> None:
    """upsert_position() must create a new position from dict."""
    pos = position_manager.upsert_position(
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 50,
            "avg_price": "2500",
            "ltp": "2510",
        }
    )
    assert pos.symbol == "RELIANCE"
    assert pos.quantity == 50
    assert pos.avg_price == Decimal("2500")


def test_upsert_position_updates_existing(position_manager: PositionManager) -> None:
    """upsert_position() must update existing position."""
    position_manager.apply_trade(Trade("T1", "O1", "RELIANCE", "NSE", Side.BUY, 10, Decimal("100")))
    pos = position_manager.upsert_position(
        {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "quantity": 20,
            "avg_price": "150",
        }
    )
    assert pos.quantity == 20


def test_upsert_position_upstox_format(position_manager: PositionManager) -> None:
    """upsert_position() must accept Upstox format keys."""
    pos = position_manager.upsert_position(
        {
            "trading_symbol": "RELIANCE",
            "exchange_segment": "NSE_EQ",
            "net_quantity": "50",
            "average_price": "2500",
        }
    )
    assert pos.symbol == "RELIANCE"
    assert pos.quantity == 50


def test_upsert_position_missing_symbol_raises(position_manager: PositionManager) -> None:
    """upsert_position() must raise ValueError if no symbol."""
    import pytest

    with pytest.raises(ValueError, match="symbol"):
        position_manager.upsert_position({"quantity": 10})
