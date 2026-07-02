"""Dhan reconciliation — drift detection between local OMS and Dhan broker state.

Delegates order/position comparison to the shared
:class:`~brokers.common.reconciliation.engine.ReconciliationEngine`
so broker-specific services only handle fetch + repair logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from brokers.common.reconciliation.engine import ReconciliationEngine
from brokers.dhan.orders import OrdersAdapter
from brokers.dhan.portfolio import PortfolioAdapter
from domain import DriftItem, ReconciliationReport

logger = logging.getLogger(__name__)


def create_reconciliation_service(
    orders_adapter: OrdersAdapter,
    portfolio_adapter: PortfolioAdapter,
    oms: Any = None,
    auto_repair: bool = False,
) -> DhanReconciliationService:
    """Factory that creates a DhanReconciliationService with the right wiring.

    Args:
        orders_adapter: Adapter for fetching broker order state.
        portfolio_adapter: Adapter for fetching broker position state.
        oms: Optional OMS (OrderManager) for auto-repair of local state.
        auto_repair: When True and oms is provided, repair local state from broker.

    Returns:
        A configured DhanReconciliationService instance.
    """
    return DhanReconciliationService(
        orders=orders_adapter,
        portfolio=portfolio_adapter,
        oms=oms,
        auto_repair=auto_repair,
    )


class DhanReconciliationService:
    """Detects drift between local OMS state and Dhan broker state.

    When ``auto_repair=True`` and an ``oms`` object is provided, the service
    will also repair local state by upserting missing/mismatched orders and
    positions from broker state.

    Usage::

        recon = DhanReconciliationService(orders, portfolio, oms=order_manager)
        report = recon.reconcile()
        if report.has_drift:
            for item in report.drift_items:
                print(f"{item.severity}: {item.kind} — {item.symbol}: {item.details}")
    """

    def __init__(
        self,
        orders: OrdersAdapter,
        portfolio: PortfolioAdapter,
        oms: Any = None,
        *,
        auto_repair: bool = False,
    ):
        self._orders = orders
        self._portfolio = portfolio
        self._oms = oms
        self._auto_repair = auto_repair

    def reconcile(
        self,
        local_orders: list[Any] | None = None,
        local_positions: list[Any] | None = None,
    ) -> ReconciliationReport:
        """Run reconciliation and return a drift report.

        Order/position comparison is delegated to the shared
        :class:`ReconciliationEngine`. This method handles broker-specific
        fetch + repair logic.

        Args:
            local_orders: Optional list of local OMS orders to compare against broker.
            local_positions: Optional list of local positions to compare against broker.
        """
        report = ReconciliationReport(timestamp_ms=int(time.time() * 1000))
        drift: list[DriftItem] = []

        # 1. Fetch broker state
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
            broker_positions = self._portfolio.get_positions()
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

        # 2. Compare using shared engine
        engine = ReconciliationEngine()
        if local_orders is not None:
            drift += engine.compare_orders(local_orders, broker_orders)
        if local_positions is not None:
            drift += engine.compare_positions(local_positions, broker_positions)

        report.drift_items = drift

        # 3. Repair local OMS if auto_repair is enabled
        if self._auto_repair and self._oms is not None:
            self._repair_local_oms(broker_orders, broker_positions, drift)

        logger.info(
            "reconciliation_complete",
            extra={
                "drift_count": len(drift),
                "high_severity": report.high_severity_count,
                "broker_orders": report.broker_orders,
                "broker_positions": report.broker_positions,
            },
        )
        return report

    def _repair_local_oms(
        self,
        broker_orders: list[Any],
        broker_positions: list[Any],
        drift: list[DriftItem],
    ) -> None:
        """Repair local OMS state from broker state."""
        # Upsert missing orders
        upsert_order = getattr(self._oms, "upsert_order", None)
        if upsert_order is not None:
            for broker_order in broker_orders:
                local_order = getattr(self._oms, "get_order", lambda oid: None)(
                    broker_order.order_id
                )
                if local_order is None:
                    try:
                        upsert_order(broker_order)
                        logger.info("Repaired missing order %s", broker_order.order_id)
                    except Exception as exc:
                        logger.warning("Failed to repair order %s: %s", broker_order.order_id, exc)

        # Upsert positions from broker
        upsert_position = getattr(self._oms, "upsert_position", None)
        if upsert_position is not None:
            for broker_pos in broker_positions:
                try:
                    upsert_position(
                        {
                            "symbol": broker_pos.symbol,
                            "exchange": getattr(broker_pos, "exchange", "NSE"),
                            "quantity": broker_pos.quantity,
                            "avg_price": str(getattr(broker_pos, "avg_price", "0")),
                            "ltp": str(getattr(broker_pos, "ltp", "0")),
                        }
                    )
                    logger.info("Repaired position %s", broker_pos.symbol)
                except Exception as exc:
                    logger.warning("Failed to repair position %s: %s", broker_pos.symbol, exc)
