"""Upstox reconciliation: drift detection between local OMS and Upstox state.

Mirrors Trade_J ``UpstoxReconciliationService``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from brokers.upstox.market_data.portfolio_client import UpstoxPortfolioClient
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from domain import DriftItem, OrderStatus, ReconciliationReport

logger = logging.getLogger(__name__)


class ReconciliationDrift:
    def __init__(self) -> None:
        self.items: list[DriftItem] = []

    def compare_orders(self, local: list[dict[str, Any]], upstox: list[dict[str, Any]]) -> None:
        local_by_id = {str(o.get("order_id")): o for o in local}
        upstox_by_id = {str(o.get("order_id")): o for o in upstox}
        for oid, order in upstox_by_id.items():
            if oid not in local_by_id:
                self.items.append(
                    DriftItem(
                        kind="missing_local_order",
                        severity="HIGH",
                        details=f"Upstox order {oid} not present in local OMS",
                        payload=order,
                    )
                )
        for oid, order in local_by_id.items():
            if oid not in upstox_by_id:
                status = str(order.get("status", "")).upper()
                if status in (OrderStatus.OPEN.value, "PENDING", "TRIGGER_PENDING"):
                    continue
                self.items.append(
                    DriftItem(
                        kind="missing_upstox_order",
                        severity="MEDIUM",
                        details=f"Local order {oid} not present in Upstox state",
                        payload=order,
                    )
                )

    def compare_positions(
        self,
        local: list[dict[str, Any]],
        upstox: list[dict[str, Any]],
    ) -> None:
        local_by_key = {
            (str(p.get("exchange_segment")), str(p.get("trading_symbol"))): p for p in local
        }
        upstox_by_key = {
            (str(p.get("exchange_segment")), str(p.get("trading_symbol"))): p for p in upstox
        }
        for key, pos in upstox_by_key.items():
            local_pos = local_by_key.get(key)
            if local_pos is None:
                self.items.append(
                    DriftItem(
                        kind="missing_local_position",
                        severity="HIGH",
                        details=f"Upstox position {key} not present locally",
                        payload=pos,
                    )
                )
                continue
            try:
                local_qty = int(local_pos.get("net_quantity") or local_pos.get("quantity") or 0)
                upstox_qty = int(pos.get("net_quantity") or pos.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if local_qty != upstox_qty:
                self.items.append(
                    DriftItem(
                        kind="position_quantity_mismatch",
                        severity="HIGH",
                        details=f"Position {key}: local={local_qty} upstox={upstox_qty}",
                        payload={"local": local_pos, "upstox": pos},
                    )
                )


def create_reconciliation_service(
    order_client: UpstoxRestOrderClient,
    portfolio_client: UpstoxPortfolioClient,
    oms: Any = None,
    auto_repair: bool = False,
) -> UpstoxReconciliationService:
    """Factory function to create an UpstoxReconciliationService."""
    return UpstoxReconciliationService(
        order_client=order_client,
        portfolio_client=portfolio_client,
        oms=oms,
        auto_repair=auto_repair,
    )


class UpstoxReconciliationService:
    """Run on boot, every 5 min, and on WS reconnect. Compares OMS state
    to Upstox's authoritative state and repairs drift (with safety guards).
    """

    def __init__(
        self,
        order_client: UpstoxRestOrderClient,
        portfolio_client: UpstoxPortfolioClient,
        oms: Any = None,
        *,
        auto_repair: bool = False,
    ) -> None:
        self._order_client = order_client
        self._portfolio_client = portfolio_client
        self._oms = oms
        self._auto_repair = auto_repair

    def reconcile(
        self,
        *,
        on_drift: Callable[[ReconciliationReport], None] | None = None,
    ) -> ReconciliationReport:
        drift = ReconciliationDrift()
        report = ReconciliationReport(timestamp_ms=int(time.time() * 1000))

        try:
            upstox_orders = self._order_client.get_order_list()
        except Exception as exc:
            logger.warning("Reconciliation: could not fetch Upstox orders: %s", exc)
            upstox_orders = []
        try:
            upstox_positions = self._portfolio_client.get_short_term_positions()
        except Exception as exc:
            logger.warning("Reconciliation: could not fetch Upstox positions: %s", exc)
            upstox_positions = []

        local_orders = self._oms_orders() if self._oms is not None else []
        local_positions = self._oms_positions() if self._oms is not None else []

        drift.compare_orders(local_orders, upstox_orders)
        drift.compare_positions(local_positions, upstox_positions)

        report.drift_items = list(drift.items)
        orders_repaired = 0
        positions_repaired = 0
        if self._auto_repair:
            for item in drift.items:
                if item.severity != "HIGH":
                    continue
                if item.kind == "missing_local_order":
                    orders_repaired += self._repair_missing_order(item.payload)
                elif item.kind == "position_quantity_mismatch":
                    positions_repaired += self._repair_position_drift(item.payload)
        report.orders_repaired = orders_repaired
        report.positions_repaired = positions_repaired

        if on_drift is not None and drift.items:
            try:
                on_drift(report)
            except (ValueError, KeyError, ConnectionError, TimeoutError) as exc:
                logger.exception("on_drift callback failed: %s", exc)

        return report

    def _oms_orders(self) -> list[dict[str, Any]]:
        if self._oms is None:
            return []
        method = getattr(self._oms, "get_all_orders", None)
        if method is None:
            return []
        try:
            return method()
        except (ValueError, KeyError, ConnectionError, TimeoutError):
            return []

    def _oms_positions(self) -> list[dict[str, Any]]:
        if self._oms is None:
            return []
        # Prefer get_positions_as_dicts() for dict-compatible format
        method = getattr(self._oms, "get_positions_as_dicts", None)
        if method is not None:
            try:
                return method()
            except Exception as exc:
                logger.debug("oms_get_positions_as_dicts_failed: %s", exc)
        # Fallback to get_positions()
        method = getattr(self._oms, "get_positions", None)
        if method is None:
            return []
        try:
            result = method()
            # Convert Position objects to dicts if needed
            if result and not isinstance(result[0], dict):
                return [
                    {
                        "exchange_segment": getattr(p, "exchange", ""),
                        "trading_symbol": getattr(p, "symbol", ""),
                        "net_quantity": getattr(p, "quantity", 0),
                        "avg_price": str(getattr(p, "avg_price", "0")),
                    }
                    for p in result
                ]
            return result
        except (ValueError, KeyError, ConnectionError, TimeoutError):
            return []

    def _repair_missing_order(self, payload: dict[str, Any]) -> int:
        if self._oms is None:
            return 0
        method = getattr(self._oms, "upsert_order", None)
        if method is None:
            return 0
        try:
            method(payload)
            return 1
        except (ValueError, KeyError, ConnectionError, TimeoutError):
            return 0

    def _repair_position_drift(self, payload: dict[str, Any]) -> int:
        if self._oms is None:
            return 0
        method = getattr(self._oms, "upsert_position", None)
        if method is None:
            return 0
        try:
            upstox = payload.get("upstox") or {}
            method(upstox)
            return 1
        except (ValueError, KeyError, ConnectionError, TimeoutError):
            return 0
