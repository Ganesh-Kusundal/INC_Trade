"""Thread-safe DuckDB connection pool for in-memory analytics.

DEPRECATED: This module is a backward-compatibility shim.
The canonical implementation is in ``datalake.core.duckdb_utils.InMemoryDuckDBPool``.
All new code should import from ``datalake.core.duckdb_utils`` directly.
"""

from __future__ import annotations

from datalake.core.duckdb_utils import InMemoryDuckDBPool as DuckDBPool
from datalake.core.duckdb_utils import get_memory_pool

# Backward-compat aliases — existing callers use these names
DuckDBPool = DuckDBPool  # re-export


def get_pool() -> DuckDBPool:
    """Return the process-wide InMemoryDuckDBPool singleton.

    Backward-compat alias for ``get_memory_pool()``.
    """
    return get_memory_pool()


def shutdown_pool() -> None:
    """Shut down the module-wide default pool (for graceful shutdown).

    Resets the singleton so the next get_pool() call creates a fresh pool.
    Uses the public reset_memory_pool() API instead of accessing private state.
    """
    from datalake.core.duckdb_utils import reset_memory_pool
    reset_memory_pool()
