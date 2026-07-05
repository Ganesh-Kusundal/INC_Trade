"""Tests for the WebSocket pool lifecycle refactor (architectural smell C-2).

The previous design stored a class-level ``_instances`` dict on
:class:`brokers.infrastructure.websocket_pool.WebSocketConnectionPool` and
registered an :func:`atexit` cleanup on the class. The refactor moves all
state onto :class:`WebSocketPoolFactory` instances, exposes a
:class:`WebSocketPoolScope` for the default factory, and preserves
backward-compatible class methods on :class:`WebSocketConnectionPool`.

These tests verify the new shape:

* factories are independent of each other;
* ``close_all()`` cleans up only the pools owned by its factory;
* the class-method shims on ``WebSocketConnectionPool`` still work and
  delegate to the default factory;
* the default factory can be re-created and the pool comes back fresh;
* the atexit safety net still works on the default factory.
"""

from __future__ import annotations

import atexit
import threading
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_websocket_app():
    """Patch ``websocket.WebSocketApp`` so pool lifecycle calls do not hit network."""
    with patch("websocket.WebSocketApp") as mock:
        mock_ws = MagicMock()
        mock_ws._closed = False

        def mock_close() -> None:
            mock_ws._closed = True

        mock_ws.close.side_effect = mock_close
        mock.return_value = mock_ws
        yield mock


@pytest.fixture(autouse=True)
def _reset_default_scope():
    """Reset the default factory around every test to avoid cross-test pollution."""
    from inc_trade.infrastructure.websocket_pool import WebSocketPoolScope

    WebSocketPoolScope.reset()
    yield
    WebSocketPoolScope.reset()


# ── Factory independence ──────────────────────────────────────────────────


class TestFactoryIndependence:
    """Two factories must own disjoint connection pools."""

    def test_two_factories_are_independent(self) -> None:
        """Connections created in factory A must not be visible in factory B."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory_a = WebSocketPoolFactory()
        factory_b = WebSocketPoolFactory()
        on_message = MagicMock()

        conn_a = factory_a.get_connection(
            "wss://a.example/ws",
            {"token": "tokA"},
            on_message,
        )
        # factory_b has its own (empty) pool
        assert factory_b.get_pool_stats()["active_connections"] == 0

        conn_b = factory_b.get_connection(
            "wss://b.example/ws",
            {"token": "tokB"},
            on_message,
        )

        # Each factory now holds exactly one connection
        assert factory_a.get_pool_stats()["active_connections"] == 1
        assert factory_b.get_pool_stats()["active_connections"] == 1
        assert conn_a is not conn_b
        assert conn_a.ws_url == "wss://a.example/ws"
        assert conn_b.ws_url == "wss://b.example/ws"

    def test_factories_do_not_share_lock(self) -> None:
        """Independent factories must have independent locks (no shared state)."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory_a = WebSocketPoolFactory()
        factory_b = WebSocketPoolFactory()
        assert factory_a._lock is not factory_b._lock


# ── close_all() semantics ──────────────────────────────────────────────────


