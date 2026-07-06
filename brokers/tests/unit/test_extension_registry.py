"""Tests for ExtensionDecoratorRegistry (Phase 4).

Covers:
- Registry registration, unregistration, lookup
- apply() with matching capabilities
- apply_from_adapter() with broker adapter
- get_default_registry() with pre-populated factories
- Registry integrated with InstrumentFactory
- Edge cases: duplicate registration, override, empty caps
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from inc_trade.extensions.registry import (
    ExtensionDecoratorRegistry,
    get_default_registry,
    reset_default_registry,
)
from inc_trade.market.instrument import Instrument

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def base_instrument() -> Instrument:
    inst = Instrument(symbol="RELIANCE", exchange="NSE", name="Reliance", lot_size=1)
    object.__setattr__(inst, "_provider", MagicMock())
    object.__setattr__(inst, "_depth_provider", MagicMock())
    return inst


@pytest.fixture
def registry() -> ExtensionDecoratorRegistry:
    return ExtensionDecoratorRegistry()


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.max_levels = 200
    return adapter


# ── Registration Tests ──────────────────────────────────────────────────


class TestRegistration:
    def test_register_and_get_factory(self, registry: ExtensionDecoratorRegistry) -> None:
        factory = lambda inst, **kw: inst
        registry.register("depth_200", factory)
        assert registry.get_factory("depth_200") is factory

    def test_register_duplicate_raises(self, registry: ExtensionDecoratorRegistry) -> None:
        registry.register("depth_200", lambda inst, **kw: inst)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("depth_200", lambda inst, **kw: inst)

    def test_register_duplicate_with_override(self, registry: ExtensionDecoratorRegistry) -> None:
        factory1 = lambda inst, **kw: inst
        factory2 = lambda inst, **kw: inst
        registry.register("depth_200", factory1)
        registry.register("depth_200", factory2, override=True)
        assert registry.get_factory("depth_200") is factory2

    def test_unregister(self, registry: ExtensionDecoratorRegistry) -> None:
        registry.register("depth_200", lambda inst, **kw: inst)
        registry.unregister("depth_200")
        assert registry.get_factory("depth_200") is None

    def test_unregister_nonexistent(self, registry: ExtensionDecoratorRegistry) -> None:
        registry.unregister("nonexistent")  # should not raise

    def test_has_key(self, registry: ExtensionDecoratorRegistry) -> None:
        registry.register("logging", lambda inst, **kw: inst)
        assert registry.has_key("logging")
        assert not registry.has_key("depth_200")

    def test_registered_keys(self, registry: ExtensionDecoratorRegistry) -> None:
        registry.register("a", lambda inst, **kw: inst)
        registry.register("b", lambda inst, **kw: inst)
        assert registry.registered_keys == frozenset({"a", "b"})

    def test_repr(self, registry: ExtensionDecoratorRegistry) -> None:
        registry.register("depth_200", lambda inst, **kw: inst)
        r = repr(registry)
        assert "depth_200" in r


# ── Apply Tests ──────────────────────────────────────────────────────────


class TestApply:
    def test_apply_matching_capability(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """A registered factory should be called when its capability is present."""
        was_called = False

        def test_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal was_called
            was_called = True
            return inst

        registry.register("test_cap", test_factory)
        result = registry.apply(base_instrument, {"test_cap": True})
        assert was_called
        assert result is base_instrument

    def test_apply_non_matching_capability(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """Factory should NOT be called when capability is absent."""
        was_called = False

        def test_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal was_called
            was_called = True
            return inst

        registry.register("test_cap", test_factory)
        registry.apply(base_instrument, {"other_cap": True})
        assert not was_called

    def test_apply_zero_value_skips(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """A capability value of 0 should NOT trigger the decorator."""
        was_called = False

        def test_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal was_called
            was_called = True
            return inst

        registry.register("depth_200", test_factory)
        registry.apply(base_instrument, {"depth_200": 0})
        assert not was_called

    def test_apply_false_value_skips(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        was_called = False

        def test_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal was_called
            was_called = True
            return inst

        registry.register("logging", test_factory)
        registry.apply(base_instrument, {"logging": False})
        assert not was_called

    def test_apply_empty_capabilities(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """Empty capabilities should not cause errors."""
        registry.register("depth_200", lambda inst, **kw: inst)
        result = registry.apply(base_instrument, {})
        assert result is base_instrument

    def test_apply_multiple_decorators(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """Multiple matching capabilities should apply in registration order."""
        applied: list[str] = []

        def factory_a(inst: Instrument, **kwargs: Any) -> Instrument:
            applied.append("a")
            return inst

        def factory_b(inst: Instrument, **kwargs: Any) -> Instrument:
            applied.append("b")
            return inst

        registry.register("cap_a", factory_a)
        registry.register("cap_b", factory_b)
        registry.apply(base_instrument, {"cap_a": True, "cap_b": True})
        assert applied == ["a", "b"]


# ── Apply from Adapter Tests ─────────────────────────────────────────────


class TestApplyFromAdapter:
    def test_apply_from_adapter_with_depth(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """Adapter with max_levels > 5 should trigger depth decorator."""
        depth_applied = False

        def depth_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal depth_applied
            depth_applied = True
            return inst

        registry.register("depth_200", depth_factory)

        adapter = MagicMock()
        adapter.max_levels = 200

        registry.apply_from_adapter(base_instrument, adapter)
        assert depth_applied

    def test_apply_from_adapter_no_depth(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """Adapter with max_levels <= 5 should NOT trigger depth decorator."""
        depth_applied = False

        def depth_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal depth_applied
            depth_applied = True
            return inst

        registry.register("depth_20", depth_factory)

        adapter = MagicMock()
        adapter.max_levels = 5

        registry.apply_from_adapter(base_instrument, adapter)
        assert not depth_applied

    def test_apply_from_adapter_no_max_levels(
        self, registry: ExtensionDecoratorRegistry, base_instrument: Instrument
    ) -> None:
        """Adapter without max_levels should default to 5."""
        depth_applied = False

        def depth_factory(inst: Instrument, **kwargs: Any) -> Instrument:
            nonlocal depth_applied
            depth_applied = True
            return inst

        registry.register("depth_200", depth_factory)

        adapter = MagicMock()
        del adapter.max_levels  # Remove max_levels attribute

        registry.apply_from_adapter(base_instrument, adapter)
        assert not depth_applied


# ── Default Registry Tests ────────────────────────────────────────────────


class TestDefaultRegistry:
    def test_get_default_registry(self) -> None:
        reset_default_registry()
        reg = get_default_registry()
        assert isinstance(reg, ExtensionDecoratorRegistry)
        assert reg.has_key("depth_20")
        assert reg.has_key("depth_30")
        assert reg.has_key("depth_200")
        assert reg.has_key("cache")
        assert reg.has_key("logging")

    def test_default_registry_singleton(self) -> None:
        reset_default_registry()
        reg1 = get_default_registry()
        reg2 = get_default_registry()
        assert reg1 is reg2

    def test_default_registry_depth_factory(self) -> None:
        """Default depth factory should create proper decorators."""
        reset_default_registry()
        reg = get_default_registry()

        inst = Instrument(symbol="RELIANCE", exchange="NSE", lot_size=1)
        provider = MagicMock()
        object.__setattr__(inst, "_provider", provider)
        object.__setattr__(inst, "_depth_provider", provider)

        result = reg.apply(inst, {"depth_200": 200})
        from inc_trade.market.depth_decorators import Depth200Decorator

        assert isinstance(result, Depth200Decorator)

    def test_default_registry_cache_factory(self) -> None:
        reset_default_registry()
        reg = get_default_registry()

        inst = Instrument(symbol="RELIANCE", exchange="NSE", lot_size=1)
        result = reg.apply(inst, {"cache": True})
        from inc_trade.market.cache_decorator import CachedDecorator

        assert isinstance(result, CachedDecorator)

    def test_default_registry_logging_factory(self) -> None:
        reset_default_registry()
        reg = get_default_registry()

        inst = Instrument(symbol="RELIANCE", exchange="NSE", lot_size=1)
        result = reg.apply(inst, {"logging": True})
        from inc_trade.market.log_decorator import LoggedDecorator

        assert isinstance(result, LoggedDecorator)


# ── Integration with InstrumentFactory ─────────────────────────────────────


class TestFactoryIntegration:
    def test_factory_with_extension_registry(self) -> None:
        """InstrumentFactory should apply decorators via extension registry."""
        from inc_trade.market.factory import InstrumentFactory

        reset_default_registry()
        reg = get_default_registry()

        adapter = MagicMock()
        adapter.max_levels = 200

        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=adapter,
            depth_provider=adapter,
            extension_registry=reg,
        )

        from inc_trade.market.depth_decorators import Depth200Decorator

        assert isinstance(inst, Depth200Decorator)

    def test_factory_apply_depth_still_works(self) -> None:
        """Legacy apply_depth parameter should still work without registry."""
        from inc_trade.market.factory import InstrumentFactory

        adapter = MagicMock()
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=adapter,
            depth_provider=adapter,
            apply_depth=200,
        )

        from inc_trade.market.depth_decorators import Depth200Decorator

        assert isinstance(inst, Depth200Decorator)

    def test_factory_registry_takes_precedence(self) -> None:
        """Extension registry should take precedence over apply_depth."""
        from inc_trade.market.factory import InstrumentFactory

        reset_default_registry()
        reg = get_default_registry()

        adapter = MagicMock()
        adapter.max_levels = 200

        # Both extension_registry and apply_depth=5 are provided — registry wins
        inst = InstrumentFactory.create(
            symbol="RELIANCE",
            exchange="NSE",
            provider=adapter,
            depth_provider=adapter,
            apply_depth=5,
            extension_registry=reg,
        )

        # Registry should apply depth_200 (from adapter.max_levels=200)
        from inc_trade.market.depth_decorators import Depth200Decorator

        assert isinstance(inst, Depth200Decorator)
