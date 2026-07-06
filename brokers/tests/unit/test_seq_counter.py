"""Unit tests for streaming tick sequence numbers (Kleppmann blueprint deliverable)."""

from __future__ import annotations

import threading

from inc_trade.infrastructure.seq_counter import SequenceCounter


class TestSequenceCounter:
    def test_starts_at_zero(self) -> None:
        """Counter starts at 0 before any calls."""
        counter = SequenceCounter()
        assert counter.current == 0

    def test_first_call_returns_one(self) -> None:
        """First next() returns 1 (1-based)."""
        counter = SequenceCounter()
        assert counter.next() == 1

    def test_increments_monotonically(self) -> None:
        """Successive calls return monotonically increasing values."""
        counter = SequenceCounter()
        values = [counter.next() for _ in range(10)]
        assert values == list(range(1, 11))

    def test_reset_allows_restart(self) -> None:
        """reset() brings counter back to 0 so next() returns 1 again."""
        counter = SequenceCounter()
        counter.next()
        counter.next()
        counter.reset()
        assert counter.current == 0
        assert counter.next() == 1

    def test_thread_safe_increments(self) -> None:
        """Concurrent increments from multiple threads produce unique seq_nos."""
        counter = SequenceCounter()
        results: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            for _ in range(100):
                val = counter.next()
                with lock:
                    results.append(val)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 1000 values must be unique (no race conditions)
        assert len(results) == 1000
        assert len(set(results)) == 1000
        # Max value must equal total count
        assert max(results) == 1000


class TestTickSeqNoStamping:
    """Verify that _dispatch_tick stamps seq_no on each outgoing tick dict."""

    def _make_streaming(self):
        """Create a minimal BaseWebSocketStreaming subclass for testing."""
        from brokers.adapters.base_streaming import _TICK_SEQ, BaseWebSocketStreaming

        _TICK_SEQ.reset()  # Start fresh for reproducibility

        class _StubStreaming(BaseWebSocketStreaming):
            def _get_ws_headers(self):
                return {}

            def _build_subscribe_message(self, keys):
                return ""

            def _build_unsubscribe_message(self, keys):
                return ""

            def _parse_tick(self, data):
                return data

        return _StubStreaming(ws_url="ws://stub")

    def test_dispatch_tick_stamps_seq_no(self) -> None:
        """Each call to _dispatch_tick should add a seq_no to the tick dict."""
        streaming = self._make_streaming()

        received: list[dict] = []
        streaming.on_tick = received.append

        streaming._dispatch_tick({"symbol": "NIFTY", "ltp": 22000})
        streaming._dispatch_tick({"symbol": "NIFTY", "ltp": 22001})
        streaming._dispatch_tick({"symbol": "NIFTY", "ltp": 22002})

        assert len(received) == 3
        seq_nos = [t["seq_no"] for t in received]
        # Must be strictly monotonically increasing
        assert seq_nos[0] < seq_nos[1] < seq_nos[2]

    def test_seq_no_increments_per_tick(self) -> None:
        """seq_no increments by exactly 1 per tick (no gaps, no duplicates)."""
        streaming = self._make_streaming()

        received: list[dict] = []
        streaming.on_tick = received.append

        n = 5
        for i in range(n):
            streaming._dispatch_tick({"symbol": "X", "ltp": i})

        seq_nos = [t["seq_no"] for t in received]
        diffs = [seq_nos[i + 1] - seq_nos[i] for i in range(len(seq_nos) - 1)]
        assert all(d == 1 for d in diffs), f"Expected all diffs=1, got {diffs}"

    def test_quote_carries_seq_no(self) -> None:
        """Quote built by stream() callback carries the seq_no from the tick dict."""

        from inc_trade.domain.entities import Quote

        streaming = self._make_streaming()

        quotes: list[Quote] = []
        streaming.stream("NIFTY", exchange="NSE", on_tick=quotes.append)

        # Simulate a tick arriving via _dispatch_tick (bypassing WS)
        streaming._dispatch_tick({"symbol": "NIFTY", "ltp": "22500", "seq_no": 0})

        # The Quote should have the stamped seq_no (set by _dispatch_tick)
        assert len(quotes) == 1
        assert quotes[0].seq_no > 0
