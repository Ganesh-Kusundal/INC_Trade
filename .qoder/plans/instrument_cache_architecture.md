# Architecture: Instrument Cache Lifecycle Design

## Problem Analysis

### Current Architecture Issues

1. **No Cache Population Strategy**
   - `load_instruments()` loads into memory only
   - SQLite cache remains empty
   - Every CLI startup pays full CSV parse cost (27-37s)

2. **No Failure Handling**
   - If CSV download fails, no fallback to stale cache
   - If SQLite insert fails, no retry or graceful degradation
   - No logging of cache hit/miss/failure

3. **No Observability**
   - Can't tell if cache is being used
   - Can't measure cache performance
   - Can't debug cache failures

4. **Blocking Lazy Refresh**
   - Lazy refresh happens during initialization
   - Blocks entire CLI startup for 27s
   - No async or deferred loading

## Proper Architecture Design

### Cache Lifecycle States

```
┌─────────────────────────────────────────────────────────────┐
│                   Cache State Machine                       │
└─────────────────────────────────────────────────────────────┘

[EMPTY] ──load_instruments()──→ [POPULATING] ──success──→ [VALID]
   ↑                              ↓                         │
   │                          failure                       │
   │                              ↓                         │
   │                         [STALE] ──retry(3)──→ [VALID] │
   │                              ↓                         │
   │                         failure (3x)                   │
   │                              ↓                         │
   │                         [FAILED] ──log+continue        │
   │                                                        │
   └────────── TTL expires (24h) ───────────────────────────┘
```

### Design Principles

1. **Fail-Safe, Not Fail-Fast**
   - If cache population fails, log warning and continue
   - Don't block CLI startup on cache failures
   - Always fall back to in-memory resolver

2. **Observability First**
   - Log cache hits, misses, population times
   - Track cache state in metrics
   - Expose cache statistics via CLI

3. **Retry with Backoff**
   - SQLite insert failures: retry 3x with 100ms, 200ms, 400ms backoff
   - CSV download failures: retry with exponential backoff
   - Circuit breaker after 5 consecutive failures

4. **Async Population (Future)**
   - Don't block initialization on cache population
   - Return immediately, populate in background
   - Use cache on next invocation

### Implementation Strategy

#### Phase 1: Safe Cache Population (Current)

**Goal**: Populate SQLite cache safely with proper error handling

**Design**:

```python
def load_instruments(self, source: Optional[str] = None, use_cache: bool = True) -> None:
    """Load instruments into memory AND populate SQLite cache.
    
    Failure Modes:
    1. CSV download fails → raise (can't load instruments at all)
    2. Memory load fails → raise (can't function without instruments)
    3. SQLite cache fails → log warning, continue (degraded mode)
    
    Observability:
    - Log population time for memory and SQLite
    - Log cache state after population
    - Track instrument count
    """
    # Step 1: Load from CSV (existing logic)
    start = time.monotonic()
    rows = self._load_instrument_rows(source, use_cache)
    load_time = time.monotonic() - start
    
    logger.info(
        "instrument_load_completed",
        extra={
            "count": len(rows),
            "load_time_s": round(load_time, 2),
            "source": source or "cached",
        }
    )
    
    # Step 2: Load into memory resolver (critical - must succeed)
    start = time.monotonic()
    self.instruments.load_from_rows(rows)
    memory_time = time.monotonic() - start
    
    logger.info(
        "instrument_memory_load_completed",
        extra={
            "count": len(rows),
            "memory_time_s": round(memory_time, 2),
        }
    )
    
    # Step 3: Populate SQLite cache (best-effort)
    if hasattr(self, 'instrument_cache') and self.instrument_cache:
        self._populate_sqlite_cache_safely(rows)
```

#### Phase 2: Safe Cache Population Method

