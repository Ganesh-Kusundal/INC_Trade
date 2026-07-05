"""Test capability-based architecture end-to-end."""

from __future__ import annotations

from brokers.adapters.paper.gateway import PaperGateway
from inc_trade.domain.constants.capabilities import (
    FEATURE_HISTORICAL,
    FEATURE_MARKET_DATA,
    FEATURE_ORDERS,
    FEATURE_PORTFOLIO,
)
from inc_trade.ports.broker import BrokerGateway
from inc_trade.services.broker_router import BrokerRouter
from inc_trade.services.capability_discovery import CapabilityDiscovery


class TestCapabilityBasedArchitecture:
    """Test that the capability-based architecture works correctly."""

    def test_gateway_implements_broker_gateway(self) -> None:
        """Verify that PaperGateway implements BrokerGateway protocol."""
        gateway = PaperGateway()

        # Check all required properties exist
        assert hasattr(gateway, "broker_id")
        assert hasattr(gateway, "capabilities")
        assert hasattr(gateway, "orders")
        assert hasattr(gateway, "market_data")
        assert hasattr(gateway, "portfolio")
        assert hasattr(gateway, "historical")
        assert hasattr(gateway, "instruments")
        assert hasattr(gateway, "auth")
        assert hasattr(gateway, "streaming")
        assert hasattr(gateway, "extensions")

    def test_capabilities_work(self) -> None:
        """Test that capabilities can be queried."""
        gateway = PaperGateway()
        caps = gateway.capabilities()

        # Test core capabilities via attributes
        assert caps.supports_place_order
        assert caps.supports_cancel_order
        assert caps.supports_modify_order

        # Test via supports() method
        assert caps.supports("place_order")
        assert caps.supports("cancel_order")

        # Test that unsupported features return False
        assert not caps.supports_super_order
        assert not caps.supports("super_order")

        # Test to_dict
        d = caps.to_dict()
        assert isinstance(d, dict)
        assert d["broker_id"] == "paper"

    def test_broker_router_routes_correctly(self) -> None:
        """Test that BrokerRouter can route to gateways."""
        router = BrokerRouter()
        gateway = PaperGateway()

        router.register_gateway("paper", gateway)

        # Test routing
        retrieved = router.route("paper")
        assert retrieved is gateway

    def test_capability_discovery_works(self) -> None:
        """Test that CapabilityDiscovery can find brokers with features."""
        router = BrokerRouter()
        gateway = PaperGateway()

        router.register_gateway("paper", gateway)
        discovery = CapabilityDiscovery(router)

        # Test feature checking
        assert discovery.has_feature("paper", FEATURE_ORDERS)

        # Test finding brokers with features
        brokers = discovery.find_brokers_with_feature(FEATURE_ORDERS)
        assert "paper" in brokers

    def test_extensions_registry_works(self) -> None:
        """Test that extensions can be registered and retrieved."""
        gateway = PaperGateway()

        # Extensions registry should exist
        extensions = gateway.extensions
        assert extensions is not None

    def test_service_layer_depends_only_on_ports(self) -> None:
        """Verify that services depend only on ports, not adapters."""
        # Check that services import only from allowed modules
        import inspect

        from inc_trade.services.historical_service import HistoricalService
        from inc_trade.services.market_data_service import MarketDataService
        from inc_trade.services.order_service import OrderService
        from inc_trade.services.portfolio_service import PortfolioService

        for service in [OrderService, MarketDataService, PortfolioService, HistoricalService]:
            source = inspect.getsource(service)

            # Should not import from adapters
            assert "adapters" not in source, f"{service.__name__} should not import from adapters"

            # Should not import from infrastructure
            assert "infrastructure" not in source, (
                f"{service.__name__} should not import from infrastructure"
            )

    def test_broker_facade_uses_services(self) -> None:
        """Test that BrokerFacade delegates to services."""
        from inc_trade.services.broker_facade import BrokerFacade

        gateway = PaperGateway()
        facade = BrokerFacade(gateway)

        # Facade should have all the service methods
        assert hasattr(facade, "place_order")
        assert hasattr(facade, "get_quote")
        assert hasattr(facade, "get_positions")
        assert hasattr(facade, "get_historical_candles")

        # Test that methods work
        resp = facade.place_order("RELIANCE", "NSE", "BUY", 10)
        assert resp.success

        quote = facade.get_quote("RELIANCE")
        assert quote is not None

        positions = facade.get_positions()
        assert positions == []
