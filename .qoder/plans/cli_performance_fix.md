# Plan: Fix CLI Performance via SQLite Cache Population

## Problem Statement

CLI takes 27-37s to initialize because SQLite instrument cache is never populated. Every invocation reloads 234,825 instruments from CSV.

## Root Cause

`DhanConnection.load_instruments()` loads instruments into in-memory resolver only. The SQLite cache (`instrument_cache`) is set up in the factory but never used during `load_instruments()`.

## Implementation Plan

### Task 1: Wire SQLite Cache into DhanConnection.load_instruments()
**File**: `brokers/dhan/connection.py`

**Changes**:
- After `self.instruments.load_from_rows(rows)`, check if `self.instrument_cache` exists
- If yes, call `self.instrument_cache.cache_instruments('dhan', rows)`
- This populates SQLite cache during initial load
- Subsequent CLI runs will use fast SQLite path

**Code**:
```python
def load_instruments(self, source: Optional[str] = None, use_cache: bool = True) -> None:
    # Existing logic to load rows
    if source is not None:
        if source.startswith(("http://", "https://")):
            rows = InstrumentLoader.load_from_url(source)
        else:
            rows = InstrumentLoader.load_from_file(source)
    elif use_cache:
        rows = InstrumentLoader.load_cached()
    else:
        rows = InstrumentLoader.load_cached(force_refresh=True)
    
    # Load into in-memory resolver (existing)
    self.instruments.load_from_rows(rows)
    
    # NEW: Populate SQLite cache for fast subsequent lookups
    if hasattr(self, 'instrument_cache') and self.instrument_cache:
        self.instrument_cache.cache_instruments('dhan', rows)
```

### Task 2: Do the Same for Upstox
**File**: `brokers/upstox/broker.py` (or wherever `load_instruments()` is)

**Changes**:
- Find Upstox's `load_instruments()` method
- Add same SQLite cache population logic

### Task 3: Test Cold Start Performance
**Script**: `test_cli_speed.py`

**Expected Results**:
- First run (cold): ~12s (CSV load 11s + SQLite insert 1s)
- Second run (warm): < 2s (SQLite load only)

### Task 4: Test Symbol Resolution Speed
**Test**: Quote a symbol after warm start

**Expected**: < 1ms for symbol resolution via SQLite

### Task 5: Run Full Test Suite
**Command**: `pytest brokers/ -x -q`

**Expected**: All 835+ tests passing, zero regressions

## Success Criteria

- ✅ Cold start < 15s (currently 37s)
- ✅ Warm start < 2s (currently 37s)
- ✅ All tests passing
- ✅ Zero breaking changes
- ✅ Symbol resolution < 1ms

## Risks & Mitigations

1. **Risk**: SQLite insert of 234k rows is slow
   - **Mitigation**: Already using bulk insert with transactions, should be < 2s
   
2. **Risk**: Memory spike loading 234k rows
   - **Mitigation**: Already loading into memory, no additional overhead
   
3. **Risk**: Cache corruption on interrupted writes
   - **Mitigation**: SQLite is ACID-compliant, transactions are atomic

## Execution Order

1. Fix Dhan `load_instruments()` (Task 1)
2. Fix Upstox `load_instruments()` (Task 2)
3. Test cold/warm start (Tasks 3-4)
4. Run full test suite (Task 5)
5. Commit and document
