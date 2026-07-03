# Phase 6 — Implementation Tasks: Historical & Market Data
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 6 — Historical Data  
**Date:** 2026-07-03  
**Status:** Implementation Plan  

---

## 1. Task Dependency Graph

```
Layer 0 (No Dependencies) — Critical Data-Correctness Fixes
├── T0.1: Fix intraday endpoint routing
├── T0.2: Add exchange-aware session times
└── T0.3: Fix LTP error handling

Layer 1 (Depends on Layer 0) — Behavioral Parity Fixes
├── T1.1: Add API failure status check [depends on T0.1]
├── T1.2: Fix service ltp() to use adapter ltp() [depends on T0.3]
├── T1.3: Add post-fetch historical logging [depends on T0.1]
└── T1.4: Fix instrument type resolution [depends on T0.2]

Layer 2 (Depends on Layer 1) — Missing Features
├── T2.1: Add OI field to Candle entity [depends on T1.1]
├── T2.2: Add batch LTP to port + adapter [depends on T1.2]
├── T2.3: Add batch Quote to port + adapter [depends on T1.2]
└── T2.4: Add OHLC method to port + adapter [depends on T1.2]

Layer 3 (Depends on Layer 2) — Enhancements & Polish
├── T3.1: Add historical data caching service [depends on T2.1]
├── T3.2: Add date-range chunking [depends on T1.1]
├── T3.3: Fix depth level count alignment [depends on T1.2]
└── T3.4: Add candles_to_dataframe utility [depends on T2.1]
```

**Dependency Rationale:**
- Layer 0: Data-correctness bugs that produce wrong results or mask failures
- Layer 1: Observability and behavioral alignment that depend on correct endpoints
- Layer 2: Missing capabilities that require stable foundation
- Layer 3: Performance and convenience enhancements

---

## 2. Layer 0 — No Dependencies (Critical Data-Correctness Fixes)

### T0.1: Fix Intraday Endpoint Routing

**Priority:** CRITICAL  
**Gap Reference:** Evidence Matrix #2; Design Doc G-1  
**Estimated Effort:** 1 hour  

**Problem:**  
Greenfield sends all historical requests (daily and intraday) to `/charts/historical`. Archive correctly routes intraday (sub-day) requests to `/charts/intraday`. Dhan API requires separate endpoints.

**Implementation Steps:**

1. **Add intraday endpoint to config**
   ```python
   # brokers/adapters/dhan/config.py — add to ENDPOINTS dict
   "intraday": f"{REST_BASE}/charts/intraday",
   ```

2. **Route by interval in DhanHistorical**
   ```python
   # brokers/adapters/dhan/historical.py — get_historical_candles()
   if interval == "1D":
       endpoint = ENDPOINTS["historical"]
   else:
       endpoint = ENDPOINTS["intraday"]
   data = self._client.post(endpoint, json=payload)
   ```

3. **Add unit test**
   ```python
   # brokers/tests/test_historical_endpoints.py
   def test_intraday_uses_intraday_endpoint():
       # Mock client, call with resolution="5m"
       # Assert POST goes to /charts/intraday
   
   def test_daily_uses_historical_endpoint():
       # Mock client, call with resolution="1D"
       # Assert POST goes to /charts/historical
   ```

**Acceptance Criteria:**
- Sub-day resolutions (1m, 5m, 15m, 25m, 60m) POST to `/charts/intraday`
- Daily resolution (1D) POSTs to `/charts/historical`
- Unit tests pass for both paths

---

### T0.2: Add Exchange-Aware Session Times

**Priority:** HIGH  
**Gap Reference:** Evidence Matrix #4; Design Doc G-2  
**Estimated Effort:** 1.5 hours  

**Problem:**  
Greenfield hardcodes NSE session times (09:15–15:30) for all exchanges. MCX trades until 23:30. MCX intraday requests will cover the wrong time window.

**Implementation Steps:**

1. **Add session times to config**
   ```python
   # brokers/adapters/dhan/config.py
   SESSION_TIMES = {
       "NSE_EQ": {"open": "09:15:00", "close": "15:30:00"},
       "BSE_EQ": {"open": "09:15:00", "close": "15:30:00"},
       "NSE_FNO": {"open": "09:15:00", "close": "15:30:00"},
       "BSE_FNO": {"open": "09:15:00", "close": "15:30:00"},
       "MCX_COMM": {"open": "09:00:00", "close": "23:30:00"},
       "NSE_CD": {"open": "09:00:00", "close": "17:00:00"},
       "IDX_I": {"open": "09:15:00", "close": "15:30:00"},
   }
   DEFAULT_SESSION = {"open": "09:15:00", "close": "15:30:00"}
   ```

