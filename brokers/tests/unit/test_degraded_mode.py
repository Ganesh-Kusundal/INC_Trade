"""Unit tests for DegradedMode and DegradedGuard."""

from __future__ import annotations

import time

import pytest

from inc_trade.market.degraded_mode import DegradedGuard, DegradedMode


class TestDegradedMode:
    def test_initially_not_degraded(self) -> None:
        dm = DegradedMode()
        assert dm.is_degraded("NSE:X") is False

    def test_enter_degraded(self) -> None:
        dm = DegradedMode()
        dm.enter_degraded("NSE:X")
        assert dm.is_degraded("NSE:X") is True

    def test_recover_clears_degraded(self) -> None:
        dm = DegradedMode()
        dm.enter_degraded("NSE:X")
        dm.recover("NSE:X")
        assert dm.is_degraded("NSE:X") is False

    def test_auto_recovery_after_max_duration(self) -> None:
        dm = DegradedMode(max_degraded_duration_s=0.05)
        dm.enter_degraded("NSE:X")
        assert dm.is_degraded("NSE:X") is True
        time.sleep(0.1)
        assert dm.is_degraded("NSE:X") is False

    def test_degraded_keys_listing(self) -> None:
        dm = DegradedMode()
        dm.enter_degraded("A")
        dm.enter_degraded("B")
        dm.recover("A")
        assert "B" in dm.degraded_keys()
        assert "A" not in dm.degraded_keys()

    def test_clear(self) -> None:
        dm = DegradedMode()
        dm.enter_degraded("X")
        dm.clear()
        assert dm.degraded_keys() == []


class TestDegradedGuard:
    def test_primary_success_recovered(self) -> None:
        dm = DegradedMode()
        guard = DegradedGuard(dm, "NSE:X")
        result = guard.call(lambda: "primary-ok")
        assert result == "primary-ok"
        assert not dm.is_degraded("NSE:X")

    def test_primary_failure_uses_fallback(self) -> None:
        dm = DegradedMode()
        guard = DegradedGuard(dm, "NSE:X")

        def fail() -> str:
            raise RuntimeError("down")

        result = guard.call(fail, fallback=lambda: "stale")
        assert result == "stale"
        assert dm.is_degraded("NSE:X")

    def test_no_fallback_propagates(self) -> None:
        dm = DegradedMode()
        guard = DegradedGuard(dm, "NSE:X")

        def fail() -> str:
            raise RuntimeError("down")

        with pytest.raises(RuntimeError, match="down"):
            guard.call(fail)

    def test_recovery_after_failure(self) -> None:
        dm = DegradedMode()
        guard = DegradedGuard(dm, "NSE:X")
        # First call fails
        guard.call(lambda: (_ for _ in ()).throw(RuntimeError("down")), fallback=lambda: "stale")
        assert dm.is_degraded("NSE:X")
        # Second call succeeds → recovery
        result = guard.call(lambda: "primary-ok")
        assert result == "primary-ok"
        assert not dm.is_degraded("NSE:X")
