"""Unit tests for BrokerRouter — capability-based gateway routing service."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from inc_trade.services.broker_router import BrokerRouter


def _make_gateway(broker_id: str, capabilities: list[str] | None = None) -> MagicMock:
    """Create a mock BrokerGateway with controllable capabilities."""
    gateway = MagicMock()
    gateway.broker_id = broker_id

    caps = MagicMock(spec=["has_feature", "supports"])
    caps.has_feature.side_effect = lambda cap: cap in (capabilities or [])
    caps.supports.side_effect = lambda cap: cap in (capabilities or [])
    gateway.capabilities.return_value = caps
    return gateway


class TestBrokerRouterInstantiation:
    def test_router_can_be_instantiated(self) -> None:
        router = BrokerRouter()
        assert isinstance(router, BrokerRouter)

    def test_initial_registry_is_empty(self) -> None:
        router = BrokerRouter()
        assert router.get_available_brokers() == []


class TestGatewayRegistration:
    def test_register_single_gateway(self) -> None:
        router = BrokerRouter()
        gw = _make_gateway("dhan")
        router.register_gateway("dhan", gw)
        assert "dhan" in router.get_available_brokers()

    def test_register_multiple_gateways(self) -> None:
        router = BrokerRouter()
        for name in ("dhan", "upstox", "zerodha"):
            router.register_gateway(name, _make_gateway(name))
        brokers = router.get_available_brokers()
        assert sorted(brokers) == ["dhan", "upstox", "zerodha"]

    def test_register_overwrites_existing_gateway(self) -> None:
        router = BrokerRouter()
        gw1 = _make_gateway("dhan")
        gw2 = _make_gateway("dhan")
        router.register_gateway("dhan", gw1)
        router.register_gateway("dhan", gw2)
        assert router.route("dhan") is gw2


class TestRouteById:
    def test_route_returns_registered_gateway(self) -> None:
        router = BrokerRouter()
        gw = _make_gateway("dhan")
        router.register_gateway("dhan", gw)
        assert router.route("dhan") is gw

    def test_route_raises_for_unknown_broker(self) -> None:
        router = BrokerRouter()
        with pytest.raises(ValueError, match="not registered"):
            router.route("unknown_broker")

    def test_route_different_brokers_independently(self) -> None:
        router = BrokerRouter()
        gw_dhan = _make_gateway("dhan")
        gw_upstox = _make_gateway("upstox")
        router.register_gateway("dhan", gw_dhan)
        router.register_gateway("upstox", gw_upstox)

        assert router.route("dhan") is gw_dhan
        assert router.route("upstox") is gw_upstox
        assert router.route("dhan") is not router.route("upstox")


class TestRouteByCapability:
    def test_returns_gateway_with_capability(self) -> None:
        router = BrokerRouter()
        router.register_gateway("dhan", _make_gateway("dhan", capabilities=["FEATURE_GTT"]))
        router.register_gateway("upstox", _make_gateway("upstox", capabilities=[]))

        result = router.route_by_capability("FEATURE_GTT")
        assert result is not None
        assert result.broker_id == "dhan"

    def test_returns_none_if_no_broker_has_capability(self) -> None:
        router = BrokerRouter()
        router.register_gateway("dhan", _make_gateway("dhan", capabilities=[]))
        router.register_gateway("upstox", _make_gateway("upstox", capabilities=[]))

        result = router.route_by_capability("FEATURE_SUPERORDER")
        assert result is None

    def test_returns_none_for_empty_registry(self) -> None:
        router = BrokerRouter()
        assert router.route_by_capability("FEATURE_GTT") is None

    def test_returns_first_matching_gateway(self) -> None:
        router = BrokerRouter()
        gw_a = _make_gateway("a", capabilities=["FEATURE_GTT"])
        gw_b = _make_gateway("b", capabilities=["FEATURE_GTT"])
        router.register_gateway("a", gw_a)
        router.register_gateway("b", gw_b)

        result = router.route_by_capability("FEATURE_GTT")
        # Must be one of the two registered gateways
        assert result in (gw_a, gw_b)


class TestGetGateway:
    def test_get_gateway_returns_registered(self) -> None:
        router = BrokerRouter()
        gw = _make_gateway("dhan")
        router.register_gateway("dhan", gw)
        assert router.get_gateway("dhan") is gw

    def test_get_gateway_returns_none_for_unknown(self) -> None:
        router = BrokerRouter()
        assert router.get_gateway("missing") is None

    def test_get_gateway_does_not_raise(self) -> None:
        """Unlike route(), get_gateway() must never raise."""
        router = BrokerRouter()
        result = router.get_gateway("nonexistent")
        assert result is None


class TestGetAvailableBrokers:
    def test_returns_list_of_ids(self) -> None:
        router = BrokerRouter()
        router.register_gateway("dhan", _make_gateway("dhan"))
        router.register_gateway("upstox", _make_gateway("upstox"))
        ids = router.get_available_brokers()
        assert isinstance(ids, list)
        assert set(ids) == {"dhan", "upstox"}

    def test_returns_empty_list_initially(self) -> None:
        router = BrokerRouter()
        assert router.get_available_brokers() == []
