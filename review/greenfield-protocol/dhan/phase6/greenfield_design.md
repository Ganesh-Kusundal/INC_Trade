# Phase 6 — Greenfield Design Document: Historical & Market Data
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 6 — Historical Data  
**Date:** 2026-07-03  
**Status:** Design Review  

---

## 1. Architecture Overview

### 1.1 Archive Architecture (Flat Adapter)

```
archive/brokers/dhan/
├── historical.py (173 lines)
│   ├── HistoricalAdapter class
│   ├── Timeframe map (16 entries)
│   ├── MCX session time constants
│   ├── Daily + intraday endpoint routing
│   ├── DataFrame-based parsing (row-dict only)
│   └── Complex instrument type resolution (4-level fallback)
│
├── market_data.py (187 lines)
│   ├── MarketDataAdapter class
│   ├── get_ltp() — single symbol
│   ├── get_quote() — single symbol
│   ├── get_depth() — 5-level depth
│   ├── get_ohlc() — dedicated OHLC endpoint
│   ├── get_batch_ltp() — multi-symbol, segment-grouped
│   └── get_batch_quote() — multi-symbol, segment-grouped
│
archive/datalake/
└── gateway.py (13 lines) — Empty stub

No service layer. No caching. No port abstraction.
```

**Characteristics:**
- Two monolithic adapter classes with all logic inline
- Returns `pd.DataFrame` for historical data (heavy dependency)
- Returns `Decimal` for LTP, domain `Quote`/`MarketDepth` for market data
- Batch operations built directly into adapter
- No caching, no port abstraction, no service layer
- Complex instrument type resolution embedded in adapter

### 1.2 Greenfield Architecture (Layered with Ports)

```
brokers/
├── ports/
│   ├── historical.py (44 lines) — HistoricalPort Protocol
│   └── market_data.py (19 lines) — MarketDataPort Protocol
│
├── adapters/dhan/
│   ├── historical.py (160 lines)
│   │   ├── DhanHistorical class
│   │   ├── Timeframe map (17 entries)
│   │   ├── Dual-format parsing (columnar + row-dict)
│   │   └── Returns list[Candle] (domain entities)
│   │
│   ├── market_data.py (90 lines)
│   │   ├── DhanMarketData class
│   │   ├── ltp() — with multi-fallback response parsing
│   │   ├── quote() — via map_quote helper
│   │   └── depth() — via map_depth helper (up to 20 levels)
│   │
│   └── mapper.py (202 lines) — DTO → domain entity mapping
│
├── services/
│   └── market_data_service.py (75 lines)
│       ├── TTL-based cache (default 1s)
│       ├── Thread-safe (threading.Lock)
│       ├── ltp() derived from quote()
│       └── invalidate() API
│
└── domain/
    └── entities.py
        ├── Candle (frozen dataclass) — OHLCV only, no OI
        ├── Quote (frozen dataclass) — LTP + OHLC + volume
        └── MarketDepth (frozen dataclass) — bids/asks tuples
```

**Characteristics:**
- Clean port → adapter → service layering
- Domain entities (frozen dataclasses) replace DataFrames
- Dedicated mapper module for DTO → entity conversion
- Service layer adds caching transparently
- Narrow port interfaces (ISP compliance)
- Adapter depends on resolver, not identity provider

---

## 2. Improvements Over Archive

### 2.1 Domain Entity Return Types

**Archive:** `get_historical()` returns `pd.DataFrame` — pulls pandas dependency into the data path, mutable, no type safety.

**Greenfield:** `get_historical_candles()` returns `list[Candle]` — frozen dataclass, zero external dependencies, full type safety. Callers can convert to DataFrame if needed.

**Impact:** Eliminates pandas coupling from the adapter layer. Candle is a pure domain value object.

### 2.2 Dual-Format Response Parsing

**Archive:** Only handles row-dict format (each candle is a dict with timestamp/open/high/etc keys).

**Greenfield:** Handles both columnar format (`start_Time` array + `open`/`high`/`low`/`close` arrays) and row-dict format. Dhan's API sometimes returns columnar data for chart endpoints.

**Impact:** Greenfield is more robust against API response format variations.

### 2.3 Multi-Fallback Response Parsing (Market Data)

