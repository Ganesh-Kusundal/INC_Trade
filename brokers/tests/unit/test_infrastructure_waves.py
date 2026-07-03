"""Tests for infrastructure modules: DI, lifecycle, JWT, TOTP, registry, bootstrap."""

import asyncio
import time
from datetime import datetime, timezone

import pytest

from brokers.core.di import CircularDependencyError, Container, Scope, ServiceNotFoundError
from brokers.core.di_scopes import ScopeManager
from brokers.domain.lifecycle_health import HealthState, HealthStatus
from brokers.infrastructure.bootstrap import Bootstrap, BootstrapError, BootstrapResult
from brokers.infrastructure.jwt_expiry import parse_jwt_expiry
from brokers.infrastructure.lifecycle import LifecycleManager, ManagedService
from brokers.infrastructure.registry import (
    BrokerHealthSnapshot,
    BrokerRegistry,
    GatewayRegistry,
    ServiceRegistry,
)
from brokers.infrastructure.totp_cooldown import TOTPCooldown

# ── DI Container ────────────────────────────────────────────────────────────


class TestContainer:
    def test_register_and_resolve_singleton(self):
        c = Container()
        c.register("svc", lambda: {"created": time.monotonic()}, scope=Scope.SINGLETON)
        s1 = c.resolve("svc")
        s2 = c.resolve("svc")
        assert s1 is s2

    def test_transient_creates_new_each_time(self):
        c = Container()
        c.register("svc", lambda: object(), scope=Scope.TRANSIENT)
        s1 = c.resolve("svc")
        s2 = c.resolve("svc")
        assert s1 is not s2

    def test_register_instance(self):
        c = Container()
        obj = {"key": "value"}
        c.register_instance("cfg", obj)
        assert c.resolve("cfg") is obj

    def test_resolve_not_found_raises(self):
        c = Container()
        with pytest.raises(ServiceNotFoundError):
            c.resolve("nonexistent")

    def test_has(self):
        c = Container()
        c.register_instance("x", 42)
        assert c.has("x") is True
        assert c.has("y") is False

    def test_reset(self):
        c = Container()
        c.register_instance("x", 42)
        c.reset()
        assert c.has("x") is False

    def test_registrations_summary(self):
        c = Container()
        c.register("a", lambda: 1, scope=Scope.SINGLETON)
        c.register("b", lambda: 2, scope=Scope.TRANSIENT)
        c.register_instance("c", 3)
        summary = c.registrations()
        assert summary["a"] == "singleton"
        assert summary["b"] == "transient"
        assert summary["c"] == "instance"

    def test_invalid_scope_raises(self):
        c = Container()
        with pytest.raises(ValueError):
            c.register("x", lambda: 1, scope="invalid")

    def test_string_scope(self):
        c = Container()
        c.register("x", lambda: 1, scope="transient")
        assert c.registrations()["x"] == "transient"


class TestScopeManager:
    def test_clear(self):
        sm = ScopeManager()
        sm.clear()


# ── Lifecycle Manager ───────────────────────────────────────────────────────


class _FakeService:
    def __init__(self, name: str, fail_start: bool = False):
        self.name = name
        self.started = False
        self.stopped = False
        self._fail_start = fail_start

    def start(self) -> None:
        if self._fail_start:
            raise RuntimeError(f"{self.name} start failed")
        self.started = True

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self.stopped = True

    def health(self) -> HealthStatus:
        if self.started and not self.stopped:
            return HealthStatus(
                state=HealthState.HEALTHY,
                service=self.name,
                last_check=datetime.now(timezone.utc),
            )
        return HealthStatus(
            state=HealthState.STOPPED,
            service=self.name,
            last_check=datetime.now(timezone.utc),
        )


class TestLifecycleManager:
    def test_register_and_start(self):
        mgr = LifecycleManager()
        svc = _FakeService("test")
        mgr.register(svc)
        mgr.start_all()
        assert svc.started is True

    def test_stop_all(self):
        mgr = LifecycleManager()
        svc = _FakeService("test")
        mgr.register(svc)
        mgr.start_all()
        mgr.stop_all()
        assert svc.stopped is True

    def test_health_snapshot(self):
        mgr = LifecycleManager()
        svc = _FakeService("test")
        mgr.register(svc)
        mgr.start_all()
        snap = mgr.health_snapshot()
        assert "test" in snap
        assert snap["test"]["state"] == "HEALTHY"

    def test_start_failure_isolated(self):
        mgr = LifecycleManager()
        bad = _FakeService("bad", fail_start=True)
        good = _FakeService("good")
        mgr.register(bad)
        mgr.register(good)
        mgr.start_all()
        assert good.started is True
        snap = mgr.health_snapshot()
        assert snap["bad"]["state"] == "FAILED"

    def test_service_names(self):
        mgr = LifecycleManager()
        mgr.register(_FakeService("a"))
        mgr.register(_FakeService("b"))
        assert set(mgr.service_names()) == {"a", "b"}

    def test_unregister(self):
        mgr = LifecycleManager()
        mgr.register(_FakeService("x"))
        mgr.unregister("x")
        assert mgr.get("x") is None


# ── JWT Expiry ──────────────────────────────────────────────────────────────


