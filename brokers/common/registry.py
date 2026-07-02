"""BrokerRegistry — registration, lifecycle, health, and session summaries.

The registry is the single source of truth for which brokers are available,
what their capabilities are, and what their current health state is.  The
router reads from the registry; broker adapters register into it at bootstrap.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from brokers.common.broker_port import CommonBrokerGateway
from brokers.common.capabilities import BrokerCapabilities, CapabilityDescriptor
from brokers.common.errors import BrokerUnavailableError
from brokers.common.extensions import ExtensionBundle, ExtensionRegistry
from brokers.common.models import BrokerHealthSnapshot, RegistrySnapshot
from domain.stream_health import StreamStateSummary

logger = logging.getLogger(__name__)


class BrokerRegistry:
    """Thread-safe registry of broker gateways, capabilities, and health state.

    Lifecycle
    ---------
    1. At bootstrap, call ``register()`` for each available broker.
    2. The router reads health via ``get_health()`` on each routing decision.
    3. Health monitors call ``update_health()`` periodically.
    4. Stream orchestrator calls ``update_stream_summary()`` on session changes.
    5. On shutdown, call ``close_all()``.

    Design note: health state is mutable (updated by monitors); capability
    descriptors are immutable after registration (capabilities don't change at
    runtime — reconnect triggers re-registration with a fresh descriptor).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._gateways: dict[str, CommonBrokerGateway] = {}
        self._capabilities: dict[str, CapabilityDescriptor] = {}
        self._health: dict[str, BrokerHealthSnapshot] = {}
        self._stream_summaries: dict[str, StreamStateSummary] = {}
        self._extensions = ExtensionRegistry()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        gateway: CommonBrokerGateway,
        bundle: ExtensionBundle | None = None,
    ) -> None:
        """Register a broker gateway (and optionally its extension bundle).

        The capability descriptor is refreshed from the gateway at registration
        time.  Health is initialized to a best-effort alive state.
        """
        broker_id = gateway.broker_id
        descriptor = gateway.list_capabilities()
        with self._lock:
            self._gateways[broker_id] = gateway
            self._capabilities[broker_id] = descriptor
            self._health[broker_id] = BrokerHealthSnapshot(
                broker_id=broker_id,
                alive=True,
            )
            if bundle is not None:
                self._extensions.register_bundle(broker_id, bundle)
        logger.info(
            "broker.registered",
            extra={
                "broker_id": broker_id,
                "extensions": list(bundle.registered_names() if bundle else []),
            },
        )

    def deregister(self, broker_id: str) -> None:
        """Remove a broker from the registry (e.g. on fatal auth failure)."""
        with self._lock:
            self._gateways.pop(broker_id, None)
            self._capabilities.pop(broker_id, None)
            self._health.pop(broker_id, None)
            self._stream_summaries.pop(broker_id, None)
        logger.warning("broker.deregistered", extra={"broker_id": broker_id})

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_gateway(self, broker_id: str) -> CommonBrokerGateway:
        """Return the gateway for the given broker_id.

        Raises ``BrokerUnavailableError`` if the broker is not registered or
        its health is not usable.
        """
        with self._lock:
            gw = self._gateways.get(broker_id)
            if gw is None:
                raise BrokerUnavailableError(broker_id, reason="not registered")
            health = self._health.get(broker_id)
            if health is not None and not health.is_usable():
                raise BrokerUnavailableError(broker_id, reason=health.reason)
            return gw

    def get_capabilities(self, broker_id: str) -> CapabilityDescriptor:
        """Return the capability descriptor for the given broker."""
        with self._lock:
            descriptor = self._capabilities.get(broker_id)
            if descriptor is None:
                raise BrokerUnavailableError(broker_id, reason="not registered")
            return descriptor

    def get_health(self, broker_id: str) -> BrokerHealthSnapshot:
        """Return the latest health snapshot (may be stale if monitor is slow)."""
        with self._lock:
            return self._health.get(
                broker_id,
                BrokerHealthSnapshot(broker_id=broker_id, alive=False, reason="not registered"),
            )

    def get_stream_summary(self, broker_id: str) -> StreamStateSummary | None:
        """Return the latest stream state summary for the broker, or None."""
        with self._lock:
            return self._stream_summaries.get(broker_id)

    def get_extensions(self) -> ExtensionRegistry:
        """Return the extension registry for capability-aware extension resolution."""
        return self._extensions

    def list_brokers(self) -> tuple[str, ...]:
        """Return all registered broker ids."""
        with self._lock:
            return tuple(self._gateways.keys())

    def find_brokers(
        self,
        predicate: Callable[[BrokerCapabilities], bool],
    ) -> list[str]:
        """Return broker_ids whose capabilities satisfy the given predicate."""
        with self._lock:
            return [bid for bid, desc in self._capabilities.items() if predicate(desc.capabilities)]

    def snapshot(self) -> RegistrySnapshot:
        """Return a point-in-time snapshot of the entire registry state."""
        with self._lock:
            return RegistrySnapshot(
                broker_ids=tuple(self._gateways.keys()),
                health=dict(self._health),
            )

    # ------------------------------------------------------------------
    # Mutations (called by monitors and orchestrator)
    # ------------------------------------------------------------------

    def update_health(self, snapshot: BrokerHealthSnapshot) -> None:
        """Update the health state for a broker (called by health monitors)."""
        with self._lock:
            if snapshot.broker_id in self._gateways:
                self._health[snapshot.broker_id] = snapshot

    def update_stream_summary(self, summary: StreamStateSummary) -> None:
        """Update stream state summary (called by StreamOrchestrator)."""
        with self._lock:
            self._stream_summaries[summary.broker_id] = summary

    def refresh_capabilities(self, broker_id: str) -> None:
        """Re-fetch and cache capabilities from the live gateway.

        Called after auth reconnect or on scheduled TTL refresh.
        """
        with self._lock:
            gw = self._gateways.get(broker_id)
        if gw is None:
            return
        descriptor = gw.list_capabilities()
        with self._lock:
            self._capabilities[broker_id] = descriptor
        logger.debug("broker.capabilities.refreshed", extra={"broker_id": broker_id})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close_all(self) -> None:
        """Gracefully close all registered gateways."""
        with self._lock:
            gateways = list(self._gateways.values())
        for gw in gateways:
            try:
                await gw.close()
            except Exception:
                logger.exception("broker.close.error", extra={"broker_id": gw.broker_id})
