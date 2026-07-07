"""Dhan reconciliation — subclass of :class:`BaseReconciliation`.

Uses ``/orders`` and maps response keys ``orderId`` / ``orderStatus``.
Comparison + event emission live in the shared base.

Canonical import for ``ReconciliationDrift``: ``from brokers.common.reconciliation import ReconciliationDrift``.
This module exposes only :class:`DhanReconciliation` (the broker-specific subclass).
"""

from __future__ import annotations

from typing import ClassVar

from brokers.common.reconciliation import BaseReconciliation


class DhanReconciliation(BaseReconciliation):
    """Order/position reconciliation for Dhan.

    Detects drift and emits events; **never** auto-repairs.
    """

    SOURCE_LABEL: ClassVar[str] = "dhan_reconciliation"
    ORDER_ID_KEY: ClassVar[str] = "orderId"
    STATUS_KEY: ClassVar[str] = "orderStatus"

    def _fetch_broker_orders(self):
        return self._safe_fetch(
            lambda: self._client.get("/orders")
        )


__all__ = ["DhanReconciliation"]