2. **Look up session times in adapter**
   ```python
   # brokers/adapters/dhan/historical.py — get_historical_candles()
   session = SESSION_TIMES.get(ref.exchange_segment, DEFAULT_SESSION)
   # Use session["open"] and session["close"] in payload
   ```

3. **Add unit test for MCX session times**
   ```python
   def test_mcx_intraday_uses_correct_session_times():
       # Resolve MCX symbol, verify payload has 09:00:00 and 23:30:00
   ```

**Acceptance Criteria:**
- MCX_COMM segment uses 09:00–23:30 session window
- NSE_EQ and NFO use 09:15–15:30
- Unknown segments fall back to default NSE times
- Unit tests cover MCX, NSE, and fallback cases

---

### T0.3: Fix LTP Error Handling

**Priority:** HIGH  
**Gap Reference:** Evidence Matrix #18; Design Doc G-4  
**Estimated Effort:** 0.5 hours  

**Problem:**  
Greenfield returns `Decimal(0)` when LTP data is missing. Archive raises `ValueError` with descriptive message. Silent zero masks data availability issues.

**Implementation Steps:**

1. **Raise on missing LTP data**
   ```python
   # brokers/adapters/dhan/market_data.py — ltp()
   if price is None:
       raise InstrumentNotFoundError(symbol)
   ```

2. **Add unit test**
   ```python
   def test_ltp_missing_raises_error():
       # Mock client returning empty data
       # Assert InstrumentNotFoundError raised
   ```

**Acceptance Criteria:**
- Missing LTP data raises `InstrumentNotFoundError` (or `DataError`)
- Error message includes symbol, exchange, and security_id
- Unit test verifies error is raised for missing data

---

## 3. Layer 1 — Depends on Layer 0 (Behavioral Parity Fixes)

### T1.1: Add API Failure Status Check

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #10; Design Doc G-5  
**Estimated Effort:** 0.5 hours  
**Depends on:** T0.1  

**Problem:**  
Archive checks `data.get("status") == "failure"` and raises `MarketDataError`. Greenfield parser silently processes failure responses as valid data.

**Implementation Steps:**

1. **Add failure check in _parse()**
   ```python
   # brokers/adapters/dhan/historical.py — _parse()
   if isinstance(data, dict) and data.get("status") == "failure":
       raise BrokerError(f"Historical API returned failure: {data}")
   ```

2. **Add unit test**
   ```python
   def test_parse_raises_on_failure_status():
       # Call _parse with {"status": "failure", ...}
       # Assert BrokerError raised
   ```

**Acceptance Criteria:**
- API responses with `status == "failure"` raise `BrokerError`
- Successful responses parse normally
- Unit test covers failure and success paths

---

### T1.2: Fix Service ltp() to Use Adapter ltp()

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #33; Design Doc G-11  
**Estimated Effort:** 0.5 hours  
**Depends on:** T0.3  

**Problem:**  
`MarketDataService.ltp()` calls `self.quote()` and extracts `.ltp`. This hits the heavier `/marketfeed/quote` endpoint when only price is needed.

**Implementation Steps:**

1. **Change service ltp() to call provider.ltp() directly**
   ```python
   # brokers/services/market_data_service.py
   def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
       key = f"ltp:{exchange}:{symbol}"
       cached = self._get_cached(key)
       if cached is not None:
           return cast(Decimal, cached)
       result = self._provider.ltp(symbol, exchange)
       self._set_cached_ltp(key, result)
       return result
   ```

2. **Extend cache to support Decimal values**
   ```python
   _CacheEntry = tuple[float, Quote | MarketDepth | Decimal]
   ```

**Acceptance Criteria:**
- `MarketDataService.ltp()` calls `provider.ltp()` (not `provider.quote()`)
- LTP has its own cache entries separate from quote cache
- Existing tests still pass

---

### T1.3: Add Post-Fetch Historical Logging

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #14; Design Doc G-7  
**Estimated Effort:** 0.25 hours  
**Depends on:** T0.1  

**Problem:**  
Archive logs every historical fetch with symbol, timeframe, candle count, and date range. Greenfield has no post-fetch logging.