**Archive:** Direct path lookup: `data["data"][segment][str(sid)]` — crashes if response structure differs.

**Greenfield:** 4-tier fallback: `segment[sid]` → `feed[str(sid)]` → `feed["segment:sid"]` → `feed[symbol]`. Handles non-standard Dhan response nesting.

**Impact:** More resilient to Dhan API response format inconsistencies.

### 2.4 Port Abstractions

**Archive:** No port/interface definitions. Callers depend on concrete adapter classes.

**Greenfield:** `HistoricalPort` and `MarketDataPort` Protocols with `runtime_checkable`. Enables dependency inversion, testing with fakes, and multi-broker support.

**Impact:** Clean architecture dependency rule. Adapters are swappable.

### 2.5 Service-Layer Caching

**Archive:** No caching. Every LTP/quote call hits the broker API.

**Greenfield:** `MarketDataService` wraps `MarketDataPort` with TTL cache (default 1s), thread-safe via `threading.Lock`. Supports per-symbol or full invalidation.

**Impact:** Reduces API call volume for high-frequency LTP/quote consumers. Configurable TTL.

### 2.6 Timezone-Aware Timestamps

**Archive:** `pd.to_datetime(df["timestamp"], unit="s")` — timezone-naive datetime.

**Greenfield:** `datetime.fromtimestamp(ts, tz=ZoneInfo("Asia/Kolkata"))` — timezone-aware IST timestamps.

**Impact:** Prevents timezone ambiguity bugs in downstream strategy code.

### 2.7 Dedicated Mapper Module

**Archive:** Parsing logic embedded in adapter methods.

**Greenfield:** `mapper.py` centralizes all DTO → domain entity conversions (`map_quote`, `map_depth`, `map_order`, etc.). Single place to update when Dhan API changes.

**Impact:** Separation of concerns. Adapter focuses on HTTP orchestration; mapper focuses on field mapping.

---

## 3. Dropped Behaviors (Gaps)

### 3.1 CRITICAL Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-1 | Intraday endpoint uses `/charts/historical` instead of `/charts/intraday` | `archive/brokers/dhan/historical.py:81` | Intraday historical data requests may fail or return wrong data. Dhan API documents separate endpoints for daily vs intraday. |

### 3.2 HIGH Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-2 | MCX exchange session times not supported | `archive/brokers/dhan/historical.py:17-18` | MCX intraday candles use NSE times (09:15–15:30) instead of MCX times (09:00–23:30). Data will cover wrong time window. |
| G-3 | Open Interest (OI) not in Candle entity | `archive/brokers/dhan/historical.py:133-134` | OI data requested from API (`"oi": True`) but silently dropped. Derivatives strategies that need OI history cannot use greenfield. |
| G-4 | LTP returns `Decimal(0)` instead of raising on missing data | `archive/brokers/dhan/market_data.py:53-55` | Silent zero masks data availability issues. Strategies may act on stale/missing data without knowing. |

### 3.3 MEDIUM Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-5 | No API failure status check in historical parser | `archive/brokers/dhan/historical.py:119-120` | API returning `{"status": "failure"}` silently produces empty results instead of raising |
| G-6 | Simplified instrument type resolution | `archive/brokers/dhan/historical.py:153-172` | 4-level fallback chain replaced by direct `ref.instrument_type`. Edge cases (INDEX→EQUITY, NFO→OPTIDX) may fail. |
| G-7 | No post-fetch logging for historical data | `archive/brokers/dhan/historical.py:100-109` | Lost observability: cannot audit how many candles were fetched or verify date ranges |
| G-8 | Quote `change`/`net_change` field not mapped | `archive/brokers/dhan/market_data.py:77` | `Quote.change` always defaults to `Decimal("0")` in greenfield |
| G-9 | Depth level count mismatch (5 vs 20) | `archive/brokers/dhan/market_data.py:96` | Archive returns DEPTH_5; greenfield may return up to 20 levels. Downstream code expecting 5 levels may break. |
| G-10 | Depth response format assumption differs | `archive/brokers/dhan/market_data.py:90-105` | Archive parses `depth.buy[]`/`depth.sell[]`; greenfield parses `bid0`-`bid19` flat keys. One of them is wrong for actual API. |
| G-11 | Service `ltp()` hits quote endpoint instead of LTP endpoint | `brokers/services/market_data_service.py:30-32` | Fetches full quote data when only price is needed. Wastes bandwidth and API quota. |

