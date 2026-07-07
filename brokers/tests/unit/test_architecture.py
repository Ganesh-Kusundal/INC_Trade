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
BROKERS_CORE_ROOT = BROKERS_ROOT / "brokers-core" / "src" / "brokers_core"
INC_TRADE_ROOT = BROKERS_ROOT / "inc_trade"


def _list_modules(layer: str) -> list[Path]:
    layer_dir = BROKERS_ROOT / "brokers" / layer
    if not layer_dir.exists():
        return []
    return [p for p in layer_dir.rglob("*.py") if "tests" not in str(p)]


def _list_brokers_core_modules(layer: str) -> list[Path]:
    layer_dir = BROKERS_CORE_ROOT / layer
    if not layer_dir.exists():
        return []
    return [p for p in layer_dir.rglob("*.py") if "__pycache__" not in p.parts]


def _list_inc_trade_native_modules() -> list[Path]:
    native_dirs = ("services", "trading", "oms", "core", "utils")
    files: list[Path] = []
    for name in native_dirs:
        layer_dir = INC_TRADE_ROOT / name
        if layer_dir.exists():
            files.extend(
                p for p in layer_dir.rglob("*.py") if "__pycache__" not in p.parts
            )
    profiles = INC_TRADE_ROOT / "config" / "profiles"
    if profiles.exists():
        files.extend(p for p in profiles.rglob("*.py") if "__pycache__" not in p.parts)
    return files


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


def _get_brokers_core_imports(filepath: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith("brokers_core."):
                imports.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("brokers_core."):
                    imports.append((node.lineno, alias.name))
    return imports


def _get_inc_trade_imports(filepath: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith(("brokers.", "brokers_core.", "brokers.")):
                imports.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(("brokers.", "brokers_core.", "brokers.")):
                    imports.append((node.lineno, alias.name))
    return imports


BOUNDARY_RULES: dict[str, set[str]] = {
    "domain": {"brokers.domain"},
    "core": {"brokers.core"},
    "utils": set(),
    "config": {"brokers.domain.exceptions", "brokers.config"},
    "ports": {"brokers.domain", "brokers.ports", "brokers.extensions"},
    "services": {
        "brokers.domain",
        "brokers.ports",
        "brokers.utils",
        "brokers.services",
        "brokers.market",
        "brokers.adapters",
        "brokers.trading",
    },
    "resilience": {"brokers.domain", "brokers.resilience"},
    "infrastructure": {
        "brokers.domain",
        "brokers.infrastructure",
        "brokers.config",
        "brokers.core",
        "brokers.ports",
        "brokers.resilience",
    },
    "extensions": {"brokers.domain", "brokers.extensions"},
    "market": {
        "brokers.domain",
        "brokers.market",
        "brokers.ports",
        "brokers.extensions",
        "brokers.config",
    },
    "trading": {
        "brokers.domain",
        "brokers.trading",
        "brokers.ports",
    },
    "oms": {
        "brokers.domain",
        "brokers.trading",
        "brokers.oms",
        "brokers.ports",
        "brokers.services",
    },
}

BROKERS_CORE_BOUNDARY_RULES: dict[str, set[str]] = {
    "domain": {"brokers_core.domain"},
    "utils": set(),
    "config": {"brokers_core.domain.exceptions", "brokers_core.config"},
    "ports": {"brokers_core.domain", "brokers_core.ports", "brokers_core.extensions"},
    "resilience": {"brokers_core.domain", "brokers_core.resilience"},
    "extensions": {"brokers_core.domain", "brokers_core.extensions"},
    "market": {
        "brokers_core.domain",
        "brokers_core.market",
        "brokers_core.ports",
        "brokers_core.config",
        "brokers_core.extensions",
    },
    "infrastructure": {
        "brokers_core.domain",
        "brokers_core.infrastructure",
        "brokers_core.config",
        "brokers_core.ports",
        "brokers_core.resilience",
        "brokers_core.core",
    },
    "adapters": {
        "brokers_core.domain",
        "brokers_core.ports",
        "brokers_core.utils",
        "brokers_core.infrastructure",
        "brokers_core.config",
        "brokers_core.adapters",
        "brokers_core.resilience",
        "brokers_core.market",
    },
}

INC_TRADE_NATIVE_ALLOWED = {
    "brokers.domain",
    "brokers.ports",
    "brokers.services",
    "brokers.trading",
    "brokers.oms",
    "brokers.core",
    "brokers.utils",
    "brokers.config.profiles",
    "brokers.market",
    "brokers_core.utils",
}

INC_TRADE_NATIVE_BRIDGE_FILES = {
    "inc_trade/utils/idempotency_cache.py",
    "inc_trade/oms/idempotency.py",
}


@pytest.mark.architecture
class TestBoundaryRules:
    @pytest.mark.parametrize(
        "layer",
        [
            "domain",
            "core",
            "utils",
            "config",
            "ports",
            "services",
            "resilience",
            "infrastructure",
            "extensions",
            "market",
            "trading",
            "oms",
        ],
    )
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
class TestBrokersCoreBoundaryRules:
    @pytest.mark.parametrize(
        "layer",
        [
            "domain",
            "utils",
            "config",
            "ports",
            "resilience",
            "infrastructure",
            "extensions",
            "market",
            "adapters",
        ],
    )
    def test_brokers_core_layer_boundary(self, layer: str) -> None:
        allowed = BROKERS_CORE_BOUNDARY_RULES[layer]
        violations = []
        for filepath in _list_brokers_core_modules(layer):
            for lineno, module in _get_brokers_core_imports(filepath):
                if not any(module.startswith(a) for a in allowed):
                    rel = filepath.relative_to(BROKERS_ROOT)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            f"brokers_core layer '{layer}' has boundary violations:\n" + "\n".join(violations)
        )

    def test_market_does_not_import_infrastructure(self) -> None:
        violations = []
        for filepath in _list_brokers_core_modules("market"):
            for lineno, module in _get_brokers_core_imports(filepath):
                if module.startswith("brokers_core.infrastructure"):
                    rel = filepath.relative_to(BROKERS_ROOT)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            "market/ must not import infrastructure/:\n" + "\n".join(violations)
        )

    def test_extensions_does_not_import_market(self) -> None:
        violations = []
        for filepath in _list_brokers_core_modules("extensions"):
            for lineno, module in _get_brokers_core_imports(filepath):
                if module.startswith("brokers_core.market"):
                    rel = filepath.relative_to(BROKERS_ROOT)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            "extensions/ must not import market/:\n" + "\n".join(violations)
        )