**Implementation Steps:**

1. **Add structured log after fetch**
   ```python
   # brokers/adapters/dhan/historical.py — get_historical_candles()
   candles = self._parse(data, symbol)
   logger.info(
       "historical_candles_fetched",
       extra={
           "symbol": symbol,
           "exchange": exchange,
           "resolution": resolution,
           "candle_count": len(candles),
           "from": from_date,
           "to": to_date,
       },
   )
   return candles
   ```

**Acceptance Criteria:**
- Every successful historical fetch logs symbol, resolution, candle count, date range
- Log level is INFO
- No sensitive data (tokens, client IDs) in log output

---

### T1.4: Fix Instrument Type Resolution

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #11; Design Doc G-6  
**Estimated Effort:** 1 hour  
**Depends on:** T0.2  

**Problem:**  
Archive has 4-level fallback for instrument type: `name` → `exchange` → `ref_type` → `"EQUITY"`. Includes INDEX→EQUITY and NFO/BFO→OPTIDX mappings. Greenfield relies on `ref.instrument_type` which may not handle all edge cases.

**Implementation Steps:**

1. **Port instrument type logic to resolver or adapter**
   ```python
   # brokers/adapters/dhan/historical.py
   def _resolve_instrument_type(self, ref) -> str:
       # Check resolver's instrument type map first
       inst_type = ref.instrument_type
       if inst_type:
           return INSTRUMENT_TYPE_MAP.get(inst_type, inst_type)
       # Fallback: derive from exchange segment
       segment = ref.exchange_segment
       if segment in ("NFO", "BFO"):
           return "OPTIDX"
       if segment == "MCX_COMM":
           return "FUTCOM"
       return "EQUITY"
   ```

2. **Add unit tests for edge cases**
   ```python
   def test_index_resolves_to_equity():
   def test_nfo_resolves_to_optidx():
   def test_mcx_resolves_to_futcom():
   ```

**Acceptance Criteria:**
- INDEX instruments resolve to "EQUITY"
- NFO/BFO segments resolve to "OPTIDX" (or appropriate type)
- MCX resolves to "FUTCOM"
- Unit tests cover all exchange segment → instrument type mappings

---

## 4. Layer 2 — Depends on Layer 1 (Missing Features)

### T2.1: Add OI Field to Candle Entity

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #7; Design Doc G-3  
**Estimated Effort:** 0.5 hours  
**Depends on:** T1.1  

**Implementation Steps:**

1. **Add `oi` field to Candle dataclass**
   ```python
   # brokers/domain/entities.py
   @dataclass(frozen=True)
   class Candle:
       symbol: str
       timestamp: datetime
       open: Decimal
       high: Decimal
       low: Decimal
       close: Decimal
       volume: int
       oi: int = 0  # Open Interest — 0 for non-derivatives
   ```

2. **Parse OI from API response**
   ```python
   # brokers/adapters/dhan/historical.py — _parse()
   # In row-dict path:
   oi=int(item.get("oi", 0)),
   # In columnar path:
   oi=int(ois[i]) if i < len(ois) else 0,
   ```

**Acceptance Criteria:**
- `Candle.oi` defaults to 0 for non-derivative instruments
- OI populated from API response when available
- Existing tests still pass (backward compatible default)

---

### T2.2: Add Batch LTP

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #28; Design Doc G-13  
**Estimated Effort:** 2 hours  
**Depends on:** T1.2  

**Implementation Steps:**

1. **Add batch_ltp to MarketDataPort**
   ```python
   # brokers/ports/market_data.py
   def batch_ltp(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]: ...
   ```

2. **Implement in DhanMarketData**
   ```python
   # brokers/adapters/dhan/market_data.py
   def batch_ltp(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
       segment_map: dict[str, list[int]] = {}
       symbol_map: dict[int, str] = {}
       for sym in symbols:
           try:
               ref = self._resolver.resolve(sym, exchange)
               sid = ref.security_id_int()
               segment_map.setdefault(ref.exchange_segment, []).append(sid)
               symbol_map[sid] = sym
           except Exception:
               continue
       if not segment_map:
           return {}
       data = self._client.post(ENDPOINTS["ltp"], json=segment_map)
       # Parse response, map back to symbols
       ...
   ```

3. **Add unit test with multiple symbols across segments**