```python
def _populate_sqlite_cache_safely(self, rows: list[dict], max_retries: int = 3) -> None:
    """Populate SQLite cache with retries and error handling.
    
    This is best-effort. If it fails, we log and continue.
    The in-memory resolver is already populated and functional.
    
    Args:
        rows: Instrument rows from CSV
        max_retries: Number of retries on failure (default: 3)
    """
    cache = self.instrument_cache
    
    for attempt in range(1, max_retries + 1):
        try:
            start = time.monotonic()
            cache.cache_instruments('dhan', rows)
            cache_time = time.monotonic() - start
            
            # Verify cache was populated
            count = cache.get_instrument_count('dhan')
            
            logger.info(
                "instrument_cache_populated",
                extra={
                    "broker": "dhan",
                    "count": count,
                    "cache_time_s": round(cache_time, 2),
                    "attempt": attempt,
                    "cache_status": "valid",
                }
            )
            
            # Success - cache is now valid
            return
            
        except Exception as e:
            wait_time = 0.1 * (2 ** (attempt - 1))  # 100ms, 200ms, 400ms
            
            logger.warning(
                f"instrument_cache_population_failed (attempt {attempt}/{max_retries})",
                extra={
                    "broker": "dhan",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt,
                    "next_retry_in_s": wait_time,
                },
                exc_info=True if attempt == max_retries else False,
            )
            
            if attempt < max_retries:
                time.sleep(wait_time)
    
    # All retries exhausted - log final failure
    logger.error(
        "instrument_cache_population_exhausted",
        extra={
            "broker": "dhan",
            "max_retries": max_retries,
            "fallback": "using_in_memory_only",
            "impact": "next_cli_startup_will_reload_csv",
        }
    )
```

#### Phase 3: Cache Statistics CLI Command

**New CLI command**: `tradex cache status`

```
$ tradex cache status

Instrument Cache Status
=======================

Dhan Cache:
  Status:          ✅ Valid
  Instruments:     234,825
  Last Refresh:    2026-06-16 14:23:45 IST
  Cache Age:       2h 15m
  TTL:             24h
  Database Size:   52.0 MB
  Load Time:       1.2s (last population)

Upstox Cache:
  Status:          ⚠️  Expired
  Instruments:     218,432
  Last Refresh:    2026-06-15 10:15:30 IST
  Cache Age:       28h 23m
  TTL:             24h
  Database Size:   48.3 MB
  Load Time:       N/A (needs refresh)

Cache Performance:
  SQLite Query:    0.4μs (average)
  Memory Hit:      0.0003μs (average)
  Cache Hit Rate:  94.2% (last 1000 resolutions)
```

## Failure Mode Analysis

### Scenario 1: CSV Download Fails
**Impact**: Can't load instruments at all
**Handling**: Raise exception, CLI fails fast
**User Action**: Check network, retry

### Scenario 2: SQLite Disk Full
**Impact**: Can't populate cache, but memory works
**Handling**: Log error, continue with memory-only mode
**User Action**: Free disk space, next run will retry

### Scenario 3: SQLite Corruption
**Impact**: Cache reads fail
**Handling**: Detect corruption, delete cache, recreate
**User Action**: Automatic recovery, transparent

### Scenario 4: Partial Population (interrupted)
**Impact**: Inconsistent cache state
**Handling**: SQLite transactions prevent this (ACID)
**User Action**: Automatic, no action needed

### Scenario 5: Cache TTL Expired
**Impact**: Cache is stale
**Handling**: Lazy refresh on next symbol resolution
**User Action**: Transparent, automatic

## Metrics to Track

1. **Cache Population**
   - `cache_population_time_s` - Time to populate SQLite
   - `cache_population_status` - success/failed/retry
   - `cache_instrument_count` - Number of instruments cached

2. **Cache Usage**
   - `cache_hit_count` - Cache hits (SQLite query)
   - `cache_miss_count` - Cache misses (not found in SQLite)
   - `cache_refresh_count` - Cache refreshes (TTL expired)
   - `cache_hit_rate` - hit / (hit + miss)

3. **Performance**
   - `symbol_resolution_time_us` - Time per resolution
   - `cache_query_time_us` - SQLite query time
   - `memory_query_time_us` - Memory dict lookup time

4. **Errors**
   - `cache_population_failure_count` - Failed population attempts
   - `cache_corruption_count` - Detected corruption events
   - `cache_retry_count` - Retry attempts

## Implementation Checklist

- [ ] Add `_populate_sqlite_cache_safely()` with retries
- [ ] Add structured logging for all cache operations
- [ ] Add cache statistics tracking
- [ ] Add `cache status` CLI command
- [ ] Add cache health check to `doctor` command
- [ ] Add metrics export (Prometheus gauges)
- [ ] Add integration tests for failure modes
- [ ] Document cache architecture in README

## Next Steps

1. **Immediate**: Implement safe cache population (Phase 1-2)
2. **Short-term**: Add cache statistics CLI command (Phase 3)
3. **Medium-term**: Add async cache population (non-blocking)
4. **Long-term**: Add distributed cache (Redis) for multi-process
