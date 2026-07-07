"""Shared reconciliation base — broker-agnostic drift detection + event emission.

Compares local OMS order state against broker-fetched state and emits
:class:`DomainEvent` records describing drift. **No auto-repair is performed.**
Drift remediation is the responsibility of downstream event subscribers.

Both :class:`~brokers.upstox.extended.reconciliation.UpstoxReconciliation` and
:class:`~brokers.dhan.extended.reconciliation.DhanReconciliation` subclass
:class:`BaseReconciliation`, supplying only:

- ``SOURCE_LABEL`` — string identifier for event sources
- ``ORDER_ID_KEY`` — key used in broker order dict for the order id
- ``STATUS_KEY`` — key used in broker order dict for the order status
- ``_fetch_broker_orders()`` — API call returning ``list[dict]``

Usage via the shared base::

    class UpstoxReconciliation(BaseReconciliation):
        SOURCE_LABEL = "upstox_reconciliation"
        ORDER_ID_KEY = "order_id"
        STATUS_KEY = "status"

        def _fetch_broker_orders(self):
            data = self._client.get("/v2/order/retrieve-all")
            return data.get("data", [])
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar

from brokers.domain.events import DomainEvent, EventType
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from brokers.infrastructure.event_bus import EventBus

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReconciliationDrift:
    """Describes a discrepancy between OMS and broker state.

    Frozen value object returned from :meth:`BaseReconciliation.compare_orders`.
    Carries three categories of drift: orders that exist broker-side but not
    locally (``missing_in_local``), orders that exist locally but not broker-side
    (``missing_in_broker``), and orders present in both with conflicting status
    (``status_mismatches`` — tuples of ``(order_id, local_status, broker_status)``).
    """

    missing_in_local: list[str] = field(default_factory=list)
    missing_in_broker: list[str] = field(default_factory=list)
    status_mismatches: tuple[tuple[str, str, str], ...] = ()

    @property
    def has_drift(self) -> bool:
        return bool(
            self.missing_in_local
            or self.missing_in_broker
            or self.status_mismatches
        )

    @property
    def total_count(self) -> int:
        return (
            len(self.missing_in_local)
            + len(self.missing_in_broker)
            + len(self.status_mismatches)
        )


class BaseReconciliation(ABC):
    """Template-method base for broker order reconciliation.

    Subclasses MUST define ``SOURCE_LABEL``, ``ORDER_ID_KEY``, ``STATUS_KEY``
    class attributes and implement :meth:`_fetch_broker_orders`.

    Subclasses MAY override :meth:`_emit_drift` if they want a different
    payload shape, but the default implementation is sufficient for current
    consumers.
    """

    SOURCE_LABEL: ClassVar[str] = ""
    ORDER_ID_KEY: ClassVar[str] = ""
    STATUS_KEY: ClassVar[str] = ""

    def __init__(self, *, client: BaseHttpClient) -> None:
        missing = [
            name for name, val in (
                ("SOURCE_LABEL", self.SOURCE_LABEL),
                ("ORDER_ID_KEY", self.ORDER_ID_KEY),
                ("STATUS_KEY", self.STATUS_KEY),
            ) if not val
        ]
        if missing:
            raise ValueError(
                f"{type(self).__name__} is missing required class "
                f"attribute(s): {', '.join(missing)}. Subclasses of "
                f"BaseReconciliation must set SOURCE_LABEL, ORDER_ID_KEY, "
                f"and STATUS_KEY as non-empty ClassVar[str] values."
            )
        self._client = client

    @abstractmethod
    def _fetch_broker_orders(self) -> list[dict[str, Any]]:
        """Subclass hook: return a list of broker order dicts.

        Implementations can delegate to :meth:`_safe_fetch` so they only need
        to supply the HTTP call; the base handles the try/except wrapper,
        the warning log, and the JSON-shaped response normalisation.
        """

    def _safe_fetch(
        self,
        fetch: Callable[[], Any],
    ) -> list[dict[str, Any]]:
        """Run ``fetch()``, swallow exceptions, normalise the response.

        Behaviour:

        - ``fetch()`` raises any exception → return ``[]`` and log a
          warning tagged ``{SOURCE_LABEL}_fetch_failed``.
        - ``fetch()`` returns a non-``dict`` → return ``[]``.
        - ``fetch()`` returns ``dict`` without a ``"data"`` key → return ``[]``.
        - ``fetch()`` returns ``dict`` with ``"data"`` not a ``list`` → return ``[]``.
        - Otherwise return ``fetch()["data"]`` as ``list[dict[str, Any]]``.

        Subclasses can therefore expose a 1-line ``_fetch_broker_orders``::

            return self._safe_fetch(
                lambda: self._client.get("/v2/order/retrieve-all")
            )
        """
        try:
            data = fetch()
        except Exception as exc:
            logger.warning(
                f"{self.SOURCE_LABEL}_fetch_failed",
                error=str(exc)[:200],
            )
            return []

        if not isinstance(data, dict):
            return []
        result = data.get("data", [])
        if not isinstance(result, list):
            return []
        return result


    def compare_orders(self, local_orders: dict[str, str]) -> ReconciliationDrift:
        """Compare local orders (order_id -> status) with broker state.

        Synchronous, side-effect-free. Returns :class:`ReconciliationDrift`.
        """
        broker_orders = self._fetch_broker_orders()
        broker_map: dict[str, str] = {}
        for o in broker_orders:
            oid = str(o.get(self.ORDER_ID_KEY, "") or "")
            if not oid:
                continue
            status = str(o.get(self.STATUS_KEY, "") or "")
            broker_map[oid] = status

        missing_in_local = [
            oid for oid in broker_map if oid not in local_orders
        ]
        missing_in_broker = [
            oid for oid in local_orders if oid not in broker_map
        ]

        status_mismatches: list[tuple[str, str, str]] = []
        for oid in set(local_orders) & set(broker_map):
            if local_orders[oid] != broker_map[oid]:
                status_mismatches.append(
                    (oid, local_orders[oid], broker_map[oid])
                )

        return ReconciliationDrift(
            missing_in_local=missing_in_local,
            missing_in_broker=missing_in_broker,
            status_mismatches=tuple(status_mismatches),
        )

    def compare_orders_with_events(
        self,
        local_orders: dict[str, str],
        *,
        bus: "EventBus | None" = None,
    ) -> ReconciliationDrift:
        """Compare and publish events to ``bus`` when provided.

        Event pattern:

        - No drift → ``RECONCILIATION_OK`` + ``RECONCILIATION_COMPLETED``
        - Drift → one ``RECONCILIATION_DRIFT`` per item,
          then ``RECONCILIATION_COMPLETED``

        If ``bus`` is ``None``, the method is equivalent to :meth:`compare_orders`.
        """
        drift = self.compare_orders(local_orders)
        if bus is None:
            return drift

        now_iso = datetime.now(timezone.utc).isoformat()

        if not drift.has_drift:
            bus.publish(
                DomainEvent.now(
                    event_type=EventType.RECONCILIATION_OK.value,
                    payload={
                        "checked_at": now_iso,
                        "symbols": sorted(local_orders),
                    },
                    source=self.SOURCE_LABEL,
                )
            )
        else:
            for oid in drift.missing_in_local:
                self._emit_drift(bus, oid, internal="missing", broker="present")
            for oid in drift.missing_in_broker:
                self._emit_drift(bus, oid, internal="present", broker="missing")
            for oid, local_status, broker_status in drift.status_mismatches:
                self._emit_drift(
                    bus, oid, internal=local_status, broker=broker_status
                )

        bus.publish(
            DomainEvent.now(
                event_type=EventType.RECONCILIATION_COMPLETED.value,
                payload={
                    "checked_at": now_iso,
                    "symbols": sorted(local_orders),
                    "drift_count": drift.total_count,
                },
                source=self.SOURCE_LABEL,
            )
        )
        return drift

    def _emit_drift(
        self,
        bus: "EventBus",
        oid: str,
        *,
        internal: str,
        broker: str,
    ) -> None:
        """Publish a single ``RECONCILIATION_DRIFT`` event.

        Subclasses may override to customise payload shape, but the default
        covers the contract defined in
        :data:`brokers.domain.events.EVENT_PAYLOADS` for ``RECONCILIATION_DRIFT``.
        """
        bus.publish(
            DomainEvent.now(
                event_type=EventType.RECONCILIATION_DRIFT.value,
                payload={
                    "symbol": oid,
                    "order_id": oid,
                    "internal": internal,
                    "broker": broker,
                },
                source=self.SOURCE_LABEL,
            )
        )


__all__ = ["BaseReconciliation", "ReconciliationDrift"]