@pytest.mark.architecture
class TestIncTradeNativeBoundaryRules:
    def test_native_modules_do_not_import_adapters(self) -> None:
        violations = []
        for filepath in _list_inc_trade_native_modules():
            for lineno, module in _get_inc_trade_imports(filepath):
                if module.startswith(("brokers_core.adapters", "brokers.adapters")):
                    if module.startswith("brokers.adapters.replay"):
                        continue
                    rel = filepath.relative_to(BROKERS_ROOT)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            "inc_trade native modules must not import adapters:\n" + "\n".join(violations)
        )

    def test_native_modules_import_allowed_prefixes(self) -> None:
        violations = []
        for filepath in _list_inc_trade_native_modules():
            rel = filepath.relative_to(BROKERS_ROOT)
            if str(rel) in INC_TRADE_NATIVE_BRIDGE_FILES:
                continue
            for lineno, module in _get_inc_trade_imports(filepath):
                if module.startswith("brokers."):
                    continue
                if not any(module.startswith(a) for a in INC_TRADE_NATIVE_ALLOWED):
                    rel = filepath.relative_to(BROKERS_ROOT)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            "inc_trade native modules have disallowed imports:\n" + "\n".join(violations)
        )


@pytest.mark.architecture
class TestPortStructure:
    ALL_PORTS = [
        "brokers.ports.auth.AuthPort",
        "brokers.ports.clock.ClockPort",
        "brokers.ports.connection_lifecycle.ConnectionLifecyclePort",
        "brokers.ports.historical.HistoricalPort",
        "brokers.ports.instruments.InstrumentPort",
        "brokers.ports.market_data.MarketDataPort",
        "brokers.ports.order_execution.OrderExecutionPort",
        "brokers.ports.order_guard.OrderGuardPort",
        "brokers.ports.portfolio.PortfolioPort",
        "brokers.ports.risk_manager.RiskManagerPort",
        "brokers.ports.streaming.StreamHandle",
        "brokers.ports.streaming.StreamingPort",
        "brokers.ports.token_store.TokenStorePort",
        "brokers.ports.capabilities.MarginProvider",
        "brokers.ports.capabilities.SuperOrderProvider",
        "brokers.ports.capabilities.ForeverOrderProvider",
        "brokers.ports.capabilities.KillSwitchProvider",
        "brokers.ports.capabilities.SliceOrderProvider",
        "brokers.ports.capabilities.NewsProvider",
        "brokers.ports.options.OptionsPort",
        "brokers.ports.extension_registry.ExtensionRegistryPort",
    ]

    @pytest.mark.parametrize("dotted_path", ALL_PORTS, ids=lambda p: p.rsplit(".", 1)[-1])
    def test_is_runtime_checkable_protocol(self, dotted_path: str) -> None:
        mod_path, cls_name = dotted_path.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        assert getattr(cls, "_is_protocol", False), f"{dotted_path} is not a Protocol"
        assert getattr(cls, "_is_runtime_protocol", False), (
            f"{dotted_path} is not @runtime_checkable"
        )

    def test_all_core_ports_exported(self) -> None:
        import brokers.ports

        for dotted_path in self.ALL_PORTS:
            cls_name = dotted_path.rsplit(".", 1)[-1]
            assert hasattr(brokers.ports, cls_name), (
                f"{cls_name} not exported from brokers.ports"
            )


