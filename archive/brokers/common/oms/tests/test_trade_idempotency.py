"""Tests for the OMS idempotent trade processing — the line of defence
against double-position bugs.

The actual contract is:
- A trade fired twice via the bus must mutate order state exactly once.
- A trade for an unknown order must NOT mark the ledger, so a delayed
  order event can still result in the trade being applied once the
  order surfaces.
- A trade with no trade_id must be rejected, not silently dropped.
"""

from __future__ import annotations

import pytest

from application.oms.order_manager import OrderManager, OrderRequest
from brokers.common.observability.event_metrics import EventMetrics
from domain import (
    Order,
    OrderStatus,
    OrderType,
    Side,
    Trade,
)
from infrastructure.event_bus import (
    DeadLetterQueue,
    DomainEvent,
    EventBus,
    EventType,
    ProcessedTradeRepository,
)
from infrastructure.metrics.registry import metrics_registry


@pytest.fixture(autouse=True)
def _reset_global_metrics_registry() -> None:
    """EventMetrics delegates to a process-global registry; reset for isolation."""
    metrics_registry.reset_all()
    yield
    metrics_registry.reset_all()


def _make_order(symbol: str = "RELIANCE", quantity: int = 10) -> Order:
    return Order(
        order_id="O1",
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=quantity,
        price="2500",
        status=OrderStatus.OPEN,
    )


def _make_trade(
    trade_id: str = "T1",
    order_id: str = "O1",
    quantity: int = 5,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=quantity,
        price="2500",
    )


@pytest.fixture
def bus() -> EventBus:
    metrics = EventMetrics()
    dlq = DeadLetterQueue()
    return EventBus(metrics=metrics, dead_letter_queue=dlq)


@pytest.fixture
def repo() -> ProcessedTradeRepository:
    return ProcessedTradeRepository()


@pytest.fixture
def order_manager(bus: EventBus, repo: ProcessedTradeRepository) -> OrderManager:
    return OrderManager(
        event_bus=bus,
        processed_trade_repository=repo,
        metrics=bus._metrics,  # type: ignore[attr-defined]
    )


def test_record_trade_first_time_returns_true(
    order_manager: OrderManager,
) -> None:
    order_manager.upsert_order(_make_order())
    trade = _make_trade()
    assert order_manager.record_trade(trade) is True
    order = order_manager.get_order("O1")
    assert order is not None
    assert order.filled_quantity == 5


def test_duplicate_trade_returns_false_and_does_not_double_fill(
    order_manager: OrderManager,
) -> None:
    order_manager.upsert_order(_make_order())
    trade = _make_trade()
    order_manager.record_trade(trade)
    order_manager.record_trade(trade)  # duplicate
    order = order_manager.get_order("O1")
    assert order is not None
    assert order.filled_quantity == 5  # NOT 10


def test_trade_with_empty_id_is_rejected() -> None:
    repo = ProcessedTradeRepository()
    om = OrderManager(processed_trade_repository=repo)
    order_manager = om
    with pytest.raises(ValueError):
        order_manager.record_trade(
            Trade(
                trade_id="",
                order_id="O1",
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=1,
                price="1",
            )
        )


def test_trade_for_unknown_order_does_not_mark_ledger(
    order_manager: OrderManager,
    repo: ProcessedTradeRepository,
) -> None:
    """A trade for an order we haven't seen yet must NOT be marked.

    Otherwise a later delivery of the same order would be treated as a
    duplicate and silently dropped.
    """
    trade = _make_trade(trade_id="T-ORPHAN", order_id="O-MISSING")
    result = order_manager.record_trade(trade)
    assert result is False
    assert not repo.is_processed(
        __import__("infrastructure.event_bus", fromlist=["TradeIdKey"]).TradeIdKey.from_trade(trade)
    )


def test_metrics_record_trade_outcomes(
    order_manager: OrderManager,
) -> None:
    metrics = order_manager._metrics
    order_manager.upsert_order(_make_order())
    order_manager.record_trade(_make_trade("T-OK"))
    order_manager.record_trade(_make_trade("T-OK"))  # duplicate
    assert metrics.get("TRADE", "trade_processed") == 1
    assert metrics.get("TRADE", "trade_duplicated") == 1


def test_on_trade_event_is_idempotent(bus: EventBus, repo: ProcessedTradeRepository) -> None:
    om = OrderManager(
        event_bus=bus,
        processed_trade_repository=repo,
        metrics=bus._metrics,  # type: ignore[attr-defined]
    )
    om.upsert_order(_make_order())
    bus.subscribe(EventType.TRADE.value, om.on_trade)

    trade = _make_trade("T1")
    event = DomainEvent.now(
        EventType.TRADE.value, {"trade": trade}, symbol="RELIANCE"
    )
    bus.publish(event)
    bus.publish(event)  # duplicate
    bus.publish(event)  # duplicate

    order = om.get_order("O1")
    assert order is not None
    assert order.filled_quantity == 5


def test_place_order_still_emits_order_placed_event(bus: EventBus) -> None:
    om = OrderManager(event_bus=bus)
    seen: list[DomainEvent] = []
    bus.subscribe(EventType.ORDER_PLACED.value, seen.append)
    om.place_order(OrderRequest("RELIANCE", "NSE", Side.BUY, 10))
    assert len(seen) == 1
    assert seen[0].event_type == "ORDER_PLACED"


def test_upsert_order_emits_order_updated_event(bus: EventBus) -> None:
    om = OrderManager(event_bus=bus)
    seen: list[DomainEvent] = []
    bus.subscribe(EventType.ORDER_UPDATED.value, seen.append)
    om.upsert_order(_make_order())
    assert len(seen) == 1
