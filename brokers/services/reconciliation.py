import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal, Any
import time

from brokers.domain import Order, Position
from brokers.domain.entities import OrderResponse
from brokers.domain.enums import OrderStatus
from brokers.ports.broker import BrokerGateway

logger = logging.getLogger(__name__)

DriftSeverity = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(slots=True)
class DriftItem:
    """Canonical reconciliation drift entry."""

    kind: str
    severity: DriftSeverity
    symbol: str = ""
    details: str = ""
    payload: dict[str, Any] | None = None


@dataclass(slots=True)
class ReconciliationReport:
    """Reconciliation report produced after comparing local OMS vs broker state."""

    drift_items: list[DriftItem] = field(default_factory=list)
    broker_orders: int = 0
    broker_positions: int = 0
    orders_repaired: int = 0
    positions_repaired: int = 0
    timestamp_ms: int = 0

    @property
    def has_drift(self) -> bool:
        return len(self.drift_items) > 0

    @property
    def high_severity_count(self) -> int:
        return sum(1 for d in self.drift_items if d.severity == "HIGH")


class ReconciliationEngine:
    """
    Background daemon that periodically synchronizes local OMS state against the broker's authoritative ledger.
    Crucial for catching ghost fills or dropped WebSocket events.
    Also provides core logic to compare local OMS state against broker-authoritative state.
    """

    def __init__(self, broker: BrokerGateway | None = None, sync_interval_seconds: int = 30):
        self.broker = broker
        self.sync_interval_seconds = sync_interval_seconds
        self._running = False
        self._task = None
        self.local_order_ledger: dict[str, OrderResponse] = {}

    def compare_orders(
        self,
        local_orders: list[Order],
        broker_orders: list[Order],
    ) -> list[DriftItem]:
        """Compare local OMS orders against broker-authoritative orders."""
        drift: list[DriftItem] = []

        broker_by_id = {o.order_id: o for o in broker_orders if o.order_id}
        local_by_id = {o.order_id: o for o in local_orders if o.order_id}

        for oid, broker_order in broker_by_id.items():
            if oid not in local_by_id:
                drift.append(
                    DriftItem(
                        kind="missing_local_order",
                        severity="HIGH",
                        symbol=broker_order.symbol,
                        details=f"Broker order {oid} not present in local OMS",
                        payload={"order_id": oid, "symbol": broker_order.symbol},
                    )
                )

        for oid, local_order in local_by_id.items():
            if oid not in broker_by_id:
                if local_order.status in (
                    OrderStatus.OPEN,
                    OrderStatus.PARTIALLY_FILLED,
                ):
                    drift.append(
                        DriftItem(
                            kind="missing_broker_order",
                            severity="HIGH",
                            symbol=local_order.symbol,
                            details=f"Local order {oid} ({local_order.status.value}) not on broker",
                            payload={"order_id": oid, "symbol": local_order.symbol},
                        )
                    )
                continue

            broker_order = broker_by_id[oid]
            if str(local_order.status) != str(broker_order.status):
                drift.append(
                    DriftItem(
                        kind="order_status_mismatch",
                        severity="MEDIUM",
                        symbol=local_order.symbol,
                        details=f"Order {oid}: local={local_order.status.value}, broker={broker_order.status.value}",
                        payload={"order_id": oid, "symbol": local_order.symbol},
                    )
                )

        return drift

    def compare_positions(
        self,
        local_positions: list[Position],
        broker_positions: list[Position],
    ) -> list[DriftItem]:
        """Compare local positions against broker-authoritative positions."""
        drift: list[DriftItem] = []

        broker_by_key = {(p.exchange, p.symbol): p for p in broker_positions}
        local_by_key = {(p.exchange, p.symbol): p for p in local_positions}

        for key, broker_pos in broker_by_key.items():
            local_pos = local_by_key.get(key)
            if local_pos is None:
                drift.append(
                    DriftItem(
                        kind="missing_local_position",
                        severity="HIGH",
                        symbol=broker_pos.symbol,
                        details=f"Broker has position {key} qty={broker_pos.quantity}, local has none",
                        payload={
                            "symbol": broker_pos.symbol,
                            "exchange": broker_pos.exchange,
                        },
                    )
                )
                continue

            if local_pos.quantity != broker_pos.quantity:
                drift.append(
                    DriftItem(
                        kind="position_quantity_mismatch",
                        severity="HIGH",
                        symbol=broker_pos.symbol,
                        details=f"Position {key}: local_qty={local_pos.quantity}, broker_qty={broker_pos.quantity}",
                        payload={
                            "symbol": broker_pos.symbol,
                            "exchange": broker_pos.exchange,
                            "local_qty": local_pos.quantity,
                            "broker_qty": broker_pos.quantity,
                        },
                    )
                )

        for key, local_pos in local_by_key.items():
            if key not in broker_by_key and local_pos.quantity != 0:
                drift.append(
                    DriftItem(
                        kind="missing_broker_position",
                        severity="HIGH",
                        symbol=local_pos.symbol,
                        details=f"Local has position {key} qty={local_pos.quantity}, broker has none",
                        payload={
                            "symbol": local_pos.symbol,
                            "exchange": local_pos.exchange,
                        },
                    )
                )

        return drift

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._reconciliation_loop())
            logger.info("ReconciliationEngine started.")

    async def stop(self) -> None:
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("ReconciliationEngine stopped.")

    async def _reconciliation_loop(self) -> None:
        while self._running:
            try:
                await self._sync_orders()
            except Exception as e:
                logger.error(f"Reconciliation loop error: {e}")
            await asyncio.sleep(self.sync_interval_seconds)

    async def _sync_orders(self) -> None:
        logger.debug("Performing authoritative broker ledger sync...")
        pass


