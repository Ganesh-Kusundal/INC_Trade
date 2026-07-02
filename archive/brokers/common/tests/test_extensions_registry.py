"""Integration tests for ExtensionRegistry and ExtensionBundle."""

import pytest

from brokers.common.errors import UnsupportedExtensionError
from brokers.common.extensions import ExtensionBundle, ExtensionRegistry
from brokers.common.extensions.news import NewsProvider
from brokers.common.extensions.super_order import SuperOrderProvider


class _UpstoxNewsProvider:
    async def fetch_symbol_news(self, symbol, *, quota, limit=20):
        return []

    async def fetch_market_news(self, *, quota, category=None, limit=20):
        return []


class TestExtensionRegistry:
    def test_resolve_returns_none_when_unregistered(self):
        registry = ExtensionRegistry()
        bundle = ExtensionBundle("dhan")
        registry.register_bundle("dhan", bundle)
        assert registry.resolve("dhan", NewsProvider) is None

    def test_require_raises_with_alternatives(self):
        registry = ExtensionRegistry()
        dhan_bundle = ExtensionBundle("dhan")
        upstox_bundle = ExtensionBundle("upstox")
        upstox_bundle.register(NewsProvider, _UpstoxNewsProvider())
        registry.register_bundle("dhan", dhan_bundle)
        registry.register_bundle("upstox", upstox_bundle)

        with pytest.raises(UnsupportedExtensionError) as exc_info:
            registry.require("dhan", NewsProvider)

        err = exc_info.value
        assert err.broker_id == "dhan"
        assert err.extension_name == "NewsProvider"
        assert "upstox" in err.alternatives

    def test_brokers_supporting_extension(self):
        registry = ExtensionRegistry()
        upstox_bundle = ExtensionBundle("upstox")
        upstox_bundle.register(NewsProvider, _UpstoxNewsProvider())
        registry.register_bundle("upstox", upstox_bundle)
        assert registry.brokers_supporting(NewsProvider) == ["upstox"]
        assert registry.brokers_supporting(SuperOrderProvider) == []
