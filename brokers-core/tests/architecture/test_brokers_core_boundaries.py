"""Architecture boundary tests for brokers-core package independence."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BROKERS_CORE_ROOT = Path(__file__).resolve().parents[2] / "src" / "brokers_core"
STDLIB_MODULES = {
    "abc",
    "asyncio",
    "collections",
    "contextlib",
    "copy",
    "dataclasses",
    "datetime",
    "decimal",
    "enum",
    "functools",
    "hashlib",
    "hmac",
    "io",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "queue",
    "re",
    "socket",
    "ssl",
    "string",
    "struct",
    "sys",
    "threading",
    "time",
    "types",
    "typing",
    "urllib",
    "uuid",
    "warnings",
    "weakref",
    "zoneinfo",
    "__future__",
}


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


@pytest.mark.architecture
class TestBrokersCoreBoundaryRules:
    def test_brokers_core_never_imports_inc_trade(self) -> None:
        violations: list[str] = []
        for path in _iter_python_files(BROKERS_CORE_ROOT):
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "inc_trade" in line and (
                    "import inc_trade" in line
                    or "from inc_trade" in line
                    or "import inc_trade." in line
                    or "from inc_trade." in line
                ):
                    violations.append(f"{path.relative_to(BROKERS_CORE_ROOT.parent.parent)}:{line_no}")
        assert not violations, "brokers-core must not import inc_trade:\n" + "\n".join(violations)

    def test_domain_imports_only_stdlib(self) -> None:
        domain_root = BROKERS_CORE_ROOT / "domain"
        allowed = STDLIB_MODULES | {"brokers_core"}
        violations: list[str] = []
        for path in _iter_python_files(domain_root):
            for mod in _top_level_imports(path):
                if mod not in allowed:
                    violations.append(f"{path.name}: {mod}")
        assert not violations, "domain/ must not import outside stdlib + domain:\n" + "\n".join(
            violations
        )

    def test_ports_imports_only_domain_and_stdlib(self) -> None:
        ports_root = BROKERS_CORE_ROOT / "ports"
        allowed = STDLIB_MODULES | {"brokers_core"}
        violations: list[str] = []
        for path in _iter_python_files(ports_root):
            for mod in _top_level_imports(path):
                if mod not in allowed:
                    violations.append(f"{path.name}: {mod}")
        assert not violations, "ports/ must only import domain + stdlib:\n" + "\n".join(violations)


@pytest.mark.architecture
class TestPortStructure:
    def test_infrastructure_ports_are_runtime_checkable(self) -> None:
        from brokers_core.ports.infrastructure import (
            ConcurrencyPort,
            DataAccessPort,
            HttpPort,
            ObservabilityPort,
            SecurityPort,
            WebSocketPort,
        )

        for port in (
            HttpPort,
            WebSocketPort,
            SecurityPort,
            ObservabilityPort,
            DataAccessPort,
            ConcurrencyPort,
        ):
            assert getattr(port, "_is_runtime_protocol", False), f"{port} not runtime_checkable"


@pytest.mark.architecture
class TestExceptionHierarchy:
    def test_all_exceptions_inherit_from_tradexv2_error(self) -> None:
        import brokers_core.domain.exceptions as exceptions

        for name in dir(exceptions):
            if name.startswith("_"):
                continue
            cls = getattr(exceptions, name)
            if isinstance(cls, type) and issubclass(cls, BaseException):
                assert issubclass(cls, exceptions.TradeXV2Error), (
                    f"{name} missing TradeXV2Error base"
                )
