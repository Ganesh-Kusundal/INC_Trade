# Execution Plan: Instrument Cache Lifecycle & CLI Performance

## Analysis: Existing Code Flow

### Dhan Flow (Current)

```
BrokerService._ensure_initialized()
  → BrokerFactory.create(load_instruments=True)
      1. Create DhanConnection
      2. Create InstrumentCacheManager + DhanInstrumentAdapter
      3. Register loader (returns list[dict] via InstrumentLoader.load_cached)
      4. Create SymbolResolutionInterceptor
      5. connection.instrument_cache = cache_mgr     ← Set on connection
      6. connection._market_data._symbol_interceptor = symbol_interceptor
      7. gateway.load_instruments()
           → connection.load_instruments()
                → InstrumentLoader.load_cached()  → 234k dicts  (~11s CSV parse)
                → self.instruments.load_from_rows(rows)  ← In-memory resolver ✅
                → ❌ SQLite cache NEVER populated
```

**Result**: SQLite `instruments_dhan` table = 0 rows. Next CLI run repeats the full 11s CSV parse.

### Upstox Flow (Current)

```
BrokerService._ensure_initialized()
  → UpstoxBrokerFactory.create(load_instruments=True)
      1. Create UpstoxBroker (with instrument_resolver + instrument_loader)
      2. broker.connect()  (~2-3s)
      3. Create InstrumentCacheManager + UpstoxInstrumentAdapter
      4. Register loader (download JSON → parse → list[UpstoxInstrumentDefinition])
      5. broker.instrument_cache = cache_mgr       ← Set on broker
      6. broker.symbol_interceptor = symbol_interceptor
      7. gateway.load_instruments()
           → broker.instrument_loader.load(path)  → list[UpstoxInstrumentDefinition]
           → broker.instrument_resolver.register_many(defs)  ← In-memory resolver ✅
           → ❌ SQLite cache NEVER populated
```

**Result**: SQLite `instruments_upstox` table = 0 rows. Next CLI run repeats JSON parse.

### Key Architectural Gap

Both brokers load instruments into their **in-memory resolver** but **never write to SQLite**.
The `InstrumentCacheManager.cache_instruments()` method exists but is never called during
`load_instruments()`. It's only called by `_lazy_refresh()` inside `resolve_symbol()` —
which only fires when a symbol lookup actually happens AND the cache is expired.

### Type Mismatch

| Broker  | Loader returns                  | Adapter expects                  | Status |
|---------|----------------------------------|----------------------------------|--------|
| Dhan    | `list[dict]` with SEM_ keys    | `dict` with SEM_ keys            | ✅ Match |
| Upstox  | `list[UpstoxInstrumentDefinition]` | `UpstoxInstrumentDefinition`   | ✅ Match |

No conversion needed. Both adapters already handle their native types correctly.

---

## Execution Plan

### Task 1: Wire SQLite cache into Dhan `load_instruments()` ✅ (already done)

**File**: `brokers/dhan/connection.py`
**Status**: Implemented with retries, logging, observability

### Task 2: Wire SQLite cache into Upstox `load_instruments()`

**File**: `brokers/upstox/gateway.py`

The Upstox gateway's `load_instruments()` loads into the in-memory resolver.
We need to also populate the SQLite cache with the same definitions.

**Current code**:
```python
def load_instruments(self, source: Optional[str] = None) -> None:
    from pathlib import Path
    cache_path = Path(".cache/upstox/complete.json.gz")
    if source:
        path = Path(source)
    elif cache_path.exists():
        path = cache_path
    else:
        path = self._broker.instrument_loader.download(cache_path)
    defs = self._broker.instrument_loader.load(path)
    self._broker.instrument_resolver.register_many(defs)
    # ❌ Missing: SQLite cache population
```

**New code**: Add `_populate_sqlite_cache_safely()` after `register_many()`,
same pattern as Dhan. The broker already has `instrument_cache` set by the factory.

### Task 3: Write TDD tests first

**Files**:
- `brokers/dhan/tests/unit/test_cache_population.py`
- `brokers/upstox/tests/unit/test_cache_population.py`

