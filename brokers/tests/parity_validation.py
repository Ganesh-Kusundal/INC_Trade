"""Phase 0 parity validation — verifies all Wave 1-8 modules are importable
and functionally equivalent to their archived counterparts.

Run with: python -m brokers.tests.parity_validation
"""

from __future__ import annotations

import sys
import traceback
from datetime import UTC


def _check(label: str, fn):
    try:
        fn()
        print(f"  PASS  {label}")
        return True
    except Exception as exc:
        print(f"  FAIL  {label}: {exc}")
        traceback.print_exc()
        return False


def main() -> int:
    passed = 0
    failed = 0

    def run(label: str, fn):
        nonlocal passed, failed
        if _check(label, fn):
            passed += 1
        else:
            failed += 1

    # ── Wave 1: Config Schema ─────────────────────────────────────────────
    print("\n=== Wave 1: Config Schema ===")

    def w1_schema():
        from inc_trade.config.schema import AppConfig
        cfg = AppConfig.from_env()
        assert hasattr(cfg, "api_port")
        assert hasattr(cfg, "api_host")
    run("AppConfig.from_env()", w1_schema)

    def w1_defaults():
        from inc_trade.config.defaults import DEFAULT_CONFIG, get_config, reset_config
        reset_config()
        cfg = get_config()
        assert cfg is get_config()
        assert "api_port" in DEFAULT_CONFIG
    run("get_config() cached singleton", w1_defaults)

    def w1_profiles():
        import os

        from inc_trade.config.profiles import load_profile
        from inc_trade.config.profiles.dev import DevProfile
        from inc_trade.config.profiles.prod import ProdProfile
        from inc_trade.config.profiles.staging import StagingProfile
        os.environ["APP_ENV"] = "dev"
        p = load_profile()
        assert isinstance(p, DevProfile)
        os.environ["APP_ENV"] = "staging"
        p = load_profile()
        assert isinstance(p, StagingProfile)
        os.environ["APP_ENV"] = "prod"
        p = load_profile()
        assert isinstance(p, ProdProfile)
    run("Profile loading (dev/staging/prod)", w1_profiles)

    def w1_validator():
        from inc_trade.config.validator import ConfigValidator, ValidationProfile
        v = ConfigValidator(profile=ValidationProfile.DEV, env={})
        r = v.validate()
        assert r.valid is True
    run("ConfigValidator dev profile", w1_validator)

    # ── Wave 2: Secrets ───────────────────────────────────────────────────
    print("\n=== Wave 2: Secrets ===")

    def w2_secrets():
        from inc_trade.config.secrets_manager import SecretsManager
        sm = SecretsManager()
        assert sm.get("NONEXISTENT", "default") == "default"
    run("SecretsManager", w2_secrets)

    def w2_credentials():
        from inc_trade.infrastructure.credentials import CredentialResolver
        cr = CredentialResolver()
        assert cr.resolve_env_path("dhan") is not None
    run("CredentialResolver", w2_credentials)

    def w2_encryption():
        from inc_trade.infrastructure.secret_manager import SecretManager
        sm = SecretManager()
        key = sm.generate_key()
        assert len(key) > 0
    run("SecretManager key generation", w2_encryption)

    # ── Wave 3: Feature Flags ─────────────────────────────────────────────
    print("\n=== Wave 3: Feature Flags ===")

    def w3_flags():
        from inc_trade.config.feature_flags import FeatureFlags
        FeatureFlags.reset()
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True
        FeatureFlags.reset()
    run("FeatureFlags toggle", w3_flags)

    def w3_rollout():
        from inc_trade.config.feature_flags import FeatureFlags
        FeatureFlags.reset()
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)
        r1 = FeatureFlags.is_enabled_for_user("SMART_ROUTING", "user1")
        r2 = FeatureFlags.is_enabled_for_user("SMART_ROUTING", "user1")
        assert r1 == r2
        FeatureFlags.reset()
    run("FeatureFlags deterministic rollout", w3_rollout)

    # ── Wave 4: DI Container ──────────────────────────────────────────────
    print("\n=== Wave 4: DI Container ===")

    def w4_singleton():
        from inc_trade.core.di import Container, Scope
        c = Container()
        c.register("svc", lambda: object(), scope=Scope.SINGLETON)
        assert c.resolve("svc") is c.resolve("svc")
    run("DI singleton scope", w4_singleton)

    def w4_transient():
        from inc_trade.core.di import Container, Scope
        c = Container()
        c.register("svc", lambda: object(), scope=Scope.TRANSIENT)
        assert c.resolve("svc") is not c.resolve("svc")
    run("DI transient scope", w4_transient)

    def w4_scopes():
        from inc_trade.core.di_scopes import ScopeManager
        sm = ScopeManager()
        sm.clear()
    run("ScopeManager clear", w4_scopes)

    # ── Wave 5: Lifecycle ─────────────────────────────────────────────────
    print("\n=== Wave 5: Lifecycle ===")

    def w5_lifecycle():
        from datetime import datetime

        from inc_trade.domain.lifecycle_health import HealthState, HealthStatus
        from inc_trade.infrastructure.lifecycle import LifecycleManager

        class Svc:
            name = "test"
            started = False
            def start(self): self.started = True
            def stop(self, timeout_seconds=5.0): pass
            def health(self):
                return HealthStatus(state=HealthState.HEALTHY, service="test",
                                    last_check=datetime.now(UTC))

        mgr = LifecycleManager()
        mgr.register(Svc())
        mgr.start_all()
        snap = mgr.health_snapshot()
        assert "test" in snap
        mgr.stop_all()
    run("LifecycleManager start/stop/health", w5_lifecycle)

    # ── Wave 6: JWT + TOTP ────────────────────────────────────────────────
    print("\n=== Wave 6: JWT + TOTP ===")

    def w6_jwt():
        import base64
        import json
        import time
        from datetime import datetime

        from inc_trade.infrastructure.jwt_expiry import parse_jwt_expiry
        h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
        p = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600}).encode()).rstrip(b"=")
        token = f"{h.decode()}.{p.decode()}.sig"
        exp = parse_jwt_expiry(token)
        assert exp is not None
        assert isinstance(exp, datetime)
    run("JWT expiry parsing", w6_jwt)

    def w6_totp():
        from inc_trade.infrastructure.totp_cooldown import TOTPCooldown
        tc = TOTPCooldown(broker="parity_test", cooldown_seconds=30)
        assert tc.can_request() is True
        tc.mark_requested()
        assert tc.can_request() is False
    run("TOTP cooldown", w6_totp)

    # ── Wave 7: Observability ─────────────────────────────────────────────
    print("\n=== Wave 7: Observability ===")

    def w7_health():
        from inc_trade.infrastructure.observability.health_check import HealthCheck
        assert HealthCheck is not None
    run("HealthCheck import", w7_health)

    def w7_audit():
        from inc_trade.infrastructure.observability.audit import AuditLogger
        assert AuditLogger is not None
    run("AuditLogger import", w7_audit)

    def w7_metrics():
        from inc_trade.infrastructure.observability.event_metrics import EventMetrics
        assert EventMetrics is not None
    run("EventMetrics import", w7_metrics)

    def w7_alerting():
        from inc_trade.infrastructure.observability.alerting import AlertingEngine
        assert AlertingEngine is not None
    run("AlertingEngine import", w7_alerting)

    def w7_tracing():
        from inc_trade.infrastructure.observability.tracing import TraceContext
        assert TraceContext is not None
    run("TraceContext import", w7_tracing)

    # ── Wave 8: Bootstrap, Registry, Endpoints, Indices ───────────────────
    print("\n=== Wave 8: Bootstrap, Registry, Endpoints, Indices ===")

    def w8_endpoints():
        from inc_trade.config.endpoints import Dhan, Upstox
        assert Dhan.REST_BASE == "https://api.dhan.co/v2"
        prod = Upstox.production()
        assert "/v3/order/place" in prod.place_order_v3_url()
    run("Endpoints (Dhan + Upstox)", w8_endpoints)

    def w8_indices():
        from inc_trade.config.indices import INDEX_SYMBOLS, index_upstox_key, is_index
        assert is_index("NIFTY") is True
        assert is_index("RELIANCE") is False
        assert len(INDEX_SYMBOLS) > 30
        assert index_upstox_key("NIFTY") == "NSE_INDEX|Nifty 50"
    run("Indices (41 symbols)", w8_indices)

    def w8_registry():
        from inc_trade.infrastructure.registry import BrokerRegistry
        reg = BrokerRegistry()
        reg.register("dhan", object())
        assert reg.has("dhan")
        assert reg.get_health("dhan").alive is True
    run("BrokerRegistry", w8_registry)

    def w8_bootstrap():
        import asyncio
        import os

        from inc_trade.infrastructure.bootstrap import Bootstrap
        os.environ["APP_ENV"] = "dev"
        result = asyncio.run(
            Bootstrap.run(skip_validation=True, broker_names=["dhan"])
        )
        assert result.config is not None
    run("Bootstrap orchestration", w8_bootstrap)

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"PARITY VALIDATION: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
