"""Integration tests for BrokerRouter with SourceSelectionPolicy.

Tests cover:
- Fixed mode routing
- Quota-aware mode scoring
- Capability filtering
- Health filtering
- Fallback behavior
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from brokers.common.capabilities import (
    BrokerCapabilities,
    CapabilityDescriptor,
)
from brokers.common.errors import RoutingError
from brokers.common.models import BrokerHealthSnapshot, OperationKind, RoutingRequest
from brokers.common.policy import RoutingPolicy, SourceSelectionPolicy
from brokers.dhan.capabilities import dhan_capabilities
from brokers.upstox.capabilities import upstox_capabilities
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter


@pytest.fixture
def mock_gateway():
    """Create a mock gateway for testing."""
    gateway = Mock()
    gateway.broker_id = "test_broker"
    gateway.list_capabilities.return_value = CapabilityDescriptor.build(
        capabilities=BrokerCapabilities(broker_id="test_broker"),
        extensions=frozenset(),
    )
    return gateway


@pytest.fixture
def registry_with_dhan_upstox():
    """Registry with Dhan and Upstox gateways."""
    registry = BrokerRegistry()

    dhan_gw = Mock()
    dhan_gw.broker_id = "dhan"
    dhan_gw.list_capabilities.return_value = CapabilityDescriptor.build(
        capabilities=dhan_capabilities(),
        extensions=frozenset(),
    )
    registry.register(dhan_gw)

    upstox_gw = Mock()
    upstox_gw.broker_id = "upstox"
    upstox_gw.list_capabilities.return_value = CapabilityDescriptor.build(
        capabilities=upstox_capabilities(),
        extensions=frozenset(),
    )
    registry.register(upstox_gw)

    return registry


class TestFixedModeRouting:
    """Test fixed mode always selects first candidate."""

    def test_fixed_mode_selects_first_candidate(self, registry_with_dhan_upstox):
        policy = SourceSelectionPolicy(
            policy_version="test-1.0",
            historical=RoutingPolicy(
                mode="quota_aware",
                candidates=("dhan", "upstox"),
            ),
            live_market_data=RoutingPolicy(
                mode="capability_match",
                candidates=("dhan", "upstox"),
            ),
            execution=RoutingPolicy(
                mode="fixed",
                candidates=("dhan", "upstox"),
            ),
            enrichment=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            instrument_metadata=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
        )

        router = BrokerRouter(registry_with_dhan_upstox, policy)
        request = RoutingRequest(
            operation=OperationKind.PLACE_ORDER,
            trace_id="test-trace-1",
        )

        decision = router.route(request)

        assert decision.primary_broker == "dhan"
        assert decision.fallback_brokers == ()


class TestCapabilityFiltering:
    """Test router filters by required features."""

    def test_capability_match_filters_unsupported_brokers(self, registry_with_dhan_upstox):
        policy = SourceSelectionPolicy(
            policy_version="test-1.0",
            historical=RoutingPolicy(
                mode="quota_aware",
                candidates=("dhan", "upstox"),
                required_features=frozenset({"expired_options_history"}),
            ),
            live_market_data=RoutingPolicy(
                mode="capability_match",
                candidates=("dhan", "upstox"),
            ),
            execution=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            enrichment=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            instrument_metadata=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
        )

        router = BrokerRouter(registry_with_dhan_upstox, policy)
        request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS,
            trace_id="test-trace-2",
        )

        decision = router.route(request)

        # Dhan supports expired_options_history, Upstox doesn't
        assert decision.primary_broker == "dhan"


class TestHealthFiltering:
    """Test router filters by broker health."""

    def test_unhealthy_broker_rejected(self, registry_with_dhan_upstox):
        # Mark Upstox as unhealthy
        registry_with_dhan_upstox.update_health(
            BrokerHealthSnapshot(
                broker_id="upstox",
                alive=False,
                reason="auth_expired",
            )
        )

        policy = SourceSelectionPolicy(
            policy_version="test-1.0",
            historical=RoutingPolicy(
                mode="quota_aware",
                candidates=("dhan", "upstox"),
            ),
            live_market_data=RoutingPolicy(
                mode="priority_list",
                candidates=("upstox", "dhan"),
                allow_fallback=True,
            ),
            execution=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            enrichment=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            instrument_metadata=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
        )

        router = BrokerRouter(registry_with_dhan_upstox, policy)
        request = RoutingRequest(
            operation=OperationKind.GET_QUOTE,
            trace_id="test-trace-3",
        )

        decision = router.route(request)

        # Upstox is unhealthy, falls back to Dhan
        assert decision.primary_broker == "dhan"
        assert "upstox" in decision.rejected


class TestQuotaAwareMode:
    """Test quota-aware mode scoring."""

    def test_quota_aware_prefers_higher_headroom(self, registry_with_dhan_upstox):
        def mock_headroom(broker_id: str, endpoint_class: str) -> float:
            # Dhan has more headroom
            return 0.8 if broker_id == "dhan" else 0.3

        policy = SourceSelectionPolicy(
            policy_version="test-1.0",
            historical=RoutingPolicy(
                mode="quota_aware",
                candidates=("dhan", "upstox"),
                allow_fallback=True,
            ),
            live_market_data=RoutingPolicy(
                mode="capability_match",
                candidates=("dhan", "upstox"),
            ),
            execution=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            enrichment=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            instrument_metadata=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
        )

        router = BrokerRouter(
            registry_with_dhan_upstox,
            policy,
            quota_headroom_fn=mock_headroom,
        )
        request = RoutingRequest(
            operation=OperationKind.GET_HISTORICAL_BARS,
            trace_id="test-trace-4",
        )

        decision = router.route(request)

        # Dhan has higher headroom, should be selected
        assert decision.primary_broker == "dhan"


class TestFallbackBehavior:
    """Test fallback when primary unavailable."""

    def test_fallback_to_second_candidate(self, registry_with_dhan_upstox):
        # Remove Dhan from registry
        registry_with_dhan_upstox.deregister("dhan")

        policy = SourceSelectionPolicy(
            policy_version="test-1.0",
            historical=RoutingPolicy(
                mode="quota_aware",
                candidates=("dhan", "upstox"),
            ),
            live_market_data=RoutingPolicy(
                mode="capability_match",
                candidates=("dhan", "upstox"),
            ),
            execution=RoutingPolicy(
                mode="priority_list",
                candidates=("dhan", "upstox"),
                allow_fallback=True,
            ),
            enrichment=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            instrument_metadata=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
        )

        router = BrokerRouter(registry_with_dhan_upstox, policy)
        request = RoutingRequest(
            operation=OperationKind.PLACE_ORDER,
            trace_id="test-trace-5",
        )

        decision = router.route(request)

        assert decision.primary_broker == "upstox"

    def test_no_eligible_broker_raises(self, registry_with_dhan_upstox):
        # Remove both brokers
        registry_with_dhan_upstox.deregister("dhan")
        registry_with_dhan_upstox.deregister("upstox")

        policy = SourceSelectionPolicy(
            policy_version="test-1.0",
            historical=RoutingPolicy(
                mode="quota_aware",
                candidates=("dhan", "upstox"),
            ),
            live_market_data=RoutingPolicy(
                mode="capability_match",
                candidates=("dhan", "upstox"),
            ),
            execution=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            enrichment=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
            instrument_metadata=RoutingPolicy(
                mode="fixed",
                candidates=("dhan",),
            ),
        )

        router = BrokerRouter(registry_with_dhan_upstox, policy)
        request = RoutingRequest(
            operation=OperationKind.PLACE_ORDER,
            trace_id="test-trace-6",
        )

        with pytest.raises(RoutingError):
            router.route(request)
