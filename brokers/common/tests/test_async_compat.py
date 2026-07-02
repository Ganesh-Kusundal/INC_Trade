"""Tests for brokers.common.async_compat — async/sync boundary helpers."""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

from brokers.common.async_compat import connect_async_then, run_async_compat

# ── Helpers ────────────────────────────────────────────────────────────


async def _async_add(a: int, b: int) -> int:
    """Trivial async coroutine that returns a + b."""
    await asyncio.sleep(0)
    return a + b


async def _async_slow(delay: float = 0.5) -> str:
    """Async coroutine that sleeps then returns."""
    await asyncio.sleep(delay)
    return "done"


async def _async_raises() -> None:
    """Async coroutine that always raises."""
    raise ValueError("boom")


# ── Sync context (no running event loop) ───────────────────────────────


class TestSyncContext:
    """Tests when called from a thread with no running event loop."""

    def test_returns_result(self) -> None:
        """run_async_compat should return the coroutine's result in sync context."""
        result = run_async_compat(_async_add(2, 3), fire_and_forget=False)
        assert result == 5

    def test_fire_and_forget_returns_result_in_sync(self) -> None:
        """In sync context there is no loop to schedule on, so fire_and_forget
        is irrelevant — the coroutine runs synchronously and returns the result."""
        result = run_async_compat(_async_add(10, 20))
        assert result == 30

    def test_exception_propagates(self) -> None:
        """Exceptions from the coroutine should propagate in sync context."""
        with pytest.raises(ValueError, match="boom"):
            run_async_compat(_async_raises(), fire_and_forget=False)

    def test_temporary_loop_not_leaked(self) -> None:
        """Sync path creates a temporary loop, runs the coroutine, then closes
        it.  After the call, no loop should be left as the running loop for
        this thread, and any default loop should be closed (not active)."""
        run_async_compat(_async_add(1, 1), fire_and_forget=False)

        # 1. No running loop should be left on this thread.
        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()

        # 2. Any default loop should be closed, not active.
        #    On Python 3.10-3.11 get_event_loop() returns the closed loop
        #    (with DeprecationWarning); on 3.12+ it raises RuntimeError.
        try:
            default_loop = asyncio.get_event_loop()
            assert default_loop.is_closed()
        except RuntimeError:
            pass  # 3.12+: no default loop, which is also correct

    def test_sync_context_from_thread(self) -> None:
        """run_async_compat should work correctly from a non-main thread."""
        result_holder: list[object] = []
        error_holder: list[BaseException] = []

        def _worker() -> None:
            try:
                r = run_async_compat(_async_add(7, 8), fire_and_forget=False)
                result_holder.append(r)
            except BaseException as exc:
                error_holder.append(exc)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=5)

        assert not error_holder, f"Thread raised: {error_holder}"
        assert result_holder == [15]


# ── Async context (running event loop on another thread) ───────────────


