"""Architecture tests — validate dependency rules and structural integrity.

These tests ensure the SDK follows its own architectural rules:
- No circular dependencies
- Core has no domain knowledge
- Provider-specific code stays in provider packages
- Domain objects are immutable where required
"""

import importlib
import pkgutil
from pathlib import Path

import pytest


def get_all_modules(package_path: Path, package_name: str) -> list[str]:
    """Recursively get all module names in a package."""
    modules = []
    for importer, modname, ispkg in pkgutil.walk_packages(
        [str(package_path)], prefix=package_name + "."
    ):
        modules.append(modname)
    return modules


class TestArchitecture:
    """Architecture validation tests."""

    def test_core_has_no_domain_imports(self):
        """Core framework must not import from domain layer."""
        core_path = Path(__file__).parent.parent / "src" / "tradex" / "core"
        core_modules = get_all_modules(core_path, "tradex.core")

        forbidden = {"tradex.domain", "tradex.broker", "tradex.streaming", "tradex.providers"}

        violations = []
        for mod_name in core_modules:
            try:
                mod = importlib.import_module(mod_name)
                source = getattr(mod, "__file__", "")
                if source:
                    with open(source) as f:
                        content = f.read()
                    for fb in forbidden:
                        if f"from {fb}" in content or f"import {fb}" in content:
                            violations.append(f"{mod_name} imports {fb}")
            except (ImportError, FileNotFoundError):
                pass

        assert not violations, f"Core layer violations: {violations}"

    def test_domain_has_no_broker_imports(self):
        """Domain layer must not import from broker or provider layers."""
        domain_path = Path(__file__).parent.parent / "src" / "tradex" / "domain"
        domain_modules = get_all_modules(domain_path, "tradex.domain")

        forbidden = {"tradex.broker", "tradex.providers", "tradex.streaming"}

        violations = []
        for mod_name in domain_modules:
            try:
                mod = importlib.import_module(mod_name)
                source = getattr(mod, "__file__", "")
                if source:
                    with open(source) as f:
                        content = f.read()
                    for fb in forbidden:
                        if f"from {fb}" in content or f"import {fb}" in content:
                            violations.append(f"{mod_name} imports {fb}")
            except (ImportError, FileNotFoundError):
                pass

        assert not violations, f"Domain layer violations: {violations}"

    def test_providers_only_import_from_broker_domain_core(self):
        """Providers must not import from other providers."""
        providers_path = Path(__file__).parent.parent / "src" / "tradex" / "providers"
        provider_modules = []
        for provider_dir in providers_path.iterdir():
            if provider_dir.is_dir() and provider_dir.name != "__pycache__":
                provider_modules.extend(
                    get_all_modules(provider_dir, f"tradex.providers.{provider_dir.name}")
                )

        violations = []
        for mod_name in provider_modules:
            try:
                mod = importlib.import_module(mod_name)
                source = getattr(mod, "__file__", "")
                if source:
                    with open(source) as f:
                        content = f.read()
                    # Check for imports of other providers
                    for line in content.split("\n"):
                        if "import" in line:
                            for other_provider in ["dhan", "upstox", "zerodha"]:
                                if (
                                    f"providers.{other_provider}" in line
                                    and f"providers.{mod_name.split('.')[2]}" not in line
                                ):
                                    violations.append(f"{mod_name} imports another provider")
            except (ImportError, FileNotFoundError):
                pass

        assert not violations, f"Provider isolation violations: {violations}"

    def test_value_objects_are_frozen(self):
        """Value objects should be immutable (frozen dataclasses)."""
        from tradex.domain.value_objects import (
            DateRange,
            InstrumentKey,
            Money,
            Price,
            Quantity,
            SecurityID,
        )

        for cls in [Money, Price, Quantity, DateRange, SecurityID, InstrumentKey]:
            assert hasattr(cls, "__dataclass_params__"), f"{cls.__name__} should be a dataclass"
            assert cls.__dataclass_params__.frozen, f"{cls.__name__} should be frozen"

    def test_domain_events_are_frozen(self):
        """Domain events should be immutable."""
        from tradex.domain.events import (
            OrderFilled,
            OrderPlaced,
            QuoteReceived,
            SessionConnected,
        )

        for cls in [OrderPlaced, OrderFilled, QuoteReceived, SessionConnected]:
            assert cls.__dataclass_params__.frozen, f"{cls.__name__} should be frozen"

    def test_all_packages_have_init(self):
        """All packages should have __init__.py."""
        src_path = Path(__file__).parent.parent / "src" / "tradex"
        packages = [
            src_path,
            src_path / "core",
            src_path / "domain",
            src_path / "broker",
            src_path / "streaming",
            src_path / "providers",
            src_path / "providers" / "dhan",
        ]
        for pkg in packages:
            init_file = pkg / "__init__.py"
            assert init_file.exists(), f"Missing __init__.py in {pkg}"

    def test_no_circular_imports(self):
        """Verify the main modules can be imported without circular import errors."""
        modules_to_test = [
            "tradex.core.errors",
            "tradex.core.events",
            "tradex.core.config",
            "tradex.core.cache",
            "tradex.core.rate_limiter",
            "tradex.core.retry",
            "tradex.core.validation",
            "tradex.core.health",
            "tradex.core.metrics",
            "tradex.core.serialization",
            "tradex.domain.enums",
            "tradex.domain.value_objects",
            "tradex.domain.events",
            "tradex.domain.account",
            "tradex.domain.portfolio",
            "tradex.domain.execution",
            "tradex.domain.instruments",
            "tradex.domain.market_data",
            "tradex.domain.mapping",
            "tradex.broker.capability",
            "tradex.broker.extensions",
            "tradex.broker.auth",
            "tradex.broker.session",
            "tradex.streaming.engine",
            "tradex.streaming.feed",
            "tradex.streaming.order_feed",
        ]

        for mod_name in modules_to_test:
            try:
                importlib.import_module(mod_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {mod_name}: {e}")
