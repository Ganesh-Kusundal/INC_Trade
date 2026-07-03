# Phase 6 — Failure Analysis: Historical Data & Market Data

> Greenfield Broker Replication Protocol — Dhan  
> Phase 6: Historical Data  
> Source: `archive/brokers/dhan/historical.py`, `archive/brokers/dhan/market_data.py`, `brokers/adapters/dhan/historical.py`, `brokers/adapters/dhan/market_data.py`, `brokers/services/market_data_service.py`, `brokers/domain/exceptions.py`

---

## 1. Timeout Policies

### 1.1 Archive

**No explicit timeout policy for historical or market data requests.**

The archive `HistoricalAdapter` and `MarketDataAdapter` delegate to `DhanHttpClient.post()`. Timeout behavior is entirely determined by the HTTP client's default configuration. There is:
- No per-endpoint timeout override.
- No timeout parameter exposed in `get_historical()`, `get_ltp()`, `get_quote()`, etc.
- No client-side timeout enforcement.

**Risk:** A slow or hanging Dhan API will block the calling thread indefinitely.

### 1.2 Greenfield

**Same situation — no explicit timeout policy.**

The greenfield `DhanHistorical` and `DhanMarketData` also delegate to `DhanHttpClient.post()` without timeout parameters. The `ENDPOINTS` config dict defines URLs but not timeouts.

**Rate limits are defined** in `RATE_LIMITS` config:
```python
RATE_LIMITS = {
    "/marketfeed/quote": 1.0,   # 1 req/s
    "/marketfeed/ltp": 0.15,    # ~6.7 req/s
    "/marketfeed/ohlc": 0.15,   # ~6.7 req/s
    "/charts/": 0.15,           # ~6.7 req/s
}
```

These govern request *throttling* but not *timeout*. If the HTTP client enforces these as minimum intervals between requests, they provide backpressure but not deadline enforcement.

### 1.3 Gap Assessment

| Requirement | Status | Risk |
|---|---|---|
| Per-request timeout | **MISSING** | Thread blocked indefinitely |
| Connect timeout | **MISSING** | DNS/TCP hang |
| Read timeout | **MISSING** | API hangs after connect |
| Historical-specific timeout | **MISSING** | Large date ranges may take longer |
| Timeout propagation from port | **MISSING** | `HistoricalPort` has no timeout param |

---

## 2. Exception Hierarchy for Market Data

### 2.1 Domain Exception Tree

```
TradeXV2Error
├── ConfigError
├── DataError
├── ValidationError
├── BrokerError(code: str)
│   ├── RetryableError
│   │   └── NetworkError          ← connection reset, timeout, DNS
│   ├── NonRetryableError
│   ├── BrokerServerError         ← HTTP 5xx
│   ├── RateLimitError(retry_after)  ← HTTP 429
│   ├── CircuitOpenError          ← circuit breaker open
│   ├── AuthenticationError       ← token expired/invalid
│   ├── TokenRateLimitError       ← token generation cooldown
│   ├── InstrumentNotFoundError(symbol)  ← symbol unresolvable
│   ├── NotSupportedError         ← operation not supported
│   ├── BrokerDegradedError(health_status)  ← health below threshold
│   └── OrderRejectedError(order_id)  ← order rejected
```

### 2.2 Exceptions Actually Raised by Historical/Market Data Code

| Component | Exception | Condition | Caught by caller? |
|---|---|---|---|
| Archive `HistoricalAdapter._parse()` | `MarketDataError` | API returns `status=failure` | Not in adapter; caller must handle |
| Archive `MarketDataAdapter.get_ltp()` | `ValueError` | No LTP data for security ID | Not in adapter; caller must handle |
| Archive `MarketDataAdapter.get_quote()` | `KeyError` | Missing response key | **Not caught** — unhandled |
| Archive `MarketDataAdapter.get_depth()` | `KeyError` | Missing response key | **Not caught** — unhandled |
| Archive `MarketDataAdapter.get_ohlc()` | `KeyError` | Missing response key | **Not caught** — unhandled |
| Greenfield `DhanHistorical._parse()` | (none) | Bad data → skipped silently | N/A — graceful |
| Greenfield `DhanMarketData.ltp()` | (none) | Missing data → `Decimal("0")` | N/A — silent zero |
| Greenfield `DhanMarketData.quote()` | (none) | Missing data → zeroed Quote | N/A — silent |
| Both adapters | `InstrumentNotFoundError` | Symbol not in master CSV | Caller must handle |
| Both adapters | `AssertionError` | Invariant violation | Should never happen (bug) |
| HTTP client | `NetworkError` | Connection failure | Caller must handle |
| HTTP client | `RateLimitError` | HTTP 429 | Caller must handle |
| HTTP client | `BrokerServerError` | HTTP 5xx | Caller must handle |

