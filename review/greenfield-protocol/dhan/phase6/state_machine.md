# Phase 6 — State Machines: Historical Data & Market Data Caching

> Greenfield Broker Replication Protocol — Dhan  
> Phase 6: Historical Data  
> Source: `archive/brokers/dhan/historical.py`, `archive/brokers/dhan/market_data.py`, `brokers/adapters/dhan/historical.py`, `brokers/adapters/dhan/market_data.py`, `brokers/services/market_data_service.py`

---

## 1. Historical Data Request State Machine

### 1.1 Archive State Machine

The archive `HistoricalAdapter.get_historical()` is a synchronous, single-shot call.
There is no explicit state machine — the method executes linearly and returns a
`pd.DataFrame`. The implicit states are:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                    ARCHIVE: Historical Request (implicit)                  │
│                                                                            │
│  ┌─────────┐   resolve_ref()   ┌────────────┐   post()    ┌───────────┐  │
│  │  IDLE    │ ───────────────▶ │ RESOLVING  │ ─────────▶ │ PARSING   │  │
│  └─────────┘                   └────────────┘             └───────────┘  │
│       │                                │                        │          │
│       │                          InstrumentNotFound         parse fails   │
│       ▼                                ▼                        ▼          │
│  ┌─────────┐                    ┌────────────┐          ┌───────────┐   │
│  │ (entry)  │                    │   ERROR    │          │  ERROR    │   │
│  └─────────┘                    └────────────┘          └───────────┘   │
│                                                                         │
│  No retry. No pagination. No caching.                                   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Implicit states:**
| State | Trigger | Outcome |
|---|---|---|
| IDLE | Method entry | Begin resolution |
| RESOLVING | `resolve_ref(symbol, exchange)` | Success → build payload; Failure → `InstrumentNotFoundError` |
| REQUESTING | `self._client.post(endpoint, json=payload)` | HTTP response received |
| PARSING | `_parse(data, ...)` | DataFrame returned or `MarketDataError` raised |
| COMPLETE | Return `pd.DataFrame` | Caller receives data |
| ERROR | Any exception | Propagates to caller unhandled |

**Key observations:**
- No explicit state tracking — purely procedural.
- No retry on network failure.
- No pagination — Dhan's API returns all data in a single response.
- No caching layer.
- Failure detection is limited to checking `data["status"] == "failure"`.

---

### 1.2 Greenfield State Machine

