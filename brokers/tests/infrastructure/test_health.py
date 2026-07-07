"""Tests for health check system — HealthRegistry + @health_check decorator."""

from __future__ import annotations

import pytest

from brokers.infrastructure.health import (
    HealthEntry,
    HealthStatus,
    health_check,
    health_registry,
)


class TestHealthStatus:
    def test_enum_values(self):
        assert HealthStatus.HEALTHY == "HEALTHY"
        assert HealthStatus.DEGRADED == "DEGRADED"
        assert HealthStatus.UNHEALTHY == "UNHEALTHY"
        assert HealthStatus.UNKNOWN == "UNKNOWN"

    def test_enum_is_string(self):
        assert isinstance(HealthStatus.HEALTHY, str)


class TestHealthEntry:
    def test_default_entry(self):
        entry = HealthEntry(name="test_check", status=HealthStatus.UNKNOWN)
        assert entry.name == "test_check"
        assert entry.status == HealthStatus.UNKNOWN
        assert entry.consecutive_failures == 0
        assert entry.latency_ms == 0.0
        assert entry.last_success is None


class TestHealthRegistry:
    def setup_method(self):
        health_registry.reset()

    def test_aggregate_unknown_when_empty(self):
        assert health_registry.aggregate() == HealthStatus.UNKNOWN

    def test_aggregate_healthy_when_all_healthy(self):
        health_registry.register("check_a")
        health_registry.record("check_a", success=True)
        assert health_registry.aggregate() == HealthStatus.HEALTHY

    def test_aggregate_unhealthy_when_one_is_unhealthy(self):
        health_registry.register("check_a")
        health_registry.register("check_b")
        health_registry.record("check_a", success=True)
        # 4 failures with threshold=3 → UNHEALTHY (4 > 3)
        for _ in range(4):
            health_registry.record("check_b", success=False)
        assert health_registry.aggregate() == HealthStatus.UNHEALTHY

    def test_aggregate_degraded_when_one_is_degraded(self):
        health_registry.register("check_a")
        health_registry.record("check_a", success=False)  # 1 failure → DEGRADED
        assert health_registry.aggregate() == HealthStatus.DEGRADED

    def test_record_success_resets_failures(self):
        health_registry.register("check_a")
        health_registry.record("check_a", success=False)
        health_registry.record("check_a", success=False)
        health_registry.record("check_a", success=True)
        status = health_registry.status()
        assert status["check_a"].consecutive_failures == 0
        assert status["check_a"].status == HealthStatus.HEALTHY

    def test_status_returns_snapshot(self):
        health_registry.register("ping")
        health_registry.record("ping", success=True, latency_ms=15.0)
        snapshot = health_registry.status()
        assert "ping" in snapshot
        assert snapshot["ping"].latency_ms == 15.0

    def test_record_ignores_unregistered_check(self):
        """Recording an unregistered check should not crash."""
        health_registry.record("nonexistent", success=True)


class TestHealthCheckDecorator:
    def setup_method(self):
        health_registry.reset()

    def test_successful_check_records_healthy(self):
        @health_check("my_check")
        def check() -> bool:
            return True

        check()
        entry = health_registry.status()["my_check"]
        assert entry.status == HealthStatus.HEALTHY
        assert entry.latency_ms >= 0

    def test_failed_check_records_degraded(self):
        @health_check("fail_check", unhealthy_after_failures=2)
        def check() -> bool:
            return False

        check()
        check()
        entry = health_registry.status()["fail_check"]
        assert entry.status == HealthStatus.DEGRADED

    def test_consecutive_failures_record_unhealthy(self):
        @health_check("bad_check", unhealthy_after_failures=2)
        def check() -> bool:
            raise RuntimeError("boom")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                check()

        entry = health_registry.status()["bad_check"]
        assert entry.status == HealthStatus.UNHEALTHY

    def test_truthy_non_bool_result_counts_as_success(self):
        @health_check("int_check")
        def check() -> int:
            return 42

        check()
        entry = health_registry.status()["int_check"]
        assert entry.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_async_health_check(self):
        @health_check("async_check")
        async def check() -> bool:
            return True

        await check()
        entry = health_registry.status()["async_check"]
        assert entry.status == HealthStatus.HEALTHY

    def test_aggregate_reflects_decorator_status(self):
        @health_check("a")
        def check_a() -> bool:
            return True

        @health_check("b")
        def check_b() -> bool:
            return False

        check_a()
        for _ in range(4):
            check_b()

        assert health_registry.aggregate() == HealthStatus.UNHEALTHY