@pytest.mark.architecture
class TestExceptionHierarchy:
    def test_order_state_error_inherits_tradexv2_error(self) -> None:
        from brokers.domain.exceptions import TradeXV2Error
        from brokers.domain.order_lifecycle import OrderStateError

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
        from brokers_core.domain import error_codes as it_error_codes
        import brokers_core.domain.exceptions as it_exceptions

        it_exc_source = Path(it_exceptions.__file__).read_text()
        defined = [
            name for name in dir(it_error_codes) if name.isupper() and not name.startswith("_")
        ]
        for const_name in defined:
            value = getattr(it_error_codes, const_name)
            assert value in it_exc_source or const_name in it_exc_source, (
                f"Error code {const_name}={value!r} not referenced in inc_trace/domain/exceptions.py"
            )


@pytest.mark.architecture
class TestNoDuplicateAll:
    def test_no_duplicate_all_entries(self) -> None:
        from collections import Counter

        init_files = [
            p
            for p in BROKERS_ROOT.rglob("__init__.py")
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
                                items = [
                                    elt.value
                                    for elt in node.value.elts
                                    if isinstance(elt, ast.Constant)
                                ]
                                dupes = [
                                    name for name, count in Counter(items).items() if count > 1
                                ]
                                if dupes:
                                    rel = init_file.relative_to(BROKERS_ROOT.parent)
                                    violations.append(f"{rel}: duplicate __all__: {dupes}")
        assert not violations, "Duplicate __all__ entries:\n" + "\n".join(violations)


@pytest.mark.architecture
class TestInfrastructureBoundary:
    """Infrastructure-specific architecture rules beyond boundary."""

    def test_infrastructure_does_not_import_adapters(self) -> None:
        """Infrastructure must never import adapters (outer layer)."""
        infra_dir = BROKERS_CORE_ROOT / "infrastructure"
        if not infra_dir.exists():
            pytest.skip("brokers_core/infrastructure/ directory does not exist")
        violations = []
        for filepath in infra_dir.rglob("*.py"):
            if "__pycache__" in filepath.parts:
                continue
            for lineno, module in _get_brokers_core_imports(filepath):
                if module.startswith("brokers_core.adapters"):
                    rel = filepath.relative_to(BROKERS_ROOT)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, "Infrastructure imports adapters (forbidden):\n" + "\n".join(
            violations
        )


@pytest.mark.architecture
class TestNoBrokerIdentifiersInDomain:
    """Broker-specific identifiers must not leak into domain, ports, or market."""

    BROKER_ID_PATTERNS = [
        "security_id",
        "dhan_id",
        "upstox_id",
        "exchange_token",
        "dhan_security",
    ]

    TARGET_DIRS = ["domain", "ports", "market"]

    # Known false positives: generic financial terms that happen to match patterns
    # Format: "relpath: pattern" — the relpath is relative to BROKERS_ROOT.parent
    ALLOWED_VIOLATIONS: set[str] = {
        "INC_Trade/brokers-core/src/brokers_core/domain/entities.py: security_id",
    }

    def test_no_broker_ids_in_domain_ports_market(self) -> None:
        violations = []
        for target in self.TARGET_DIRS:
            target_dir = BROKERS_CORE_ROOT / target
            if not target_dir.exists():
                continue
            for filepath in target_dir.rglob("*.py"):
                if "tests" in str(filepath) or "venv" in str(filepath):
                    continue
                content = filepath.read_text()
                for pattern in self.BROKER_ID_PATTERNS:
                    if pattern in content:
                        rel = filepath.relative_to(BROKERS_ROOT.parent)
                        violation = f"{rel}: {pattern}"
                        if violation not in self.ALLOWED_VIOLATIONS:
                            violations.append(f"  {rel}: contains '{pattern}'")
        assert not violations, (
            "Broker-specific identifiers found in domain/ports/market:\n" + "\n".join(violations)
        )


@pytest.mark.architecture
class TestSingleIdempotencyImplementation:
    """Idempotency logic must exist only in core/order_result_cache.py."""

    def test_no_adapters_idempotency_modules(self) -> None:
        adapter_dir = BROKERS_ROOT / "brokers" / "adapters"
        if not adapter_dir.exists():
            pytest.skip("brokers/adapters/ directory does not exist")
        violations = []
        for filepath in adapter_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            if filepath.name == "__init__.py":
                continue
            if "idempoten" in filepath.name.lower():
                rel = filepath.relative_to(BROKERS_ROOT.parent)
                violations.append(f"  {rel}: idempotency logic outside core/")
        assert not violations, "Idempotency logic found outside core/:\n" + "\n".join(violations)


@pytest.mark.architecture
class TestNoCompatGateways:
    """No compat_gateway.py files should exist (deprecated pattern)."""

    def test_no_compat_gateway_files(self) -> None:
        violations = []
        for filepath in BROKERS_ROOT.rglob("compat_gateway.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            rel = filepath.relative_to(BROKERS_ROOT)
            violations.append(f"  {rel}")
        assert not violations, "Compat gateway files found (should be removed):\n" + "\n".join(
            violations
        )


@pytest.mark.architecture
class TestNoRawDictInDomain:
    """Domain entities must not have raw dict fields."""

    def test_domain_entities_no_dict_fields(self) -> None:
        domain_dir = BROKERS_CORE_ROOT / "domain"
        if not domain_dir.exists():
            pytest.skip("brokers_core/domain/ directory does not exist")
        violations = []
        for filepath in domain_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            try:
                tree = ast.parse(filepath.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.AnnAssign) and isinstance(node.annotation, ast.Name):
                    if node.annotation.id == "dict":
                        rel = filepath.relative_to(BROKERS_ROOT)
                        violations.append(f"  {rel}:{node.lineno}: raw dict field")
        assert not violations, "Domain entities have raw dict fields:\n" + "\n".join(violations)


@pytest.mark.architecture
class TestSingleEndpointAuthority:
    """No adapters/dhan/endpoints.py file should exist."""

    def test_no_dhan_endpoints_file(self) -> None:
        dhan_dir = BROKERS_ROOT / "brokers" / "adapters" / "dhan"
        if not dhan_dir.exists():
            pytest.skip("brokers/adapters/dhan/ directory does not exist")
        endpoints_file = dhan_dir / "endpoints.py"
        assert not endpoints_file.exists(), (
            f"Found {endpoints_file.relative_to(BROKERS_ROOT.parent)}: "
            f"endpoint authority should be in a single location"
        )


@pytest.mark.architecture
class TestNoGlobalSingletons:
    """No class-level _instances dicts outside allowed definitions."""

    ALLOWED_PATTERNS = [
        "brokers/infrastructure/totp_cooldown.py",
        "inc_trade/infrastructure/totp_cooldown.py",
        "brokers-core/src/brokers_core/infrastructure/registry.py",
        "brokers-core/src/brokers_core/infrastructure/totp_cooldown.py",
    ]

    def test_no_class_level_instances(self) -> None:
        violations = []
        for filepath in BROKERS_ROOT.rglob("*.py"):
            if "venv" in str(filepath) or "site-packages" in str(filepath):
                continue
            if "test_" in filepath.name:
                continue
            if "archive" in filepath.parts:
                continue
            try:
                tree = ast.parse(filepath.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if (
                        isinstance(item, ast.AnnAssign)
                        and isinstance(item.target, ast.Name)
                        and item.target.id == "_instances"
                    ):
                        rel = filepath.relative_to(BROKERS_ROOT)
                        if str(rel) not in self.ALLOWED_PATTERNS:
                            violations.append(
                                f"  {rel}:{item.lineno}: annotated class-level _instances"
                            )
                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == "_instances":
                                rel = filepath.relative_to(BROKERS_ROOT)
                                if str(rel) not in self.ALLOWED_PATTERNS:
                                    violations.append(
                                        f"  {rel}:{item.lineno}: class-level _instances"
                                    )
        assert not violations, (
            f"Global singleton _instances found (allowed: {self.ALLOWED_PATTERNS}):\n"
            + "\n".join(violations)
        )


@pytest.mark.architecture
class TestNoHasattrOnGateway:
    """No hasattr() in BrokerFacade for capability detection."""

    def test_no_hasattr_in_broker_facade(self) -> None:
        facade_path = INC_TRADE_ROOT / "services" / "broker_facade.py"
        if not facade_path.exists():
            pytest.skip("broker_facade.py not found")
        tree = ast.parse(facade_path.read_text())
        violations = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(getattr(node, "func", None), ast.Name)
                and node.func.id == "hasattr"
            ):
                rel = facade_path.relative_to(BROKERS_ROOT)
                violations.append(f"  {rel}:{node.lineno}: hasattr() call")
        assert not violations, (
            "hasattr() calls found in BrokerFacade (use ExtensionRegistry.resolve()):\n"
            + "\n".join(violations)
        )


@pytest.mark.architecture
class TestNoAdapterImportsService:
    """Adapters must not import from services/."""

    ALLOWED_PATTERNS: list[str] = []

    def test_adapters_not_import_services(self) -> None:
        adapter_dir = BROKERS_ROOT / "brokers" / "adapters"
        if not adapter_dir.exists():
            pytest.skip("brokers/adapters/ directory does not exist")
        violations = []
        for filepath in adapter_dir.rglob("*.py"):
            if "test_" in filepath.name or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.services"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    if str(rel) not in self.ALLOWED_PATTERNS:
                        violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            "Adapters importing from services (violates clean architecture):\n"
            + "\n".join(violations)
        )


@pytest.mark.architecture
class TestCapabilityConstants:
    """All capability constants must be defined in domain/constants/capabilities.py."""

    def test_all_capabilities_in_all_caps(self) -> None:
        from brokers.domain.constants.capabilities import ALL_CAPABILITIES

        for cap in ALL_CAPABILITIES:
            assert cap.islower() or cap.isupper(), f"Capability {cap} should be in ALL_CAPS"

    def test_no_duplicate_capabilities(self) -> None:
        from brokers.domain.constants.capabilities import ALL_CAPABILITIES

        assert len(ALL_CAPABILITIES) == len(set(ALL_CAPABILITIES)), "Duplicate capabilities found"


class TestServiceLayer:
    """Domain services must depend only on ports, not on adapters or infrastructure."""

    def test_order_service_depends_only_on_ports(self) -> None:
        import inspect

        from brokers.services.order_service import OrderService

        # Check that OrderService only imports from allowed modules
        source = inspect.getsource(OrderService)
        disallowed_imports = [
            "adapters",
            "infrastructure",
            "resilience",
        ]
        for disallowed in disallowed_imports:
            assert disallowed not in source, f"OrderService should not import from {disallowed}"

    def test_historical_service_depends_only_on_ports(self) -> None:
        import inspect

        from brokers.services.historical_service import HistoricalService

        source = inspect.getsource(HistoricalService)
        disallowed_imports = [
            "adapters",
            "infrastructure",
            "resilience",
        ]
        for disallowed in disallowed_imports:
            assert disallowed not in source, (
                f"HistoricalService should not import from {disallowed}"
            )


class TestGatewayContract:
    """All broker gateways must implement the required port properties."""

    def test_dhan_gateway_has_required_ports(self) -> None:
        from brokers.adapters.dhan.gateway import DhanGateway

        assert hasattr(DhanGateway, "broker_id"), "DhanGateway must have broker_id property"
        assert hasattr(DhanGateway, "capabilities"), "DhanGateway must have capabilities property"
        assert hasattr(DhanGateway, "orders"), "DhanGateway must have orders property"
        assert hasattr(DhanGateway, "market_data"), "DhanGateway must have market_data property"
        assert hasattr(DhanGateway, "portfolio"), "DhanGateway must have portfolio property"
        assert hasattr(DhanGateway, "historical"), "DhanGateway must have historical property"
        assert hasattr(DhanGateway, "instruments"), "DhanGateway must have instruments property"
        assert hasattr(DhanGateway, "auth"), "DhanGateway must have auth property"
        assert hasattr(DhanGateway, "streaming"), "DhanGateway must have streaming property"
        assert hasattr(DhanGateway, "extensions"), "DhanGateway must have extensions property"

    def test_upstox_gateway_has_required_ports(self) -> None:
        from brokers.adapters.upstox.gateway import UpstoxGateway

        assert hasattr(UpstoxGateway, "broker_id"), "UpstoxGateway must have broker_id property"
        assert hasattr(UpstoxGateway, "capabilities"), (
            "UpstoxGateway must have capabilities property"
        )
        assert hasattr(UpstoxGateway, "orders"), "UpstoxGateway must have orders property"
        assert hasattr(UpstoxGateway, "market_data"), "UpstoxGateway must have market_data property"
        assert hasattr(UpstoxGateway, "portfolio"), "UpstoxGateway must have portfolio property"
        assert hasattr(UpstoxGateway, "historical"), "UpstoxGateway must have historical property"
        assert hasattr(UpstoxGateway, "instruments"), "UpstoxGateway must have instruments property"
        assert hasattr(UpstoxGateway, "auth"), "UpstoxGateway must have auth property"
        assert hasattr(UpstoxGateway, "streaming"), "UpstoxGateway must have streaming property"
        assert hasattr(UpstoxGateway, "extensions"), "UpstoxGateway must have extensions property"


class TestHttpClientPort:
    """Adapters must import HttpClientPort, not concrete implementations.

    Known violations are ALLOWED (P2 target — Task 6.4: Inject HttpClientPort
    into all Dhan/Upstox adapters). New adapters must NOT add new violations.
    """

    FORBIDDEN_PREFIXES = ("brokers.infrastructure.http",)

    # Factory files that legitimately create/extend ResilientHttpClient.
    # Consumer adapters use HttpClientPort via constructor injection.
    ALLOWED_PATTERNS = [
        # Factory: creates the concrete ResilientHttpClient instance
        "INC_Trade/brokers/adapters/dhan/http_client.py",
        "INC_Trade/brokers/adapters/upstox/http_client.py",
        # Subclass: extends ResilientHttpClient
        "INC_Trade/brokers/adapters/upstox/http.py",
    ]

    def test_adapters_not_import_concrete_http(self) -> None:
        adapter_dir = BROKERS_ROOT / "brokers" / "adapters"
        if not adapter_dir.exists():
            pytest.skip("brokers/adapters/ directory does not exist")
        violations = []
        for filepath in adapter_dir.rglob("*.py"):
            if "test_" in filepath.name or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith(self.FORBIDDEN_PREFIXES):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    if str(rel) not in self.ALLOWED_PATTERNS:
                        violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            "Adapters importing concrete HTTP clients (use HttpClientPort):\n"
            + "\n".join(violations)
        )


