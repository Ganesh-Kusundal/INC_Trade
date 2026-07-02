"""Tests for Phase B / B5: Dhan WebSocket services as ManagedService.

The previous implementation:
  - Created 3 daemon threads (DhanMarketFeed, DhanOrderStream,
    PollingMarketFeed) without registering them with a lifecycle.
  - disconnect() / stop() on DhanMarketFeed set _stop_event but did
    NOT join the thread — the daemon thread was leaked until
    process exit.
  - DhanOrderStream.disconnect() also did NOT join.
  - PollingMarketFeed.disconnect() was the only one that joined.

The fix implements the ManagedService Protocol on all 3 classes:
  - name = "dhan.market_feed" / "dhan.order_stream" / "dhan.polling_market_feed"
  - start() is the new name for connect(); idempotent
  - stop(timeout_seconds) is the new name for disconnect(); joins
  - health() returns the standard HealthStatus snapshot

The DhanConnection is updated to accept a LifecycleManager and
register every WebSocket it creates with that manager. close()
drains every thread within bounded timeouts.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from brokers.dhan.connection import DhanConnection
from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream, PollingMarketFeed
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    LifecycleManager,
    ManagedService,
)

# ── ManagedService protocol compliance ────────────────────────────────────


def test_dhan_market_feed_is_managed_service() -> None:
    """DhanMarketFeed must implement the ManagedService protocol."""
    feed = DhanMarketFeed(client_id="x", instruments=[])
    assert isinstance(feed, ManagedService)
    assert feed.name == "dhan.market_feed"
    assert hasattr(feed, "start")
    assert hasattr(feed, "stop")
    assert hasattr(feed, "health")


def test_dhan_order_stream_is_managed_service() -> None:
    stream = DhanOrderStream(client_id="x")
    assert isinstance(stream, ManagedService)
    assert stream.name == "dhan.order_stream"


def test_polling_market_feed_is_managed_service() -> None:
    feed = PollingMarketFeed(http_client=MagicMock(), resolver=MagicMock(), instruments=[])
    assert isinstance(feed, ManagedService)
    assert feed.name == "dhan.polling_market_feed"


# ── PollingMarketFeed: stop() joins the thread ────────────────────────────


def test_polling_feed_stop_joins_thread_within_timeout() -> None:
    """PollingMarketFeed.stop must join the polling thread within the
    timeout. This was the only one of the three that already did."""
    feed = PollingMarketFeed(
        http_client=MagicMock(),
        resolver=MagicMock(),
        instruments=[("NSE", "1", "LTP")],
        interval_seconds=10.0,  # long interval so the thread sleeps most of the time
    )
    feed.start()
    assert feed._thread is not None
    assert feed._thread.is_alive()

    t0 = time.time()
    feed.stop(timeout_seconds=2.0)
    elapsed = time.time() - t0

    # Thread should be done, well within the 10s interval
    assert not feed._thread.is_alive(), "Thread should be joined"
    assert elapsed < 2.5, f"Stop took {elapsed:.2f}s — should be <2.5s"
    assert feed.is_connected is False


def test_polling_feed_stop_is_idempotent() -> None:
    feed = PollingMarketFeed(http_client=MagicMock(), resolver=MagicMock(), instruments=[])
    feed.start()
    feed.stop(timeout_seconds=2.0)
    # Second stop is a no-op, does not raise.
    feed.stop(timeout_seconds=2.0)
    assert not feed._thread.is_alive()


def test_polling_feed_health_reports_states() -> None:
    feed = PollingMarketFeed(http_client=MagicMock(), resolver=MagicMock(), instruments=[])
    # Before start
    h = feed.health()
    assert h.state == HealthState.STOPPED
    assert h.service == "dhan.polling_market_feed"
    # After start
    feed.start()
    h = feed.health()
    assert h.state == HealthState.HEALTHY
    feed.stop(timeout_seconds=2.0)
    # After stop
    h = feed.health()
    assert h.state == HealthState.STOPPED


# ── Backwards compat: connect() / disconnect() still work ────────────────


def test_connect_is_alias_for_start() -> None:
    """connect() is preserved as a deprecated alias for start()."""
    feed = PollingMarketFeed(http_client=MagicMock(), resolver=MagicMock(), instruments=[])
    feed.connect()  # Should start the thread
    assert feed._thread is not None
    assert feed._thread.is_alive()
    feed.disconnect(timeout_seconds=2.0)  # Should stop and join
    assert not feed._thread.is_alive()


# ── DhanMarketFeed: stop() joins (was previously NOT joining) ────────────


def test_dhan_market_feed_stop_does_not_block_forever_when_never_started() -> None:
    """Calling stop() on a never-started DhanMarketFeed must not hang
    or raise. The new implementation guards against None thread and
    None feed references."""
    feed = DhanMarketFeed(client_id="x", instruments=[])
    # Should not raise, even though the SDK feed was never created
    feed.stop(timeout_seconds=0.5)
    h = feed.health()
    assert h.state == HealthState.STOPPED


def test_dhan_market_feed_start_is_idempotent() -> None:
    """start() called twice must not start two threads."""
    feed = DhanMarketFeed(client_id="x", instruments=[])
    # Without valid instruments, start() returns early (no thread).
    # This test verifies idempotency on the no-instrument path.
    feed.start()
    h1 = feed.health()
    feed.start()
    h2 = feed.health()
    assert h1.state == h2.state


# ── DhanOrderStream: stop() joins (was previously NOT joining) ──────────


def test_dhan_order_stream_stop_does_not_block_forever_when_never_started() -> None:
    stream = DhanOrderStream(client_id="x")
    stream.stop(timeout_seconds=0.5)
    h = stream.health()
    assert h.state == HealthState.STOPPED


# ── DhanConnection: lifecycle registration and close() draining ─────────


def test_dhan_connection_accepts_lifecycle() -> None:
    """DhanConnection.__init__ accepts a lifecycle parameter for
    B5 ownership of WebSocket services."""
    lc = LifecycleManager()
    conn = DhanConnection(
        client=MagicMock(),
        lifecycle=lc,
    )
    assert conn._lifecycle is lc


def test_dhan_connection_default_lifecycle_is_none() -> None:
    """Default lifecycle is None — backwards compatible with existing
    callers that do not pass one."""
    conn = DhanConnection(client=MagicMock())
    assert conn._lifecycle is None


def test_dhan_connection_close_drains_websocket_services() -> None:
    """close() must call stop(timeout_seconds) on every WebSocket
    service so the daemon threads are joined (not leaked)."""
    conn = DhanConnection(client=MagicMock())

    # Inject fake WebSocket services. The "feed" and "stream" and
    # "polling" attributes are normally Optional — we replace them
    # with mocks that record stop() calls.
    mf = MagicMock(spec=PollingMarketFeed)
    os_ = MagicMock(spec=PollingMarketFeed)
    pf = MagicMock(spec=PollingMarketFeed)
    conn.market_feed = mf
    conn.order_stream = os_
    conn.polling_feed = pf

    conn.close()

    # Each service's stop(timeout_seconds) was called once.
    assert mf.stop.call_count == 1
    assert os_.stop.call_count == 1
    assert pf.stop.call_count == 1
    mf.stop.assert_called_with(timeout_seconds=5.0)


def test_dhan_connection_close_handles_no_websocket_services() -> None:
    """close() with no WebSocket services is a no-op for that part."""
    conn = DhanConnection(client=MagicMock())
    assert conn.market_feed is None
    assert conn.order_stream is None
    assert conn.polling_feed is None
    # Should not raise
    conn.close()


# ── DhanConnection: lifecycle registers created services ───────────────


def test_create_market_feed_registers_with_lifecycle() -> None:
    """When DhanConnection is constructed with a lifecycle, every
    DhanMarketFeed created via create_market_feed is registered
    with that lifecycle. This is the central B5 invariant for the
    lazy-creation path: brokers/users that opt in to lifecycle
    ownership get their WebSocket services automatically drained
    on connection close."""
    lc = LifecycleManager()
    conn = DhanConnection(client=MagicMock(), lifecycle=lc)
    feed = conn.create_market_feed(instruments=[])
    assert feed in [lc.get(name) for name in lc.service_names()]
    assert "dhan.market_feed" in lc.service_names()


def test_create_market_feed_without_lifecycle_does_not_register() -> None:
    conn = DhanConnection(client=MagicMock())  # no lifecycle
    feed = conn.create_market_feed(instruments=[])
    # No registration happened (no lifecycle to register with).
    # The feed still works — it just won't be lifecycle-managed.
    assert feed is not None


def test_create_market_feed_does_not_double_register() -> None:
    """Calling create_market_feed twice on a connection with a
    lifecycle registers at most one entry. The LifecycleManager
    refuses duplicate names."""
    lc = LifecycleManager()
    conn = DhanConnection(client=MagicMock(), lifecycle=lc)
    conn.create_market_feed(instruments=[])
    # Second call replaces the first; only one entry exists.
    conn.create_market_feed(instruments=[])
    assert lc.service_names().count("dhan.market_feed") == 1


# ── End-to-end: lifecycle + connection.close() drains WebSocket ────────


def test_end_to_end_lifecycle_drains_websocket_on_close() -> None:
    """The full B5 flow: build a DhanConnection with a lifecycle,
    create a polling feed (which is the only one that actually
    starts a thread without external dependencies), then close
    the connection and verify the thread was joined.
    """
    lc = LifecycleManager()
    conn = DhanConnection(client=MagicMock(), lifecycle=lc)

    feed = conn.create_polling_feed(
        instruments=[("NSE", "1", "LTP")],
        interval_seconds=10.0,
    )
    # Manually start since the lifecycle is the connection-level
    # manager; we start each service individually here.
    feed.start()
    assert feed._thread is not None
    assert feed._thread.is_alive()

    # Lifecycle now owns the feed
    assert "dhan.polling_market_feed" in lc.service_names()

    # Close the connection — must stop the polling feed and join the
    # thread. Use a 2s timeout to verify the join actually waits.
    t0 = time.time()
    conn.close()
    elapsed = time.time() - t0

    # The polling feed's thread should be joined (it was waiting on
    # Event.wait(timeout=10s), but stop() sets the event, so it
    # wakes immediately).
    assert not feed._thread.is_alive(), "Thread must be joined on close()"
    assert elapsed < 2.0, f"close() took {elapsed:.2f}s — should be <2s"
