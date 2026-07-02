"""Source selection policy — policy-driven routing configuration.

A ``SourceSelectionPolicy`` is a pure-data object that describes how the
``BrokerRouter`` should select brokers for each class of operation.  Policies
are injected at composition time and can be loaded from environment variables,
YAML config, or constructed in tests with full control over routing behavior.

The critical invariant: ``execution.execution_account`` must match the broker
used for ``place_order`` — market-data and execution accounts are independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from brokers.common.models import OperationKind

# ---------------------------------------------------------------------------
# Per-operation-class routing policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingPolicy:
    """Routing rules for a single class of operations.

    mode
        ``"fixed"``           — always use ``candidates[0]``; no fallback.
        ``"priority_list"``   — try candidates in order; fall back on failure.
        ``"capability_match"``— select first candidate satisfying
                                ``required_features``; error if none qualify.
        ``"quota_aware"``     — select the candidate with the most quota
                                headroom in the relevant endpoint class.
        ``"latency_aware"``   — select the candidate with the lowest p50 latency.

    candidates
        Ordered list of broker_ids eligible for this operation class.

    required_features
        Feature names that the selected broker must declare in
        ``BrokerCapabilities.supports()``.  Selection skips candidates that
        fail this check.

    allow_fallback
        If True and the primary is unavailable, the router tries the next
        healthy candidate from ``candidates``.

    max_parallel_sources
        Maximum number of brokers to use in parallel (only meaningful for
        ``OperationKind.GET_HISTORICAL_BARS`` federation). None = single source.

    execution_account
        Explicit broker_id that must be used for execution operations.  This
        decouples market-data routing from trading account ownership.  A value
        of None means execution follows the standard policy.
    """

    mode: Literal["fixed", "priority_list", "capability_match", "quota_aware", "latency_aware"]
    candidates: tuple[str, ...]
    required_features: frozenset[str] = field(default_factory=frozenset)
    allow_fallback: bool = True
    max_parallel_sources: int | None = None
    execution_account: str | None = None


# ---------------------------------------------------------------------------
# Full source selection policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSelectionPolicy:
    """Per-operation-class routing configuration injected into BrokerRouter.

    Each field is a separate RoutingPolicy so that, for example, live market
    data can route to Upstox while execution always goes to Dhan.

    policy_version
        Monotonically increasing version string embedded in every RouteDecision
        for audit traceability.
    """

    historical: RoutingPolicy
    live_market_data: RoutingPolicy
    execution: RoutingPolicy
    enrichment: RoutingPolicy
    instrument_metadata: RoutingPolicy
    policy_version: str = "1.0.0"

    def for_operation_kind(self, kind: OperationKind) -> RoutingPolicy:  # type: ignore[name-defined]
        """Return the applicable RoutingPolicy for the given OperationKind."""
        from brokers.common.models import OperationKind

        if kind in {
            OperationKind.PLACE_ORDER,
            OperationKind.CANCEL_ORDER,
            OperationKind.MODIFY_ORDER,
            OperationKind.PLACE_SUPER_ORDER,
            OperationKind.PLACE_FOREVER_ORDER,
            OperationKind.PLACE_SLICE_ORDER,
        }:
            return self.execution
        if kind == OperationKind.GET_HISTORICAL_BARS:
            return self.historical
        if kind in {
            OperationKind.OPEN_MARKET_STREAM,
            OperationKind.GET_QUOTE,
            OperationKind.GET_DEPTH,
            OperationKind.FETCH_OPTION_CHAIN,
        }:
            return self.live_market_data
        if kind in {
            OperationKind.FETCH_NEWS,
            OperationKind.FETCH_FUNDAMENTALS,
            OperationKind.FETCH_MARKET_INTELLIGENCE,
        }:
            return self.enrichment
        return self.instrument_metadata


# ---------------------------------------------------------------------------
# Factory helpers for common policy configurations
# ---------------------------------------------------------------------------


def default_dhan_only_policy(policy_version: str = "1.0.0") -> SourceSelectionPolicy:
    """Single-broker policy routing everything to Dhan."""
    policy = RoutingPolicy(
        mode="fixed",
        candidates=("dhan",),
        allow_fallback=False,
    )
    return SourceSelectionPolicy(
        historical=policy,
        live_market_data=policy,
        execution=RoutingPolicy(
            mode="fixed",
            candidates=("dhan",),
            allow_fallback=False,
            execution_account="dhan",
        ),
        enrichment=policy,
        instrument_metadata=policy,
        policy_version=policy_version,
    )


def default_upstox_only_policy(policy_version: str = "1.0.0") -> SourceSelectionPolicy:
    """Single-broker policy routing everything to Upstox."""
    policy = RoutingPolicy(
        mode="fixed",
        candidates=("upstox",),
        allow_fallback=False,
    )
    return SourceSelectionPolicy(
        historical=policy,
        live_market_data=policy,
        execution=RoutingPolicy(
            mode="fixed",
            candidates=("upstox",),
            allow_fallback=False,
            execution_account="upstox",
        ),
        enrichment=policy,
        instrument_metadata=policy,
        policy_version=policy_version,
    )


def auto_dual_broker_policy(
    execution_account: str = "dhan",
    policy_version: str = "1.0.0",
) -> SourceSelectionPolicy:
    """Auto-mode policy using both brokers where each excels.

    - Historical: parallel federation (Upstox for recent 30d, Dhan for remainder)
    - Live data: Upstox primary (broader mode support), Dhan fallback
    - Execution: fixed to ``execution_account`` (default Dhan)
    - Enrichment: Upstox (has news and fundamentals)
    - Instruments: Dhan primary (larger master file)
    """
    return SourceSelectionPolicy(
        historical=RoutingPolicy(
            mode="capability_match",
            candidates=("upstox", "dhan"),
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
        execution=RoutingPolicy(
            mode="fixed",
            candidates=(execution_account,),
            allow_fallback=False,
            execution_account=execution_account,
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
        policy_version=policy_version,
    )
