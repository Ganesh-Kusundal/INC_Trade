"""Unit tests for DhanReconciliationService."""

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.dhan.reconciliation import DhanReconciliationService
from domain import Order, OrderStatus, OrderType, Position, Side


def _make_orders_adapter(orders=None):
    adapter = MagicMock()
    adapter.get_orderbook.return_value = orders or []
    return adapter


def _make_portfolio_adapter(positions=None):
    adapter = MagicMock()
    adapter.get_positions.return_value = positions or []
    return adapter


def test_reconcile_no_drift_when_empty():
    """No local state + no broker state = no drift."""
    orders = _make_orders_adapter()
    portfolio = _make_portfolio_adapter()
    recon = DhanReconciliationService(orders, portfolio)
    report = recon.reconcile()
    assert not report.has_drift
    assert report.broker_orders == 0
    assert report.broker_positions == 0


def test_reconcile_detects_missing_order():
    """Local open order not found on broker = HIGH drift."""
    orders = _make_orders_adapter([])
    portfolio = _make_portfolio_adapter()
    recon = DhanReconciliationService(orders, portfolio)

    local_orders = [
        Order(
            order_id="ORD-001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            status=OrderStatus.OPEN,
        ),
    ]
    report = recon.reconcile(local_orders=local_orders)
    assert report.has_drift
    assert report.high_severity_count == 1
    assert report.drift_items[0].kind == "missing_broker_order"
    assert report.drift_items[0].symbol == "RELIANCE"


def test_reconcile_detects_status_mismatch():
    """Local says OPEN, broker says FILLED = MEDIUM drift."""
    broker_order = Order(
        order_id="ORD-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        status=OrderStatus.FILLED,
    )
    orders = _make_orders_adapter([broker_order])
    portfolio = _make_portfolio_adapter()
    recon = DhanReconciliationService(orders, portfolio)

    local_orders = [
        Order(
            order_id="ORD-001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            status=OrderStatus.OPEN,
        ),
    ]
    report = recon.reconcile(local_orders=local_orders)
    assert report.has_drift
    assert any(d.kind == "order_status_mismatch" for d in report.drift_items)


def test_reconcile_detects_position_quantity_mismatch():
    """Local qty=100, broker qty=50 = HIGH drift."""
    orders = _make_orders_adapter()
    broker_positions = [
        Position(symbol="RELIANCE", exchange="NSE", quantity=50, avg_price=Decimal("2500")),
    ]
    portfolio = _make_portfolio_adapter(broker_positions)
    recon = DhanReconciliationService(orders, portfolio)

    local_positions = [
        Position(symbol="RELIANCE", exchange="NSE", quantity=100, avg_price=Decimal("2500")),
    ]
    report = recon.reconcile(local_positions=local_positions)
    assert report.has_drift
    assert any(d.kind == "position_quantity_mismatch" for d in report.drift_items)


def test_reconcile_detects_missing_position():
    """Local has position, broker doesn't = HIGH drift."""
    orders = _make_orders_adapter()
    portfolio = _make_portfolio_adapter([])
    recon = DhanReconciliationService(orders, portfolio)

    local_positions = [
        Position(symbol="RELIANCE", exchange="NSE", quantity=100, avg_price=Decimal("2500")),
    ]
    report = recon.reconcile(local_positions=local_positions)
    assert report.has_drift
    assert any(d.kind == "missing_broker_position" for d in report.drift_items)


def test_reconcile_handles_fetch_error():
    """Broker API failure = HIGH drift with fetch_error."""
    orders = MagicMock()
    orders.get_orderbook.side_effect = Exception("API down")
    portfolio = _make_portfolio_adapter()
    recon = DhanReconciliationService(orders, portfolio)

    report = recon.reconcile()
    assert report.has_drift
    assert any(d.kind == "fetch_error" for d in report.drift_items)


def test_reconcile_no_drift_when_matching():
    """Matching local and broker state = no drift."""
    broker_order = Order(
        order_id="ORD-001",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        status=OrderStatus.FILLED,
    )
    orders = _make_orders_adapter([broker_order])
    broker_positions = [
        Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500")),
    ]
    portfolio = _make_portfolio_adapter(broker_positions)
    recon = DhanReconciliationService(orders, portfolio)

    local_orders = [
        Order(
            order_id="ORD-001",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            status=OrderStatus.FILLED,
        ),
    ]
    local_positions = [
        Position(symbol="RELIANCE", exchange="NSE", quantity=10, avg_price=Decimal("2500")),
    ]
    report = recon.reconcile(local_orders=local_orders, local_positions=local_positions)
    assert not report.has_drift


def test_reconcile_auto_repair_upserts_missing_order():
    """auto_repair=True must upsert broker orders not in local OMS."""
    broker_order = Order(
        order_id="ORD-002",
        symbol="INFY",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=5,
        status=OrderStatus.FILLED,
    )
    orders = _make_orders_adapter([broker_order])
    portfolio = _make_portfolio_adapter()

    oms = MagicMock()
    oms.get_order.return_value = None  # Order not in local OMS
    oms.get_all_orders.return_value = []

    recon = DhanReconciliationService(orders, portfolio, oms=oms, auto_repair=True)
    recon.reconcile(local_orders=[])
    oms.upsert_order.assert_called_once_with(broker_order)


def test_reconcile_auto_repair_upserts_position():
    """auto_repair=True must upsert broker positions."""
    broker_positions = [
        Position(symbol="RELIANCE", exchange="NSE", quantity=50, avg_price=Decimal("2500")),
    ]
    orders = _make_orders_adapter()
    portfolio = _make_portfolio_adapter(broker_positions)

    oms = MagicMock()
    oms.get_all_orders.return_value = []
    oms.get_positions_as_dicts.return_value = []

    recon = DhanReconciliationService(orders, portfolio, oms=oms, auto_repair=True)
    recon.reconcile(local_positions=[])
    oms.upsert_position.assert_called_once()
    call_args = oms.upsert_position.call_args[0][0]
    assert call_args["symbol"] == "RELIANCE"
    assert call_args["quantity"] == 50


def test_reconcile_no_repair_when_auto_repair_false():
    """auto_repair=False must not call upsert methods."""
    broker_order = Order(
        order_id="ORD-003",
        symbol="TCS",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=5,
        status=OrderStatus.FILLED,
    )
    orders = _make_orders_adapter([broker_order])
    portfolio = _make_portfolio_adapter()

    oms = MagicMock()
    oms.get_all_orders.return_value = []

    recon = DhanReconciliationService(orders, portfolio, oms=oms, auto_repair=False)
    recon.reconcile(local_orders=[])
    oms.upsert_order.assert_not_called()
