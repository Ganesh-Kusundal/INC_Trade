"""Architecture tests — enforce hexagonal boundary rules and invariants.

These tests run in <1s and catch import direction violations, missing
decorators, and structural regressions.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

BROKERS_ROOT = Path(__file__).resolve().parents[3]


def _list_modules(layer: str) -> list[Path]:
    layer_dir = BROKERS_ROOT / layer
    return [p for p in layer_dir.rglob("*.py") if "tests" not in str(p)]


def _get_imports(filepath: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith("brokers."):
                imports.append((node.lineno, node.module))
    return imports


BOUNDARY_RULES: dict[str, set[str]] = {
    "domain": set(),
    "core": set(),
    "utils": set(),
    "config": {"brokers.domain.exceptions"},
    "ports": {"brokers.domain", "brokers.ports"},
    "services": {"brokers.domain", "brokers.ports", "brokers.utils", "brokers.services"},
    "resilience": {"brokers.domain", "brokers.resilience"},
}


@pytest.mark.architecture
class TestBoundaryRules:
    @pytest.mark.parametrize("layer", [
        "domain", "core", "utils", "config", "ports", "services", "resilience",
    ])
    def test_boundary(self, layer: str) -> None:
        allowed = BOUNDARY_RULES[layer]
        violations = []
        for filepath in _list_modules(layer):
            for lineno, module in _get_imports(filepath):
                if not any(module.startswith(a) for a in allowed):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, f"Layer '{layer}' has boundary violations:\n" + "\n".join(violations)


@pytest.mark.architecture
class TestPortStructure:
    ALL_PORTS = [
        "brokers.ports.auth.AuthPort",
        "brokers.ports.broker.BrokerGateway",
        "brokers.ports.clock.ClockPort",
        "brokers.ports.historical.HistoricalPort",
        "brokers.ports.instruments.InstrumentPort",
        "brokers.ports.market_data.MarketDataPort",
        "brokers.ports.order_execution.OrderExecutionPort",
        "brokers.ports.portfolio.PortfolioPort",
        "brokers.ports.risk_manager.RiskManagerPort",
        "brokers.ports.streaming.StreamingPort",
        "brokers.ports.capabilities.MarginProvider",
        "brokers.ports.capabilities.SuperOrderProvider",
        "brokers.ports.capabilities.ForeverOrderProvider",
        "brokers.ports.capabilities.ConditionalTriggerProvider",
        "brokers.ports.capabilities.EDISTransferProvider",
        "brokers.ports.capabilities.IPManagementProvider",
        "brokers.ports.capabilities.LedgerProvider",
        "brokers.ports.capabilities.UserProfileProvider",
        "brokers.ports.capabilities.ReconciliationProvider",
        "brokers.ports.extensions.BrokerExtension",
    ]

    @pytest.mark.parametrize("dotted_path", ALL_PORTS, ids=lambda p: p.rsplit(".", 1)[-1])
    def test_is_runtime_checkable_protocol(self, dotted_path: str) -> None:
        mod_path, cls_name = dotted_path.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        assert getattr(cls, "_is_protocol", False), f"{dotted_path} is not a Protocol"
        assert getattr(cls, "_is_runtime_protocol", False), f"{dotted_path} is not @runtime_checkable"

    def test_all_core_ports_exported(self) -> None:
        import brokers.ports
        for dotted_path in self.ALL_PORTS:
            cls_name = dotted_path.rsplit(".", 1)[-1]
            assert hasattr(brokers.ports, cls_name), f"{cls_name} not exported from brokers.ports"


@pytest.mark.architecture
class TestExceptionHierarchy:
    def test_order_state_error_inherits_tradexv2_error(self) -> None:
        from brokers.domain.order_lifecycle import OrderStateError
        from brokers.domain.exceptions import TradeXV2Error
        assert issubclass(OrderStateError, TradeXV2Error)

    def test_all_exceptions_inherit_tradexv2_error(self) -> None:
        from brokers.domain import exceptions
        from brokers.domain.exceptions import TradeXV2Error
        for name in dir(exceptions):
            obj = getattr(exceptions, name)
            if isinstance(obj, type) and issubclass(obj, Exception) and obj is not TradeXV2Error:
                assert issubclass(obj, TradeXV2Error), f"{name} does not inherit TradeXV2Error"


@pytest.mark.architecture
class TestErrorCodeCoverage:
    def test_all_constants_referenced(self) -> None:
        from brokers.domain import error_codes, exceptions
        exc_source = Path(exceptions.__file__).read_text()
        defined = [name for name in dir(error_codes) if name.isupper() and not name.startswith("_")]
        for const_name in defined:
            value = getattr(error_codes, const_name)
            assert value in exc_source or const_name in exc_source, (
                f"Error code {const_name}={value!r} not referenced in exceptions.py"
            )


@pytest.mark.architecture
class TestNoDuplicateAll:
    def test_no_duplicate_all_entries(self) -> None:
        from collections import Counter
        init_files = [
            p for p in BROKERS_ROOT.rglob("__init__.py")
            if "venv" not in str(p) and "site-packages" not in str(p)
        ]
        violations = []
        for init_file in init_files:
            try:
                tree = ast.parse(init_file.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "__all__":
                            if isinstance(node.value, ast.List):
                                items = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]
                                dupes = [name for name, count in Counter(items).items() if count > 1]
                                if dupes:
                                    rel = init_file.relative_to(BROKERS_ROOT.parent)
                                    violations.append(f"{rel}: duplicate __all__: {dupes}")
        assert not violations, "Duplicate __all__ entries:\n" + "\n".join(violations)