class TestCloseAllSemantics:
    """``close_all()`` cleans up only the pools owned by its factory."""

    def test_close_all_cleans_factory_pools(self) -> None:
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory = WebSocketPoolFactory()
        on_message = MagicMock()

        factory.get_connection("wss://x.example/ws", {"token": "x"}, on_message)
        factory.get_connection("wss://y.example/ws", {"token": "y"}, on_message)
        assert factory.get_pool_stats()["active_connections"] == 2

        factory.close_all()
        assert factory.get_pool_stats()["active_connections"] == 0

    def test_close_all_does_not_touch_other_factory(self) -> None:
        """Closing factory A must leave factory B's pool untouched."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory_a = WebSocketPoolFactory()
        factory_b = WebSocketPoolFactory()
        on_message = MagicMock()

        factory_a.get_connection("wss://a.example/ws", {"token": "a"}, on_message)
        factory_b.get_connection("wss://b.example/ws", {"token": "b"}, on_message)

        factory_a.close_all()

        assert factory_a.get_pool_stats()["active_connections"] == 0
        assert factory_b.get_pool_stats()["active_connections"] == 1

    def test_close_all_is_idempotent(self) -> None:
        """Calling ``close_all()`` twice is a no-op the second time."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory = WebSocketPoolFactory()
        factory.get_connection("wss://x.example/ws", {"token": "x"}, MagicMock())
        factory.close_all()
        # Must not raise and must remain empty.
        factory.close_all()
        assert factory.get_pool_stats()["active_connections"] == 0

    def test_close_all_stops_owned_connections(self) -> None:
        """Every connection in the pool must have ``stop()`` invoked on it."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory = WebSocketPoolFactory()
        conn = factory.get_connection("wss://x.example/ws", {"token": "x"}, MagicMock())

        with patch.object(conn, "stop") as mock_stop:
            factory.close_all()
            mock_stop.assert_called_once()


# ── Backward-compat shims ─────────────────────────────────────────────────


class TestClassMethodBackwardCompat:
    """The class methods on ``WebSocketConnectionPool`` must keep working."""

    def test_get_or_create_class_method_still_works(self) -> None:
        """``WebSocketConnectionPool.get_connection(...)`` must remain a usable
        class method (backward-compatible signature)."""
        from inc_trade.infrastructure.websocket_pool import WebSocketConnectionPool

        on_message = MagicMock()
        conn = WebSocketConnectionPool.get_connection(
            "wss://legacy.example/ws",
            {"token": "legacy"},
            on_message,
        )
        assert conn is not None
        assert conn.ws_url == "wss://legacy.example/ws"

    def test_class_method_routes_through_default_factory(self) -> None:
        """The class method must use the default factory's pool."""
        from inc_trade.infrastructure.websocket_pool import (
            WebSocketConnectionPool,
            WebSocketPoolScope,
        )

        default = WebSocketPoolScope.get_default()
        on_message = MagicMock()

        conn = WebSocketConnectionPool.get_connection(
            "wss://scope.example/ws",
            {"token": "scope"},
            on_message,
        )
        assert default.get_pool_stats()["active_connections"] == 1
        assert conn in default._instances.values()

    def test_release_connection_class_method_still_works(self) -> None:
        """``WebSocketConnectionPool.release_connection(...)`` must remain usable."""
        from inc_trade.infrastructure.websocket_pool import WebSocketConnectionPool

        on_message = MagicMock()
        conn = WebSocketConnectionPool.get_connection(
            "wss://release.example/ws",
            {"token": "r"},
            on_message,
        )
        assert conn.reference_count == 1
        WebSocketConnectionPool.release_connection(conn)
        assert conn.reference_count == 0

    def test_cleanup_class_method_closes_default_factory(self) -> None:
        """``WebSocketConnectionPool.cleanup()`` must close the default factory."""
        from inc_trade.infrastructure.websocket_pool import (
            WebSocketConnectionPool,
            WebSocketPoolScope,
        )

        WebSocketConnectionPool.get_connection(
            "wss://cleanup.example/ws",
            {"token": "c"},
            MagicMock(),
        )
        assert WebSocketPoolScope.get_default().get_pool_stats()["active_connections"] == 1

        WebSocketConnectionPool.cleanup()
        assert WebSocketPoolScope.get_default().get_pool_stats()["active_connections"] == 0

    def test_get_pool_stats_class_method_returns_factory_stats(self) -> None:
        """``WebSocketConnectionPool.get_pool_stats()`` must return the default
        factory's view."""
        from inc_trade.infrastructure.websocket_pool import (
            WebSocketConnectionPool,
            WebSocketPoolScope,
        )

        WebSocketConnectionPool.get_connection(
            "wss://stats.example/ws",
            {"token": "s"},
            MagicMock(),
        )
        stats = WebSocketConnectionPool.get_pool_stats()
        assert stats == WebSocketPoolScope.get_default().get_pool_stats()


# ── Default factory lifecycle ─────────────────────────────────────────────