**Acceptance Criteria:**
- Single API call fetches LTP for all resolvable symbols
- Unresolvable symbols silently skipped (matches archive behavior)
- Returns `dict[str, Decimal]` mapping symbol → price
- Empty list returns empty dict

---

### T2.3: Add Batch Quote

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #29; Design Doc G-14  
**Estimated Effort:** 2 hours  
**Depends on:** T1.2  

**Implementation Steps:**

1. **Add batch_quote to MarketDataPort**
   ```python
   # brokers/ports/market_data.py
   def batch_quote(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]: ...
   ```

2. **Implement in DhanMarketData** (pattern mirrors T2.2)
3. **Add unit test**

**Acceptance Criteria:**
- Single API call fetches quotes for all resolvable symbols
- Returns `dict[str, Quote]`
- Unresolvable symbols silently skipped

---

### T2.4: Add OHLC Method

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #27; Design Doc G-12  
**Estimated Effort:** 1 hour  
**Depends on:** T1.2  

**Implementation Steps:**

1. **Add ohlc to MarketDataPort**
   ```python
   # brokers/ports/market_data.py
   def ohlc(self, symbol: str, exchange: str = "NSE") -> dict: ...
   ```

2. **Implement in DhanMarketData**
   ```python
   def ohlc(self, symbol: str, exchange: str = "NSE") -> dict:
       ref = self._resolver.resolve(symbol, exchange)
       sid = ref.security_id_int()
       segment = ref.exchange_segment
       payload = {segment: [sid]}
       data = self._client.post(ENDPOINTS["ohlc"], json=payload)
       feed = data.get("data", {})
       # Extract OHLC from response
       ...
   ```

3. **Add unit test**

**Acceptance Criteria:**
- Uses dedicated `/marketfeed/ohlc` endpoint (lighter than full quote)
- Returns dict with open, high, low, close keys
- Unit test verifies endpoint and parsing

---

## 5. Layer 3 — Depends on Layer 2 (Enhancements & Polish)

### T3.1: Add Historical Data Caching Service

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #34; Design Doc G-16  
**Estimated Effort:** 2 hours  
**Depends on:** T2.1  

**Implementation Steps:**

1. **Create HistoricalDataService with TTL cache**
   ```python
   # brokers/services/historical_data_service.py
   class HistoricalDataService:
       def __init__(self, provider: HistoricalPort, cache_ttl_seconds: float = 300.0):
           self._provider = provider
           self._ttl = cache_ttl_seconds
           self._cache: dict[str, tuple[float, list[Candle]]] = {}
           self._lock = threading.Lock()
       
       def get_historical_candles(self, symbol, exchange, start, end, resolution):
           key = f"hist:{exchange}:{symbol}:{resolution}:{start}:{end}"
           # Check cache, return if fresh
           # Otherwise fetch, cache, return
   ```

2. **Add invalidation API**
3. **Add unit tests for cache hit/miss/expiry**

**Acceptance Criteria:**
- Repeated queries within TTL return cached data
- Expired entries trigger fresh fetch
- Different (symbol, resolution, date_range) combinations cached independently
- Default TTL = 300s (historical data is stable)

---

### T3.2: Add Date-Range Chunking

**Priority:** LOW  
**Gap Reference:** Evidence Matrix (new); Design Doc §4.3  
**Estimated Effort:** 2 hours  
**Depends on:** T1.1  

**Implementation Steps:**

1. **Add chunking logic to DhanHistorical**
   ```python
   def get_historical_candles(self, symbol, exchange, start_time, end_time, resolution):
       if (end_time - start_time).days > 365:
           return self._get_chunked(symbol, exchange, start_time, end_time, resolution)
       return self._fetch_single(symbol, exchange, start_time, end_time, resolution)
   
   def _get_chunked(self, ...):
       chunks = split_into_annual_ranges(start_time, end_time)
       all_candles = []
       for chunk_start, chunk_end in chunks:
           all_candles.extend(self._fetch_single(...))
       return sorted(all_candles, key=lambda c: c.timestamp)
   ```

2. **Add unit test with multi-year range**

**Acceptance Criteria:**
- Date ranges > 1 year automatically chunked into annual segments
- Results merged and sorted by timestamp
- No duplicate candles at chunk boundaries
- Single-chunk ranges (< 1 year) use direct path

---

### T3.3: Fix Depth Level Count Alignment

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #25-26; Design Doc G-9, G-10  
**Estimated Effort:** 1 hour  
**Depends on:** T1.2  

