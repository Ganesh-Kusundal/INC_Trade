"""Unit tests for Dhan reconciliation engine and adapter."""

from __future__ import annotations

from decimal import Decimal

from brokers.adapters.dhan.reconciliation import DhanReconciliation
from brokers.services.reconciliation import DriftItem, ReconciliationEngine, ReconciliationReport
from brokers.domain import Order, Position
from brokers.domain.enums import OrderStatus, OrderType, Side


def _order(
    order_id: str,
    symbol: str,
    *,
    status: OrderStatus = OrderStatus.OPEN,
    quantity: int = 10,
) -> Order:
    return Order(
        order_id=order_id,
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        status=status,
    )


def _position(symbol: str, quantity: int, exchange: str = "NSE") -> Position:
    return Position(
        symbol=symbol,
        exchange=exchange,
        quantity=quantity,
        average_price=Decimal("2500"),
    )


class _OrdersStub:
    def __init__(self, orders: list[Order] | None = None, *, error: Exception | None = None):
        self._orders = orders or []
        self._error = error

    def get_orderbook(self) -> list[Order]:
        if self._error is not None:
            raise self._error
        return list(self._orders)


class _PortfolioStub:
    def __init__(
        self, positions: list[Position] | None = None, *, error: Exception | None = None
    ):
        self._positions = positions or []
        self._error = error

    def positions(self) -> list[Position]:
        if self._error is not None:
            raise self._error
        return list(self._positions)


class _OmsStub:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}
        self.positions: list[dict] = []
        self.upsert_order_calls: list[Order] = []
        self.upsert_position_calls: list[dict] = []

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def upsert_order(self, order: Order) -> None:
        self.orders[order.order_id] = order
        self.upsert_order_calls.append(order)

    def upsert_position(self, position: dict) -> None:
        self.positions.append(position)
        self.upsert_position_calls.append(position)


class TestReconciliationEngine:
    def test_compare_orders_no_drift_when_matching(self):
        engine = ReconciliationEngine()
        orders = [_order("ORD-001", "RELIANCE", status=OrderStatus.FILLED)]
        drift = engine.compare_orders(orders, list(orders))
        assert drift == []

    def test_compare_orders_missing_broker_order_high_severity(self):
        engine = ReconciliationEngine()
        local = [_order("ORD-001", "RELIANCE", status=OrderStatus.OPEN)]
        drift = engine.compare_orders(local, [])
        assert len(drift) == 1
        assert drift[0].kind == "missing_broker_order"
        assert drift[0].severity == "HIGH"
        assert drift[0].symbol == "RELIANCE"

    def test_compare_orders_missing_local_order_high_severity(self):
        engine = ReconciliationEngine()
        broker = [_order("ORD-002", "INFY", status=OrderStatus.FILLED)]
        drift = engine.compare_orders([], broker)
        assert len(drift) == 1
        assert drift[0].kind == "missing_local_order"
        assert drift[0].severity == "HIGH"

    def test_compare_orders_status_mismatch_medium_severity(self):
        engine = ReconciliationEngine()
        local = [_order("ORD-001", "RELIANCE", status=OrderStatus.OPEN)]
        broker = [_order("ORD-001", "RELIANCE", status=OrderStatus.FILLED)]
        drift = engine.compare_orders(local, broker)
        assert len(drift) == 1
        assert drift[0].kind == "order_status_mismatch"
        assert drift[0].severity == "MEDIUM"

    def test_compare_orders_ignores_terminal_missing_on_broker(self):
        engine = ReconciliationEngine()
        local = [_order("ORD-001", "RELIANCE", status=OrderStatus.FILLED)]
        drift = engine.compare_orders(local, [])
        assert drift == []

    def test_compare_positions_no_drift_when_matching(self):
        engine = ReconciliationEngine()
        positions = [_position("RELIANCE", 10)]
        drift = engine.compare_positions(positions, list(positions))
        assert drift == []

    def test_compare_positions_quantity_mismatch_high_severity(self):
        engine = ReconciliationEngine()
        local = [_position("RELIANCE", 100)]
        broker = [_position("RELIANCE", 50)]
        drift = engine.compare_positions(local, broker)
        assert len(drift) == 1
        assert drift[0].kind == "position_quantity_mismatch"
        assert drift[0].severity == "HIGH"
        assert drift[0].payload == {
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "local_qty": 100,
            "broker_qty": 50,
        }

    def test_compare_positions_missing_broker_position_high_severity(self):
        engine = ReconciliationEngine()
        local = [_position("RELIANCE", 100)]
        drift = engine.compare_positions(local, [])
        assert len(drift) == 1
        assert drift[0].kind == "missing_broker_position"
        assert drift[0].severity == "HIGH"

    def test_compare_positions_missing_local_position_high_severity(self):
        engine = ReconciliationEngine()
        broker = [_position("RELIANCE", 50)]
        drift = engine.compare_positions([], broker)
        assert len(drift) == 1
        assert drift[0].kind == "missing_local_position"
        assert drift[0].severity == "HIGH"

    def test_compare_positions_ignores_zero_local_without_broker(self):
        engine = ReconciliationEngine()
        local = [_position("RELIANCE", 0)]
        drift = engine.compare_positions(local, [])
        assert drift == []


