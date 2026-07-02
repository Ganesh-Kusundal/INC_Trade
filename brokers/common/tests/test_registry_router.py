"""Integration tests for BrokerRegistry and BrokerRouter."""

import pytest

from brokers.common.errors import BrokerUnavailableError, RoutingError
from brokers.common.models import BrokerHealthSnapshot, OperationKind, RoutingRequest
from brokers.common.policy import auto_dual_broker_policy, default_dhan_only_policy
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter
from brokers.common.tests.fixtures.in_memory_gateway import InMemoryBrokerGateway
from brokers.dhan.capabilities import dhan_capabilities
from brokers.upstox.capabilities import upstox_capabilities


@pytest.fixture
def dual_registry():
    registry = BrokerRegistry()
    registry.register(
        InMemoryBrokerGateway("dhan", dhan_capabilities()),
    )
    registry.register(
        InMemoryBrokerGateway("upstox", upstox_capabilities()),
    )
    return registry


class TestBrokerRegistry:
    def test_register_and_list_brokers(self, dual_registry):
        assert set(dual_registry.list_brokers()) == {"dhan", "upstox"}

    def test_get_gateway_when_unhealthy_raises(self, dual_registry):
        dual_registry.update_health(
            BrokerHealthSnapshot(broker_id="dhan", alive=False, reason="auth expired")
        )
        with pytest.raises(BrokerUnavailableError):
            dual_registry.get_gateway("dhan")

    def test_find_brokers_by_capability_predicate(self, dual_registry):
        news_brokers = dual_registry.find_brokers(lambda c: c.supports("news"))
        assert news_brokers == ["upstox"]


class TestBrokerRouter:
    def test_execution_routes_to_fixed_account(self, dual_registry):
        router = BrokerRouter(dual_registry, auto_dual_broker_policy(execution_account="dhan"))
        decision = router.route(
            RoutingRequest(
                operation=OperationKind.PLACE_ORDER,
                trace_id="trace-1",
            )
        )
        assert decision.primary_broker == "dhan"
        assert decision.fallback_brokers == ()
        assert "mode:fixed" in decision.reason_codes

    def test_live_market_data_priority_list_with_fallback(self, dual_registry):
        router = BrokerRouter(dual_registry, auto_dual_broker_policy())
        decision = router.route(
            RoutingRequest(
                operation=OperationKind.OPEN_MARKET_STREAM,
                trace_id="trace-2",
            )
        )
        assert decision.primary_broker == "upstox"
        assert "dhan" in decision.fallback_brokers

    def test_historical_parallel_brokers_in_auto_mode(self, dual_registry):
        router = BrokerRouter(dual_registry, auto_dual_broker_policy())
        decision = router.route(
            RoutingRequest(
                operation=OperationKind.GET_HISTORICAL_BARS,
                trace_id="trace-3",
                instrument="RELIANCE:NSE",
            )
        )
        assert set(decision.parallel_brokers) == {"upstox", "dhan"}

    def test_unhealthy_broker_skipped_with_fallback(self):
        registry = BrokerRegistry()
        registry.register(InMemoryBrokerGateway("dhan", dhan_capabilities()))
        registry.register(InMemoryBrokerGateway("upstox", upstox_capabilities()))
        registry.update_health(BrokerHealthSnapshot(broker_id="upstox", alive=False, reason="down"))
        router = BrokerRouter(registry, auto_dual_broker_policy())
        decision = router.route(
            RoutingRequest(
                operation=OperationKind.OPEN_MARKET_STREAM,
                trace_id="trace-4",
            )
        )
        assert decision.primary_broker == "dhan"
        assert "upstox" in decision.rejected

    def test_no_eligible_broker_raises_routing_error(self):
        registry = BrokerRegistry()
        registry.register(InMemoryBrokerGateway("dhan", dhan_capabilities(), alive=False))
        registry.update_health(BrokerHealthSnapshot(broker_id="dhan", alive=False, reason="down"))
        router = BrokerRouter(registry, default_dhan_only_policy())
        with pytest.raises(RoutingError):
            router.route(
                RoutingRequest(
                    operation=OperationKind.PLACE_ORDER,
                    trace_id="trace-5",
                )
            )

    def test_route_decision_audit_dict(self, dual_registry):
        router = BrokerRouter(dual_registry, auto_dual_broker_policy())
        decision = router.route(
            RoutingRequest(
                operation=OperationKind.GET_MARGINS,
                trace_id="trace-6",
            )
        )
        audit = decision.to_audit_dict()
        assert audit["event"] == "routing.decision"
        assert audit["trace_id"] == "trace-6"
        assert audit["primary_broker"] in {"dhan", "upstox"}
