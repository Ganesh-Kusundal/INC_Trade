"""Tests for the extension factory registry (replaces lazy broker imports)."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.common.extensions import (
    ExtensionBundle,
    get_extension_factory,
    register_extension_factory,
)
from brokers.common.extensions.news import NewsProvider
from brokers.common.extensions.super_order import SuperOrderProvider


class TestExtensionFactoryRegistry:
    """Tests for register_extension_factory / get_extension_factory."""

    def setup_method(self):
        """Clear registry before each test."""
        from brokers.common.extensions import _extension_factories

        _extension_factories.clear()

    def test_register_and_get_factory(self):
        def dummy_factory(gateway):
            return ExtensionBundle("dummy")

        register_extension_factory("dummy", dummy_factory)
        assert get_extension_factory("dummy") is dummy_factory

    def test_get_unknown_factory_returns_none(self):
        assert get_extension_factory("nonexistent") is None

    def test_register_overwrites_previous(self):
        def factory_v1(gw):
            return ExtensionBundle("b")

        def factory_v2(gw):
            return ExtensionBundle("b")

        register_extension_factory("b", factory_v1)
        register_extension_factory("b", factory_v2)
        assert get_extension_factory("b") is factory_v2


class TestBuildExtensionBundle:
    """Tests for build_extension_bundle using the registry."""

    def setup_method(self):
        from brokers.common.extensions import _extension_factories

        _extension_factories.clear()

    def test_build_with_registered_factory(self):
        from brokers.common.adapters.extensions import build_extension_bundle

        class FakeProvider:
            pass

        def factory(gateway):
            bundle = ExtensionBundle("test")
            bundle.register(FakeProvider, MagicMock())
            return bundle

        register_extension_factory("test", factory)
        bundle = build_extension_bundle("test", MagicMock())

        assert bundle.resolve(FakeProvider) is not None
        assert "FakeProvider" in bundle.registered_names()

    def test_build_without_factory_returns_empty_bundle(self):
        from brokers.common.adapters.extensions import build_extension_bundle

        bundle = build_extension_bundle("unknown_broker", MagicMock())
        assert bundle.registered_names() == frozenset()

    def test_build_bundle_has_correct_broker_id(self):
        from brokers.common.adapters.extensions import build_extension_bundle

        def factory(gw):
            return ExtensionBundle("mybroker")

        register_extension_factory("mybroker", factory)
        bundle = build_extension_bundle("mybroker", MagicMock())
        assert bundle._broker_id == "mybroker"


class TestDhanRegistration:
    """Verify Dhan registers its factory at import time."""

    def test_dhan_factory_registered(self):
        # Explicit import triggers self-registration of the dhan factory.
        import brokers.dhan.common_extensions  # noqa: F401

        factory = get_extension_factory("dhan")
        assert factory is not None
        assert callable(factory)

    def test_dhan_factory_returns_bundle_with_providers(self):
        import brokers.dhan.common_extensions  # noqa: F401
        from brokers.common.extensions.forever_order import ForeverOrderProvider
        from brokers.common.extensions.native_slice_order import NativeSliceOrderProvider

        factory = get_extension_factory("dhan")
        gateway = MagicMock()
        # Dhan extensions access gateway.extended
        gateway.extended = MagicMock()
        bundle = factory(gateway)

        assert bundle.resolve(SuperOrderProvider) is not None
        assert bundle.resolve(ForeverOrderProvider) is not None
        assert bundle.resolve(NativeSliceOrderProvider) is not None


class TestUpstoxRegistration:
    """Verify Upstox registers its factory at import time."""

    def test_upstox_factory_registered(self):
        # Explicit import triggers self-registration of the upstox factory.
        import brokers.upstox.common_extensions  # noqa: F401

        factory = get_extension_factory("upstox")
        assert factory is not None
        assert callable(factory)

    def test_upstox_factory_returns_bundle_with_providers(self):
        import brokers.upstox.common_extensions  # noqa: F401
        from brokers.common.extensions.forever_order import ForeverOrderProvider
        from brokers.common.extensions.fundamentals import FundamentalsProvider

        factory = get_extension_factory("upstox")
        gateway = MagicMock()
        # Upstox extensions access gateway._broker
        broker = MagicMock()
        broker.news = MagicMock()
        broker.fundamentals = MagicMock()
        gateway._broker = broker
        bundle = factory(gateway)

        assert bundle.resolve(NewsProvider) is not None
        assert bundle.resolve(FundamentalsProvider) is not None
        assert bundle.resolve(ForeverOrderProvider) is not None
