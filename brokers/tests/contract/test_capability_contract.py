"""Contract tests — Capability model compliance.

Every broker adapter must expose a capabilities() method that returns a
``BrokerCapabilities`` dataclass with ``supports()`` and ``to_dict()``.

This file provides contract tests for all three adapters (Dhan, Upstox, Paper)
and verifies per-adapter distinctive capabilities, so that regressions in the
capability matrix are caught at the contract layer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from inc_trade.domain.capabilities import BrokerCapabilities
from inc_trade.domain.enums import BrokerID
from inc_trade.services._gateway_compat import BrokerGateway


class CapabilityContractTests:
    """Mixin-style contract tests for broker capability reporting."""

    def test_capabilities_exists(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps is not None

    def test_capabilities_is_broker_capabilities(self, gateway: BrokerGateway) -> None:
        """Capabilities must be a BrokerCapabilities dataclass."""
        caps = gateway.capabilities()
        assert isinstance(caps, BrokerCapabilities), (
            f"Expected BrokerCapabilities, got {type(caps).__name__}"
        )

    def test_capabilities_broker_id_present(self, gateway: BrokerGateway) -> None:
        """BrokerCapabilities must expose broker_id."""
        caps = gateway.capabilities()
        assert str(caps.broker_id)

    def test_capabilities_supports_method(self, gateway: BrokerGateway) -> None:
        """BrokerCapabilities must expose supports() method."""
        caps = gateway.capabilities()
        assert callable(caps.supports)

    def test_capabilities_to_dict(self, gateway: BrokerGateway) -> None:
        """BrokerCapabilities must expose to_dict()."""
        caps = gateway.capabilities()
        d = caps.to_dict()
        assert "broker_id" in d
        assert "supports" in d
        assert isinstance(d["supports"], dict)

    def test_core_capabilities_present(self, gateway: BrokerGateway) -> None:
        """Core trading capabilities must always be advertised."""
        caps = gateway.capabilities()
        supported = [
            caps.supports("place_order"),
            caps.supports("cancel_order"),
            caps.supports("modify_order"),
        ]
        for s in supported:
            assert s is not None, "Capability check must return bool"
        # At least some features are supported
        assert any(supported), "No core capabilities advertised"

    def test_supports_returns_bool(self, gateway: BrokerGateway) -> None:
        """supports() must always return a bool."""
        caps = gateway.capabilities()
        result = caps.supports("place_order")
        assert isinstance(result, bool)


@pytest.mark.contract
class TestCapabilityContractConformance:
    """Base test class — override ``gateway`` fixture for each broker."""

    @pytest.fixture
    def gateway(self) -> BrokerGateway:
        pytest.skip("No concrete BrokerGateway fixture provided")

    def test_capabilities_exists(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_capabilities_exists(gateway)

    def test_capabilities_is_broker_capabilities(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_capabilities_is_broker_capabilities(gateway)

    def test_capabilities_broker_id_present(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_capabilities_broker_id_present(gateway)

    def test_capabilities_supports_method(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_capabilities_supports_method(gateway)

    def test_capabilities_to_dict(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_capabilities_to_dict(gateway)

    def test_core_capabilities_present(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_core_capabilities_present(gateway)

    def test_supports_returns_bool(self, gateway: BrokerGateway) -> None:
        CapabilityContractTests().test_supports_returns_bool(gateway)


# ---------------------------------------------------------------------------
# Per-adapter contract test mixins
#
# These define the *distinguishing* assertions for each adapter. They are
# applied to each adapter test class below to keep the conformance and the
# per-adapter tests in one consistent suite.
# ---------------------------------------------------------------------------


class DhanCapabilityContractTests:
    """Distinctive capability assertions for the Dhan adapter."""

    broker_id: str = "dhan"

    def test_capabilities_broker_id_is_dhan(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.broker_id == BrokerID.DHAN
        # The to_dict() projection normalizes BrokerID to a plain string.
        assert caps.to_dict()["broker_id"] == "dhan"

    def test_core_trading_flags_true(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.supports_place_order is True
        assert caps.supports_cancel_order is True
        assert caps.supports_modify_order is True

    def test_supports_method_known_features(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        # supports() dispatches onto the supports_<feature> attribute.
        assert caps.supports("place_order") is True
        assert caps.supports("cancel_order") is True
        assert caps.supports("modify_order") is True
        assert caps.supports("historical_data") is True
        assert caps.supports("depth_20_ws") is True
        assert caps.supports("depth_200_ws") is True

    def test_distinctive_super_order_supported(self, gateway: BrokerGateway) -> None:
        """Dhan uniquely advertises super orders."""
        caps = gateway.capabilities()
        assert caps.supports_super_order is True
        assert caps.supports("super_order") is True

    def test_distinctive_native_slice_order_supported(self, gateway: BrokerGateway) -> None:
        """Dhan supports native slice orders natively."""
        caps = gateway.capabilities()
        assert caps.supports_native_slice_order is True
        assert caps.supports("native_slice_order") is True

    def test_distinctive_mtf_supported(self, gateway: BrokerGateway) -> None:
        """Dhan supports MTF product type."""
        caps = gateway.capabilities()
        assert caps.supports_mtf is True
        assert "MTF" in caps.product_types

    def test_portfolio_stream_not_supported(self, gateway: BrokerGateway) -> None:
        """Dhan does not natively expose a portfolio stream."""
        caps = gateway.capabilities()
        assert caps.supports_portfolio_stream is False
        assert caps.supports("portfolio_stream") is False

    def test_to_dict_is_json_serializable(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        d = caps.to_dict()
        # Must be a plain dict (not a MappingProxy) and round-trip through json.
        assert isinstance(d, dict)
        json.dumps(d, default=str)  # raises if not serializable

    def test_to_dict_supports_keys_match_dataclass(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        d = caps.to_dict()
        # Every supports_<x> field on the dataclass must appear in the dict.
        for field_name in caps.__dataclass_fields__:
            if field_name.startswith("supports_"):
                key = field_name.replace("supports_", "")
                assert key in d["supports"], f"Missing key in to_dict(): {key}"
                assert isinstance(d["supports"][key], bool)


class UpstoxCapabilityContractTests:
    """Distinctive capability assertions for the Upstox adapter."""

    broker_id: str = "upstox"

    def test_capabilities_broker_id_is_upstox(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.broker_id == BrokerID.UPSTOX
        assert caps.to_dict()["broker_id"] == "upstox"

    def test_core_trading_flags_true(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.supports_place_order is True
        assert caps.supports_cancel_order is True
        assert caps.supports_modify_order is True

    def test_supports_method_known_features(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.supports("place_order") is True
        assert caps.supports("cancel_order") is True
        assert caps.supports("modify_order") is True
        assert caps.supports("historical_data") is True

    def test_distinctive_forever_order_supported(self, gateway: BrokerGateway) -> None:
        """Upstox uses ``supports_forever_order`` to flag its GTT-style orders.

        Upstox exposes GTT orders via the ``GTTProvider`` extension protocol,
        and the matrix surfaces this as ``supports_forever_order=True``.
        """
        caps = gateway.capabilities()
        assert caps.supports_forever_order is True
        assert caps.supports("forever_order") is True

    def test_distinctive_news_supported(self, gateway: BrokerGateway) -> None:
        """Upstox is the only adapter advertising a news feed."""
        caps = gateway.capabilities()
        assert caps.supports_news is True
        assert caps.supports("news") is True

    def test_distinctive_portfolio_stream_supported(self, gateway: BrokerGateway) -> None:
        """Upstox supports a native portfolio stream."""
        caps = gateway.capabilities()
        assert caps.supports_portfolio_stream is True
        assert caps.supports("portfolio_stream") is True

    def test_super_order_not_supported(self, gateway: BrokerGateway) -> None:
        """Upstox does not natively support super orders (unlike Dhan)."""
        caps = gateway.capabilities()
        assert caps.supports_super_order is False
        assert caps.supports("super_order") is False

    def test_native_slice_order_not_supported(self, gateway: BrokerGateway) -> None:
        """Upstox does not support native slice orders (unlike Dhan)."""
        caps = gateway.capabilities()
        assert caps.supports_native_slice_order is False
        assert caps.supports("native_slice_order") is False

    def test_mtf_not_supported(self, gateway: BrokerGateway) -> None:
        """MTF is a Dhan-specific product type."""
        caps = gateway.capabilities()
        assert caps.supports_mtf is False
        assert "MTF" not in caps.product_types

    def test_to_dict_is_json_serializable(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        d = caps.to_dict()
        assert isinstance(d, dict)
        json.dumps(d, default=str)

    def test_to_dict_supports_keys_match_dataclass(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        d = caps.to_dict()
        for field_name in caps.__dataclass_fields__:
            if field_name.startswith("supports_"):
                key = field_name.replace("supports_", "")
                assert key in d["supports"], f"Missing key in to_dict(): {key}"
                assert isinstance(d["supports"][key], bool)


class PaperCapabilityContractTests:
    """Distinctive capability assertions for the Paper adapter."""

    broker_id: str = "paper"

    def test_capabilities_broker_id_is_paper(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.broker_id == BrokerID.PAPER
        assert caps.to_dict()["broker_id"] == "paper"

    def test_core_trading_flags_true(self, gateway: BrokerGateway) -> None:
        """Paper trading must still support the basic order lifecycle."""
        caps = gateway.capabilities()
        assert caps.supports_place_order is True
        assert caps.supports_cancel_order is True
        assert caps.supports_modify_order is True

    def test_supports_method_known_features(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.supports("place_order") is True
        assert caps.supports("cancel_order") is True
        assert caps.supports("modify_order") is True

    def test_no_market_data_features(self, gateway: BrokerGateway) -> None:
        """Paper trading has no live market data, depth, or streams."""
        caps = gateway.capabilities()
        assert caps.supports_live_market_data is False
        assert caps.supports("live_market_data") is False
        assert caps.supports_depth is False
        assert caps.supports("depth") is False
        assert caps.supports_historical_data is False
        assert caps.supports("historical_data") is False
        assert caps.supports_order_stream is False
        assert caps.supports("order_stream") is False
        assert caps.supports_portfolio_stream is False
        assert caps.supports("portfolio_stream") is False

    def test_no_advanced_order_types(self, gateway: BrokerGateway) -> None:
        """Paper trading does not advertise advanced order constructs."""
        caps = gateway.capabilities()
        assert caps.supports_super_order is False
        assert caps.supports("super_order") is False
        assert caps.supports_forever_order is False
        assert caps.supports("forever_order") is False
        assert caps.supports_gtt is False
        assert caps.supports("gtt") is False
        assert caps.supports_bracket_orders is False
        assert caps.supports("bracket_orders") is False
        assert caps.supports_cover_orders is False
        assert caps.supports("cover_orders") is False
        assert caps.supports_basket_orders is False
        assert caps.supports("basket_orders") is False
        assert caps.supports_native_slice_order is False
        assert caps.supports("native_slice_order") is False

    def test_no_options_support(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.supports_options is False
        assert caps.supports("options") is False
        assert caps.supports_option_chain is False
        assert caps.supports("option_chain") is False

    def test_to_dict_is_json_serializable(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        d = caps.to_dict()
        assert isinstance(d, dict)
        json.dumps(d, default=str)

    def test_to_dict_supports_keys_match_dataclass(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        d = caps.to_dict()
        for field_name in caps.__dataclass_fields__:
            if field_name.startswith("supports_"):
                key = field_name.replace("supports_", "")
                assert key in d["supports"], f"Missing key in to_dict(): {key}"
                assert isinstance(d["supports"][key], bool)

    def test_latency_class_is_simulated(self, gateway: BrokerGateway) -> None:
        caps = gateway.capabilities()
        assert caps.latency_class == "simulated"


# ---------------------------------------------------------------------------
# Per-adapter test classes
# ---------------------------------------------------------------------------


class TestDhanCapabilityContract(TestCapabilityContractConformance):
    """Contract tests for the Dhan adapter's capabilities surface."""

    @pytest.fixture
    def gateway(self) -> BrokerGateway:
        from brokers.adapters.dhan.capabilities import dhan_capabilities

        class _MockDhanGw:
            _caps = dhan_capabilities()

            @property
            def broker_id(self) -> str:
                return "dhan"

            def capabilities(self) -> Any:
                return self._caps

        return _MockDhanGw()

    # --- Dhan-specific tests ---

    def test_capabilities_broker_id_is_dhan(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_capabilities_broker_id_is_dhan(gateway)

    def test_core_trading_flags_true(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_core_trading_flags_true(gateway)

    def test_supports_method_known_features(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_supports_method_known_features(gateway)

    def test_distinctive_super_order_supported(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_distinctive_super_order_supported(gateway)

    def test_distinctive_native_slice_order_supported(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_distinctive_native_slice_order_supported(gateway)

    def test_distinctive_mtf_supported(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_distinctive_mtf_supported(gateway)

    def test_portfolio_stream_not_supported(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_portfolio_stream_not_supported(gateway)

    def test_to_dict_is_json_serializable(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_to_dict_is_json_serializable(gateway)

    def test_to_dict_supports_keys_match_dataclass(self, gateway: BrokerGateway) -> None:
        DhanCapabilityContractTests().test_to_dict_supports_keys_match_dataclass(gateway)


class TestUpstoxCapabilityContract(TestCapabilityContractConformance):
    """Contract tests for the Upstox adapter's capabilities surface."""

    @pytest.fixture
    def gateway(self) -> BrokerGateway:
        from brokers.adapters.upstox.capabilities import upstox_capabilities

        class _MockUpstoxGw:
            _caps = upstox_capabilities()

            @property
            def broker_id(self) -> str:
                return "upstox"

            def capabilities(self) -> Any:
                return self._caps

        return _MockUpstoxGw()

    # --- Upstox-specific tests ---

    def test_capabilities_broker_id_is_upstox(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_capabilities_broker_id_is_upstox(gateway)

    def test_core_trading_flags_true(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_core_trading_flags_true(gateway)

    def test_supports_method_known_features(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_supports_method_known_features(gateway)

    def test_distinctive_forever_order_supported(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_distinctive_forever_order_supported(gateway)

    def test_distinctive_news_supported(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_distinctive_news_supported(gateway)

    def test_distinctive_portfolio_stream_supported(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_distinctive_portfolio_stream_supported(gateway)

    def test_super_order_not_supported(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_super_order_not_supported(gateway)

    def test_native_slice_order_not_supported(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_native_slice_order_not_supported(gateway)

    def test_mtf_not_supported(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_mtf_not_supported(gateway)

    def test_to_dict_is_json_serializable(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_to_dict_is_json_serializable(gateway)

    def test_to_dict_supports_keys_match_dataclass(self, gateway: BrokerGateway) -> None:
        UpstoxCapabilityContractTests().test_to_dict_supports_keys_match_dataclass(gateway)


class TestPaperCapabilityContract(TestCapabilityContractConformance):
    """Contract tests for the Paper adapter's capabilities surface.

    The Paper adapter does not require any broker credentials, so this
    test class exercises the *real* ``PaperGateway`` end-to-end.
    """

    @pytest.fixture
    def gateway(self) -> BrokerGateway:
        from brokers.adapters.paper.gateway import PaperGateway

        return PaperGateway()

    # --- Paper-specific tests ---

    def test_capabilities_broker_id_is_paper(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_capabilities_broker_id_is_paper(gateway)

    def test_core_trading_flags_true(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_core_trading_flags_true(gateway)

    def test_supports_method_known_features(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_supports_method_known_features(gateway)

    def test_no_market_data_features(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_no_market_data_features(gateway)

    def test_no_advanced_order_types(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_no_advanced_order_types(gateway)

    def test_no_options_support(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_no_options_support(gateway)

    def test_to_dict_is_json_serializable(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_to_dict_is_json_serializable(gateway)

    def test_to_dict_supports_keys_match_dataclass(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_to_dict_supports_keys_match_dataclass(gateway)

    def test_latency_class_is_simulated(self, gateway: BrokerGateway) -> None:
        PaperCapabilityContractTests().test_latency_class_is_simulated(gateway)
