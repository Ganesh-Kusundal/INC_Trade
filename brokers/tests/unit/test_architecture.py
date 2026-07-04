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
    layer_dir = BROKERS_ROOT / "brokers" / layer
    if not layer_dir.exists():
        return []
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
    "domain": {"brokers.domain"},
    "core": {"brokers.core"},
    "utils": set(),
    "config": {"brokers.domain.exceptions", "brokers.config"},
    "ports": {"brokers.domain", "brokers.ports"},
    "services": {"brokers.domain", "brokers.ports", "brokers.utils", "brokers.services"},
    "resilience": {"brokers.domain", "brokers.resilience"},
    "infrastructure": {
        "brokers.domain",
        "brokers.infrastructure",
        "brokers.config",
        "brokers.core",
        "brokers.ports",
        "brokers.resilience",
    },
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
class TestPortStructure:
    ALL_PORTS = [
        "brokers.ports.auth.AuthPort",
        "brokers.ports.broker.BrokerGateway",
        "brokers.ports.clock.ClockPort",
        "brokers.ports.connection_lifecycle.ConnectionLifecyclePort",
        "brokers.ports.historical.HistoricalPort",
        "brokers.ports.instruments.InstrumentPort",
        "brokers.ports.market_data.MarketDataPort",
        "brokers.ports.order_execution.OrderExecutionPort",
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
            assert hasattr(brokers.ports, cls_name), f"{cls_name} not exported from brokers.ports"


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
        infra_dir = BROKERS_ROOT / "brokers" / "infrastructure"
        if not infra_dir.exists():
            pytest.skip("brokers/infrastructure/ directory does not exist")
        violations = []
        for filepath in infra_dir.rglob("*.py"):
            if "tests" in str(filepath) or "venv" in str(filepath):
                continue
            for lineno, module in _get_imports(filepath):
                if module.startswith("brokers.adapters") or module.startswith("brokers.services"):
                    rel = filepath.relative_to(BROKERS_ROOT.parent)
                    violations.append(f"  {rel}:{lineno}: imports {module}")
        assert not violations, (
            f"Infrastructure imports from adapters/services (forbidden):\n" + "\n".join(violations)
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
        assert not violations, f"Idempotency logic found outside core/:\n" + "\n".join(violations)


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
        assert not violations, f"Compat gateway files found (should be removed):\n" + "\n".join(
            violations
        )


@pytest.mark.architecture
class TestNoRawDictInDomain:
    """Domain entities must not have raw dict fields."""

    def test_domain_entities_no_dict_fields(self) -> None:
        domain_dir = BROKERS_ROOT / "brokers" / "domain"
        if not domain_dir.exists():
            pytest.skip("brokers/domain/ directory does not exist")
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
        assert not violations, f"Domain entities have raw dict fields:\n" + "\n".join(violations)


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
        "brokers/infrastructure/websocket_pool.py",  # Phase 5 target
        "brokers/infrastructure/totp_cooldown.py",  # Phase 5 target
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
        facade_path = BROKERS_ROOT / "brokers" / "services" / "broker_facade.py"
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
                violations.append(
                    f"  brokers/services/broker_facade.py:{node.lineno}: hasattr() call"
                )
        assert not violations, (
            f"hasattr() calls found in BrokerFacade (use ExtensionRegistry.resolve()):\n"
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
            f"Adapters importing from services (violates clean architecture):\n"
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

        from brokers.ports.order_execution import OrderExecutionPort
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


class TestBrokerGatewayContract:
    """All broker gateways must implement BrokerGateway protocol."""

    def test_dhan_gateway_implements_broker_gateway(self) -> None:
        # Use isinstance() with a mock instance since issubclass() doesn't work
        # with protocols that have properties
        import inspect

        from brokers.adapters.dhan.gateway import DhanGateway
        from brokers.ports.broker import BrokerGateway

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

    def test_upstox_gateway_implements_broker_gateway(self) -> None:
        # Use isinstance() with a mock instance since issubclass() doesn't work
        # with protocols that have properties
        import inspect

        from brokers.adapters.upstox.gateway import UpstoxGateway
        from brokers.ports.broker import BrokerGateway

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
            f"Adapters importing concrete HTTP clients (use HttpClientPort):\n"
            + "\n".join(violations)
        )


@pytest.mark.architecture
class TestServiceConstructorArgLimit:
    """Fitness Rule 2: public __init__ methods in services/ should have <= 5 parameters (excluding self)."""

    def test_service_constructor_arg_limit(self) -> None:
        import inspect
        import pkgutil
        import importlib

        services_dir = BROKERS_ROOT / "brokers" / "services"
        if not services_dir.exists():
            pytest.skip("brokers/services/ directory does not exist")

        violations = []
        for _, module_name, _ in pkgutil.walk_packages([str(services_dir)], prefix="brokers.services."):
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
                    p.name for p in sig.parameters.values()
                    if p.name != "self"
                    and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                ]
                if len(params) > 5:
                    violations.append(
                        f"  {obj.__module__}.{obj.__name__}.__init__ has {len(params)} parameters: {params} (limit: 5)"
                    )
        assert not violations, (
            f"Constructor parameter count violations found (limit: 5 parameters):\n"
            + "\n".join(violations)
        )