class BrokerReconciliation:
    """Detects drift between local OMS state and broker state.

    When ``auto_repair=True`` and an ``oms`` object is provided, repairs local
    state by upserting missing orders and positions from broker state.
    """

    def __init__(
        self,
        orders: Any,
        portfolio: Any,
        oms: Any = None,
        *,
        auto_repair: bool = False,
    ) -> None:
        self._orders = orders
        self._portfolio = portfolio
        self._oms = oms
        self._auto_repair = auto_repair
        self._engine = ReconciliationEngine()

    def reconcile(
        self,
        local_orders: list[Order] | None = None,
        local_positions: list[Position] | None = None,
    ) -> ReconciliationReport:
        """Fetch broker state, compare against local OMS, optionally repair."""
        report = ReconciliationReport(timestamp_ms=int(time.time() * 1000))
        drift: list[DriftItem] = []

        try:
            broker_orders = self._orders.get_orderbook()
            report.broker_orders = len(broker_orders)
        except Exception as exc:
            logger.error("reconciliation_orders_failed: %s", exc)
            broker_orders = []
            drift.append(
                DriftItem(
                    kind="fetch_error",
                    severity="HIGH",
                    details=f"Failed to fetch broker orders: {exc}",
                )
            )

        try:
            broker_positions = self._portfolio.positions()
            report.broker_positions = len(broker_positions)
        except Exception as exc:
            logger.error("reconciliation_positions_failed: %s", exc)
            broker_positions = []
            drift.append(
                DriftItem(
                    kind="fetch_error",
                    severity="HIGH",
                    details=f"Failed to fetch broker positions: {exc}",
                )
            )

        if local_orders is not None:
            drift += self._engine.compare_orders(local_orders, broker_orders)
        if local_positions is not None:
            drift += self._engine.compare_positions(local_positions, broker_positions)

        report.drift_items = drift

        if self._auto_repair and self._oms is not None:
            report.orders_repaired, report.positions_repaired = self._repair_local_oms(
                broker_orders, broker_positions
            )

        logger.info(
            "reconciliation_complete",
            extra={
                "drift_count": len(drift),
                "high_severity": report.high_severity_count,
                "broker_orders": report.broker_orders,
                "broker_positions": report.broker_positions,
                "orders_repaired": report.orders_repaired,
                "positions_repaired": report.positions_repaired,
            },
        )
        return report

    def _repair_local_oms(
        self,
        broker_orders: list[Order],
        broker_positions: list[Position],
    ) -> tuple[int, int]:
        """Repair local OMS state from broker state. Returns repair counts."""
        orders_repaired = 0
        positions_repaired = 0

        upsert_order = getattr(self._oms, "upsert_order", None)
        get_order = getattr(self._oms, "get_order", None)
        if upsert_order is not None and get_order is not None:
            for broker_order in broker_orders:
                local_order = get_order(broker_order.order_id)
                if local_order is None:
                    try:
                        upsert_order(broker_order)
                        orders_repaired += 1
                        logger.info("Repaired missing order %s", broker_order.order_id)
                    except Exception as exc:
                        logger.warning(
                            "Failed to repair order %s: %s",
                            broker_order.order_id,
                            exc,
                        )

        upsert_position = getattr(self._oms, "upsert_position", None)
        if upsert_position is not None:
            for broker_pos in broker_positions:
                try:
                    upsert_position(
                        {
                            "symbol": broker_pos.symbol,
                            "exchange": broker_pos.exchange,
                            "quantity": broker_pos.quantity,
                            "avg_price": str(broker_pos.average_price),
                        }
                    )
                    positions_repaired += 1
                    logger.info("Repaired position %s", broker_pos.symbol)
                except Exception as exc:
                    logger.warning(
                        "Failed to repair position %s: %s",
                        broker_pos.symbol,
                        exc,
                    )

        return orders_repaired, positions_repaired


# Alias for backward compatibility
DhanReconciliation = BrokerReconciliation

