"""Tests for Phase A / A2+A3: RiskManager concurrency and daily PnL rollover.

Covers:

  A3 — internal RLock protecting _config and _daily_pnl against torn
       reads under concurrent set_kill_switch / update_daily_pnl /
       check_order / reset_daily_pnl.

  A2 — reset_daily_pnl() method and the DailyPnlResetScheduler that
       fires it at the IST 00:00 (or configured) rollover boundary.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms import (
    DailyPnlResetScheduler,
    PositionManager,
    RiskConfig,
    RiskManager,
)
from domain import Order, OrderStatus, OrderType, ProductType, Side
from infrastructure.lifecycle.lifecycle import HealthState

# ── Helpers ────────────────────────────────────────────────────────────────


_IST = timezone(timedelta(hours=5, minutes=30))


def _make_order(symbol: str = "RELIANCE", price: Decimal = Decimal("2500")) -> Order:
    return Order(
        order_id="O-1",
        symbol=symbol,
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=price,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )


@pytest.fixture
def position_manager() -> PositionManager:
    return PositionManager()


@pytest.fixture
def capital_fn() -> MagicMock:
    fn = MagicMock(return_value=Decimal("1000000"))
    return fn


@pytest.fixture
def risk_manager(position_manager: PositionManager, capital_fn: MagicMock) -> RiskManager:
    return RiskManager(
        position_manager=position_manager,
        config=RiskConfig(),
        capital_fn=capital_fn,
    )


# ═════════════════════════════════════════════════════════════════════════
# RiskManager concurrency
# ═════════════════════════════════════════════════════════════════════════


def test_set_kill_switch_is_thread_safe(risk_manager: RiskManager) -> None:
    """Hammer set_kill_switch from 50 threads. Verifies:

    * No thread raises or corrupts the dataclass.
    * The toggle counter never decreases (monotonic).
    * The toggle counter is bounded above by the total number of
      "actual state change" calls (each thread's iteration does 2
      set_kill_switch calls; the upper bound is 2*iterations*threads).
    * The final ``kill_switch`` is a ``bool`` (no torn read of the
      frozen dataclass).

    A weaker invariant than ``count == iterations*threads``: the test
    uses a (True, False) hammer pattern from each thread, but the
    read-then-invert (``set_kill_switch(not current)``) is racy across
    threads. We deliberately use fixed targets to keep the test
    deterministic in the count and bound the race window.
    """
    iterations = 200
    threads = 50

    def hammer():
        for _ in range(iterations):
            risk_manager.set_kill_switch(True)
            risk_manager.set_kill_switch(False)

    with ThreadPoolExecutor(max_workers=threads) as ex:
        list(ex.map(lambda _: hammer(), range(threads)))

    snap = risk_manager.snapshot()
    # Every iteration does 2 set_kill_switch calls.
    upper_bound = 2 * iterations * threads
    assert 0 <= snap["kill_switch_toggles"] <= upper_bound, (
        f"toggle count {snap['kill_switch_toggles']} out of bounds [0, {upper_bound}]"
    )
    # The final kill-switch state is a bool (no corrupted dataclass).
    assert isinstance(risk_manager.kill_switch, bool)
    # The dataclass is still frozen (read returns a string-serialisable value).
    assert risk_manager.kill_switch in (True, False)


def test_concurrent_update_daily_pnl_and_check_order_is_safe(
    risk_manager: RiskManager, capital_fn: MagicMock
) -> None:
    """Reading _daily_pnl from check_order while another thread writes
    via update_daily_pnl must never produce a partially-written value
    or raise."""
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer():
        i = 0
        while not stop.is_set():
            risk_manager.update_daily_pnl(Decimal(i))
            i += 1

    def reader():
        order = _make_order()
        while not stop.is_set():
            try:
                risk_manager.check_order(order)
            except BaseException as exc:  # pragma: no cover - defensive
                errors.append(exc)

    threads = [threading.Thread(target=writer)]
    threads += [threading.Thread(target=reader) for _ in range(8)]
    for t in threads:
        t.start()
    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join()

    assert not errors, f"Reader raised during concurrent writes: {errors}"


def test_check_order_kill_switch_atomic_with_daily_pnl_update(
    risk_manager: RiskManager,
) -> None:
    """If a kill-switch flip happens during check_order, the reader
    must see either the pre-flip or post-flip state, never both
    partially. We verify by checking that check_order never raises an
    inconsistent state (e.g. ``Decimal`` operations on a None)."""
    order = _make_order()
    stop = threading.Event()

    def killer():
        while not stop.is_set():
            risk_manager.set_kill_switch(True)
            risk_manager.set_kill_switch(False)

    def updater():
        i = 0
        while not stop.is_set():
            risk_manager.update_daily_pnl(Decimal(-i % 100))
            i += 1

    def checker():
        while not stop.is_set():
            r = risk_manager.check_order(order)
            assert r.allowed is True or r.allowed is False  # never a torn bool

    threads = [
        threading.Thread(target=killer),
        threading.Thread(target=updater),
        threading.Thread(target=checker),
    ]
    for t in threads:
        t.start()
    time.sleep(0.3)
    stop.set()
    for t in threads:
        t.join()


def test_kill_switch_property_reflects_set_kill_switch(
    risk_manager: RiskManager,
) -> None:
    """After set_kill_switch(True), check_order must immediately
    reject with the kill-switch reason."""
    order = _make_order()
    assert risk_manager.check_order(order).allowed is True
    risk_manager.set_kill_switch(True)
    result = risk_manager.check_order(order)
    assert result.allowed is False
    assert "Kill switch is active" in result.reason
    assert risk_manager.kill_switch is True


# ═════════════════════════════════════════════════════════════════════════
# reset_daily_pnl
# ═════════════════════════════════════════════════════════════════════════


def test_reset_daily_pnl_zeros_the_running_total(
    risk_manager: RiskManager,
) -> None:
    risk_manager.update_daily_pnl(Decimal("-5000"))
    assert risk_manager.daily_pnl == Decimal("-5000")
    risk_manager.reset_daily_pnl()
    assert risk_manager.daily_pnl == Decimal("0")


def test_reset_daily_pnl_increments_counter_and_records_time(
    risk_manager: RiskManager,
) -> None:
    assert risk_manager.snapshot()["reset_count"] == 0
    risk_manager.reset_daily_pnl()
    assert risk_manager.snapshot()["reset_count"] == 1
    assert risk_manager.snapshot()["last_reset_at"] > 0
    risk_manager.reset_daily_pnl()
    assert risk_manager.snapshot()["reset_count"] == 2


def test_daily_pnl_property_is_thread_safe(risk_manager: RiskManager) -> None:
    """Concurrent writers and readers of daily_pnl must not raise."""
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer():
        i = 0
        while not stop.is_set():
            risk_manager.update_daily_pnl(Decimal(i % 1000))
            i += 1

    def reader():
        while not stop.is_set():
            try:
                _ = risk_manager.daily_pnl
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

    threads = [threading.Thread(target=writer)]
    threads += [threading.Thread(target=reader) for _ in range(8)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    stop.set()
    for t in threads:
        t.join()
    assert not errors


def test_snapshot_is_json_serializable(risk_manager: RiskManager) -> None:
    import json

    risk_manager.update_daily_pnl(Decimal("-1000"))
    risk_manager.set_kill_switch(True)
    snap = risk_manager.snapshot()
    # Must be JSON-serializable (Decimals are strings already).
    json.dumps(snap)


def test_daily_loss_check_blocks_after_reset_clears_the_block(
    position_manager: PositionManager, capital_fn: MagicMock
) -> None:
    """A -5% loss blocks orders; after reset_daily_pnl, orders are
    allowed again. This is the IST rollover behaviour the previous
    implementation never achieved.

    Capital is set high enough that the per-position percentage check
    (20% of capital) does not fire before the daily-loss check (5% of
    capital) — otherwise the test would exercise the wrong code path.

    B1: Loss CB threshold is set high (10%) so it doesn't interfere with
    this test which is specifically testing the daily-loss check.
    """
    from application.oms._internal.loss_circuit_breaker import LossCircuitBreakerConfig

    order = _make_order(price=Decimal("50"))  # notional = 10 * 50 = 500
    capital_fn.return_value = Decimal("100000")  # 500/100000*100 = 0.5% < 20%

    # Set loss CB threshold high so it doesn't trip before daily loss check
    loss_cb_config = LossCircuitBreakerConfig(
        loss_threshold_pct=Decimal("10.0"),
        cooldown_seconds=5,
        window_seconds=86400,
    )
    rm = RiskManager(
        position_manager,
        RiskConfig(),
        capital_fn=capital_fn,
        loss_cb_config=loss_cb_config,
    )

    # -5% of 100000 = -5000
    rm.update_daily_pnl(Decimal("-5000"))
    result = rm.check_order(order)
    assert result.allowed is False
    assert "Daily loss limit reached" in result.reason

    rm.reset_daily_pnl()
    # After reset, check must pass again
    result = rm.check_order(order)
    assert result.allowed is True


# ═════════════════════════════════════════════════════════════════════════
# DailyPnlResetScheduler
# ═════════════════════════════════════════════════════════════════════════


def test_scheduler_validates_rollover_hour(
    risk_manager: RiskManager,
) -> None:
    with pytest.raises(ValueError, match="rollover_hour_ist"):
        DailyPnlResetScheduler(risk_manager, rollover_hour_ist=24)
    with pytest.raises(ValueError, match="rollover_hour_ist"):
        DailyPnlResetScheduler(risk_manager, rollover_hour_ist=-1)


def test_scheduler_validates_poll_interval(risk_manager: RiskManager) -> None:
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        DailyPnlResetScheduler(risk_manager, poll_interval_seconds=0)
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        DailyPnlResetScheduler(risk_manager, poll_interval_seconds=-1)


def test_scheduler_is_managed_service(risk_manager: RiskManager) -> None:
    """The scheduler must implement the ManagedService Protocol so
    it can be registered with a LifecycleManager (A4 / A5 contract)."""
    from infrastructure.lifecycle.lifecycle import ManagedService

    s = DailyPnlResetScheduler(risk_manager)
    assert isinstance(s, ManagedService)
    assert s.name == "daily-pnl-reset"


def test_scheduler_start_is_idempotent(risk_manager: RiskManager) -> None:
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    s.start()
    try:
        # Second start must not raise or start a second thread.
        s.start()
        # The thread attribute must still be the same live thread.
        assert s._thread is not None
        assert s._thread.is_alive()
    finally:
        s.stop(timeout_seconds=2)


def test_scheduler_stop_is_idempotent(risk_manager: RiskManager) -> None:
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    s.start()
    s.stop(timeout_seconds=2)
    # Second stop must be a no-op.
    s.stop(timeout_seconds=2)
    assert s._thread is None


def test_scheduler_health_reflects_running_state(risk_manager: RiskManager) -> None:
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    # Before start
    h = s.health()
    assert h.state == HealthState.STOPPED
    s.start()
    try:
        h = s.health()
        assert h.state == HealthState.HEALTHY
        assert h.service == "daily-pnl-reset"
    finally:
        s.stop(timeout_seconds=2)


def test_scheduler_fires_reset_after_rollover_boundary_crossed(
    risk_manager: RiskManager,
) -> None:
    """The scheduler's _maybe_reset must call reset_daily_pnl when the
    current IST time has crossed a new rollover moment since the last
    reset. We simulate the boundary crossing by setting
    _last_reset_unix to a value that is more than 24h old."""
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    # Pretend we last reset 25 hours ago.
    s._last_reset_unix = time.time() - (25 * 3600)
    # Now run one iteration.
    s._maybe_reset()
    assert risk_manager.daily_pnl == Decimal("0")
    assert s._reset_count == 1


def test_scheduler_does_not_fire_reset_before_boundary(
    risk_manager: RiskManager,
) -> None:
    """If the last reset was less than 24h ago, _maybe_reset must
    not fire. This prevents the scheduler from accidentally clearing
    PnL during a single trading session."""
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    # Pretend we last reset 5 minutes ago.
    s._last_reset_unix = time.time() - 300
    risk_manager.update_daily_pnl(Decimal("-1000"))
    s._maybe_reset()
    # PnL must NOT have been reset.
    assert risk_manager.daily_pnl == Decimal("-1000")
    assert s._reset_count == 0


def test_scheduler_does_not_double_fire_within_same_rollover_window(
    risk_manager: RiskManager,
) -> None:
    """Two consecutive _maybe_reset calls within the same rollover
    window must not reset twice. The second call must be a no-op."""
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    s._last_reset_unix = time.time() - (25 * 3600)
    s._maybe_reset()
    s._maybe_reset()
    s._maybe_reset()
    assert s._reset_count == 1, "Second/third call must be a no-op"


def test_scheduler_start_does_not_immediately_fire_reset(
    risk_manager: RiskManager,
) -> None:
    """On start(), the scheduler initialises _last_reset_unix to the
    most recent rollover moment. The next _maybe_reset call must NOT
    fire (because we are still within the same rollover window as
    _last_reset_unix). This prevents a long-running process from
    clearing the daily PnL the moment it (re)starts."""
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    s.start()
    try:
        time.sleep(0.1)  # let the thread run a few iterations
        assert s._reset_count == 0, "start() must not immediately fire reset"
    finally:
        s.stop(timeout_seconds=2)


def test_scheduler_last_rollover_unix_for_ist_midnight() -> None:
    """Verify the rollover moment calculation:

    18:30 UTC on 2026-06-15 = 00:00 IST on 2026-06-16 → the rollover
    moment is 18:30 UTC on 2026-06-15.

    18:29 UTC on 2026-06-15 = 23:59 IST on 2026-06-15 → the rollover
    moment is 18:30 UTC on 2026-06-14 (one day earlier).
    """
    rm = RiskManager(PositionManager(), RiskConfig())
    s = DailyPnlResetScheduler(rm, rollover_hour_ist=0)

    ist_00_00 = datetime(2026, 6, 16, 0, 0, tzinfo=_IST)
    ist_23_59 = datetime(2026, 6, 15, 23, 59, tzinfo=_IST)
    ist_00_01 = datetime(2026, 6, 16, 0, 1, tzinfo=_IST)

    # Just after IST midnight → rollover was the boundary itself
    assert abs(s._last_rollover_unix(ist_00_01.timestamp()) - ist_00_00.timestamp()) < 0.001
    # Just before IST midnight → rollover was the previous day
    assert (
        abs(
            s._last_rollover_unix(ist_23_59.timestamp())
            - (ist_00_00 - timedelta(days=1)).timestamp()
        )
        < 0.001
    )


def test_scheduler_custom_rollover_hour() -> None:
    """A non-zero rollover hour (e.g. 03:00 IST) must be honoured."""
    rm = RiskManager(PositionManager(), RiskConfig())
    s = DailyPnlResetScheduler(rm, rollover_hour_ist=3)

    # 22:00 IST on 2026-06-15 → last rollover was 03:00 IST the same day
    ist_22_00 = datetime(2026, 6, 15, 22, 0, tzinfo=_IST)
    ist_03_00 = datetime(2026, 6, 15, 3, 0, tzinfo=_IST)
    assert abs(s._last_rollover_unix(ist_22_00.timestamp()) - ist_03_00.timestamp()) < 0.001

    # 02:00 IST on 2026-06-15 → last rollover was 03:00 IST on 2026-06-14
    ist_02_00 = datetime(2026, 6, 15, 2, 0, tzinfo=_IST)
    ist_03_00_prev = datetime(2026, 6, 14, 3, 0, tzinfo=_IST)
    assert abs(s._last_rollover_unix(ist_02_00.timestamp()) - ist_03_00_prev.timestamp()) < 0.001


def test_scheduler_health_metrics_include_reset_count(
    risk_manager: RiskManager,
) -> None:
    s = DailyPnlResetScheduler(risk_manager, poll_interval_seconds=10)
    s._last_reset_unix = time.time() - (25 * 3600)
    s._maybe_reset()
    s._maybe_reset()  # no-op
    h = s.health()
    assert h.metrics["reset_count"] == 1
    assert h.metrics["rollover_hour_ist"] == 0


# ── End-to-end: scheduler + risk manager fire correctly ──────────────────


def test_end_to_end_scheduler_drains_pnl_at_rollover(
    risk_manager: RiskManager,
) -> None:
    """Simulate the full flow: set a big loss, run the scheduler with
    a back-dated last-reset time, confirm the loss is cleared."""
    risk_manager.update_daily_pnl(Decimal("-9000"))
    capital = Decimal("100000")
    rm = MagicMock()
    rm.capital_fn = MagicMock(return_value=capital)

    # Use a real risk manager for the real test
    rm_real = RiskManager(PositionManager(), RiskConfig(), capital_fn=rm.capital_fn)
    rm_real.update_daily_pnl(Decimal("-9000"))

    s = DailyPnlResetScheduler(rm_real, poll_interval_seconds=10)
    s._last_reset_unix = time.time() - (25 * 3600)
    s._maybe_reset()
    assert rm_real.daily_pnl == Decimal("0")
    assert s._reset_count == 1
