"""Architecture boundary tests — V4 redesign enforcement.

These tests prevent regressions by ensuring:
1. Magic constants are centralized in domain/constants/
2. Adapters use Side enum, not string literals
3. Broker IDs use the centralized constants or BrokerID enum
4. Streaming layer uses SubscriptionPort protocol

All tests run in <1s and are marked @pytest.mark.architecture.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BROKERS_CORE_ROOT = Path(__file__).resolve().parents[2] / "src" / "brokers_core"
SRC_ROOT = BROKERS_CORE_ROOT


def _iter_python_files(root: Path) -> list[Path]:
    """Iterate Python files, excluding __pycache__ and tests."""
    return sorted(
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and "test" not in p.parts
    )


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── TestConstantCentralization ─────────────────────────────────────────


@pytest.mark.architecture
class TestConstantCentralization:
    """Magic constants must be centralized in domain/constants/.

    Adapters, services, and infrastructure should import constants from
    the centralized location rather than defining their own magic numbers.
    """

    # Reconnect delay constants that should be centralized
    RECONNECT_PATTERNS = [
        re.compile(r"reconnect_delay\s*[:=]\s*5\.0"),
        re.compile(r"max_reconnect_delay\s*[:=]\s*60\.0"),
    ]

    # TTL / lifetime constants that should be centralized
    TTL_PATTERNS = [
        re.compile(r"ttl_seconds\s*[:=]\s*86400"),
        re.compile(r"token_lifetime_seconds\s*[:=]\s*86400"),
        re.compile(r"ttl_seconds\s*[:=]\s*3600"),
    ]

    ALLOWED_FILES = {
        # The centralized constant definitions are allowed
        str(BROKERS_CORE_ROOT / "domain" / "constants" / "timeouts.py"),
        str(BROKERS_CORE_ROOT / "domain" / "cache_policy.py"),
        # Test files are allowed
    }

    def test_no_reconnect_constants_outside_constants_dir(self) -> None:
        """Reconnect delay constants must only be in domain/constants/."""
        violations: list[str] = []
        constants_dir = BROKERS_CORE_ROOT / "domain" / "constants"
        for path in _iter_python_files(SRC_ROOT):
            if str(path) in self.ALLOWED_FILES:
                continue
            # Skip the centralized location itself
            if constants_dir in path.parents or path.parent == constants_dir:
                continue
            # Skip test files
            if "test" in path.parts:
                continue
            content = _read_source(path)
            for pattern in self.RECONNECT_PATTERNS:
                if pattern.search(content):
                    rel = path.relative_to(SRC_ROOT.parent.parent)
                    violations.append(f"  {rel}: {pattern.pattern}")
        assert not violations, (
            "Reconnect constants found outside domain/constants/:\n"
            + "\n".join(violations)
            + "\nUse DEFAULT_RECONNECT_DELAY / DEFAULT_MAX_RECONNECT_DELAY from domain.constants.timeouts"
        )

    def test_no_ttl_constants_outside_constants_dir(self) -> None:
        """TTL/lifetime constants must only be in domain/constants/ or cache_policy."""
        violations: list[str] = []
        constants_dir = BROKERS_CORE_ROOT / "domain" / "constants"
        for path in _iter_python_files(SRC_ROOT):
            if str(path) in self.ALLOWED_FILES:
                continue
            if constants_dir in path.parents or path.parent == constants_dir:
                continue
            if "test" in path.parts:
                continue
            content = _read_source(path)
            for pattern in self.TTL_PATTERNS:
                if pattern.search(content):
                    rel = path.relative_to(SRC_ROOT.parent.parent)
                    violations.append(f"  {rel}: {pattern.pattern}")
        assert not violations, (
            "TTL constants found outside domain/constants/:\n"
            + "\n".join(violations)
            + "\nUse DEFAULT_TOKEN_LIFETIME_SECONDS / DEFAULT_IDEMPOTENCY_TTL_SECONDS from domain.constants.timeouts"
        )

    def test_constants_dir_exports_all_reconnect_symbols(self) -> None:
        """domain/constants/__init__.py must export all reconnect/TTL symbols."""
        from brokers_core.domain.constants import (
            DEFAULT_IDEMPOTENCY_TTL_SECONDS,
            DEFAULT_MAX_RECONNECT_DELAY,
            DEFAULT_RECONNECT_DELAY,
            DEFAULT_TOKEN_LIFETIME_SECONDS,
        )

        assert DEFAULT_RECONNECT_DELAY == 5.0
        assert DEFAULT_MAX_RECONNECT_DELAY == 60.0
        assert DEFAULT_TOKEN_LIFETIME_SECONDS == 86400
        assert DEFAULT_IDEMPOTENCY_TTL_SECONDS == 3600.0


# ── TestSideEnumEnforcement ────────────────────────────────────────────


@pytest.mark.architecture
class TestSideEnumEnforcement:
    """Adapters and order providers must use Side enum, not string literals.

    The string conversion pattern ``Side.BUY if side.upper() == "BUY"`` is
    forbidden in adapters — the caller should pass Side enum directly.
    """

    FORBIDDEN_PATTERNS = [
        re.compile(r'side\.upper\(\)\s*==\s*["\']BUY["\']'),
        re.compile(r'Side\.BUY\s+if\s+side\.upper\(\)'),
        re.compile(r'Side\.SELL\s+if\s+side\.upper\(\)'),
    ]

    ADAPTER_DIRS = [
        BROKERS_CORE_ROOT / "adapters",
    ]

    def test_adapters_do_not_convert_string_side(self) -> None:
        """Adapters must accept Side enum, not convert strings to Side."""
        violations: list[str] = []
        for adapter_dir in self.ADAPTER_DIRS:
            if not adapter_dir.exists():
                continue
            for path in _iter_python_files(adapter_dir):
                content = _read_source(path)
                for pattern in self.FORBIDDEN_PATTERNS:
                    if pattern.search(content):
                        rel = path.relative_to(SRC_ROOT.parent.parent)
                        violations.append(f"  {rel}: {pattern.pattern}")
        assert not violations, (
            "Adapters contain string-to-Side conversion (use Side enum directly):\n"
            + "\n".join(violations)
        )

    def test_order_provider_uses_side_enum_in_signature(self) -> None:
        """OrderProvider.place_order must declare side: Side, not side: str."""
        from brokers_core.ports.providers import OrderProvider
        import inspect

        sig = inspect.signature(OrderProvider.place_order)
        side_param = sig.parameters.get("side")
        assert side_param is not None, "OrderProvider.place_order must have 'side' parameter"

        # The annotation should reference Side, not str
        from brokers_core.domain.enums import Side
        annotation = side_param.annotation
        # With from __future__ import annotations, annotation is a string
        if isinstance(annotation, str):
            assert "Side" in annotation, (
                f"OrderProvider.place_order(side) should be typed as Side, got {annotation}"
            )
        else:
            assert annotation is Side or str(annotation) == "Side", (
                f"OrderProvider.place_order(side) should be typed as Side, got {annotation}"
            )

    def test_order_command_passes_side_enum(self) -> None:
        """OrderCommand.buy/sell must pass Side enum, not string literals."""
        from brokers_core.market.order import OrderCommand
        import inspect

        buy_src = inspect.getsource(OrderCommand.buy)
        sell_src = inspect.getsource(OrderCommand.sell)

        assert "Side.BUY" in buy_src, "OrderCommand.buy() must pass Side.BUY"
        assert "Side.SELL" in sell_src, "OrderCommand.sell() must pass Side.SELL"
        assert 'side="BUY"' not in buy_src, "OrderCommand.buy() must not pass string 'BUY'"
        assert 'side="SELL"' not in sell_src, "OrderCommand.sell() must not pass string 'SELL'"


# ── TestBrokerIdEnumEnforcement ────────────────────────────────────────


@pytest.mark.architecture
class TestBrokerIdEnumEnforcement:
    """Broker IDs must use BrokerID enum or centralized constants.

    Hardcoded string literals like ``"dhan"``, ``"upstox"``, ``"paper"``
    in adapter broker_id properties should use the BrokerID enum or the
    constants from domain/constants/broker_ids.py.
    """

    def test_broker_ids_constants_are_centralized(self) -> None:
        """domain/constants/broker_ids.py must define all broker ID strings."""
        from brokers_core.domain.constants.broker_ids import (
            DHAN_ID,
            PAPER_ID,
            UPSTOX_ID,
        )

        assert DHAN_ID == "dhan"
        assert UPSTOX_ID == "upstox"
        assert PAPER_ID == "paper"

    def test_broker_id_enum_values_match_constants(self) -> None:
        """BrokerID enum values must match the centralized constants."""
        from brokers_core.domain.enums import BrokerID
        from brokers_core.domain.constants.broker_ids import (
            DHAN_ID,
            PAPER_ID,
            UPSTOX_ID,
        )

        assert BrokerID.DHAN.value == DHAN_ID
        assert BrokerID.UPSTOX.value == UPSTOX_ID
        assert BrokerID.PAPER.value == PAPER_ID

    def test_adapters_import_broker_id_constants(self) -> None:
        """Adapters should import broker_id from centralized constants or enum.

        This is a soft check — adapters that still use string literals
        are flagged but not failed (to avoid blocking the migration).
        """
        violations: list[str] = []
        adapter_dir = BROKERS_CORE_ROOT / "adapters"
        if not adapter_dir.exists():
            pytest.skip("adapters/ directory does not exist")

        for path in _iter_python_files(adapter_dir):
            content = _read_source(path)
            # Check for broker_id = "dhan" / "upstox" / "paper" patterns
            for pattern in [
                re.compile(r'broker_id\s*[:=]\s*["\']dhan["\']'),
                re.compile(r'broker_id\s*[:=]\s*["\']upstox["\']'),
                re.compile(r'broker_id\s*[:=]\s*["\']paper["\']'),
            ]:
                if pattern.search(content):
                    rel = path.relative_to(SRC_ROOT.parent.parent)
                    violations.append(f"  {rel}: {pattern.pattern}")

        # Soft assertion: warn but don't fail (migration in progress)
        if violations:
            import warnings

            warnings.warn(
                f"Adapters with hardcoded broker_id strings ({len(violations)} found). "
                f"Use DHAN_ID / UPSTOX_ID / PAPER_ID from domain.constants.broker_ids:\n"
                + "\n".join(violations),
                stacklevel=1,
            )


# ── TestSubscriptionPortEnforcement ────────────────────────────────────


@pytest.mark.architecture
class TestSubscriptionPortEnforcement:
    """Streaming layer must use SubscriptionPort protocol.

    All subscription-capable classes should implement SubscriptionPort
    for a unified interface.
    """

    def test_subscription_port_exists(self) -> None:
        """SubscriptionPort must be defined in ports/subscription.py."""
        from brokers_core.ports.subscription import SubscriptionPort

        assert hasattr(SubscriptionPort, "subscribe")
        assert hasattr(SubscriptionPort, "unsubscribe")
        assert hasattr(SubscriptionPort, "is_subscribed")
        assert hasattr(SubscriptionPort, "active_count")

    def test_subscription_port_is_runtime_checkable(self) -> None:
        """SubscriptionPort must be @runtime_checkable."""
        from brokers_core.ports.subscription import SubscriptionPort

        assert getattr(SubscriptionPort, "_is_runtime_protocol", False), (
            "SubscriptionPort must be @runtime_checkable"
        )

    def test_streaming_router_implements_subscription_port(self) -> None:
        """StreamingRouter must implement SubscriptionPort."""
        from brokers_core.market.streaming_router import StreamingRouter
        from brokers_core.ports.subscription import SubscriptionPort

        assert issubclass(StreamingRouter, SubscriptionPort), (
            "StreamingRouter must inherit SubscriptionPort"
        )

    def test_subscription_manager_implements_subscription_port(self) -> None:
        """SubscriptionManager must implement SubscriptionPort."""
        from brokers_core.market.subscription_manager import SubscriptionManager
        from brokers_core.ports.subscription import SubscriptionPort

        assert issubclass(SubscriptionManager, SubscriptionPort), (
            "SubscriptionManager must inherit SubscriptionPort"
        )

    def test_subscription_port_callable_methods(self) -> None:
        """SubscriptionPort methods must be callable (not just properties)."""
        from brokers_core.ports.subscription import SubscriptionPort
        import inspect
        import types

        sig_subscribe = inspect.signature(SubscriptionPort.subscribe)
        sig_active_count = inspect.signature(SubscriptionPort.active_count)

        # active_count should be a method (returns int), not a property
        assert "self" in sig_subscribe.parameters
        assert "self" in sig_active_count.parameters
        # Verify active_count is a function, not a property descriptor
        assert not isinstance(SubscriptionPort.__dict__.get("active_count"), property), (
            "active_count must be a method, not a @property"
        )


# ── TestConnectedGuardEnforcement ──────────────────────────────────────


@pytest.mark.architecture
class TestConnectedGuardEnforcement:
    """Adapters must use ConnectedGuard mixin for connection checks."""

    def test_connected_guard_exists(self) -> None:
        """ConnectedGuard must be defined in adapters/base.py."""
        from brokers_core.adapters.base import ConnectedGuard

        assert hasattr(ConnectedGuard, "require_connected")
        assert hasattr(ConnectedGuard, "is_connected")

    def test_dhan_adapter_uses_connected_guard(self) -> None:
        """DhanAdapter must inherit ConnectedGuard."""
        from brokers_core.adapters.dhan.adapter import DhanAdapter
        from brokers_core.adapters.base import ConnectedGuard

        assert issubclass(DhanAdapter, ConnectedGuard), (
            "DhanAdapter must inherit ConnectedGuard"
        )

    def test_upstox_adapter_uses_connected_guard(self) -> None:
        """UpstoxAdapter must inherit ConnectedGuard."""
        from brokers_core.adapters.upstox.adapter import UpstoxAdapter
        from brokers_core.adapters.base import ConnectedGuard

        assert issubclass(UpstoxAdapter, ConnectedGuard), (
            "UpstoxAdapter must inherit ConnectedGuard"
        )

    def test_paper_adapter_uses_connected_guard(self) -> None:
        """PaperAdapter must inherit ConnectedGuard."""
        from brokers_core.adapters.paper.adapter import PaperAdapter
        from brokers_core.adapters.base import ConnectedGuard

        assert issubclass(PaperAdapter, ConnectedGuard), (
            "PaperAdapter must inherit ConnectedGuard"
        )


# ── TestOrderValidationService ─────────────────────────────────────────


@pytest.mark.architecture
class TestOrderValidationService:
    """OrderValidationService must consolidate validation logic."""

    def test_service_exists(self) -> None:
        """OrderValidationService must be defined in services/order_validator.py."""
        from brokers_core.services.order_validator import OrderValidationService

        assert hasattr(OrderValidationService, "validate")

    def test_service_is_configurable(self) -> None:
        """OrderValidationService must accept broker-specific constants."""
        from brokers_core.services.order_validator import OrderValidationService
        import inspect

        sig = inspect.signature(OrderValidationService.__init__)
        params = list(sig.parameters.keys())
        assert "derivative_segments" in params, "Must accept derivative_segments"
        assert "equity_only_products" in params, "Must accept equity_only_products"

    def test_dhan_uses_unified_validator(self) -> None:
        """Dhan PlaceOrderUseCase must use OrderValidationService."""
        from brokers_core.adapters.dhan.use_cases.place_order import PlaceOrderUseCase
        import inspect

        src = inspect.getsource(PlaceOrderUseCase)
        assert "OrderValidationService" in src, (
            "Dhan PlaceOrderUseCase must use OrderValidationService"
        )
        assert "validate_order" not in src, (
            "Dhan PlaceOrderUseCase must not directly import validate_order"
        )

    def test_upstox_uses_unified_validator(self) -> None:
        """Upstox PlaceOrderUseCase must use OrderValidationService."""
        from brokers_core.adapters.upstox.use_cases.place_order import PlaceOrderUseCase
        import inspect

        src = inspect.getsource(PlaceOrderUseCase)
        assert "OrderValidationService" in src, (
            "Upstox PlaceOrderUseCase must use OrderValidationService"
        )
        assert "validate_order" not in src, (
            "Upstox PlaceOrderUseCase must not directly import validate_order"
        )