### 2.3 Exception Contract Gaps

1. **Archive raises `ValueError` for missing LTP** — should be `InstrumentNotFoundError` or a domain-specific `MarketDataError`.
2. **Archive raises raw `KeyError`** for missing quote/depth keys — not a domain exception.
3. **Greenfield silently returns zero** for missing LTP — caller cannot distinguish "price is zero" from "data unavailable."
4. **No `MarketDataError` in greenfield domain** — the archive's `MarketDataError` has no greenfield equivalent. Data errors are either swallowed or surfaced as generic `BrokerError`.
5. **No `DataError` usage** — `DataError` exists in the domain but is never raised by historical or market data code.

---

## 3. Race Conditions Inventory

### 3.1 Cache Race Conditions (MarketDataService)

**RC-1: Stale Read Between Lock Acquisitions**
```
Thread A: _get_cached(key) → acquires lock → reads entry → releases lock
Thread B: _set_cached(key, new_value) → acquires lock → writes → releases lock
Thread A: checks TTL → entry is now from Thread B but TTL check uses old ts
```
**Impact:** Low. The TTL check uses `time.monotonic()` which is always current. Worst case: a fresh entry is immediately considered expired if Thread B wrote it with an older monotonic reading (impossible on same process).

**RC-2: Eviction Between Read and TTL Check**
```
_get_cached():
  with self._lock:
      entry = self._cache.get(key)   # entry exists
  # ← another thread could evict here
  ts, value = entry
  if time.monotonic() - ts > self._ttl:
      with self._lock:
          self._cache.pop(key, None)  # already gone → no-op
      return None
```
**Impact:** None. The `pop(key, None)` is safe if the key is already gone. The thread returns `None` and triggers a fresh fetch.

**RC-3: Duplicate Fetch on Concurrent Cache Miss**
```
Thread A: _get_cached(key) → None → calls provider.quote()
Thread B: _get_cached(key) → None → calls provider.quote()  ← duplicate API call
Thread A: _set_cached(key, result_a)
Thread B: _set_cached(key, result_b)  ← overwrites A's result
```
**Impact:** Medium. Two API calls for the same symbol/exchange. Wastes rate limit budget. The last writer wins, which is acceptable for idempotent reads but wasteful.

**Mitigation needed:** Request coalescing / deduplication (e.g., `concurrent.futures.Future` per key).

### 3.2 Historical Data Race Conditions

**RC-4: Concurrent Resolution**
Multiple threads calling `get_historical_candles()` with the same symbol will each call `self._resolver.resolve()`. If the resolver has internal state (e.g., caching), this could race.

**Impact:** Low. The `DhanInstrumentResolver` appears to be read-only after initialization.

**RC-5: Shared HTTP Client**
Multiple threads using the same `DhanHttpClient` instance. If the client maintains session state (cookies, tokens), concurrent requests could interfere.

**Impact:** Depends on HTTP client implementation. If using `requests.Session`, it is thread-safe for most operations but not for connection pooling under heavy load.

### 3.3 Batch Operation Race Conditions (Archive)

**RC-6: Partial Failure in Batch**
```python
for sym in symbols:
    try:
        ref, segment = self._resolve_and_segment(sym, exchange)
        ...
    except Exception:
        continue  # silently skip
```
If resolution fails for some symbols, the batch proceeds with a subset. The caller has no way to know which symbols were skipped.

**Impact:** Medium. Silent data loss — caller receives partial results without indication.

---

## 4. Recovery Paths

### 4.1 Network Failure