class TestAsyncContext:
    """Tests when called from a thread while an event loop is running.

    To hit the async-context path (``get_running_loop()`` succeeds),
    ``run_async_compat`` must be called from the thread that owns the
    running loop.  The ``_run_on_loop`` helper runs a callable on that
    thread.
    """

    @pytest.fixture()
    def _loop_thread(self) -> None:
        """Start a background event loop thread for async-context tests."""
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()
        yield
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=2)
        self._loop.close()

    def _run_on_loop(self, fn, timeout: float = 5) -> object:
        """Run *fn* on the loop thread via run_coroutine_threadsafe."""

        async def _wrap() -> object:
            return fn()

        future = asyncio.run_coroutine_threadsafe(_wrap(), self._loop)
        return future.result(timeout=timeout)

    def test_fire_and_forget_schedules_and_returns_none(self, _loop_thread: None) -> None:
        """fire_and_forget=True should schedule the coroutine and return None."""
        import time

        result = self._run_on_loop(lambda: run_async_compat(_async_add(3, 4), fire_and_forget=True))
        assert result is None
        # Give the scheduled coroutine time to complete
        time.sleep(0.2)

    def test_fire_and_forget_actually_executes(self, _loop_thread: None) -> None:
        """The scheduled coroutine should actually run on the background loop."""
        result_box: list[int] = []

        async def _capture() -> None:
            r = await _async_add(100, 200)
            result_box.append(r)

        self._run_on_loop(lambda: run_async_compat(_capture(), fire_and_forget=True))
        time.sleep(0.2)
        assert result_box == [300]

    def test_non_fire_and_forget_blocks(self, _loop_thread: None) -> None:
        """fire_and_forget=False should block and return the result.

        Must be called from a thread other than the loop thread to avoid
        deadlock (future.result() blocks the caller).
        """
        results: list[object] = []
        errors: list[BaseException] = []

        def _caller() -> None:
            try:
                r = run_async_compat(_async_add(50, 60), fire_and_forget=False, timeout=5)
                results.append(r)
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=_caller)
        t.start()
        t.join(timeout=5)

        assert not errors, f"Thread raised: {errors}"
        assert results == [110]

    def test_non_fire_and_forget_exception_propagates(self, _loop_thread: None) -> None:
        """fire_and_forget=False should propagate exceptions.

        Must be called from a thread other than the loop thread.
        """
        errors: list[BaseException] = []

        def _caller() -> None:
            try:
                run_async_compat(_async_raises(), fire_and_forget=False, timeout=5)
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=_caller)
        t.start()
        t.join(timeout=5)

        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)
        assert "boom" in str(errors[0])

    def test_cross_thread_safety(self, _loop_thread: None) -> None:
        """run_coroutine_threadsafe should work from a different thread."""
        results: list[object] = []
        errors: list[BaseException] = []

        def _caller() -> None:
            try:
                # This runs on the main thread, but calls run_async_compat
                # which detects the running loop on the loop thread via
                # run_coroutine_threadsafe.
                r = run_async_compat(_async_add(9, 10), fire_and_forget=False, timeout=5)
                results.append(r)
            except BaseException as exc:
                errors.append(exc)

        t = threading.Thread(target=_caller)
        t.start()
        t.join(timeout=5)

        assert not errors, f"Thread raised: {errors}"
        assert results == [19]

    def test_timeout_raises(self, _loop_thread: None) -> None:
        """fire_and_forget=False with a short timeout should raise TimeoutError.

        The timeout parameter only applies in async context (future.result()).
        In sync context, run_until_complete blocks until completion.
        """
        with pytest.raises(FuturesTimeoutError):
            self._run_on_loop(
                lambda: run_async_compat(_async_slow(10), fire_and_forget=False, timeout=0.1)
            )


# ── connect_async_then ──────────────────────────────────────


class TestWithSubscribe:
    """Tests for the connect-then-act helper."""

    def test_sync_context_connect_then_act(self) -> None:
        """In sync context, connect runs then callback runs immediately."""
        order: list[str] = []

        async def _connect() -> None:
            await asyncio.sleep(0)
            order.append("connected")

        def _on_connected() -> None:
            order.append("subscribed")

        connect_async_then(_connect(), _on_connected)
        assert order == ["connected", "subscribed"]

    def test_sync_context_callback_error_propagates(self) -> None:
        """If the callback raises, the exception propagates in sync context."""

        async def _connect() -> None:
            await asyncio.sleep(0)

        def _fail() -> None:
            raise RuntimeError("subscribe failed")

        with pytest.raises(RuntimeError, match="subscribe failed"):
            connect_async_then(_connect(), _fail)

    def test_sync_context_connect_error_propagates(self) -> None:
        """If connect raises, the callback never runs."""
        order: list[str] = []

        async def _fail_connect() -> None:
            raise ConnectionError("connect failed")

        def _on_connected() -> None:
            order.append("should not run")

        with pytest.raises(ConnectionError, match="connect failed"):
            connect_async_then(_fail_connect(), _on_connected)
        assert order == []

    def test_async_context_orders_connect_before_act(self) -> None:
        """In async context, callback runs after connect completes.

        To hit the async-context path, ``connect_async_then``
        must be called from a coroutine running on the loop thread (so
        ``get_running_loop()`` succeeds).  ``run_coroutine_threadsafe``
        then schedules the connect+callback atomically.
        """
        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        try:
            order: list[str] = []

            async def _connect() -> None:
                await asyncio.sleep(0)
                order.append("connected")

            def _on_connected() -> None:
                order.append("subscribed")

            async def _run() -> None:
                connect_async_then(_connect(), _on_connected)

            future = asyncio.run_coroutine_threadsafe(_run(), loop)
            future.result(timeout=5)
            time.sleep(0.2)
            assert order == ["connected", "subscribed"]
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=2)
            loop.close()


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and integration-style tests."""

    def test_nested_calls_from_sync(self) -> None:
        """Multiple sequential calls should not leak state."""
        r1 = run_async_compat(_async_add(1, 2), fire_and_forget=False)
        r2 = run_async_compat(_async_add(3, 4), fire_and_forget=False)
        r3 = run_async_compat(_async_add(5, 6), fire_and_forget=False)
        assert (r1, r2, r3) == (3, 7, 11)