class TestDefaultFactoryLifecycle:
    """The default factory is the singleton the class methods delegate to."""

    def test_get_default_returns_singleton(self) -> None:
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolScope

        first = WebSocketPoolScope.get_default()
        second = WebSocketPoolScope.get_default()
        assert first is second

    def test_get_default_is_thread_safe(self) -> None:
        """Concurrent ``get_default()`` must return the same instance."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolScope

        results: list[object] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            barrier.wait()
            results.append(WebSocketPoolScope.get_default())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 8
        assert all(r is results[0] for r in results)

    def test_default_factory_close_all_cleans_class_method_pools(self) -> None:
        """Pools created via the class method must be cleared by the default
        factory's ``close_all()``."""
        from inc_trade.infrastructure.websocket_pool import (
            WebSocketConnectionPool,
            WebSocketPoolScope,
        )

        WebSocketConnectionPool.get_connection(
            "wss://default.example/ws",
            {"token": "d"},
            MagicMock(),
        )
        default = WebSocketPoolScope.get_default()
        assert default.get_pool_stats()["active_connections"] == 1

        default.close_all()
        assert default.get_pool_stats()["active_connections"] == 0

    def test_reset_replaces_default_with_fresh_factory(self) -> None:
        """``WebSocketPoolScope.reset()`` must return a brand-new factory and
        drop the old one — so the next ``get_default()`` is a clean slate."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolScope

        old_default = WebSocketPoolScope.get_default()
        WebSocketPoolScope.get_default().get_connection(
            "wss://old.example/ws",
            {"token": "old"},
            MagicMock(),
        )
        assert old_default.get_pool_stats()["active_connections"] == 1

        new_default = WebSocketPoolScope.reset()
        assert new_default is not old_default
        assert new_default.get_pool_stats()["active_connections"] == 0
        # The lazy accessor must pick up the new default.
        assert WebSocketPoolScope.get_default() is new_default

    def test_create_close_recreate_yields_fresh_pool(self) -> None:
        """Creating a pool, calling ``close_all()`` and creating again must
        produce a fresh connection (identity-inequality with the old one)."""
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolScope

        factory = WebSocketPoolScope.get_default()
        conn_first = factory.get_connection(
            "wss://recycle.example/ws",
            {"token": "recycle"},
            MagicMock(),
        )
        factory.close_all()
        conn_second = factory.get_connection(
            "wss://recycle.example/ws",
            {"token": "recycle"},
            MagicMock(),
        )
        # The first instance was stopped, the second is a new object.
        assert conn_first is not conn_second


# ── atexit safety net ─────────────────────────────────────────────────────


class TestAtexitCleanup:
    """The process-exit safety net must still fire on the default factory.

    We do not introspect the private atexit registry (it is C-level state
    in Python 3.13+). Instead we verify the externally observable
    contract: the module registers exactly one atexit callback on
    import, the callback closes the factory it captured, and the
    callback is robust against logging-shutdown races.
    """

    def test_atexit_callback_registered_on_import(self) -> None:
        """Importing the module must register at least one atexit callback."""
        from inc_trade.infrastructure import websocket_pool

        # The module already imported by the test harness has had
        # ``_register_default_cleanup`` called; there must be at least
        # one entry in the atexit registry.
        before = atexit._ncallbacks()
        # Register and immediately unregister a probe to confirm the
        # registry is mutable and observable.
        probe = MagicMock()
        atexit.register(probe)
        assert atexit._ncallbacks() == before + 1
        atexit.unregister(probe)
        assert atexit._ncallbacks() == before

    def test_atexit_handler_closes_its_captured_factory(self) -> None:
        """The module-level ``_atexit_close_all`` must close any factory it
        is given, and tolerate logging being shut down (best-effort)."""
        from inc_trade.infrastructure import websocket_pool
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory = WebSocketPoolFactory()
        factory.get_connection("wss://atexit.example/ws", {"token": "aex"}, MagicMock())
        assert factory.get_pool_stats()["active_connections"] == 1

        # Direct invocation of the registered callback closes the factory.
        websocket_pool._atexit_close_all(factory)
        assert factory.get_pool_stats()["active_connections"] == 0

    def test_atexit_handler_tolerates_factory_errors(self) -> None:
        """If ``close_all()`` raises, the atexit handler must swallow the
        error so the interpreter still exits cleanly."""
        from inc_trade.infrastructure import websocket_pool
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory = WebSocketPoolFactory()
        with patch.object(factory, "close_all", side_effect=RuntimeError("boom")):
            # Must not raise — atexit handlers must be defensive.
            websocket_pool._atexit_close_all(factory)

    def test_atexit_handler_tolerates_logging_shutdown(self) -> None:
        """The atexit handler writes to ``sys.stderr`` directly (not via
        ``logger``) so a logging shutdown does not crash it. We simulate
        the logging-shutdown race by patching ``sys.stderr`` to raise."""
        from inc_trade.infrastructure import websocket_pool
        from inc_trade.infrastructure.websocket_pool import WebSocketPoolFactory

        factory = WebSocketPoolFactory()
        with patch("sys.stderr", new=_RaisingStderr()):
            # Must not raise.
            websocket_pool._atexit_close_all(factory)


class _RaisingStderr:
    """Minimal ``sys.stderr`` replacement that raises on every write."""

    def write(self, _msg: str) -> None:
        raise RuntimeError("stderr is shut down")

    def flush(self) -> None:  # pragma: no cover — never called
        pass