@pytest.mark.architecture
class TestInstrumentRegistryInvariants:
    """Verify InstrumentRegistry guarantees one Instrument per composite key."""

    def test_instrument_registry_single_instance(self) -> None:
        """InstrumentRegistry.get_or_create must return the same object for the same key."""
        from brokers.market.instrument_registry import InstrumentRegistry

        registry = InstrumentRegistry()
        factory_calls = 0

        def factory() -> object:
            nonlocal factory_calls
            factory_calls += 1
            return object()

        inst1 = registry.get_or_create("NSE:RELIANCE", factory)
        inst2 = registry.get_or_create("NSE:RELIANCE", factory)

        assert inst1 is inst2, "get_or_create must return the same instance for an existing key"
        assert factory_calls == 1, "factory must be called exactly once per key"

    def test_instrument_registry_different_keys(self) -> None:
        """Different composite keys must produce different instances."""
        from brokers.market.instrument_registry import InstrumentRegistry

        registry = InstrumentRegistry()
        inst1 = registry.get_or_create("NSE:RELIANCE", object)
        inst2 = registry.get_or_create("NSE:TCS", object)

        assert inst1 is not inst2, "Different keys must produce different instances"

    def test_instrument_registry_get(self) -> None:
        """Registry.get must return None for missing keys."""
        from brokers.market.instrument_registry import InstrumentRegistry

        registry = InstrumentRegistry()
        assert registry.get("NSE:MISSING") is None

    def test_instrument_registry_get_all(self) -> None:
        """Registry.get_all must return a snapshot dict."""
        from brokers.market.instrument_registry import InstrumentRegistry

        registry = InstrumentRegistry()
        registry.get_or_create("NSE:RELIANCE", object)
        registry.get_or_create("NSE:TCS", object)

        snapshot = registry.get_all()
        assert len(snapshot) == 2
        assert "NSE:RELIANCE" in snapshot
        assert "NSE:TCS" in snapshot

    def test_instrument_registry_thread_safety(self) -> None:
        """Concurrent get_or_create calls must not cause race conditions."""
        import concurrent.futures

        from brokers.market.instrument_registry import InstrumentRegistry

        registry = InstrumentRegistry()
        n_threads = 10
        results: list[object | None] = [None] * n_threads

        def get_or_create(idx: int) -> object:
            return registry.get_or_create("NSE:RELIANCE", object)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = [executor.submit(get_or_create, i) for i in range(n_threads)]
            resolved = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All threads must get the exact same instance
        first = resolved[0]
        for inst in resolved[1:]:
            assert inst is first, "Thread safety violation: different instances for same key"

        # Registry should contain exactly one entry
        assert len(registry) == 1


