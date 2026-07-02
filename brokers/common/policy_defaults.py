"""Default policy configurations for multi-broker routing.

Provides environment-aware default policies and auto-mode configuration
examples. Policies control how the BrokerRouter selects brokers for each
class of operation.

The ``SourceSelectionPolicy`` has five named routing fields, each covering
a class of ``OperationKind``:

- ``execution``        — place/cancel/modify orders, positions, margins
- ``historical``       — historical candle data
- ``live_market_data`` — LTP, quotes, depth, option chains, streams
- ``enrichment``       — news, fundamentals, market intelligence
- ``instrument_metadata`` — instrument search, loading, metadata

Usage::

    from brokers.common.policy_defaults import default_source_selection_policy

    policy = default_source_selection_policy()
    router = BrokerRouter(registry=registry, policy=policy)
"""

from __future__ import annotations

from brokers.common.policy import RoutingPolicy, SourceSelectionPolicy


def default_source_selection_policy() -> SourceSelectionPolicy:
    """Default policy for production with Dhan as primary execution broker.

    Routing strategy:
    - Orders/positions: Fixed to Dhan (primary execution account)
    - Historical: Quota-aware across Dhan + Upstox (federated fetch)
    - Market data/streams: Upstox primary (faster batch), Dhan fallback
    - Enrichment: Upstox (has news and fundamentals)
    - Instruments: Dhan primary (larger master file)
    """
    return SourceSelectionPolicy(
        policy_version="1.0.0",
        execution=RoutingPolicy(
            mode="fixed",
            candidates=("dhan",),
            required_features=frozenset({"place_order", "cancel_order", "modify_order"}),
            allow_fallback=False,
            execution_account="dhan",
        ),
        historical=RoutingPolicy(
            mode="quota_aware",
            candidates=("dhan", "upstox"),
            required_features=frozenset({"historical_data"}),
            allow_fallback=True,
            max_parallel_sources=2,
        ),
        live_market_data=RoutingPolicy(
            mode="priority_list",
            candidates=("upstox", "dhan"),
            required_features=frozenset({"live_market_data"}),
            allow_fallback=True,
        ),
        enrichment=RoutingPolicy(
            mode="capability_match",
            candidates=("upstox",),
            required_features=frozenset({"news"}),
            allow_fallback=False,
        ),
        instrument_metadata=RoutingPolicy(
            mode="priority_list",
            candidates=("dhan", "upstox"),
            allow_fallback=True,
        ),
    )


def sandbox_source_selection_policy() -> SourceSelectionPolicy:
    """Policy for sandbox/development environment.

    Uses only Dhan sandbox; all operations fixed to single broker.
    Simplifies debugging and avoids quota consumption.
    """
    dhan_only = RoutingPolicy(
        mode="fixed",
        candidates=("dhan",),
        allow_fallback=False,
    )
    return SourceSelectionPolicy(
        policy_version="1.0.0-sandbox",
        execution=RoutingPolicy(
            mode="fixed",
            candidates=("dhan",),
            allow_fallback=False,
            execution_account="dhan",
        ),
        historical=dhan_only,
        live_market_data=dhan_only,
        enrichment=dhan_only,
        instrument_metadata=dhan_only,
    )


def upstox_primary_source_selection_policy() -> SourceSelectionPolicy:
    """Policy for Upstox-primary environment.

    Routes execution and market data to Upstox; uses Dhan for historical
    data federation (Upstox has shorter historical lookback windows).
    """
    return SourceSelectionPolicy(
        policy_version="1.0.0-upstox-primary",
        execution=RoutingPolicy(
            mode="fixed",
            candidates=("upstox",),
            required_features=frozenset({"place_order", "cancel_order", "modify_order"}),
            allow_fallback=False,
            execution_account="upstox",
        ),
        historical=RoutingPolicy(
            mode="quota_aware",
            candidates=("dhan", "upstox"),
            required_features=frozenset({"historical_data"}),
            allow_fallback=True,
            max_parallel_sources=2,
        ),
        live_market_data=RoutingPolicy(
            mode="capability_match",
            candidates=("upstox", "dhan"),
            required_features=frozenset({"live_market_data"}),
            allow_fallback=True,
        ),
        enrichment=RoutingPolicy(
            mode="capability_match",
            candidates=("upstox",),
            required_features=frozenset({"news"}),
            allow_fallback=False,
        ),
        instrument_metadata=RoutingPolicy(
            mode="priority_list",
            candidates=("upstox", "dhan"),
            allow_fallback=True,
        ),
    )


def multi_broker_redundant_policy() -> SourceSelectionPolicy:
    """Policy for maximum redundancy — all operations use priority lists.

    Suitable for production environments where uptime is critical and
    both brokers are configured for failover.
    """
    return SourceSelectionPolicy(
        policy_version="1.0.0-redundant",
        execution=RoutingPolicy(
            mode="priority_list",
            candidates=("dhan", "upstox"),
            required_features=frozenset({"place_order", "cancel_order", "modify_order"}),
            allow_fallback=True,
            execution_account="dhan",
        ),
        historical=RoutingPolicy(
            mode="quota_aware",
            candidates=("dhan", "upstox"),
            required_features=frozenset({"historical_data"}),
            allow_fallback=True,
            max_parallel_sources=2,
        ),
        live_market_data=RoutingPolicy(
            mode="priority_list",
            candidates=("dhan", "upstox"),
            required_features=frozenset({"live_market_data"}),
            allow_fallback=True,
        ),
        enrichment=RoutingPolicy(
            mode="priority_list",
            candidates=("upstox", "dhan"),
            required_features=frozenset({"news"}),
            allow_fallback=True,
        ),
        instrument_metadata=RoutingPolicy(
            mode="priority_list",
            candidates=("dhan", "upstox"),
            allow_fallback=True,
        ),
    )