class TestDhanReconciliation:
    def test_reconcile_no_drift_when_empty(self):
        recon = DhanReconciliation(_OrdersStub(), _PortfolioStub())
        report = recon.reconcile()
        assert not report.has_drift
        assert report.broker_orders == 0
        assert report.broker_positions == 0

    def test_reconcile_detects_missing_order(self):
        recon = DhanReconciliation(_OrdersStub([]), _PortfolioStub())
        local_orders = [_order("ORD-001", "RELIANCE", status=OrderStatus.OPEN)]
        report = recon.reconcile(local_orders=local_orders)
        assert report.has_drift
        assert report.high_severity_count == 1
        assert report.drift_items[0].kind == "missing_broker_order"

    def test_reconcile_detects_status_mismatch(self):
        broker_order = _order("ORD-001", "RELIANCE", status=OrderStatus.FILLED)
        recon = DhanReconciliation(_OrdersStub([broker_order]), _PortfolioStub())
        local_orders = [_order("ORD-001", "RELIANCE", status=OrderStatus.OPEN)]
        report = recon.reconcile(local_orders=local_orders)
        assert any(d.kind == "order_status_mismatch" for d in report.drift_items)

    def test_reconcile_detects_position_quantity_mismatch(self):
        broker_positions = [_position("RELIANCE", 50)]
        recon = DhanReconciliation(_OrdersStub(), _PortfolioStub(broker_positions))
        local_positions = [_position("RELIANCE", 100)]
        report = recon.reconcile(local_positions=local_positions)
        assert any(d.kind == "position_quantity_mismatch" for d in report.drift_items)

    def test_reconcile_detects_missing_position(self):
        recon = DhanReconciliation(_OrdersStub(), _PortfolioStub([]))
        local_positions = [_position("RELIANCE", 100)]
        report = recon.reconcile(local_positions=local_positions)
        assert any(d.kind == "missing_broker_position" for d in report.drift_items)

    def test_reconcile_handles_fetch_error(self):
        recon = DhanReconciliation(
            _OrdersStub(error=RuntimeError("API down")),
            _PortfolioStub(),
        )
        report = recon.reconcile()
        assert report.has_drift
        assert any(d.kind == "fetch_error" for d in report.drift_items)

    def test_reconcile_no_drift_when_matching(self):
        broker_order = _order("ORD-001", "RELIANCE", status=OrderStatus.FILLED)
        broker_positions = [_position("RELIANCE", 10)]
        recon = DhanReconciliation(
            _OrdersStub([broker_order]),
            _PortfolioStub(broker_positions),
        )
        local_orders = [_order("ORD-001", "RELIANCE", status=OrderStatus.FILLED)]
        local_positions = [_position("RELIANCE", 10)]
        report = recon.reconcile(
            local_orders=local_orders,
            local_positions=local_positions,
        )
        assert not report.has_drift

    def test_reconcile_auto_repair_upserts_missing_order(self):
        broker_order = _order("ORD-002", "INFY", status=OrderStatus.FILLED, quantity=5)
        oms = _OmsStub()
        recon = DhanReconciliation(
            _OrdersStub([broker_order]),
            _PortfolioStub(),
            oms=oms,
            auto_repair=True,
        )
        report = recon.reconcile(local_orders=[])
        assert report.orders_repaired == 1
        assert len(oms.upsert_order_calls) == 1
        assert oms.upsert_order_calls[0].order_id == "ORD-002"

    def test_reconcile_auto_repair_upserts_position(self):
        broker_positions = [_position("RELIANCE", 50)]
        oms = _OmsStub()
        recon = DhanReconciliation(
            _OrdersStub(),
            _PortfolioStub(broker_positions),
            oms=oms,
            auto_repair=True,
        )
        report = recon.reconcile(local_positions=[])
        assert report.positions_repaired == 1
        assert len(oms.upsert_position_calls) == 1
        call_args = oms.upsert_position_calls[0]
        assert call_args["symbol"] == "RELIANCE"
        assert call_args["quantity"] == 50
        assert call_args["exchange"] == "NSE"

    def test_reconcile_no_repair_when_auto_repair_false(self):
        broker_order = _order("ORD-003", "TCS", status=OrderStatus.FILLED, quantity=5)
        oms = _OmsStub()
        recon = DhanReconciliation(
            _OrdersStub([broker_order]),
            _PortfolioStub(),
            oms=oms,
            auto_repair=False,
        )
        recon.reconcile(local_orders=[])
        assert oms.upsert_order_calls == []
        assert oms.upsert_position_calls == []