@pytest.mark.architecture
class TestExtensionPackage:
    """Extensions must not import from adapters; protocols must be runtime_checkable."""

    EXTENSION_PROTOCOLS = [
        "brokers.extensions.base.Extension",
        "brokers.extensions.depth.DepthExtension",
    ]

    def test_extensions_not_import_adapters(self) -> None:
        """Extensions package must never import from adapters."""
        ext_dir = BROKERS_ROOT / "brokers" / "extensions"
        if not ext_dir.exists():
            pytest.skip("brokers/extensions/ directory does not exist")
        violations = []
        for filepath in _list_modules("extensions"):
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.adapters"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, "Extensions importing from adapters (forbidden):\n" + "\n".join(
            violations
        )

    @pytest.mark.parametrize(
        "dotted_path",
        EXTENSION_PROTOCOLS,
        ids=lambda p: p.rsplit(".", 1)[-1],
    )
    def test_is_runtime_checkable_protocol(self, dotted_path: str) -> None:
        """All extension protocols must be @runtime_checkable Protocols."""
        mod_path, cls_name = dotted_path.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        assert getattr(cls, "_is_protocol", False), f"{dotted_path} is not a Protocol"
        assert getattr(cls, "_is_runtime_protocol", False), (
            f"{dotted_path} is not @runtime_checkable"
        )

    def test_all_extension_protocols_exported(self) -> None:
        """All extension protocols must be exported from brokers.extensions."""
        import brokers.extensions

        for dotted_path in self.EXTENSION_PROTOCOLS:
            cls_name = dotted_path.rsplit(".", 1)[-1]
            assert hasattr(brokers.extensions, cls_name), (
                f"{cls_name} not exported from brokers.extensions"
            )


