"""TDD tests for BrokerHealthMonitor and BrokerDegradedError.

Tests cover:
- Health tracking (success/failure recording)
- Threshold-based health determination
- Concurrent access thread safety
- BrokerDegradedError exception behavior
"""

from __future__ import annotations

import threading
import time

import pytest

from brokers.common.resilience.broker_health_monitor import (
    BrokerHealthMonitor,
    BrokerHealthStatus,
)
from brokers.common.resilience.errors import BrokerDegradedError

# ======================================================================
# BrokerHealthMonitor tests
# ======================================================================


class TestBrokerHealthMonitorInitialization:
    def test_default_threshold(self):
        monitor = BrokerHealthMonitor()
        assert monitor.failure_threshold == 5

    def test_custom_threshold(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        assert monitor.failure_threshold == 3

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            BrokerHealthMonitor(failure_threshold=0)
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            BrokerHealthMonitor(failure_threshold=-1)

    def test_empty_monitor_is_healthy_for_any(self):
        monitor = BrokerHealthMonitor()
        assert monitor.any_healthy(["dhan"]) is True  # unknown = healthy


class TestBrokerHealthMonitorSuccessFailureTracking:
    def test_record_success_marks_healthy(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_success("dhan")
        assert monitor.is_healthy("dhan") is True

    def test_record_success_resets_consecutive_failures(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.get_health_status()["dhan"].consecutive_failures == 2
        monitor.record_success("dhan")
        assert monitor.get_health_status()["dhan"].consecutive_failures == 0

    def test_consecutive_failures_reach_threshold(self):
        monitor = BrokerHealthMonitor(failure_threshold=3)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is True  # 2 < 3
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is False  # 3 >= 3

    def test_success_after_unhealthy_recovers(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is False
        monitor.record_success("dhan")
        assert monitor.is_healthy("dhan") is True

    def test_unknown_broker_is_healthy(self):
        monitor = BrokerHealthMonitor()
        assert monitor.is_healthy("nonexistent") is True

    def test_last_successful_call_updated(self):
        monitor = BrokerHealthMonitor()
        before = time.monotonic()
        monitor.record_success("dhan")
        after = time.monotonic()
        status = monitor.get_health_status()["dhan"]
        assert status.last_successful_call is not None
        assert before <= status.last_successful_call <= after

    def test_last_health_check_updated_on_failure(self):
        monitor = BrokerHealthMonitor()
        before = time.monotonic()
        monitor.record_failure("dhan")
        after = time.monotonic()
        status = monitor.get_health_status()["dhan"]
        assert before <= status.last_health_check <= after


class TestBrokerHealthMonitorGetHealthStatus:
    def test_returns_copy_not_reference(self):
        monitor = BrokerHealthMonitor()
        monitor.record_failure("dhan")
        status1 = monitor.get_health_status()
        status2 = monitor.get_health_status()
        assert status1 is not status2
        assert status1["dhan"] is not status2["dhan"]

    def test_to_dict_serializable(self):
        monitor = BrokerHealthMonitor()
        monitor.record_success("dhan")
        status = monitor.get_health_status()["dhan"]
        d = status.to_dict()
        assert isinstance(d, dict)
        assert "last_successful_call" in d
        assert "consecutive_failures" in d
        assert "circuit_state" in d
        assert "last_health_check" in d

    def test_circuit_state_values(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        status = monitor.get_health_status()
        assert "dhan" not in status  # not tracked yet

        monitor.record_failure("dhan")
        status = monitor.get_health_status()["dhan"]
        assert status.circuit_state == "healthy"

        monitor.record_failure("dhan")
        status = monitor.get_health_status()["dhan"]
        assert status.circuit_state == "unhealthy"


class TestBrokerHealthMonitorAnyHealthy:
    def test_any_healthy_with_list(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.any_healthy(["dhan", "upstox"]) is True  # upstox unknown = healthy

    def test_any_healthy_all_unhealthy(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_failure("upstox")
        monitor.record_failure("upstox")
        assert monitor.any_healthy(["dhan", "upstox"]) is False

    def test_any_healthy_empty_list(self):
        monitor = BrokerHealthMonitor()
        assert monitor.any_healthy([]) is False

    def test_any_healthy_no_tracking(self):
        monitor = BrokerHealthMonitor()
        assert monitor.any_healthy() is False  # no tracked brokers


class TestBrokerHealthMonitorReset:
    def test_reset_single_broker(self):
        monitor = BrokerHealthMonitor(failure_threshold=2)
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        assert monitor.is_healthy("dhan") is False
        monitor.reset("dhan")
        assert monitor.is_healthy("dhan") is True  # removed = unknown = healthy

    def test_reset_all(self):
        monitor = BrokerHealthMonitor()
        monitor.record_failure("dhan")
        monitor.record_failure("dhan")
        monitor.record_failure("upstox")
        monitor.record_failure("upstox")
        monitor.reset()
        assert monitor.get_health_status() == {}


class TestBrokerHealthMonitorThreadSafety:
    """Verify concurrent access does not corrupt state."""

    def test_concurrent_record_success(self):
        monitor = BrokerHealthMonitor()
        threads = []
        for _ in range(50):
            t = threading.Thread(target=monitor.record_success, args=("dhan",))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        status = monitor.get_health_status()["dhan"]
        assert status.consecutive_failures == 0
        assert status.circuit_state == "healthy"

    def test_concurrent_record_failure(self):
        monitor = BrokerHealthMonitor(failure_threshold=100)
        threads = []
        for _ in range(50):
            t = threading.Thread(target=monitor.record_failure, args=("dhan",))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        status = monitor.get_health_status()["dhan"]
        assert status.consecutive_failures == 50

    def test_concurrent_mixed_operations(self):
        monitor = BrokerHealthMonitor(failure_threshold=10)
        barrier = threading.Barrier(20)

        def worker(is_success: bool):
            barrier.wait()
            for _ in range(100):
                if is_success:
                    monitor.record_success("dhan")
                else:
                    monitor.record_failure("dhan")

        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(i % 2 == 0,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        # No exceptions means thread-safe
        status = monitor.get_health_status()["dhan"]
        assert isinstance(status, BrokerHealthStatus)



class TestBrokerDegradedError:
    """Test the BrokerDegradedError exception."""

    def test_default_message(self):
        err = BrokerDegradedError()
        assert "degraded mode" in str(err).lower()

    def test_custom_message(self):
        err = BrokerDegradedError("custom message")
        assert "custom message" in str(err)

    def test_health_status_attached(self):
        health = {"dhan": {"circuit_state": "unhealthy"}}
        err = BrokerDegradedError(health_status=health)
        assert err.health_status == health

    def test_is_broker_error(self):
        from brokers.common.resilience.errors import BrokerError

        err = BrokerDegradedError()
        assert isinstance(err, BrokerError)