The greenfield `DhanHistorical.get_historical_candles()` follows the same
procedural pattern but returns `list[Candle]` (domain entities) instead of a
DataFrame. The implicit state machine is structurally identical:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                   GREENFIELD: Historical Request (implicit)                │
│                                                                            │
│  ┌─────────┐  resolve()    ┌────────────┐  post()    ┌────────────────┐  │
│  │  IDLE   │ ───────────▶ │ RESOLVING  │ ─────────▶ │ PARSING        │  │
│  └─────────┘               └────────────┘            └────────────────┘  │
│       │                               │                       │            │
│       │                         InstrumentNotFound    parse returns []    │
│       ▼                               ▼                       ▼            │
│  ┌─────────┐                   ┌────────────┐         ┌──────────────┐  │
│  │ (entry)  │                   │   ERROR    │         │ COMPLETE     │  │
│  └─────────┘                   └────────────┘         │ (empty list) │  │
│                                                        └──────────────┘  │
│  No retry. No pagination. No caching.                                   │
└────────────────────────────────────────────────────────────────────────────┘
```

**Greenfield states:**
| State | Trigger | Outcome |
|---|---|---|
| IDLE | Method entry | Begin resolution |
| RESOLVING | `self._resolver.resolve(symbol, exchange)` | Returns `DhanInstrumentRef`; failure raises `InstrumentNotFoundError` |
| REQUESTING | `self._client.post(ENDPOINTS["historical"], json=payload)` | HTTP response |
| PARSING | `_parse(data, symbol)` | Handles both row-dict and columnar formats |
| COMPLETE | Return `list[Candle]` | May be empty if data is empty or unparseable |
| ERROR | Exception | Propagates unhandled |

**Key differences from archive:**
- Uses `datetime` objects instead of string dates.
- Returns domain `Candle` entities instead of `pd.DataFrame`.
- Handles Dhan's columnar response format (`start_Time`, `open`, etc.).
- Gracefully returns `[]` for unparseable data instead of raising.
- Uses `ZoneInfo("Asia/Kolkata")` for timezone-aware timestamps.
- Endpoint URL sourced from `ENDPOINTS` config dict instead of hardcoded.

---

## 2. Data Caching State Machine (MarketDataService)

### 2.1 Greenfield TTL Cache

The `MarketDataService` implements a TTL-based in-memory cache for `Quote` and
`MarketDepth` objects. This is the only caching layer in Phase 6.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                  GREENFIELD: MarketDataService Cache State Machine            │
│                                                                              │
│                         ┌──────────────────────┐                             │
│                         │     CACHE MISS        │                             │
│                         │  (key absent/expired) │                             │
│                         └──────────┬───────────┘                             │
│                                    │                                         │
│                           _get_cached() returns None                         │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────┐  fetch from    ┌──────────────────┐  _set_cached() ┌───────┐ │
│  │  IDLE    │ ─────────────▶ │  FETCHING        │ ─────────────▶ │ STORE │ │
│  │ (ready)  │ provider.xxx() └──────────────────┘                └───────┘ │
│  └──────────┘                                                              │
│       ▲                                                     │              │
│       │              value written to _cache dict            │              │
│       │◀────────────────────────────────────────────────────┘              │
│       │                                                                     │
│  ┌──────────┐  within TTL    ┌──────────────────┐                          │
│  │  HIT     │ ◀───────────── │  CACHE CHECK      │                          │
│  │ (return) │  _get_cached() │  (lock → lookup)  │                          │
│  └──────────┘                └──────────────────┘                          │
│                                                                              │
│  ┌──────────┐  TTL exceeded  ┌──────────────────┐                          │
│  │  EXPIRED  │ ◀──────────── │  TTL EVALUATION   │                          │
│  │ (evict)  │  monotonic()  │  (now - ts > ttl) │                          │
│  └──────────┘                └──────────────────┘                          │
│       │                                                                     │
│       │  pop from _cache → transitions to MISS                              │
│       ▼                                                                     │
│  ┌──────────────────┐                                                       │
│  │  EVICTED          │ → next access triggers FETCHING                      │
│  └──────────────────┘                                                       │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  INVALIDATE (explicit)                                               │   │
│  │  invalidate(symbol, exchange) → remove specific keys                 │   │
│  │  invalidate()                 → clear entire cache                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Cache states:**
| State | Condition | Transition |
|---|---|---|
| MISS | Key not in `_cache` dict | → FETCHING |
| FETCHING | Calling `provider.quote()` or `provider.depth()` | → STORE |
| STORE | Writing `(time.monotonic(), value)` to `_cache` | → HIT |
| HIT | Key present, `monotonic() - ts <= ttl` | Return cached value |
| EXPIRED | Key present, `monotonic() - ts > ttl` | → EVICTED → MISS |
| EVICTED | Entry removed from `_cache` | Next access → MISS |

**Cache key format:** `"{type}:{exchange}:{symbol}"` where type is `quote` or `depth`.

**Concurrency control:** `threading.Lock` protects all `_cache` mutations.
- `_get_cached()` acquires lock to read, releases, then checks TTL.
- On TTL expiry, re-acquires lock to evict.
- `_set_cached()` acquires lock for write.
- `invalidate()` acquires lock for clear/pop.

### 2.2 Archive Caching

**No caching exists in the archive.** Every call to `MarketDataAdapter` methods
hits the Dhan HTTP API directly. The `DataLakeGateway` is a stub with no
implementation.

---

## 3. Pagination State Machine

### 3.1 Analysis

**Neither archive nor greenfield implements pagination for historical data.**

Dhan's historical/intraday API returns all matching candles in a single response.
There is no cursor, page token, or offset parameter in the API contract.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                      PAGINATION: Not Applicable                              │
│                                                                              │
│  Historical API: Single POST → complete response (all candles)               │
│  Market Feed API: Single POST → complete response (all requested symbols)    │
│                                                                              │
│  No cursor / offset / pageToken in request or response.                      │
│  No client-side pagination loop required.                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Risk:** If Dhan introduces pagination or response size limits in the future,
both implementations will silently truncate results. A defensive implementation
should check for pagination tokens in responses.

---

## 4. Failure Paths and Transitions

### 4.1 Historical Data Failure Paths

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    HISTORICAL DATA: Failure Path Map                         │
│                                                                              │
│  IDLE                                                                        │
│   │                                                                          │
│   ├─ resolve() fails ──────────────▶ InstrumentNotFoundError                 │
│   │                                   (symbol not in master CSV)             │
│   │                                                                          │
│   ├─ payload assertion fails ──────▶ AssertionError                          │
│   │                                   (invariant violation, programming bug) │
│   │                                                                          │
│   ├─ HTTP post fails ──────────────▶ NetworkError / ConnectionError          │
│   │                                   (no retry, propagates to caller)       │
│   │                                                                          │
│   ├─ HTTP 429 ─────────────────────▶ RateLimitError                          │
│   │                                   (no backoff, propagates to caller)     │
│   │                                                                          │
│   ├─ HTTP 5xx ─────────────────────▶ BrokerServerError                       │
│   │                                   (no retry, propagates to caller)       │
│   │                                                                          │
│   ├─ API returns status=failure ───▶ (greenfield) empty list []              │
│   │                                   (archive) MarketDataError raised       │
│   │                                                                          │
│   └─ parse fails ──────────────────▶ (greenfield) skip bad row, return []    │
│                                       (archive) partial DataFrame with zeros │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Market Data Failure Paths

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    MARKET DATA: Failure Path Map                             │
│                                                                              │
│  IDLE                                                                        │
│   │                                                                          │
│   ├─ resolve() fails ──────────────▶ InstrumentNotFoundError                 │
│   │                                                                          │
│   ├─ HTTP post fails ──────────────▶ NetworkError                            │
│   │                                                                          │
│   ├─ LTP key missing ──────────────▶ (archive) ValueError raised             │
│   │                                   (greenfield) returns Decimal("0")      │
│   │                                                                          │
│   ├─ Quote data missing ───────────▶ (archive) KeyError (unhandled)          │
│   │                                   (greenfield) map_quote returns zeroed  │
│   │                                                                          │
│   └─ Cache write fails ───────────▶ (service layer) Exception propagated     │
│                                      cache remains stale/empty               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Cache Failure Paths

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    CACHE: Failure Path Map                                   │
│                                                                              │
│  CACHE MISS                                                                  │
│   │                                                                          │
│   ├─ provider call succeeds ───────▶ Store in cache → return value           │
│   │                                                                          │
│   ├─ provider call raises ─────────▶ Exception propagates                    │
│   │                                   Cache entry NOT written                │
│   │                                   Next call → CACHE MISS again           │
│   │                                                                          │
│   ├─ Lock acquisition blocks ──────▶ Thread waits indefinitely               │
│   │                                   (no timeout on Lock.acquire)           │
│   │                                                                          │
│   └─ TTL check races with write ──▶ Theoretical: entry could be evicted      │
│                                      between read and TTL check.             │
│                                      Mitigated by re-lock before eviction.   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Greenfield vs Archive State Machine Comparison

| Aspect | Archive | Greenfield | Delta |
|---|---|---|---|
| Historical return type | `pd.DataFrame` | `list[Candle]` | Domain entities vs DataFrame |
| Date parameters | `str` (from_date, to_date) | `datetime` (start_time, end_time) | Type-safe dates |
| Timezone handling | None (naive timestamps) | `ZoneInfo("Asia/Kolkata")` | Timezone-aware |
| Columnar response | Not handled | Handled (`start_Time` arrays) | Robustness improvement |
| Parse failure | Raises `MarketDataError` | Returns `[]`, skips bad rows | Graceful degradation |
| LTP missing | Raises `ValueError` | Returns `Decimal("0")` | Silent zero vs explicit error |
| Quote missing key | `KeyError` (unhandled) | `map_quote` returns zeroed Quote | Defensive fallback |
| Caching | None | TTL cache in `MarketDataService` | New capability |
| Pagination | None | None | No change |
| Retry | None | None | No change |
| State tracking | Implicit (procedural) | Implicit (procedural) | No explicit state machine |
| Endpoint config | Hardcoded strings | `ENDPOINTS` dict | Externalized config |
| Instrument resolution | Via `DhanIdentityProvider` | Via `DhanInstrumentResolver` | Decoupled from auth |
| Invariant checks | `assert_dhan_payload` | `assert_valid_dhan_payload` | Same pattern, renamed |
| Batch operations | `get_batch_ltp`, `get_batch_quote` | Not implemented in adapter | **Gap** — batch moved to service or omitted |

---

## 6. Summary of State Machine Gaps

1. **No explicit state machine** in either implementation — both are purely procedural.
2. **No retry state** — network failures propagate immediately.
3. **No pagination state** — Dhan API is single-shot, but no defensive check exists.
4. **No circuit breaker state** at the adapter level (exists elsewhere in infrastructure).
5. **Cache has no error state** — failed fetches simply don't cache; no backoff or error tracking.
6. **No request deduplication** — concurrent identical requests both hit the API.
7. **LTP zero-return in greenfield** masks data unavailability — caller cannot distinguish "price is zero" from "data unavailable."
