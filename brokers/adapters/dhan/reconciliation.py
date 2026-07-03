"""Dhan reconciliation — drift detection between local OMS and Dhan broker state."""

from __future__ import annotations

import logging
import time
from typing import Any

from brokers.adapters.dhan.orders import DhanOrders
from brokers.adapters.dhan.portfolio import DhanPortfolio
from brokers.services.reconciliation import DriftItem, ReconciliationEngine, ReconciliationReport
from brokers.domain import Order, Position

logger = logging.getLogger(__name__)


class DhanReconciliation:
    """Detects drift between local OMS state and Dhan broker state.

    When ``auto_repair=True`` and an ``oms`` object is provided, repairs local
    state by upserting missing orders and positions from broker state.
    """

    def __init__(
        self,
        orders: DhanOrders,
        portfolio: DhanPortfolio,
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