### 3.4 LOW Severity

| Gap ID | Behavior | Archive Reference | Impact |
|---|---|---|---|
| G-12 | No dedicated OHLC method in adapter/port | `archive/brokers/dhan/market_data.py:115-122` | OHLC data available via `quote()` but not as standalone lightweight call |
| G-13 | No batch LTP capability | `archive/brokers/dhan/market_data.py:124-146` | Multi-symbol LTP requires N sequential calls instead of 1 batched call |
| G-14 | No batch Quote capability | `archive/brokers/dhan/market_data.py:148-187` | Multi-symbol quote requires N sequential calls instead of 1 batched call |
| G-15 | No DataLakeGateway stub | `archive/datalake/gateway.py` | Stub was placeholder; no functional impact |
| G-16 | No historical data caching service | N/A | Neither archive nor greenfield caches historical data; consistent gap |

---

## 4. Key Architectural Decisions

### 4.1 Service Layer vs Direct Adapter Calls

**Decision:** Greenfield introduces `MarketDataService` between callers and `MarketDataPort`.

**Rationale:**
- Archive has no service layer — callers invoke adapter methods directly
- Service layer enables cross-cutting concerns (caching, logging, metrics) without polluting adapters
- Follows dependency inversion: callers depend on service, not adapter

**Trade-off:**
- Adds indirection for simple pass-through cases
- `ltp()` in service calls `quote()` instead of adapter's `ltp()` — wastes bandwidth
- **Recommendation:** Service `ltp()` should call adapter's `ltp()` directly, not derive from `quote()`

### 4.2 Caching Strategy

**Decision:** In-memory TTL cache with `threading.Lock` in `MarketDataService`.

**Rationale:**
- Archive has no caching — every call hits the API
- 1-second default TTL prevents API saturation for high-frequency callers
- Thread-safe for multi-threaded strategy execution

**Trade-offs:**
- In-memory only — no cross-process cache sharing
- No cache warming on startup
- No exponential backoff or stale-while-revalidate pattern
- **Recommendation:** Consider `functools.lru_cache` for historical data if repeated queries are common

### 4.3 Pagination Approach

**Decision:** Neither archive nor greenfield implements pagination for historical data.

**Analysis:**
- Dhan API returns all candles in a single response for the given date range
- No cursor/offset parameters in the API
- For very long date ranges, the API may truncate results silently
- **Recommendation:** Add date-range chunking in the adapter for ranges > 1 year to ensure complete data

### 4.4 Data Validation Approach

**Decision:** Greenfield uses `assert_valid_dhan_payload` pre-flight check; no post-response validation.

**Analysis:**
- Archive validates response status (`status == "failure"`) after parsing
- Greenfield skips response validation — relies on parser to handle bad data gracefully
- Parser returns empty list for unrecognizable data (defensive)
- **Recommendation:** Add explicit failure status check in `_parse()` to match archive behavior

### 4.5 Return Type: Domain Entities vs DataFrames

**Decision:** Greenfield returns `list[Candle]` instead of `pd.DataFrame`.

**Rationale:**
- Decouples adapter layer from pandas dependency
- Frozen dataclasses provide immutability and type safety
- Callers can convert to DataFrame with `pd.DataFrame([c.__dict__ for c in candles])`

**Trade-off:**
- Loss of DataFrame convenience (column access, resampling, rolling windows)
- **Recommendation:** Provide a utility function `candles_to_dataframe(candles: list[Candle]) -> pd.DataFrame` in a utils module

---

## 5. Design Principles Applied

### 5.1 ports and Adapters (Hexagonal Architecture)

- `HistoricalPort` and `MarketDataPort` define inbound interfaces
- `DhanHistorical` and `DhanMarketData` implement outbound adapter interfaces
- Domain entities (`Candle`, `Quote`, `MarketDepth`) are independent of both

### 5.2 Interface Segregation Principle (ISP)

