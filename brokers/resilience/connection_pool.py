"""Connection Pool Manager for broker HTTP sessions.

Manages requests.Session instances keyed by broker type with:
- HTTPAdapter(pool_connections=50, pool_maxsize=100) for connection reuse
- Thread-safe session creation with double-checked locking
- Singleton pattern for global access
- Lifecycle management via close_all()

Usage
-----
    from brokers.common.connection_pool import get_connection_pool

    # Application startup
    pool = get_connection_pool()

    # Get session for broker
    session = pool.get_session("upstox")
    http_client = UpstoxHttpClient(..., session=session)

    # Application shutdown
    pool.close_all()

Thread Safety
-------------
- Session creation uses double-checked locking
- Once created, sessions are thread-safe for concurrent use
- close_all() is safe to call from any thread
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# Known broker types
BROKER_TYPES = {"upstox", "dhan", "paper"}

# Default pool configuration
DEFAULT_POOL_CONNECTIONS = 50
DEFAULT_POOL_MAXSIZE = 100


class ConnectionPoolManager:
    """Manages HTTP connection pools for broker clients.

    Provides thread-safe access to requests.Session instances with
    optimized connection pooling for high-throughput trading systems.

    Connection Pool Configuration
    -----------------------------
    - pool_connections: 50 (number of connection pools to cache)
    - pool_maxsize: 100 (maximum connections per pool)
    - max_retries: 3 (automatic retry on transient failures)

    Thread Safety
    -------------
    - Session creation uses double-checked locking pattern
    - Once created, requests.Session is thread-safe for concurrent use
    - close_all() acquires exclusive lock during cleanup

    Singleton Pattern
    -----------------
    Use get_connection_pool() for global access. Direct instantiation
    is discouraged but supported for testing.

    Lifecycle
    ---------
    1. Application startup: get_connection_pool()
    2. Broker initialization: pool.get_session("upstox")
    3. Broker operations: session reused for all HTTP calls
    4. Application shutdown: pool.close_all()
    """

    def __init__(
        self,
        pool_connections: int = 50,
        pool_maxsize: int = 100,
        max_retries: int = 3,
    ) -> None:
        self._pool_connections = pool_connections
        self._pool_maxsize = pool_maxsize
        self._max_retries = max_retries

        self._sessions: dict[str, requests.Session] = {}
        self._lock = threading.RLock()
        self._closed = False

        logger.info(
            "ConnectionPoolManager initialized "
            "(pool_connections=%d, pool_maxsize=%d, max_retries=%d)",
            pool_connections,
            pool_maxsize,
            max_retries,
        )

    def get_session(self, broker_key: str) -> requests.Session:
        """Get or create a session for the given broker.

        Thread-safe lazy initialization. The session is created on first
        access and reused for subsequent calls.

        Parameters
        ----------
        broker_key:
            Unique key for the broker (e.g., "upstox", "dhan").

        Returns
        -------
        requests.Session:
            Configured session with connection pooling.

        Example
        -------
            session = pool.get_session("upstox")
            response = session.get("https://api.upstox.com/v2/portfolio/positions")
        """
        # Fast path: session already exists (no lock needed)
        if broker_key in self._sessions:
            return self._sessions[broker_key]

        # Slow path: create session with lock
        with self._lock:
            if self._closed:
                raise RuntimeError("ConnectionPoolManager is closed, cannot create new sessions")

            # Double-check after acquiring lock
            if broker_key in self._sessions:
                return self._sessions[broker_key]

            # Create new session
            session = self._create_session()
            self._sessions[broker_key] = session

            logger.info("Created session for broker '%s'", broker_key)
            return session

    def _create_session(self) -> requests.Session:
        """Create a new session with optimized connection pooling.

        Returns
        -------
        requests.Session:
            Session with HTTPAdapter for connection reuse.
        """
        session = requests.Session()

        # Configure connection pooling for HTTP and HTTPS
        adapter = HTTPAdapter(
            pool_connections=self._pool_connections,
            pool_maxsize=self._pool_maxsize,
            max_retries=self._max_retries,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers (optional, can be overridden per-request)
        session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        return session

    def close_all(self) -> None:
        """Close all sessions and release connection pools.

        Thread-safe. Safe to call multiple times.
        After closing, get_session() will raise RuntimeError.

        Call this during application shutdown to ensure clean
        connection release.
        """
        with self._lock:
            if self._closed:
                logger.debug("ConnectionPoolManager already closed")
                return

            self._closed = True
            closed_count = 0

            for broker_key, session in self._sessions.items():
                try:
                    session.close()
                    closed_count += 1
                    logger.debug("Closed session for broker '%s'", broker_key)
                except Exception as exc:
                    logger.warning(
                        "Error closing session for broker '%s': %s",
                        broker_key,
                        exc,
                    )

            self._sessions.clear()
            logger.info(
                "ConnectionPoolManager closed %d sessions",
                closed_count,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get connection pool statistics.

        Returns
        -------
        dict:
            Statistics including session count, pool config, etc.
        """
        return {
            "session_count": len(self._sessions),
            "broker_keys": list(self._sessions.keys()),
            "pool_connections": self._pool_connections,
            "pool_maxsize": self._pool_maxsize,
            "max_retries": self._max_retries,
            "is_closed": self._closed,
        }

    def __enter__(self) -> ConnectionPoolManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - closes all sessions."""
        self.close_all()


# ---------------------------------------------------------------------------
# Singleton Access
# ---------------------------------------------------------------------------

_connection_pool: ConnectionPoolManager | None = None
_pool_lock = threading.Lock()


def get_connection_pool() -> ConnectionPoolManager:
    """Get the global ConnectionPoolManager singleton.

    Thread-safe lazy initialization. The singleton is created on first
    access and reused for subsequent calls.

    Returns
    -------
    ConnectionPoolManager:
        Global connection pool manager instance.

    Example
    -------
        pool = get_connection_pool()
        session = pool.get_session("upstox")
    """
    global _connection_pool

    # Fast path: singleton already created (no lock needed)
    if _connection_pool is not None:
        return _connection_pool

    # Slow path: create singleton with lock
    with _pool_lock:
        # Double-check after acquiring lock
        if _connection_pool is None:
            _connection_pool = ConnectionPoolManager()
            logger.info("Created global ConnectionPoolManager singleton")

        return _connection_pool


def reset_connection_pool() -> None:
    """Reset the global singleton (for testing only).

    This closes the current pool and clears the singleton reference.
    The next call to get_connection_pool() will create a new instance.

    WARNING: Do NOT call this in production code. Only use in tests.
    """
    global _connection_pool

    with _pool_lock:
        if _connection_pool is not None:
            try:
                _connection_pool.close_all()
            except Exception as exc:
                logger.warning("Error closing pool during reset: %s", exc)
            _connection_pool = None
            logger.info("Reset global ConnectionPoolManager singleton")


# ---------------------------------------------------------------------------
# Convenience Functions (for agent test compatibility)
# ---------------------------------------------------------------------------


def get_broker_session(broker_type: str) -> requests.Session:
    """Convenience function to get a session for a specific broker.

    This is a shorthand for get_connection_pool().get_session(broker_type).

    Parameters
    ----------
    broker_type:
        Broker identifier (e.g., "upstox", "dhan").

    Returns
    -------
    requests.Session:
        A configured requests.Session instance.
    """
    return get_connection_pool().get_session(broker_type)


def close_broker_sessions() -> None:
    """Convenience function to close all broker sessions.

    This is a shorthand for get_connection_pool().close_all().
    Call this during application shutdown.
    """
    get_connection_pool().close_all()


__all__ = [
    "BROKER_TYPES",
    "DEFAULT_POOL_CONNECTIONS",
    "DEFAULT_POOL_MAXSIZE",
    "ConnectionPoolManager",
    "close_broker_sessions",
    "get_broker_session",
    "get_connection_pool",
    "reset_connection_pool",
]
