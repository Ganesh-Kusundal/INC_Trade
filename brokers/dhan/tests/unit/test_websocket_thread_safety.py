"""Thread-safety tests for DhanMarketFeed and DhanOrderStream callback lists."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream

# ---------------------------------------------------------------------------
# DhanMarketFeed
# ---------------------------------------------------------------------------


def test_market_feed_callback_registration_is_thread_safe():
    """Concurrent on_quote/on_depth registration must not lose callbacks."""
    feed = DhanMarketFeed(
        client_id="CLIENT",
        access_token="TOKEN",
        instruments=[("NSE_EQ", "2885", "LTP")],
    )
    errors: list[Exception] = []
    barrier = threading.Barrier(20)

    def register_quote() -> None:
        try:
            barrier.wait(timeout=2)
            feed.on_quote(lambda d: None)
        except Exception as exc:
            errors.append(exc)

    def register_depth() -> None:
        try:
            barrier.wait(timeout=2)
            feed.on_depth(lambda d: None)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=register_quote) for _ in range(10)] + [
        threading.Thread(target=register_depth) for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(feed._quote_callbacks) == 10
    assert len(feed._depth_callbacks) == 10


def test_market_feed_on_message_snapshots_callbacks():
    """Callbacks invoked during _on_message must see a snapshot; unregistering
    a callback from inside it must not affect the current dispatch."""
    feed = DhanMarketFeed(
        client_id="CLIENT",
        access_token="TOKEN",
        instruments=[("NSE_EQ", "2885", "LTP")],
    )
    received: list[str] = []

    def cb_a(data):
        received.append("a")

    def cb_b(data):
        received.append("b")
        # Mutate the callback list mid-dispatch (safe because iteration uses snapshot)
        feed._quote_callbacks.remove(cb_b)

    feed.on_quote(cb_a)
    feed.on_quote(cb_b)

    feed._on_message(
        MagicMock(),
        {
            "type": "Quote Data",
            "security_id": 2885,
            "last_price": "2500.00",
        },
    )

    assert received == ["a", "b"]


def test_market_feed_is_connected_guarded_by_lock():
    """Connection state transitions should be observable consistently."""
    feed = DhanMarketFeed(
        client_id="CLIENT",
        access_token="TOKEN",
        instruments=[("NSE_EQ", "2885", "LTP")],
    )
    feed._on_connect(MagicMock())
    assert feed.is_connected is True
    feed._on_close(MagicMock())
    assert feed.is_connected is False


# ---------------------------------------------------------------------------
# DhanOrderStream
# ---------------------------------------------------------------------------


def test_order_stream_callback_registration_is_thread_safe():
    """Concurrent on_order_update registration must not lose callbacks."""
    stream = DhanOrderStream(client_id="CLIENT", access_token="TOKEN")
    errors: list[Exception] = []
    barrier = threading.Barrier(10)

    def register() -> None:
        try:
            barrier.wait(timeout=2)
            stream.on_order_update(lambda d: None)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=register) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(stream._order_callbacks) == 10


def test_order_stream_on_update_snapshots_callbacks():
    """Callbacks invoked during _on_order_update must see a snapshot."""
    stream = DhanOrderStream(client_id="CLIENT", access_token="TOKEN")
    received: list[str] = []

    def cb_a(data):
        received.append("a")

    def cb_b(data):
        received.append("b")
        stream._order_callbacks.remove(cb_b)

    stream.on_order_update(cb_a)
    stream.on_order_update(cb_b)

    stream._on_order_update(
        {
            "Type": "order_alert",
            "Data": {"orderNo": "1", "status": "COMPLETE"},
        }
    )

    assert received == ["a", "b"]


def test_order_stream_disconnect_sets_stop_event():
    """disconnect() must clear connection state promptly."""
    stream = DhanOrderStream(client_id="CLIENT", access_token="TOKEN")
    stream._is_connected = True
    stream.disconnect()
    assert stream.is_connected is False
    assert stream._stop_event.is_set()


# ---------------------------------------------------------------------------
# DhanMarketFeed disconnect / reconnect race
# ---------------------------------------------------------------------------


def test_market_feed_disconnect_stops_backoff():
    """disconnect() should set the stop event so _run can exit immediately."""
    feed = DhanMarketFeed(
        client_id="CLIENT",
        access_token="TOKEN",
        instruments=[("NSE_EQ", "2885", "LTP")],
    )

    class FakeFeed:
        def __init__(self):
            self.closed = False

        def run(self):
            # Simulate a dropped connection.
            raise Exception("connection lost")

        def close_connection(self):
            self.closed = True

    fake = FakeFeed()
    feed._feed = fake
    feed._is_connected = True
    feed._stop_event.clear()

    def run_feed():
        feed._run()

    thread = threading.Thread(target=run_feed)
    thread.start()
    time.sleep(0.05)
    feed.disconnect()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert fake.closed
    assert feed.is_connected is False
