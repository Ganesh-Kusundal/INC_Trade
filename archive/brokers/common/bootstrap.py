"""Bootstrap BrokerInfrastructure from legacy MarketDataGateway instances."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from brokers.common.adapters import build_extension_bundle
from brokers.common.adapters.market_data_gateway_adapter import wrap_market_gateway
from brokers.common.gateway import MarketDataGateway
from brokers.common.infrastructure import BrokerInfrastructure, build_infrastructure
from brokers.common.intelligent_market_gateway import IntelligentMarketDataGateway
from brokers.common.policy import (
    SourceSelectionPolicy,
    auto_dual_broker_policy,
    default_dhan_only_policy,
)


def policy_from_env(execution_account: str | None = None) -> SourceSelectionPolicy:
    """Select routing policy from environment."""
    mode = os.environ.get("TRADEX_BROKER_POLICY", "auto").lower()
    exec_account = execution_account or os.environ.get("TRADEX_EXECUTION_BROKER", "dhan")
    if mode == "dhan":
        return default_dhan_only_policy()
    if mode == "upstox":
        from brokers.common.policy import default_upstox_only_policy

        return default_upstox_only_policy()
    return auto_dual_broker_policy(execution_account=exec_account)


async def bootstrap_from_gateways(
    gateways: Sequence[tuple[str, MarketDataGateway]],
    *,
    policy: SourceSelectionPolicy | None = None,
) -> BrokerInfrastructure:
    """Wrap legacy gateways and build full BrokerInfrastructure."""
    common_gateways = []
    bundles = {}
    for broker_id, legacy_gw in gateways:
        bundle = build_extension_bundle(broker_id, legacy_gw)
        adapter = wrap_market_gateway(
            legacy_gw,
            broker_id,
            extensions=bundle.registered_names(),
        )
        common_gateways.append(adapter)
        bundles[broker_id] = bundle

    return await build_infrastructure(
        common_gateways,
        policy or policy_from_env(),
        bundles=bundles,
    )


async def bootstrap_from_broker_registry(
    broker_names: Sequence[str],
    *,
    policy: SourceSelectionPolicy | None = None,
    **bootstrap_kwargs: Any,
) -> BrokerInfrastructure | None:
    """Bootstrap infrastructure using cli.services.broker_registry."""
    from cli.services.broker_registry import bootstrap_gateway

    wrapped: list[tuple[str, MarketDataGateway]] = []
    for name in broker_names:
        result = bootstrap_gateway(name, **bootstrap_kwargs)
        if result.ok and result.gateway is not None:
            wrapped.append((name, result.gateway))
    if not wrapped:
        return None
    return await bootstrap_from_gateways(wrapped, policy=policy)


async def create_intelligent_gateway(
    gateways: Sequence[tuple[str, MarketDataGateway]],
    *,
    smart: bool = True,
    policy: SourceSelectionPolicy | None = None,
    primary_broker: str | None = None,
) -> IntelligentMarketDataGateway:
    """Create an intelligent gateway with optional smart routing.

    Parameters
    ----------
    gateways : Sequence[tuple[str, MarketDataGateway]]
        List of (broker_id, gateway) tuples to include in the infrastructure.
    smart : bool, default=True
        Enable intelligent routing. When True, uses BrokerRouter for broker
        selection and QuotaScheduler for quota management. When False, delegates
        directly to primary_broker.
    policy : SourceSelectionPolicy | None
        Routing policy. If None, uses policy_from_env().
    primary_broker : str | None
        The broker to use when smart=False or as the primary broker in smart
        mode. If None, defaults to the first broker in ``gateways``.

    Returns
    -------
    IntelligentMarketDataGateway
        An intelligent gateway instance.

    Example
    -------
    ::

        # Smart mode (recommended)
        gw = await create_intelligent_gateway(
            [("dhan", dhan_gw), ("upstox", upstox_gw)],
            smart=True
        )
        result = gw.ltp("NIFTY", "NSE")  # Uses intelligent routing

        # Simple mode (backward compatible)
        gw = await create_intelligent_gateway(
            [("dhan", dhan_gw)],
            smart=False
        )
        result = gw.ltp("NIFTY", "NSE")  # Direct call to Dhan
    """
    if not gateways:
        raise ValueError("create_intelligent_gateway requires at least one gateway")
    resolved_primary = primary_broker if primary_broker is not None else gateways[0][0]
    infra = await bootstrap_from_gateways(gateways, policy=policy)
    return IntelligentMarketDataGateway(infra, smart=smart, primary_broker=resolved_primary)
