"""ResolverRefresher — scheduled background service for the instrument master.

The :class:`brokers.dhan.resolver.SymbolResolver` is loaded once at
gateway construction. The compact CSV and the MCX supplement are then
frozen for the lifetime of the process. In a long-running process this
leads to two real problems:

1. **Stale security_ids** — Dhan re-lists option series weekly. If the
   process was started on Sunday night, a new weekly series listed on
   Monday morning will not appear in the resolver until restart. Calls
   to ``place_order`` for those series will fail with ``DH-906`` or
   the resolver will silently substitute an expired contract.

2. **Schema drift** — Dhan occasionally adds new columns to the master
   CSV. Without a periodic refresh, the resolver falls behind silently.

The :class:`ResolverRefresher` is a :class:`brokers.common.lifecycle.ManagedService`
that re-runs :meth:`brokers.dhan.connection.DhanConnection.load_instruments`
on a configurable interval, atomic-swaps the new resolver, and emits a
``resolver_refreshed`` audit event. Failures are recorded in the
health snapshot but never block the main trading path — a transient
network failure should not take down order placement.

Behaviour
---------
* The refresh runs in a daemon thread, so a slow network or a large
  CSV does not block the order-placement hot path.
* The new resolver is built completely in memory and then atomic-swapped
  into :class:`DhanConnection` so readers either see the old or the
  new resolver, never a half-loaded one.
* Refresh count and last error are exposed via ``health()`` for the SRE
  layer.
* The interval is configurable; the default is once a day at 00:30 UTC
  (post-token-expiry). For tests the interval can be set to a small
  value to verify the loop fires.

Why this is a separate module
-----------------------------
It is owned by a :class:`LifecycleManager` so the process can drain it
deterministically on shutdown. The previous "fire and forget" pattern
left daemon threads leaked on process exit.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from infrastructure.lifecycle import HealthState, ManagedService, build_health

logger = logging.getLogger(__name__)


class ResolverRefresher(ManagedService):
    """Background scheduler that periodically refreshes the instrument resolver.

    Usage::

        refresher = ResolverRefresher(
            connection=conn,
            interval_seconds=24 * 3600,
        )
        lifecycle.register(refresher)
        lifecycle.start_all()

    Parameters
    ----------
    connection:
        The :class:`DhanConnection` whose resolver should be refreshed.
    interval_seconds:
        How often the refresh should fire. The default is once per day
        (86400 seconds). For unit tests a few seconds is appropriate.
    on_success:
        Optional callable invoked after a successful refresh with the
        new instrument count. Useful for dashboards / metrics.
    on_error:
        Optional callable invoked with the exception after a failed
        refresh. Useful for alerting.
    """

    name: str = "dhan.resolver_refresher"

    def __init__(
        self,
        connection,
        interval_seconds: int = 24 * 3600,
        on_success=None,
        on_error=None,
    ):
        self._connection = connection
        self._interval = interval_seconds
        self._on_success = on_success
        self._on_error = on_error
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_count: int = 0
        self._last_refresh_at: float | None = None
        self._last_error: str | None = None
        # Monotonic counter for the *failed* refresh attempts; the SRE
        # uses this together with ``_refresh_count`` to compute the
        # failure rate.
        self._error_count: int = 0

    # ── ManagedService contract ───────────────────────────────────────

    def start(self) -> None:
        """Start the background refresh thread. Idempotent."""
        if self._thread and self._thread.is_alive():
            logger.debug("Resolver refresher already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="resolver-refresher",
        )
        self._thread.start()
        logger.info(
            "Resolver refresher started (interval=%ds)",
            self._interval,
        )

    def stop(self, timeout_seconds: float = 10.0) -> None:
        """Stop the background refresh thread. Idempotent."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                logger.warning(
                    "Resolver refresher did not stop within %.1fs; "
                    "leaving the daemon to be reaped at process exit",
                    timeout_seconds,
                )
            self._thread = None
        logger.info(
            "Resolver refresher stopped (refreshed %d times, %d errors)",
            self._refresh_count,
            self._error_count,
        )

    def health(self):  # type: ignore[override]
        running = self._thread is not None and self._thread.is_alive()
        if not running:
            state = HealthState.STOPPED
            detail = "not running"
        elif self._last_error is not None:
            state = HealthState.DEGRADED
            detail = f"last error: {self._last_error}"
        else:
            state = HealthState.HEALTHY
            detail = f"refreshed {self._refresh_count} times"
        return build_health(
            self.name,
            state,
            detail=detail,
            metrics={
                "refresh_count": self._refresh_count,
                "error_count": self._error_count,
                "interval_seconds": self._interval,
                "last_refresh_at": (
                    datetime.fromtimestamp(self._last_refresh_at, timezone.utc).isoformat()
                    if self._last_refresh_at
                    else None
                ),
            },
        )

    # ── Public helpers ────────────────────────────────────────────────

    def refresh_now(self) -> bool:
        """Trigger an immediate refresh. Returns True if successful.

        Blocks until the refresh is complete. Useful for tests and
        for an operator who wants to force a refresh from a CLI
        subcommand.
        """
        return self._do_refresh()

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Background loop ───────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._do_refresh()
            except Exception as exc:
                # The exceptions are caught inside _do_refresh, but a
                # top-level guard keeps the loop alive even if a
                # coding error escapes.
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.error("Resolver refresher unhandled error: %s", exc)
            # Use ``wait`` so the stop event is honoured promptly.
            self._stop_event.wait(timeout=self._interval)

    def _do_refresh(self) -> bool:
        # Run the actual load_instruments call. This is the only place
        # we touch the connection; if it raises, the error is captured
        # and the loop continues on the next tick.
        start = time.monotonic()
        try:
            self._connection.load_instruments(use_cache=True)
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._error_count += 1
            if self._error_count >= 3:
                logger.error(
                    "resolver_refresh_repeated_failure",
                    extra={
                        "error_count": self._error_count,
                        "error": str(exc),
                        "hint": "instrument master may be stale — consider manual refresh",
                    },
                )
            else:
                logger.warning(
                    "resolver_refresh_failed",
                    extra={"error": str(exc), "elapsed_s": round(time.monotonic() - start, 2)},
                )
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception as cb_exc:  # pragma: no cover
                    logger.debug("resolver_refresh_error_callback_failed: %s", cb_exc)
            return False

        # Successful refresh. The atomic swap into the connection is
        # performed inside load_instruments; we just record the count.
        self._refresh_count += 1
        self._last_refresh_at = time.time()
        self._last_error = None
        elapsed = time.monotonic() - start
        # ``stats()`` returns {"loaded": bool, "total": int}. We log
        # the total for the audit trail.
        try:
            stats = self._connection.instruments.stats()
            count = stats.get("total", 0)
        except Exception:
            count = -1
        logger.info(
            "resolver_refreshed",
            extra={
                "refresh_count": self._refresh_count,
                "count": count,
                "elapsed_s": round(elapsed, 2),
            },
        )
        if self._on_success:
            try:
                self._on_success(count)
            except Exception as cb_exc:  # pragma: no cover
                logger.debug("resolver_refresh_success_callback_failed: %s", cb_exc)
        return True