| Scenario | Archive behavior | Greenfield behavior | Recommended |
|---|---|---|---|
| Connection refused | Exception propagates | Exception propagates | Retry with backoff |
| Connection reset mid-request | Exception propagates | Exception propagates | Idempotent retry (reads are safe) |
| DNS failure | Exception propagates | Exception propagates | Retry with backoff |
| TLS handshake failure | Exception propagates | Exception propagates | Retry, then alert |

**Current state:** No retry at adapter level. The infrastructure layer has `retry.py` but it is not wired into historical/market data adapters.

### 4.2 Rate Limiting (HTTP 429)

| Scenario | Archive behavior | Greenfield behavior | Recommended |
|---|---|---|---|
| HTTP 429 on market feed | `RateLimitError` propagates | `RateLimitError` propagates | Respect `retry_after`, exponential backoff |
| HTTP 429 on historical | `RateLimitError` propagates | `RateLimitError` propagates | Queue and retry |
| Token rate limit | `TokenRateLimitError` | `TokenRateLimitError` | Honor cooldown period |

**Current state:** `RateLimitError` carries `retry_after` but no caller respects it. `RATE_LIMITS` config provides client-side throttling but it is not enforced in the adapter code paths.

### 4.3 Data Unavailability

| Scenario | Archive behavior | Greenfield behavior | Recommended |
|---|---|---|---|
| Instrument not found | `InstrumentNotFoundError` | `InstrumentNotFoundError` | Return empty / raise with context |
| API returns failure status | `MarketDataError` raised | Empty list `[]` returned | **Divergence** — should raise or return explicit error |
| LTP data missing for ID | `ValueError` raised | `Decimal("0")` returned | **Divergence** — greenfield masks the error |
| Empty candle data | Empty DataFrame | Empty list `[]` | Consistent — both return empty |
| Market closed (no data) | Last available data or empty | Last available data or empty | Acceptable |

### 4.4 Data Parsing Errors

| Scenario | Archive behavior | Greenfield behavior |
|---|---|---|
| Unexpected response format | `MarketDataError` or `KeyError` | Returns `[]` or zeroed entity |
| Missing OHLC columns | Filled with zeros | Filled with `Decimal("0")` |
| Invalid timestamp | `pd.to_datetime` may fail | `try/except` → row skipped |
| Columnar vs row format | Not handled | Both formats handled |

**Greenfield is more robust** in parsing — it handles columnar responses and gracefully skips bad rows.

---

## 5. Data Validation Errors

### 5.1 Invalid Timeframes

Neither implementation validates the timeframe/resolution parameter before sending it to the API.

```python
# Archive:
interval = _TIMEFRAME_MAP.get(timeframe, timeframe)  # passthrough if unknown

# Greenfield:
interval = _TIMEFRAME_MAP.get(resolution, resolution)  # passthrough if unknown
```

**Consequence:** An invalid timeframe like `"3M"` or `"1H"` is sent verbatim to Dhan's API, which returns an error. The error is not translated into a domain exception.

**Recommendation:** Validate against known timeframes and raise `ValidationError` before the HTTP call.

### 5.2 Missing Instruments

Both implementations raise `InstrumentNotFoundError` when `resolve()` fails. This is correct behavior.

**Gap:** The archive's batch methods silently skip unresolvable symbols:
```python
except Exception:
    continue  # swallowed
```
This catches *all* exceptions, not just `InstrumentNotFoundError`, masking bugs.

### 5.3 Date Validation

- **Archive:** No validation. `from_date` and `to_date` are coerced to `str()`. Invalid dates are sent to the API.
- **Greenfield:** No validation. `start_time.strftime()` will raise `AttributeError` if the parameter is not a `datetime`. But no semantic validation (e.g., `start_time < end_time`).

**Missing validations:**
- `start_time < end_time`
- Dates not in the future
- Date range not excessively large (Dhan may have limits)
- Exchange is a known value

### 5.4 Symbol Validation

No symbol validation is performed before resolution. Empty strings, `None`, or whitespace are passed to the resolver, which will fail with `InstrumentNotFoundError`.

---

## 6. Secret Exposure Risks

### 6.1 Analysis

Historical and market data APIs require authentication (access token in HTTP headers). The risk surface:

| Risk | Archive | Greenfield | Assessment |
|---|---|---|---|
| Token in URL | No — POST body | No — POST body | Safe |
| Token in logs | Possible if `DhanHttpClient` logs headers | Possible if `DhanHttpClient` logs headers | **Review HTTP client** |
| Symbol/exchange in logs | Yes — `logger.info("historical_fetched", ...)` | Yes — `logger.debug(...)` | Acceptable (no secrets) |
| Security ID in logs | Archive logs `security_id` on LTP miss | Greenfield does not log SID | Low risk — SID is not a secret |
| Payload in error messages | `MarketDataError(f"API returned failure: {data}")` may include full response | No equivalent — errors are silent | **Medium** — response data may contain tokens |
| Exception stack traces | `KeyError` on missing data exposes response structure | No KeyError — silent | Safe |

### 6.2 Recommendations

1. Ensure `DhanHttpClient` redacts `Authorization` headers in log output.
2. Avoid including full API response bodies in exception messages.
3. The greenfield's silent-zero approach avoids secret exposure but creates a different class of problems (data integrity).

---

## 7. Greenfield Gaps Summary

### 7.1 Critical Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-1 | No intraday endpoint divergence | Sub-daily historical data may fail | Route to `/charts/intraday` for non-daily |
| G-2 | MCX session times hardcoded to NSE | MCX data window is wrong (09:15–15:30 vs 09:00–23:30) | Port session time overrides from archive |
| G-3 | No `get_ohlc()` method | OHLC endpoint exists but is not exposed | Add `ohlc()` to `MarketDataPort` and adapter |
| G-4 | No batch methods | Cannot fetch multiple symbols efficiently | Add batch methods to port or service layer |
| G-5 | LTP returns `Decimal("0")` on missing data | Caller cannot detect data unavailability | Raise `InstrumentNotFoundError` or return `Optional[Decimal]` |
| G-6 | No `MarketDataError` in domain | Data parsing errors have no domain exception | Add `MarketDataError(BrokerError)` to domain |

### 7.2 Moderate Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-7 | No request timeout | Thread can block indefinitely | Add timeout parameter to port methods |
| G-8 | No retry at adapter level | Transient failures propagate | Wire infrastructure retry into adapters |
| G-9 | No timeframe validation | Invalid timeframes hit the API | Validate against `_TIMEFRAME_MAP` keys |
| G-10 | No date range validation | Invalid or reversed ranges hit the API | Add `start_time < end_time` assertion |
| G-11 | No `oi` field on `Candle` | Open interest data is lost | Add `oi: int = 0` to `Candle` entity |
| G-12 | Cache duplicate fetch on concurrent miss | Wastes rate limit budget | Implement request coalescing |
| G-13 | No `change` field on `Quote` | Net change must be recalculated | Add `change: Decimal = Decimal("0")` to `Quote` |

### 7.3 Low-Priority Gaps

| ID | Gap | Impact | Recommendation |
|---|---|---|---|
| G-14 | `MarketDataPort` not `@runtime_checkable` | Cannot use `isinstance()` checks | Add `@runtime_checkable` for consistency |
| G-15 | No async support | Cannot use in async contexts | Document as sync-only or add async port |
| G-16 | Cache has no metrics | Cannot observe hit/miss rates | Add counters via observability infrastructure |
| G-17 | No circuit breaker at adapter level | Repeated failures waste resources | Rely on infrastructure circuit breaker |

---

## 8. Risk Matrix

```
                        Impact
                  Low      Medium    High
              ┌─────────┬─────────┬─────────┐
    Certain   │         │ G-1,G-2 │         │
              │         │ G-5     │         │
              ├─────────┼─────────┼─────────┤
Likely        │ G-12    │ G-7     │         │
              │         │ G-8     │         │
              ├─────────┼─────────┼─────────┤
Unlikely      │ G-14    │ G-3,G-4 │ G-6     │
              │ G-15    │ G-9,G-10│ G-11    │
              │ G-16    │ G-13    │         │
              └─────────┴─────────┴─────────┘
```

**Top 3 priorities:**
1. **G-1/G-2:** Fix intraday endpoint and MCX session times — data correctness issue.
2. **G-5:** Stop returning silent zeros for missing data — data integrity issue.
3. **G-7/G-8:** Add timeout and retry — reliability issue.