**Problem:**  
Archive returns 5-level depth (`DEPTH_5`). Greenfield `map_depth` iterates up to 20 levels. Response format assumptions differ.

**Implementation Steps:**

1. **Verify actual Dhan API response format** (requires live testing)
2. **Align parser to actual format**
3. **Add `depth_type` field back to MarketDepth or document max depth**
4. **Add unit test with actual response shape**

**Acceptance Criteria:**
- Depth parser handles actual Dhan API response format
- Documented max depth level (5 or 20)
- Unit test with captured API response

---

### T3.4: Add candles_to_dataframe Utility

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #6  
**Estimated Effort:** 0.5 hours  
**Depends on:** T2.1  

**Implementation Steps:**

1. **Add utility function**
   ```python
   # brokers/utils/dataframe.py
   import pandas as pd
   from brokers.domain.entities import Candle
   
   def candles_to_dataframe(candles: list[Candle]) -> pd.DataFrame:
       if not candles:
           return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi", "symbol"])
       return pd.DataFrame([c.__dict__ for c in candles])
   ```

2. **Add unit test**

**Acceptance Criteria:**
- Converts `list[Candle]` to DataFrame with all fields
- Empty list returns empty DataFrame with correct columns
- Optional dependency: pandas not required unless function is called

---

## 6. Parallelization Opportunities

### Fully Parallel (No Dependencies Between Tasks)

| Group | Tasks | Rationale |
|---|---|---|
| **Layer 0** | T0.1, T0.2, T0.3 | Independent fixes in different files/concerns |
| **Layer 1** | T1.1 + T1.3, T1.2, T1.4 | T1.1 and T1.3 both touch historical.py but different methods; T1.2 is service layer; T1.4 is resolver |
| **Layer 2** | T2.1, T2.2, T2.3, T2.4 | All add independent features to different files |
| **Layer 3** | T3.1, T3.2, T3.3, T3.4 | Independent enhancements |

### Maximum Parallelism Schedule

```
Wave 1: T0.1 + T0.2 + T0.3           (3 tasks parallel)
Wave 2: T1.1 + T1.2 + T1.3 + T1.4    (4 tasks parallel)
Wave 3: T2.1 + T2.2 + T2.3 + T2.4    (4 tasks parallel)
Wave 4: T3.1 + T3.2 + T3.3 + T3.4    (4 tasks parallel)
```

**Theoretical minimum wall-clock:** Sum of longest task per wave ≈ 2h + 1h + 2h + 2h = **7 hours** (vs 16.75 hours sequential)

---

## 7. Critical Path Analysis

```
T0.1 (1h) → T1.1 (0.5h) → T2.1 (0.5h) → T3.1 (2h) = 4h
T0.1 (1h) → T1.3 (0.25h)                          = 1.25h
T0.2 (1.5h) → T1.4 (1h)                           = 2.5h
T0.3 (0.5h) → T1.2 (0.5h) → T2.2 (2h) → T3.3 (1h) = 4h
```

**Critical path:** T0.1 → T1.1 → T2.1 → T3.1 = **4 hours**

The critical path runs through the intraday endpoint fix → failure check → OI field → historical caching. Any delay on this path delays the entire phase.

---

## 8. Execution Summary

| Layer | Tasks | Total Effort | Parallel Min | Priority |
|---|---|---|---|---|
| Layer 0 | T0.1, T0.2, T0.3 | 3 hours | 1.5 hours | CRITICAL + HIGH |
| Layer 1 | T1.1–T1.4 | 2.25 hours | 1 hour | MEDIUM |
| Layer 2 | T2.1–T2.4 | 5.5 hours | 2 hours | LOW–MEDIUM |
| Layer 3 | T3.1–T3.4 | 4 hours | 2 hours | LOW |
| **Total** | **14 tasks** | **14.75 hours** | **~7 hours** | — |

### Risk-Adjusted Recommendation

1. **Must-fix before production:** Layer 0 (T0.1, T0.2, T0.3) — data correctness
2. **Should-fix for parity:** Layer 1 (T1.1–T1.4) — observability and behavioral alignment
3. **Nice-to-have:** Layer 2 (T2.1–T2.4) — missing capabilities
4. **Deferred:** Layer 3 (T3.1–T3.4) — enhancements and polish

**Minimum viable phase:** Layer 0 + Layer 1 = **5.25 hours** achieves data correctness and behavioral parity.

---

*End of implementation_tasks.md*