**Test scenarios**:
1. Cold start (empty cache) → populate succeeds → cache is valid
2. SQLite failure → retry 3x → log warning → continue with memory-only
3. SQLite failure exhausted → log error with impact message
4. Warm start (valid cache) → skip population (cache already valid)
5. Partial failure → retry succeeds on attempt 2
6. Instrument count verified after population
7. Structured log messages emitted correctly

### Task 4: Run full test suite

```bash
pytest brokers/ -x -q --timeout=60
```

**Expected**: All 835+ tests passing, zero regressions

### Task 5: Measure CLI performance

```bash
# Cold start: delete cache first
rm .cache/instruments.db
time python -c "from cli.services.broker_service import BrokerService; ..."

# Warm start: cache already populated
time python -c "from cli.services.broker_service import BrokerService; ..."
```

**Expected**:
- Cold start: ~12s (CSV load 11s + SQLite insert 1s)
- Warm start: < 2s (SQLite validation + query)

### Task 6: Commit with descriptive message

---

## Error Handling Design

### Failure Classification

| Severity | Condition | Action |
|----------|-----------|--------|
| FATAL    | CSV download fails | Raise exception (can't function) |
| FATAL    | Memory resolver fails | Raise exception (can't function) |
| WARNING  | SQLite cache fails | Log warning, continue with memory-only |
| WARNING  | Cache validation fails | Skip validation, proceed to populate |

### Retry Strategy (SQLite only)

```
Attempt 1: 0ms wait
  → failure → log WARNING, wait 100ms
Attempt 2: 100ms wait
  → failure → log WARNING, wait 200ms
Attempt 3: 200ms wait
  → failure → log WARNING, wait 400ms
  → ALL RETRIES EXHAUSTED → log ERROR with impact
```

### Structured Log Events

| Event | Level | Fields |
|-------|-------|--------|
| `instrument_load_completed` | INFO | count, load_time_s, source |
| `instrument_memory_load_completed` | INFO | count, memory_time_s |
| `instrument_cache_populated` | INFO | broker, count, cache_time_s, attempt |
| `instrument_cache_population_failed` | WARNING | broker, error, attempt, next_retry_in_s |
| `instrument_cache_population_exhausted` | ERROR | broker, max_retries, fallback, impact |
| `instrument_cache_already_valid` | INFO | broker, count (skip re-population) |
| `instrument_cache_retry` | DEBUG | broker, attempt, wait_ms |

---

## Observability: What Users See

### Successful Run (cache populated)

```
instrument_load_completed: count=234825 load_time_s=11.2 source=cached
instrument_memory_load_completed: count=234825 memory_time_s=0.85
instrument_cache_populated: broker=dhan count=234825 cache_time_s=1.03 attempt=1 cache_status=valid
```

### Degraded Run (cache failed)

```
instrument_load_completed: count=234825 load_time_s=11.2 source=cached
instrument_memory_load_completed: count=234825 memory_time_s=0.85
instrument_cache_population_failed (attempt 1/3): error="disk I/O error" attempt=1 next_retry_in_s=0.1
instrument_cache_population_failed (attempt 2/3): error="disk I/O error" attempt=2 next_retry_in_s=0.2
instrument_cache_population_failed (attempt 3/3): error="disk I/O error" attempt=3
instrument_cache_population_exhausted: broker=dhan max_retries=3 fallback=using_in_memory_only impact=next_cli_startup_will_reload_csv
```

### Warm Start (cache already valid)

```
instrument_load_completed: count=234825 load_time_s=0.01 source=cached
instrument_memory_load_completed: count=234825 memory_time_s=0.001
instrument_cache_already_valid: broker=dhan count=234825 (skip re-population)
```

---

## Implementation Order

1. ✅ Write architecture doc (this file)
2. ✅ Analyze existing code flows (this analysis)
3. ⬜ Write TDD tests for cache population (both brokers)
4. ⬜ Implement Upstox `load_instruments()` cache population
5. ⬜ Run full test suite (835+ tests)
6. ⬜ Measure and verify CLI performance
7. ⬜ Commit with structured message
