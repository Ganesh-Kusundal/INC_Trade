"""Shared reconciliation engine — comparison logic used by all broker adapters.

The engine compares local OMS state against broker-authoritative state
and produces a list of DriftItem entries. Each broker adapter only
needs to provide a thin fetch layer that maps broker-specific responses
to canonical Order/Position types.

Severity vocabulary: "HIGH", "MEDIUM", "LOW" (canonical, ADR-005).
"""

from __future__ import annotations

import logging

from domain import Order, OrderStatus, Position
from domain.reconciliation import DriftItem

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """Broker-agnostic reconciliation comparison engine.

    Usage::

        engine = ReconciliationEngine()
        drift = engine.compare_orders(local_orders, broker_orders)
        drift += engine.compare_positions(local_positions, broker_positions)
    """

    def compare_orders(
        self,
        local_orders: list[Order],
        broker_orders: list[Order],
    ) -> list[DriftItem]:
        """Compare local OMS orders against broker-authoritative orders.

        Returns a list of DriftItem entries describing any drift found.
        """
        drift: list[DriftItem] = []

        broker_by_id = {o.order_id: o for o in broker_orders if o.order_id}
        local_by_id = {o.order_id: o for o in local_orders if o.order_id}

        # Check for orders on broker that are missing locally
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

        # Check for local orders that are missing on broker
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

            # Both exist — compare statuses
            broker_order = broker_by_id[oid]
            if str(local_order.status) != str(broker_order.status):
                drift.append(
                    DriftItem(
                        kind="order_status_mismatch",
                        severity="MEDIUM",
                        symbol=local_order.symbol,
                        details=(
                            f"Order {oid}: local={local_order.status.value}, "
                            f"broker={broker_order.status.value}"
                        ),
                        payload={"order_id": oid, "symbol": local_order.symbol},
                    )
                )

        return drift

    def compare_positions(
        self,
        local_positions: list[Position],
        broker_positions: list[Position],
    ) -> list[DriftItem]:
        """Compare local positions against broker-authoritative positions.

        Returns a list of DriftItem entries describing any drift found.
        """
        drift: list[DriftItem] = []

        broker_by_key = {(p.exchange, p.symbol): p for p in broker_positions}
        local_by_key = {(p.exchange, p.symbol): p for p in local_positions}

        # Check for positions on broker that are missing locally
        for key, broker_pos in broker_by_key.items():
            local_pos = local_by_key.get(key)
            if local_pos is None:
                drift.append(
                    DriftItem(
                        kind="missing_local_position",
                        severity="HIGH",
                        symbol=broker_pos.symbol,
                        details=(
                            f"Broker has position {key} qty={broker_pos.quantity}, local has none"
                        ),
                        payload={"symbol": broker_pos.symbol, "exchange": broker_pos.exchange},
                    )
                )
                continue

            # Both exist — compare quantities
            if local_pos.quantity != broker_pos.quantity:
                drift.append(
                    DriftItem(
                        kind="position_quantity_mismatch",
                        severity="HIGH",
                        symbol=broker_pos.symbol,
                        details=(
                            f"Position {key}: local_qty={local_pos.quantity}, "
                            f"broker_qty={broker_pos.quantity}"
                        ),
                        payload={
                            "symbol": broker_pos.symbol,
                            "exchange": broker_pos.exchange,
                            "local_qty": local_pos.quantity,
                            "broker_qty": broker_pos.quantity,
                        },
                    )
                )

        # Check for local positions missing on broker
        for key, local_pos in local_by_key.items():
            if key not in broker_by_key and local_pos.quantity != 0:
                drift.append(
                    DriftItem(
                        kind="missing_broker_position",
                        severity="HIGH",
                        symbol=local_pos.symbol,
                        details=(
                            f"Local has position {key} qty={local_pos.quantity}, broker has none"
                        ),
                        payload={"symbol": local_pos.symbol, "exchange": local_pos.exchange},
                    )
                )

        return drift
