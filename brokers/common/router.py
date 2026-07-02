"""BrokerRouter — deterministic, auditable broker selection.

The router translates a ``RoutingRequest`` into a ``RouteDecision`` by:
1. Consulting the ``SourceSelectionPolicy`` for the operation kind.
2. Filtering candidates by capability and health from ``BrokerRegistry``.
3. Scoring remaining candidates by quota headroom (when mode permits).
4. Producing a logged, traceable ``RouteDecision``.

Every decision is logged as a structured ``routing.decision`` event so it can
be replayed and explained after the fact.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable

from brokers.common.errors import RoutingError
from brokers.common.models import (
    OperationKind,
    RouteDecision,
    RoutingRequest,
)
from brokers.common.policy import RoutingPolicy, SourceSelectionPolicy
from brokers.common.registry import BrokerRegistry
from infrastructure.time_service import time_service

logger = logging.getLogger(__name__)


class BrokerRouter:
    """Deterministic broker router — stateless beyond the registry reference.

    All state is read from the registry and policy at decision time.  This
    makes the router deterministic and fully testable by injecting controlled
    registry snapshots.
    """

    def __init__(
        self,
        registry: BrokerRegistry,
        policy: SourceSelectionPolicy,
        *,
        quota_headroom_fn: Callable[[str, str], float] | None = None,
    ) -> None:
        """
        quota_headroom_fn
            Optional callback ``(broker_id, endpoint_class) -> float`` returning
            the fraction of non-reserved quota remaining (0.0-1.0).  When
            provided and the policy mode is ``"quota_aware"``, the router
            prefers the broker with the most headroom.  When None, quota-aware
            mode falls back to priority-list ordering.
        """
        self._registry = registry
        self._policy = policy
        self._quota_headroom_fn = quota_headroom_fn

    def route(self, request: RoutingRequest) -> RouteDecision:
        """Select broker(s) for the given operation and return an auditable decision.

        Raises ``RoutingError`` if no eligible broker can be found.
        """
        op_policy = self._policy.for_operation_kind(request.operation)
        candidates = list(op_policy.candidates)
        rejected: dict[str, str] = {}

        # 1. Filter by capability
        capable = []
        for bid in candidates:
            if not self._registry.list_brokers().__contains__(bid):
                rejected[bid] = "not_registered"
                continue
            if request.required_features:
                caps = self._registry.get_capabilities(bid).capabilities
                missing = [f for f in request.required_features if not caps.supports(f)]
                if missing:
                    rejected[bid] = f"missing_features:{','.join(missing)}"
                    continue
            # Also check per-policy required features
            if op_policy.required_features:
                caps = self._registry.get_capabilities(bid).capabilities
                missing = [f for f in op_policy.required_features if not caps.supports(f)]
                if missing:
                    rejected[bid] = f"missing_policy_features:{','.join(missing)}"
                    continue
            capable.append(bid)

        # 2. Filter by health
        healthy = []
        for bid in capable:
            health = self._registry.get_health(bid)
            if not health.is_usable():
                rejected[bid] = f"unhealthy:{health.reason}"
            else:
                healthy.append(bid)

        if not healthy:
            decision_rejected = {**rejected}
            self._log_decision(
                request=request,
                primary="",
                fallbacks=(),
                parallel=(),
                reason_codes=("no_eligible_broker",),
                rejected=decision_rejected,
                policy_version=self._policy.policy_version,
            )
            raise RoutingError(
                operation=request.operation.value,
                reason=f"no healthy capable broker; rejected={rejected}",
            )

        # 3. Order by policy mode
        primary, fallbacks, parallel = self._apply_mode(healthy, op_policy, request.operation)

        reason_codes = self._build_reason_codes(op_policy.mode, primary, rejected)

        decision = RouteDecision(
            operation=request.operation,
            primary_broker=primary,
            trace_id=request.trace_id,
            policy_version=self._policy.policy_version,
            fallback_brokers=tuple(fallbacks),
            parallel_brokers=tuple(parallel),
            reason_codes=tuple(reason_codes),
            rejected=rejected,
            decided_at=time_service.now(),
        )
        self._log_decision(
            request=request,
            primary=primary,
            fallbacks=tuple(fallbacks),
            parallel=tuple(parallel),
            reason_codes=tuple(reason_codes),
            rejected=rejected,
            policy_version=self._policy.policy_version,
        )
        with contextlib.suppress(Exception):
            from brokers.common.observability.audit import emit_routing_decision

            emit_routing_decision(decision)
        return decision

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_mode(
        self,
        healthy: list[str],
        policy: RoutingPolicy,
        operation: OperationKind,
    ) -> tuple[str, list[str], list[str]]:
        """Return (primary, fallbacks, parallel) given the routing mode."""
        mode = policy.mode

        if mode == "fixed":
            return healthy[0], [], []

        if mode in ("priority_list", "capability_match"):
            primary = healthy[0]
            fallbacks = healthy[1:] if policy.allow_fallback else []
            parallel = self._maybe_parallel(healthy, policy, operation)
            return primary, fallbacks, parallel

        if mode == "quota_aware" and self._quota_headroom_fn is not None:
            endpoint_class = self._operation_to_endpoint_class(operation)
            scored = sorted(
                healthy,
                key=lambda bid: self._quota_headroom_fn(bid, endpoint_class),
                reverse=True,
            )
            primary = scored[0]
            fallbacks = scored[1:] if policy.allow_fallback else []
            parallel = self._maybe_parallel(scored, policy, operation)
            return primary, fallbacks, parallel

        if mode == "latency_aware":
            scored = sorted(
                healthy,
                key=lambda bid: self._registry.get_health(bid).latency_p50_ms,
            )
            primary = scored[0]
            fallbacks = scored[1:] if policy.allow_fallback else []
            return primary, fallbacks, []

        # Default: first candidate
        primary = healthy[0]
        fallbacks = healthy[1:] if policy.allow_fallback else []
        return primary, fallbacks, []

    def _maybe_parallel(
        self,
        healthy: list[str],
        policy: RoutingPolicy,
        operation: OperationKind,
    ) -> list[str]:
        """Return parallel brokers for federated historical fetches."""
        if (
            operation == OperationKind.GET_HISTORICAL_BARS
            and policy.max_parallel_sources is not None
            and policy.max_parallel_sources > 1
        ):
            return healthy[: policy.max_parallel_sources]
        return []

    @staticmethod
    def _operation_to_endpoint_class(operation: OperationKind) -> str:
        if operation in {
            OperationKind.PLACE_ORDER,
            OperationKind.CANCEL_ORDER,
            OperationKind.MODIFY_ORDER,
        }:
            return "orders"
        if operation == OperationKind.GET_HISTORICAL_BARS:
            return "historical"
        if operation in {OperationKind.FETCH_OPTION_CHAIN}:
            return "option_chain"
        return "quotes"

    @staticmethod
    def _build_reason_codes(
        mode: str,
        primary: str,
        rejected: dict[str, str],
    ) -> list[str]:
        codes = [f"mode:{mode}", f"selected:{primary}"]
        if rejected:
            codes.append(f"rejected_count:{len(rejected)}")
        return codes

    def _log_decision(
        self,
        *,
        request: RoutingRequest,
        primary: str,
        fallbacks: tuple[str, ...],
        parallel: tuple[str, ...],
        reason_codes: tuple[str, ...],
        rejected: dict[str, str],
        policy_version: str,
    ) -> None:
        logger.info(
            "routing.decision",
            extra={
                "event": "routing.decision",
                "trace_id": request.trace_id,
                "operation": request.operation.value,
                "primary_broker": primary,
                "fallback_brokers": list(fallbacks),
                "parallel_brokers": list(parallel),
                "policy_version": policy_version,
                "reason_codes": list(reason_codes),
                "rejected": rejected,
            },
        )
