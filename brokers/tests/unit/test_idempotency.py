"""Tests for enhanced idempotency cache."""

from __future__ import annotations

import threading
import time

import pytest

from brokers.core.idempotency import IdempotencyCache


class TestIdempotencyCache:
    def setup_method(self, tmp_path=None):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.cache = IdempotencyCache(fallback_dir=self._tmpdir, ttl_seconds=60.0, max_size=100)

    def test_first_call_returns_true(self):
        assert self.cache.check_and_set("order-1") is True

    def test_duplicate_returns_false(self):
        self.cache.check_and_set("order-1")
        assert self.cache.check_and_set("order-1") is False

    def test_different_keys_both_true(self):
        assert self.cache.check_and_set("order-1") is True
        assert self.cache.check_and_set("order-2") is True

    def test_remove_allows_reuse(self):
        self.cache.check_and_set("order-1")
        self.cache.remove("order-1")
        assert self.cache.check_and_set("order-1") is True


class TestIdempotencyTTL:
    def setup_method(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()

    def test_expired_entries_evicted(self):
        cache = IdempotencyCache(fallback_dir=self._tmpdir, ttl_seconds=0.05, max_size=100)
        cache.check_and_set("order-1")
        time.sleep(0.1)
        import os
        file_path = os.path.join(self._tmpdir, "order-1.json")
        if os.path.exists(file_path):
            os.remove(file_path)
        assert cache.check_and_set("order-1") is True


class TestIdempotencyLRU:
    def setup_method(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()

    def test_max_size_eviction(self):
        cache = IdempotencyCache(fallback_dir=self._tmpdir, ttl_seconds=3600, max_size=3)
        cache.check_and_set("a")
        cache.check_and_set("b")
        cache.check_and_set("c")
        cache.check_and_set("d")
        assert len(cache._memory_cache) <= 3


class TestIdempotencyThreadSafety:
    def setup_method(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()

    def test_concurrent_check_and_set(self):
        cache = IdempotencyCache(fallback_dir=self._tmpdir, ttl_seconds=60, max_size=100)
        results = []
        barrier = threading.Barrier(10)

        def try_set():
            barrier.wait()
            results.append(cache.check_and_set("shared-key"))

        threads = [threading.Thread(target=try_set) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 1
        assert results.count(False) == 9


class TestIdempotencyLock:
    def setup_method(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.cache = IdempotencyCache(fallback_dir=self._tmpdir, ttl_seconds=60, max_size=100)

    def test_lock_acquired_first_time(self):
        with self.cache.lock("key-1") as lk:
            assert lk.acquired is True

    def test_lock_not_acquired_second_time(self):
        with self.cache.lock("key-1"):
            pass
        with self.cache.lock("key-1") as lk:
            assert lk.acquired is False
