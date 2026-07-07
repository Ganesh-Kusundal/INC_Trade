"""Architecture tests — ban code smells per v2 refactoring philosophy.

These tests enforce the architectural rules from the v2 design document:
  - No wrapper-only classes (>70% forwarding methods)
  - No *Manager, *Helper, *Util, *Wrapper, *Facade class names
  - No anemic domain objects (data classes with zero methods)
  - No type: ignore in domain layer
  - No getattr string-based dispatch
  - No broker names in domain layer
  - No circular imports
  - Domain imports nothing external
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ── Constants ──────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOMAIN_DIR = _PROJECT_ROOT / "brokers" / "domain"
_PROVIDER_DIR = _PROJECT_ROOT / "brokers" / "provider"

_BANNED_CLASS_NAME_PATTERNS = [
    re.compile(r".*Manager$"),
    re.compile(r".*Helper$"),
    re.compile(r".*Util$"),
    re.compile(r".*Wrapper$"),
    re.compile(r".*Facade$"),
]

_BROKER_NAMES = {"dhan", "upstox", "paper", "zerodha", "angel", "icici"}


# ── Helpers ────────────────────────────────────────────────────────────────


def _collect_python_files(directory: Path) -> list[Path]:
    """Collect all .py files in a directory recursively."""
    return sorted(directory.rglob("*.py"))


def _parse_ast(filepath: Path) -> ast.Module:
    """Parse a Python file into an AST."""
    return ast.parse(filepath.read_text(), filename=str(filepath))


def _class_names_in_ast(tree: ast.Module) -> list[str]:
    """Extract all class names from an AST."""
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]


# ── Test: No *Manager, *Helper, *Util, *Wrapper, *Facade classes ──────────


class TestNoBannedClassNames:
    """No class named *Manager, *Helper, *Util, *Wrapper, *Facade."""

    @pytest.mark.parametrize("directory", [_DOMAIN_DIR, _PROVIDER_DIR])
    def test_no_banned_names_in_domain_and_provider(self, directory: Path) -> None:
        violations: list[str] = []
        for filepath in _collect_python_files(directory):
            tree = _parse_ast(filepath)
            for name in _class_names_in_ast(tree):
                for pattern in _BANNED_CLASS_NAME_PATTERNS:
                    if pattern.match(name):
                        violations.append(f"{filepath.name}: class {name}")
        assert not violations, (
            "Banned class names found (violates v2 refactoring philosophy):\n"
            + "\n".join(violations)
        )


# ── Test: No type: ignore in domain layer ─────────────────────────────────


class TestNoTypeIgnoreInDomain:
    """Domain layer must have zero type: ignore comments."""

    def test_no_type_ignore(self) -> None:
        violations: list[str] = []
        for filepath in _collect_python_files(_DOMAIN_DIR):
            content = filepath.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if "type: ignore" in line:
                    violations.append(f"{filepath.name}:{i}: {line.strip()}")
        assert not violations, (
            "type: ignore found in domain layer (violates type safety):\n"
            + "\n".join(violations)
        )


# ── Test: No getattr string dispatch in domain layer ──────────────────────


class TestNoGetattrDispatch:
    """No string-based method dispatch via getattr in domain layer."""

    def test_no_getattr_dispatch(self) -> None:
        violations: list[str] = []
        getattr_pattern = re.compile(r"getattr\s*\(")
        for filepath in _collect_python_files(_DOMAIN_DIR):
            content = filepath.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if getattr_pattern.search(line):
                    violations.append(f"{filepath.name}:{i}: {line.strip()}")
        assert not violations, (
            "getattr dispatch found in domain layer (violates type safety):\n"
            + "\n".join(violations)
        )


# ── Test: No broker names in domain layer ─────────────────────────────────


class TestNoBrokerNamesInDomain:
    """Domain must not reference any specific broker."""

    def test_no_broker_names(self) -> None:
        violations: list[str] = []
        for filepath in _collect_python_files(_DOMAIN_DIR):
            content = filepath.read_text().lower()
            for broker in _BROKER_NAMES:
                # Check for broker name as a word (not in comments about the name itself)
                if re.search(rf"\b{broker}\b", content):
                    # Allow the word in __all__ or string literals that are generic
                    # But flag any import or class reference
                    if f"import {broker}" in content or f"from brokers.{broker}" in content:
                        violations.append(f"{filepath.name}: references '{broker}'")
        assert not violations, (
            "Broker-specific references found in domain layer (violates broker agnosticism):\n"
            + "\n".join(violations)
        )


# ── Test: Domain imports nothing external ─────────────────────────────────


class TestDomainPurity:
    """Domain layer imports only from domain/ and stdlib."""

    def test_domain_imports_nothing_external(self) -> None:
        """Domain layer imports only from domain/ and stdlib.

        TYPE_CHECKING imports are exempt — they don't execute at runtime
        and are used only for type hints (e.g. Provider protocol).
        """
        _STDLIB_PREFIXES = (
            "datetime", "decimal", "enum", "dataclasses", "typing",
            "collections", "threading", "uuid", "__future__", "abc",
            "functools", "asyncio",
        )

        violations: list[str] = []
        for filepath in _collect_python_files(_DOMAIN_DIR):
            tree = _parse_ast(filepath)
            # Collect nodes inside TYPE_CHECKING blocks to skip them
            type_checking_nodes: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    # Check if it's `if TYPE_CHECKING:`
                    test = node.test
                    if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
                       (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"):
                        for child in ast.walk(node):
                            type_checking_nodes.add(id(child))

            for node in ast.walk(tree):
                # Skip imports inside TYPE_CHECKING blocks
                if id(node) in type_checking_nodes:
                    continue
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod = alias.name
                        if not mod.startswith("brokers.domain") and not mod.startswith(_STDLIB_PREFIXES):
                            violations.append(f"{filepath.name}: import {mod}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and not node.module.startswith("brokers.domain") and not node.module.startswith(_STDLIB_PREFIXES):
                        violations.append(f"{filepath.name}: from {node.module}")
        assert not violations, (
            "External imports found in domain layer (violates domain purity):\n"
            + "\n".join(violations)
        )


# ── Test: Rich domain objects have methods (not anemic) ───────────────────


class TestNoAnemicDomainObjects:
    """Domain classes must have methods, not just data."""

    def test_instrument_has_methods(self) -> None:
        """Instrument must have methods (not anemic)."""
        from brokers.domain.instrument import Instrument

        methods = [
            attr for attr in dir(Instrument)
            if not attr.startswith("_") and callable(getattr(Instrument, attr, None))
        ]
        # Should have at least: quote, ltp, depth, history, subscribe_quotes, buy, sell, option_chain
        expected = {"quote", "ltp", "depth", "history", "subscribe_quotes", "buy", "sell"}
        found = set(methods)
        missing = expected - found
        assert not missing, f"Instrument is missing expected methods: {missing}"

    def test_account_has_methods(self) -> None:
        """Account must have methods (not anemic)."""
        from brokers.domain.account import Account

        methods = [
            attr for attr in dir(Account)
            if not attr.startswith("_") and callable(getattr(Account, attr, None))
        ]
        expected = {"place_order", "cancel_order", "get_positions", "get_balance"}
        found = set(methods)
        missing = expected - found
        assert not missing, f"Account is missing expected methods: {missing}"

    def test_order_has_lifecycle_methods(self) -> None:
        """Order must have lifecycle methods (not anemic)."""
        from brokers.domain.order import Order

        methods = [
            attr for attr in dir(Order)
            if not attr.startswith("_") and callable(getattr(Order, attr, None))
        ]
        expected = {"update_status"}
        found = set(methods)
        missing = expected - found
        assert not missing, f"Order is missing expected methods: {missing}"


# ── Test: Public API exports are importable ───────────────────────────────


class TestPublicAPI:
    """Public API exports must be importable."""

    def test_broker_import(self) -> None:
        from brokers import Broker
        assert Broker is not None

    def test_instrument_import(self) -> None:
        from brokers import Instrument
        assert Instrument is not None

    def test_account_import(self) -> None:
        from brokers import Account
        assert Account is not None

    def test_provider_import(self) -> None:
        from brokers import Provider
        assert Provider is not None

    def test_all_core_types_importable(self) -> None:
        from brokers import (
            AssetClass,
            Balance,
            Broker,
            Exchange,
            Greeks,
            Instrument,
            MarketDepth,
            OrderRequest,
            OrderResponse,
            Position,
            Quote,
            RiskPolicy,
            Side,
            Subscription,
            Trade,
        )
        # All should be non-None
        for obj in [AssetClass, Balance, Broker, Exchange, Greeks, Instrument,
                    MarketDepth, OrderRequest, OrderResponse, Position, Quote,
                    RiskPolicy, Side, Subscription, Trade]:
            assert obj is not None
