"""Upstox reconciliation — subclass of :class:`BaseReconciliation`.

Uses ``/v2/order/retrieve-all`` and maps response keys ``order_id`` /
``status``. Comparison + event emission live in the shared base.

Canonical import for ``ReconciliationDrift``: ``from brokers.common.reconciliation import ReconciliationDrift``.
This module exposes only :class:`UpstoxReconciliation` (the broker-specific subclass).
"""

from __future__ import annotations

from typing import ClassVar

from brokers.common.reconciliation import BaseReconciliation


class UpstoxReconciliation(BaseReconciliation):
    """Order/position reconciliation for Upstox.

    Detects drift and emits events; **never** auto-repairs.
    Subscribers to ``RECONCILIATION_DRIFT`` events are responsible
    for any state remediation.
    """

    SOURCE_LABEL: ClassVar[str] = "upstox_reconciliation"
    ORDER_ID_KEY: ClassVar[str] = "order_id"
    STATUS_KEY: ClassVar[str] = "status"

    def _fetch_broker_orders(self):
        return self._safe_fetch(
            lambda: self._client.get("/v2/order/retrieve-all")
        )


__all__ = ["UpstoxReconciliation"]
