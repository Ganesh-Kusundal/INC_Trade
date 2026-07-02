"""BrokerInfrastructure — the single DI container for all broker infrastructure.

Application-layer code (composers, orchestrators, CLI) depends on this object
and nothing below it.  It never imports DhanGateway or UpstoxGateway directly.

This keeps the dependency direction clean:
  application/ → brokers/common/ → brokers/dhan|upstox/ → domain/

Usage at composition root (bootstrap)::

    from brokers.common.infrastructure import BrokerInfrastructure, build_infrastructure
    from brokers.common.policy import auto_dual_broker_policy
    from brokers.dhan.capabilities import dhan_capabilities
    from brokers.upstox.capabilities import upstox_capabilities

    infra = await build_infrastructure(
        gateways=[dhan_gw, upstox_gw],
        bundles={"dhan": dhan_bundle, "upstox": upstox_bundle},
        policy=auto_dual_broker_policy(execution_account="dhan"),
    )

Usage in application code::

    series, ledger = await infra.historical.fetch(query)
    sub_id = await infra.streams.subscribe(request)
    news = infra.extensions.require("upstox", NewsProvider)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from brokers.common.broker_port import CommonBrokerGateway
from brokers.common.capabilities import BrokerCapabilities
from brokers.common.extensions import ExtensionBundle, ExtensionRegistry
from brokers.common.historical_coordinator import HistoricalDataCoordinator
from brokers.common.policy import SourceSelectionPolicy
from brokers.common.quota_scheduler import QuotaScheduler
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from brokers.common.stream_orchestrator import StreamOrchestrator


@dataclass
class BrokerInfrastructure:
    """Single facade injected into all application-layer components.

    Composers depend on this object — never on DhanGateway or UpstoxGateway.

    registry    — gateway instances, capabilities, health state.
    router      — broker selection for any operation.
    policy      — source selection configuration (injected, not hardcoded).
    quota       — global API budget coordinator.
    historical  — federated historical data coordinator.
    streams     — stream lifecycle manager.
    extensions  — typed extension interface registry.
    """

    registry: BrokerRegistry
    router: BrokerRouter
    policy: SourceSelectionPolicy
    quota: QuotaScheduler
    historical: HistoricalDataCoordinator
    streams: StreamOrchestrator
    extensions: ExtensionRegistry

    def gateway_for(self, broker_id: str) -> CommonBrokerGateway:
        """Return a gateway by broker_id — for explicit single-broker use cases."""
        return self.registry.get_gateway(broker_id)

    def capabilities_for(self, broker_id: str) -> BrokerCapabilities:
        """Return the capability matrix for a broker."""
        return self.registry.get_capabilities(broker_id).capabilities


async def build_infrastructure(
    gateways: Sequence[CommonBrokerGateway],
    policy: SourceSelectionPolicy,
    bundles: dict[str, ExtensionBundle] | None = None,
    *,
    reserved_headroom: float = 0.20,
) -> BrokerInfrastructure:
    """Bootstrap ``BrokerInfrastructure`` from a list of live gateways.

    Registers all gateways and their extension bundles, registers rate profiles
    with the quota scheduler, and starts the stream orchestrator.

    Parameters
    ----------
    gateways
        Live broker gateway instances (already authenticated and ready).
    policy
        Source selection policy — use one of the factory helpers in
        ``brokers.common.policy`` or construct your own.
    bundles
        Optional mapping of broker_id → ExtensionBundle.  Pass None if a broker
        has no extensions to register.
    reserved_headroom
        Fraction of each quota bucket held in reserve for execution-critical
        traffic.  Default 20%.
    """
    registry = BrokerRegistry()
    quota = QuotaScheduler(reserved_headroom=reserved_headroom)

    for gw in gateways:
        bundle = (bundles or {}).get(gw.broker_id)
        registry.register(gw, bundle)

        # Register the broker's rate limit profiles with the quota scheduler
        capabilities = gw.list_capabilities().capabilities
        for profile in capabilities.rate_limit_profiles:
            quota.register_profile(gw.broker_id, profile)

    router = BrokerRouter(
        registry=registry,
        policy=policy,
        quota_headroom_fn=quota.headroom_for,
    )

    historical = HistoricalDataCoordinator(
        registry=registry,
        router=router,
        quota_fn=quota.acquire,
    )

    streams = StreamOrchestrator(registry=registry, router=router)
    await streams.start()

    return BrokerInfrastructure(
        registry=registry,
        router=router,
        policy=policy,
        quota=quota,
        historical=historical,
        streams=streams,
        extensions=registry.get_extensions(),
    )