- `MarketDataPort` is narrow: only `ltp`, `quote`, `depth`
- Historical data separated into `HistoricalPort`
- Each port method is focused and minimal

### 5.3 Dependency Inversion

- Service layer depends on `MarketDataPort` (abstraction), not `DhanMarketData` (concrete)
- Enables paper broker or test fake substitution

### 5.4 Single Responsibility

- Adapter handles HTTP orchestration
- Mapper handles DTO → entity conversion
- Service handles caching
- Domain entities handle data representation

### 5.5 Frozen Value Objects

- All domain entities are `frozen=True` dataclasses
- Thread-safe by construction
- No accidental mutation

---

## 6. Recommended Architecture for Greenfield Historical Data

### 6.1 Immediate Fixes (Pre-Production)

```
1. Fix intraday endpoint routing
   - Add ENDPOINTS["intraday"] = f"{REST_BASE}/charts/intraday"
   - Route sub-day intervals to intraday endpoint in DhanHistorical

2. Add exchange-aware session times
   - Add SESSION_TIMES dict to config.py
   - Look up exchange-specific open/close in get_historical_candles()

3. Fix LTP error handling
   - Raise InstrumentNotFoundError or DataError when price is None/0
   - Match archive's descriptive error behavior

4. Add API failure status check
   - Check data.get("status") == "failure" in _parse()
   - Raise BrokerError or DataError on failure response
```

### 6.2 Short-Term Enhancements

```
5. Add OI field to Candle entity (optional)
   - Add `oi: int = 0` to Candle dataclass
   - Populate from API response in _parse()

6. Fix service ltp() to use adapter ltp()
   - MarketDataService.ltp() should call self._provider.ltp() directly
   - Add separate cache for LTP data

7. Add post-fetch logging
   - Log symbol, resolution, candle count, date range after fetch

8. Fix instrument type resolution
   - Port archive's 4-level fallback chain to resolver or adapter
```

### 6.3 Medium-Term Additions

```
9.  Add batch operations to MarketDataPort
    - batch_ltp(symbols, exchange) → dict[str, Decimal]
    - batch_quote(symbols, exchange) → dict[str, Quote]

10. Add OHLC method to MarketDataPort
    - ohlc(symbol, exchange) → dict

11. Add date-range chunking for historical data
    - Split queries > 1 year into annual chunks
    - Merge results into single list[Candle]

12. Add historical data caching
    - Extend MarketDataService or create HistoricalDataService
    - Cache by (symbol, exchange, resolution, start, end) key
    - Longer TTL (e.g., 5 minutes) since historical data is stable
```

### 6.4 Target Architecture Diagram

```
                    ┌──────────────────┐
                    │  Strategy Code   │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──────┐ ┌────▼─────┐ ┌──────▼────────┐
    │ HistoricalPort  │ │MarketData│ │MarketDataService│
    │                 │ │  Port    │ │  (cache layer) │
    └─────────┬──────┘ └────┬─────┘ └──────┬────────┘
              │              │              │
    ┌─────────▼──────┐ ┌────▼──────────────▼─────┐
    │DhanHistorical   │ │    DhanMarketData       │
    │ • endpoint route│ │ • ltp / quote / depth   │
    │ • session times │ │ • batch_ltp / batch_quote│
    │ • dual parsing  │ │ • ohlc                   │
    └─────────┬──────┘ └────┬─────────────────────┘
              │              │
    ┌─────────▼──────────────▼─────────────┐
    │         DhanHttpClient               │
    │  (rate limiting, circuit breaker)    │
    └──────────────────────────────────────┘
```

---

## 7. Summary

The greenfield historical data implementation is a **structurally superior** but **behaviorally incomplete** port of the archive.

**Strengths:**
- Clean layered architecture with port abstractions
- Domain entities replace DataFrame dependency
- Dual-format parsing is more robust
- Service-layer caching reduces API load
- Timezone-aware timestamps

**Weaknesses:**
- Intraday endpoint routing is wrong (CRITICAL)
- MCX session times not supported (HIGH)
- Missing batch operations, OHLC method
- LTP error handling is silently permissive
- No post-fetch observability

**Overall parity:** ~65% of archive behavior preserved, ~20% improved, ~15% missing or degraded.

---

*End of greenfield_design.md*