@pytest.mark.architecture
class TestServiceConstructorArgLimit:
    """Fitness Rule 2: public __init__ methods in services/ should have <= 5 parameters (excluding self)."""

    def test_service_constructor_arg_limit(self) -> None:
        import importlib
        import inspect
        import pkgutil

        services_dir = BROKERS_ROOT / "brokers" / "services"
        if not services_dir.exists():
            pytest.skip("brokers/services/ directory does not exist")

        violations = []
        for _, module_name, _ in pkgutil.walk_packages(
            [str(services_dir)], prefix="brokers.services."
        ):
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if obj.__module__ != module_name:
                    continue
                if "test" in name.lower() or name.startswith("_"):
                    continue
                # Skip dataclasses (value objects / DTOs)
                import dataclasses

                if dataclasses.is_dataclass(obj):
                    continue
                init = getattr(obj, "__init__", None)
                if init is None:
                    continue
                # Skip basic object init or parent-inherited init if not overridden
                if init is object.__init__:
                    continue
                try:
                    sig = inspect.signature(init)
                except ValueError:
                    continue
                # Exclude self and variadic args (*args, **kwargs)
                params = [
                    p.name
                    for p in sig.parameters.values()
                    if p.name != "self"
                    and p.kind
                    not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                ]
                if len(params) > 5:
                    violations.append(
                        f"  {obj.__module__}.{obj.__name__}.__init__ has {len(params)} parameters: {params} (limit: 5)"
                    )
        assert not violations, (
            "Constructor parameter count violations found (limit: 5 parameters):\n"
            + "\n".join(violations)
        )