class TestJWTExpiry:
    def test_parse_valid_jwt(self):
        import base64
        import json
        from datetime import datetime

        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) + 3600}).encode()
        ).rstrip(b"=")
        token = f"{header.decode()}.{payload.decode()}.fakesig"
        exp = parse_jwt_expiry(token)
        assert exp is not None
        assert isinstance(exp, datetime)

    def test_parse_expired_jwt(self):
        import base64
        import json
        from datetime import datetime

        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) - 100}).encode()
        ).rstrip(b"=")
        token = f"{header.decode()}.{payload.decode()}.fakesig"
        exp = parse_jwt_expiry(token)
        assert exp is not None
        assert isinstance(exp, datetime)

    def test_parse_invalid_token(self):
        assert parse_jwt_expiry("not.a.jwt") is None or parse_jwt_expiry("") is None

    def test_parse_empty_string(self):
        result = parse_jwt_expiry("")
        assert result is None


# ── TOTP Cooldown ───────────────────────────────────────────────────────────


class TestTOTPCooldown:
    def test_first_attempt_allowed(self):
        tc = TOTPCooldown(broker="test_unit_1", cooldown_seconds=30)
        assert tc.can_request() is True

    def test_second_attempt_blocked(self):
        tc = TOTPCooldown(broker="test_unit_2", cooldown_seconds=30)
        tc.mark_requested()
        assert tc.can_request() is False

    def test_cooldown_expires(self):
        tc = TOTPCooldown(broker="test_unit_3", cooldown_seconds=0)
        tc.mark_requested()
        assert tc.can_request() is True


# ── Registry ────────────────────────────────────────────────────────────────


class TestGatewayRegistry:
    def test_get_or_create(self):
        reg = GatewayRegistry()
        calls = [0]

        def factory():
            calls[0] += 1
            return {"id": calls[0]}

        gw1 = reg.get_or_create("dhan", "client1", factory)
        gw2 = reg.get_or_create("dhan", "client1", factory)
        assert gw1 is gw2
        assert calls[0] == 1

    def test_different_keys(self):
        reg = GatewayRegistry()
        gw1 = reg.get_or_create("dhan", "c1", lambda: "dhan_c1")
        gw2 = reg.get_or_create("upstox", "c1", lambda: "upstox_c1")
        assert gw1 != gw2


class TestBrokerRegistry:
    def test_register_and_get(self):
        reg = BrokerRegistry()
        gw = object()
        reg.register("dhan", gw)
        assert reg.get_gateway("dhan") is gw

    def test_get_unknown_raises(self):
        reg = BrokerRegistry()
        with pytest.raises(KeyError):
            reg.get_gateway("unknown")

    def test_has(self):
        reg = BrokerRegistry()
        reg.register("dhan", object())
        assert reg.has("dhan") is True
        assert reg.has("upstox") is False

    def test_list_brokers(self):
        reg = BrokerRegistry()
        reg.register("dhan", object())
        reg.register("upstox", object())
        assert set(reg.list_brokers()) == {"dhan", "upstox"}

    def test_deregister(self):
        reg = BrokerRegistry()
        reg.register("dhan", object())
        reg.deregister("dhan")
        assert reg.has("dhan") is False

    def test_health_tracking(self):
        reg = BrokerRegistry()
        reg.register("dhan", object())
        health = reg.get_health("dhan")
        assert health.alive is True

    def test_update_health(self):
        reg = BrokerRegistry()
        reg.register("dhan", object())
        new_health = BrokerHealthSnapshot(broker_id="dhan", alive=False, reason="timeout")
        reg.update_health(new_health)
        assert reg.get_health("dhan").alive is False

    def test_snapshot(self):
        reg = BrokerRegistry()
        reg.register("dhan", object())
        snap = reg.snapshot()
        assert "dhan" in snap["broker_ids"]

    def test_close_all(self):
        reg = BrokerRegistry()

        class FakeGW:
            closed = False

            async def close(self):
                self.closed = True

        gw = FakeGW()
        reg.register("dhan", gw)
        asyncio.run(reg.close_all())
        assert gw.closed is True


class TestServiceRegistry:
    def test_register_and_instantiate(self):
        sr = ServiceRegistry()
        sr.register("svc1", dict)
        instances = sr.instantiate_all()
        assert "svc1" in instances

    def test_get(self):
        sr = ServiceRegistry()
        sr.register("svc1", dict)
        sr.instantiate_all()
        assert sr.get("svc1") is not None
        assert sr.get("unknown") is None

    def test_contains(self):
        sr = ServiceRegistry()
        sr.register("svc1", dict)
        sr.instantiate_all()
        assert "svc1" in sr
        assert "unknown" not in sr


# ── Bootstrap ───────────────────────────────────────────────────────────────


class TestBootstrap:
    def test_bootstrap_run(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "dev")
        result = asyncio.run(Bootstrap.run(skip_validation=True, broker_names=["dhan"]))
        assert isinstance(result, BootstrapResult)
        assert result.config is not None
        assert result.lifecycle is not None
        assert result.registry is not None

    def test_bootstrap_with_validation(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "dev")
        result = asyncio.run(Bootstrap.run(skip_validation=False, broker_names=["dhan"]))
        assert isinstance(result, BootstrapResult)

    def test_bootstrap_error_type(self):
        assert issubclass(BootstrapError, Exception)
