"""Tests for DuckDB connection pool."""

from __future__ import annotations

import threading
import time

from infrastructure.db.duckdb_pool import DuckDBPool, get_pool, shutdown_pool


class TestDuckDBPool:
    """Unit tests for DuckDBPool."""

    def test_acquire_returns_connection(self):
        pool = DuckDBPool(max_size=2)
        conn = pool.acquire()
        assert conn is not None
        result = conn.execute("SELECT 1").fetchone()
        assert result[0] == 1
        pool.release(conn)
        pool.close_all()

    def test_release_reuses_connection(self):
        pool = DuckDBPool(max_size=2)
        conn1 = pool.acquire()
        pool.release(conn1)
        conn2 = pool.acquire()
        assert conn2 is conn1
        pool.release(conn2)
        pool.close_all()

    def test_respects_max_size(self):
        pool = DuckDBPool(max_size=2)
        c1 = pool.acquire()
        c2 = pool.acquire()
        assert pool.size == 2
        pool.release(c1)
        pool.release(c2)
        pool.close_all()

    def test_acquire_blocks_when_exhausted(self):
        pool = DuckDBPool(max_size=1, timeout=0.1)
        c1 = pool.acquire()
        try:
            pool.acquire()
            raise AssertionError("Should have raised RuntimeError")
        except RuntimeError as e:
            assert "exhausted" in str(e)
        finally:
            pool.release(c1)
            pool.close_all()

    def test_size_tracks_live_connections(self):
        pool = DuckDBPool(max_size=2)
        c1 = pool.acquire()
        assert pool.size == 1
        c2 = pool.acquire()
        assert pool.size == 2
        pool.release(c1)
        assert pool.size == 2
        pool.release(c2)
        assert pool.size == 2
        pool.close_all()

    def test_close_all_resets(self):
        pool = DuckDBPool(max_size=2)
        pool.acquire()
        pool.acquire()
        pool.close_all()
        assert pool.size == 0

    def test_concurrent_acquire_release(self):
        pool = DuckDBPool(max_size=4)
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(20):
                    conn = pool.acquire()
                    time.sleep(0.001)
                    pool.release(conn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        assert pool.size <= 4
        pool.close_all()


class TestModulePool:
    """Tests for the module-level get_pool/shutdown_pool."""

    def test_get_pool_returns_singleton(self):
        shutdown_pool()
        p1 = get_pool()
        p2 = get_pool()
        assert p1 is p2
        shutdown_pool()

    def test_shutdown_pool_resets(self):
        p1 = get_pool()
        shutdown_pool()
        p2 = get_pool()
        assert p1 is not p2
        shutdown_pool()