@pytest.mark.architecture
class TestMarketLayer:
    """Market layer must not import adapters or trading."""

    def test_market_does_not_import_adapters(self) -> None:
        """Market must never import from adapters (outer layer)."""
        market_dir = BROKERS_ROOT / "brokers" / "market"
        if not market_dir.exists():
            pytest.skip("brokers/market/ directory does not exist")
        violations = []
        for filepath in market_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.adapters") or module.startswith("brokers.trading"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, "Market imports from adapters or trading (forbidden):\n" + "\n".join(
            violations
        )

    def test_market_does_not_import_services(self) -> None:
        """Market must not import from services (service layer depends on market, not vice versa)."""
        market_dir = BROKERS_ROOT / "brokers" / "market"
        if not market_dir.exists():
            pytest.skip("brokers/market/ directory does not exist")
        violations = []
        for filepath in market_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.services"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, "Market imports from services (forbidden):\n" + "\n".join(violations)


@pytest.mark.architecture
class TestTradingLayer:
    """Trading layer must not import market or adapters."""

    def test_trading_does_not_import_market(self) -> None:
        """Trading must never import from market (lateral dependency)."""
        trading_dir = BROKERS_ROOT / "brokers" / "trading"
        if not trading_dir.exists():
            pytest.skip("brokers/trading/ directory does not exist")
        violations = []
        for filepath in trading_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.market") or module.startswith("brokers.adapters"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, "Trading imports from market or adapters (forbidden):\n" + "\n".join(
            violations
        )

    def test_trading_does_not_import_services(self) -> None:
        """Trading must not import from services (services depend on trading)."""
        trading_dir = BROKERS_ROOT / "brokers" / "trading"
        if not trading_dir.exists():
            pytest.skip("brokers/trading/ directory does not exist")
        violations = []
        for filepath in trading_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.services"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, "Trading imports from services (forbidden):\n" + "\n".join(
            violations
        )
