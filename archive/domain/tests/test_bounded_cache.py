"""Tests for bounded LRU cache pattern (set + deque).

This pattern is used by PositionManager._processed_trade_ids to track
processed trade IDs with bounded memory. The set provides O(1) lookup;
the deque provides FIFO eviction order with automatic maxlen enforcement.

The key correctness invariant is that when the deque is at capacity,
peeking at [0] BEFORE appending ensures exactly one element is evicted
from both the set and the deque.
"""

from __future__ import annotations

import threading
from collections import deque


def _make_bounded_cache(maxlen: int = 5):
    """Create a bounded LRU cache matching PositionManager pattern."""
    s: set[str] = set()
    q: deque[str] = deque(maxlen=maxlen)
    return s, q


def _add_to_cache(s: set, q: deque, item: str) -> None:
    """Add an item to the bounded cache (peek-before-append pattern).

    If the item is already in the set (duplicate), skip entirely to avoid
    spurious eviction when the duplicate sits at the deque head.
    """
    if item in s:
        return  # dedup: don't append duplicate to deque
    if len(q) == q.maxlen:
        oldest = q[0]
        s.discard(oldest)
    s.add(item)
    q.append(item)


class TestBoundedCacheEviction:
    def test_add_within_capacity(self):
        s, q = _make_bounded_cache(3)
        for i in ["a", "b", "c"]:
            _add_to_cache(s, q, i)
        assert len(q) == 3
        assert len(s) == 3
        assert list(q) == ["a", "b", "c"]

    def test_eviction_at_capacity(self):
        s, q = _make_bounded_cache(3)
        for i in ["a", "b", "c"]:
            _add_to_cache(s, q, i)
        _add_to_cache(s, q, "d")
        assert len(q) == 3
        assert len(s) == 3
        assert list(q) == ["b", "c", "d"]
        assert "a" not in s

    def test_multiple_evictions(self):
        s, q = _make_bounded_cache(3)
        for i in ["a", "b", "c"]:
            _add_to_cache(s, q, i)
        for i in ["d", "e", "f"]:
            _add_to_cache(s, q, i)
        assert len(q) == 3
        assert len(s) == 3
        assert list(q) == ["d", "e", "f"]
        assert "a" not in s
        assert "b" not in s
        assert "c" not in s

    def test_no_eviction_when_not_full(self):
        s, q = _make_bounded_cache(5)
        for i in ["a", "b"]:
            _add_to_cache(s, q, i)
        assert len(q) == 2
        assert len(s) == 2
        assert list(q) == ["a", "b"]

    def test_exact_capacity(self):
        s, q = _make_bounded_cache(1)
        _add_to_cache(s, q, "a")
        assert len(q) == 1
        _add_to_cache(s, q, "b")
        assert len(q) == 1
        assert list(q) == ["b"]
        assert "a" not in s

    def test_dedup_within_capacity(self):
        s, q = _make_bounded_cache(3)
        _add_to_cache(s, q, "a")
        _add_to_cache(s, q, "b")
        # Duplicate "a" should be a no-op (no spurious eviction)
        _add_to_cache(s, q, "a")
        assert len(s) == 2
        assert len(q) == 2
        assert list(q) == ["a", "b"]

    def test_dedup_at_head_no_spurious_eviction(self):
        """Critical: duplicate at deque head must not evict itself."""
        s, q = _make_bounded_cache(3)
        _add_to_cache(s, q, "a")  # head
        _add_to_cache(s, q, "b")
        _add_to_cache(s, q, "c")
        # "a" is at the head; adding it again must NOT evict "a"
        _add_to_cache(s, q, "a")
        assert len(s) == 3
        assert len(q) == 3
        assert list(q) == ["a", "b", "c"]
        assert "a" in s

    def test_dedup_after_eviction(self):
        """After "a" is evicted, re-adding "a" should succeed."""
        s, q = _make_bounded_cache(3)
        _add_to_cache(s, q, "a")
        _add_to_cache(s, q, "b")
        _add_to_cache(s, q, "c")
        # Evict "a"
        _add_to_cache(s, q, "d")
        assert "a" not in s
        # Re-add "a" — should succeed since it was evicted
        _add_to_cache(s, q, "a")
        assert len(s) == 3
        assert len(q) == 3
        assert "a" in s
        assert list(q) == ["b", "c", "d", "a"][-3:]  # ["c", "d", "a"]

    def test_eviction_removes_from_set(self):
        """Verify that eviction removes the EXACT element that was evicted."""
        s, q = _make_bounded_cache(2)
        _add_to_cache(s, q, "x")
        _add_to_cache(s, q, "y")
        _add_to_cache(s, q, "z")
        assert "x" not in s
        assert "y" in s
        assert "z" in s

    def test_large_capacity(self):
        s, q = _make_bounded_cache(10_000)
        for i in range(10_000):
            _add_to_cache(s, q, str(i))
        assert len(q) == 10_000
        assert len(s) == 10_000
        # Add one more to trigger eviction
        _add_to_cache(s, q, "overflow")
        assert len(q) == 10_000
        assert "0" not in s
        assert "overflow" in s


class TestBoundedCacheThreadSafety:
    def test_concurrent_adds(self):
        """Verify no data corruption under concurrent adds."""
        s, q = _make_bounded_cache(100)
        lock = threading.Lock()
        errors = []

        def _worker(thread_id: int):
            try:
                for i in range(200):
                    item = f"t{thread_id}_{i}"
                    with lock:
                        _add_to_cache(s, q, item)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent adds raised: {errors}"
        assert len(q) == 100
        assert len(s) == 100

    def test_concurrent_read_and_add(self):
        """Verify reads during adds don't corrupt state."""
        s, q = _make_bounded_cache(100)
        lock = threading.Lock()
        errors = []

        def _writer():
            try:
                for i in range(200):
                    with lock:
                        _add_to_cache(s, q, str(i))
            except Exception as e:
                errors.append(e)

        def _reader():
            try:
                for _ in range(200):
                    with lock:
                        _ = str(s)
                        _ = list(q)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_writer),
            threading.Thread(target=_reader),
            threading.Thread(target=_writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent read/write raised: {errors}"
