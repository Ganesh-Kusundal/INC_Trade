# Phase 6 Dependency Graph — Historical Data & Market Data

## Overview

This document maps the dependency relationships for Phase 6 (Historical Data & Market Data) components, including internal module dependencies, cross-phase dependencies, data model relationships, and identifies gaps in the greenfield implementation.

---

## 1. Internal Dependencies (Within Phase 6)

### Archive Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                    ARCHIVE PHASE 6                          │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ historical.py    │                                      │
│  │ HistoricalAdapter│                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           ├────────────────► brokers.dhan.exceptions       │
│           ├────────────────► brokers.dhan.http_client       │
│           ├────────────────► brokers.dhan.identity          │
│           ├────────────────► brokers.dhan.invariants        │
│           └────────────────► domain.symbols                 │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ market_data.py   │                                      │
│  │ MarketDataAdapter│                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           ├────────────────► brokers.dhan.http_client       │
│           ├────────────────► brokers.dhan.identity          │
│           ├────────────────► brokers.dhan.invariants        │
│           └────────────────► domain (Quote, MarketDepth,   │
│                                     DepthLevel)            │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ datalake/        │                                      │
│  │ gateway.py       │                                      │
│  │ DataLakeGateway  │                                      │
│  └──────────────────┘                                      │
│           │ imports                                        │
│           └────────────────► (none — stub)                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Greenfield Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                   GREENFIELD PHASE 6                        │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ adapters/dhan/   │                                      │
│  │ historical.py    │                                      │
│  │ DhanHistorical   │                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           ├────────────────► adapters.dhan.config           │
│           ├────────────────► adapters.dhan.http             │
│           ├────────────────► adapters.dhan.identity         │
│           ├────────────────► adapters.dhan.invariants       │
│           └────────────────► domain.entities (Candle)       │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ adapters/dhan/   │                                      │
│  │ market_data.py   │                                      │
│  │ DhanMarketData   │                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           ├────────────────► adapters.dhan.config           │
│           ├────────────────► adapters.dhan.http             │
│           ├────────────────► adapters.dhan.identity         │
│           ├────────────────► adapters.dhan.invariants       │
│           ├────────────────► adapters.dhan.mapper           │
│           └────────────────► domain (MarketDepth, Quote)   │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ ports/           │                                      │
│  │ historical.py    │                                      │
│  │ HistoricalPort   │                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           └────────────────► domain.entities (Candle)       │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ ports/           │                                      │
│  │ market_data.py   │                                      │
│  │ MarketDataPort   │                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           └────────────────► domain.entities (Quote,       │
│                                               MarketDepth) │
│                                                             │
│  ┌──────────────────┐                                      │
│  │ services/        │                                      │
│  │ market_data_     │                                      │
│  │ service.py       │                                      │
│  │ MarketDataService│                                      │
│  └────────┬─────────┘                                      │
│           │ imports                                        │
│           ├────────────────► domain (MarketDepth, Quote)   │
│           └────────────────► ports.market_data              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Cross-Phase Dependencies

### Phase 0: Foundation & Configuration

**Archive**:
- `brokers.dhan.exceptions.MarketDataError` — Exception hierarchy
- `domain.symbols.normalize_exchange` — Exchange normalization

**Greenfield**:
- `brokers.adapters.dhan.config.ENDPOINTS` — REST endpoint URLs
- `brokers.adapters.dhan.config.SEGMENT_TO_EXCHANGE` — Segment mapping
- `brokers.domain.enums` — Order enums (Side, OrderType, etc.)

**Dependency Flow**:
```
Phase 0 (config, exceptions)
    ↓
Phase 6 (historical, market_data)
```

### Phase 1: Authentication & Identity

**Archive**:
- `brokers.dhan.identity.DhanIdentityProvider` — Token management
- `brokers.dhan.identity.coerce_identity_provider` — Identity adapter
- `DhanIdentityProvider.resolve_ref()` — Symbol → instrument reference

**Greenfield**:
- `brokers.adapters.dhan.identity.DhanInstrumentResolver` — Instrument resolution
- `DhanInstrumentResolver.resolve()` — Symbol → `DhanInstrumentRef`

**Dependency Flow**:
```
Phase 1 (auth, identity)
    ↓
Phase 6 (historical, market_data)
    uses identity.resolve_ref() or resolver.resolve()
```

### Phase 2: Instruments

**Archive**:
- `DhanIdentityProvider.resolver` — Instrument resolver reference
- `resolver.get_by_security_id()` — Lookup instrument by ID
- `Instrument.name` — Used for instrument type detection

**Greenfield**:
- `DhanInstrumentResolver` — Resolves symbol → `DhanInstrumentRef`
- `DhanInstrumentRef.security_id_str()` — Security ID as string
- `DhanInstrumentRef.security_id_int()` — Security ID as integer
- `DhanInstrumentRef.exchange_segment` — Wire segment code
- `DhanInstrumentRef.instrument_type` — Instrument type string

**Dependency Flow**:
```
Phase 2 (instruments)
    ↓
Phase 6 (historical, market_data)
    uses ref.security_id, ref.exchange_segment, ref.instrument_type
```

### Phase 3: HTTP Client & Resilience

**Archive**:
- `brokers.dhan.http_client.DhanHttpClient` — HTTP POST requests
- `DhanHttpClient.post(endpoint, json=payload)` — REST API calls

**Greenfield**:
- `brokers.adapters.dhan.http.DhanHttpClient` — HTTP POST requests
- `DhanHttpClient.post(endpoint, json=payload)` — REST API calls
- Rate limiting (implicit via `RATE_LIMITS` config)

**Dependency Flow**:
```
Phase 3 (HTTP client)
    ↓
Phase 6 (historical, market_data)
    uses client.post()
```

### Phase 4: Invariants & Validation

**Archive**:
- `brokers.dhan.invariants.assert_dhan_payload` — Payload validation
- `brokers.dhan.invariants.assert_dhan_identity` — Identity validation

**Greenfield**:
- `brokers.adapters.dhan.invariants.assert_valid_dhan_payload` — Payload validation

**Dependency Flow**:
```
Phase 4 (invariants)
    ↓
Phase 6 (historical, market_data)
    uses assert_valid_dhan_payload()
```

### Phase 5: Order Management (No Direct Dependency)

Phase 6 has **no direct dependencies** on Phase 5 (Order Management). Both phases are independent read/write operations.

---

## 3. Data Model Dependencies

### Domain Entities

**Archive**:
```python
# From domain module
Quote(
    symbol: str,
    ltp: Decimal,
    open: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: int,
    change: Decimal,
)

MarketDepth(
    symbol: str,
    bids: list[DepthLevel],
    asks: list[DepthLevel],
    depth_type: str,
)

DepthLevel(
    price: Decimal,
    quantity: int,
    orders: int,
)

# pandas DataFrame for candles
DataFrame[
    timestamp: datetime64,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    oi: int,
    symbol: str,
    exchange: str,
    timeframe: str,
]
```

**Greenfield**:
```python
# From brokers.domain.entities
@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

@dataclass(frozen=True)
class Quote:
    symbol: str
    ltp: Decimal
    exchange: str = ""
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    timestamp: datetime | None = None

@dataclass(frozen=True)
class MarketDepth:
    symbol: str
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    exchange: str = ""
    timestamp: datetime | None = None

@dataclass(frozen=True)
class DepthLevel:
    price: Decimal
    quantity: int
    orders: int = 0
```

**Key Differences**:
- Archive uses pandas DataFrame (mutable, float precision)
- Greenfield uses frozen dataclass (immutable, Decimal precision)
- Archive includes `change` field in Quote
- Archive includes `oi` field in candle DataFrame
- Greenfield includes `exchange` and `timestamp` in Quote/MarketDepth
- Greenfield uses `tuple` instead of `list` for bids/asks (immutable)

### Timeframe Definitions

**Archive** (`_TIMEFRAME_MAP`):
```python
{
    "1": 1, "1M": 1, "1m": 1,
    "5": 5, "5M": 5, "5m": 5,
    "15": 15, "15M": 15, "15m": 15,
    "25": 25,
    "60": 60, "60M": 60, "60m": 60,
    "1D": "1D", "D": "1D", "DAY": "1D",
}
```

**Greenfield** (`_TIMEFRAME_MAP`):
```python
{
    "1m": 1, "1M": 1, "1": 1,
    "5m": 5, "5M": 5, "5": 5,
    "15m": 15, "15M": 15, "15": 15,
    "25m": 25, "25": 25,
    "60m": 60, "60M": 60, "60": 60,
    "1D": "1D", "D": "1D", "DAY": "1D",
}
```

**Note**: Greenfield adds explicit "m" suffix variants for consistency.

---

## 4. Complete Dependency Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        DHAN BROKER ARCHITECTURE                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  PHASE 0: FOUNDATION                       │  │
│  │  ┌──────────────────┐  ┌──────────────────┐               │  │
│  │  │ config/          │  │ domain/          │               │  │
│  │  │ - ENDPOINTS      │  │ - enums          │               │  │
│  │  │ - RATE_LIMITS    │  │ - exceptions     │               │  │
│  │  │ - EXCHANGE_MAP   │  │                  │               │  │
│  │  └────────┬─────────┘  └────────┬─────────┘               │  │
│  └───────────┼──────────────────────┼────────────────────────┘  │
│              │                      │                           │
│              └──────────┬───────────┘                           │
│                         │                                       │
│  ┌──────────────────────▼───────────────────────────────────┐  │
│  │                  PHASE 1: AUTHENTICATION                  │  │
│  │  ┌──────────────────────────────────┐                    │  │
│  │  │ identity.py                      │                    │  │
│  │  │ - DhanInstrumentResolver         │                    │  │
│  │  │ - DhanInstrumentRef              │                    │  │
│  │  │ - resolve(symbol, exchange)      │                    │  │
│  │  └────────────┬─────────────────────┘                    │  │
│  └───────────────┼──────────────────────────────────────────┘  │
│                  │                                              │
│  ┌───────────────▼──────────────────────────────────────────┐  │
│  │                  PHASE 2: INSTRUMENTS                     │  │
│  │  ┌──────────────────────────────────┐                    │  │
│  │  │ instruments.py                   │                    │  │
│  │  │ - Instrument CSV loader          │                    │  │
│  │  │ - Security ID mapping            │                    │  │
│  │  │ - Exchange segment resolution    │                    │  │
│  │  └────────────┬─────────────────────┘                    │  │
│  └───────────────┼──────────────────────────────────────────┘  │
│                  │                                              │
│  ┌───────────────▼──────────────────────────────────────────┐  │
│  │                  PHASE 3: HTTP CLIENT                     │  │
│  │  ┌──────────────────────────────────┐                    │  │
│  │  │ http.py                          │                    │  │
│  │  │ - DhanHttpClient                 │                    │  │
│  │  │ - Rate limiting                  │                    │  │
│  │  │ - Retry logic                    │                    │  │
│  │  │ - POST(endpoint, json)           │                    │  │
│  │  └────────────┬─────────────────────┘                    │  │
│  └───────────────┼──────────────────────────────────────────┘  │
│                  │                                              │
│  ┌───────────────▼──────────────────────────────────────────┐  │
│  │                  PHASE 4: INVARIANTS                      │  │
│  │  ┌──────────────────────────────────┐                    │  │
│  │  │ invariants.py                    │                    │  │
│  │  │ - assert_valid_dhan_payload()    │                    │  │
│  │  │ - Payload validation             │                    │  │
│  │  └────────────┬─────────────────────┘                    │  │
│  └───────────────┼──────────────────────────────────────────┘  │
│                  │                                              │
│  ┌───────────────▼──────────────────────────────────────────┐  │
│  │                  PHASE 6: HISTORICAL & MARKET DATA        │  │
│  │                                                          │  │
│  │  ┌─────────────────┐       ┌─────────────────┐          │  │
│  │  │ ports/          │       │ adapters/dhan/  │          │  │
│  │  │ historical.py   │◄──────│ historical.py   │          │  │
│  │  │ HistoricalPort  │       │ DhanHistorical  │          │  │
│  │  └─────────────────┘       └────────┬────────┘          │  │
│  │                                     │                    │  │
│  │  ┌─────────────────┐       ┌────────┴────────┐          │  │
│  │  │ ports/          │       │ adapters/dhan/  │          │  │
│  │  │ market_data.py  │◄──────│ market_data.py  │          │  │
│  │  │ MarketDataPort  │       │ DhanMarketData  │          │  │
│  │  └────────┬────────┘       └─────────────────┘          │  │
│  │           │                                              │  │
│  │  ┌────────┴─────────────────┐                           │  │
│  │  │ services/                │                           │  │
│  │  │ market_data_service.py   │                           │  │
│  │  │ MarketDataService        │                           │  │
│  │  │ - TTL cache              │                           │  │
│  │  │ - Thread-safe            │                           │  │
│  │  └──────────────────────────┘                           │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │ domain/entities.py                               │   │  │
│  │  │ - Candle (frozen dataclass)                      │   │  │
│  │  │ - Quote (frozen dataclass)                       │   │  │
│  │  │ - MarketDepth (frozen dataclass)                 │   │  │
│  │  │ - DepthLevel (frozen dataclass)                  │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │ adapters/dhan/mapper.py                          │   │  │
│  │  │ - map_quote(symbol, data) → Quote                │   │  │
│  │  │ - map_depth(symbol, data) → MarketDepth          │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Module Dependency Matrix

### Archive

| Module | Depends On |
|--------|------------|
| `historical.py` | `exceptions`, `http_client`, `identity`, `invariants`, `domain.symbols` |
| `market_data.py` | `http_client`, `identity`, `invariants`, `domain` (Quote, MarketDepth, DepthLevel) |
| `datalake/gateway.py` | (none) |

### Greenfield

| Module | Depends On |
|--------|------------|
| `adapters/dhan/historical.py` | `config`, `http`, `identity`, `invariants`, `domain.entities.Candle` |
| `adapters/dhan/market_data.py` | `config`, `http`, `identity`, `invariants`, `mapper`, `domain` (Quote, MarketDepth) |
| `ports/historical.py` | `domain.entities.Candle` |
| `ports/market_data.py` | `domain.entities` (Quote, MarketDepth) |
| `services/market_data_service.py` | `domain` (Quote, MarketDepth), `ports.market_data.MarketDataPort` |
| `adapters/dhan/mapper.py` | `domain` (all entities), `domain.enums`, `utils.price.to_decimal` |

---

## 6. Greenfield Gap Analysis

### Missing Features

#### Critical Gaps

1. **Batch Operations**
   - **Archive**: `get_batch_ltp(symbols)` — Single API call for N symbols
   - **Archive**: `get_batch_quote(symbols)` — Single API call for N symbols
   - **Greenfield**: ❌ Not implemented
   - **Impact**: 10x slower for bulk queries, rate limit violations
   - **Priority**: HIGH

2. **OHLC Method**
   - **Archive**: `get_ohlc(symbol)` — Dedicated OHLC endpoint
   - **Greenfield**: ❌ Not implemented (endpoint defined but no method)
   - **Impact**: Must use `quote()` and extract OHLC fields
   - **Priority**: MEDIUM

3. **Open Interest (OI)**
   - **Archive**: Included in candle DataFrame (`oi` column)
   - **Greenfield**: ❌ Not in `Candle` entity
   - **Impact**: Cannot track open interest for derivatives
   - **Priority**: MEDIUM (if derivatives trading is needed)

#### Minor Gaps

4. **Change Field in Quote**
   - **Archive**: `Quote.change` (net_change)
   - **Greenfield**: ❌ Not in `Quote` entity
   - **Impact**: Must calculate change manually (ltp - close)
   - **Priority**: LOW

5. **Depth Type Field**
   - **Archive**: `MarketDepth.depth_type = "DEPTH_5"`
   - **Greenfield**: ❌ Not in `MarketDepth` entity
   - **Impact**: Cannot distinguish between depth levels (5 vs 20)
   - **Priority**: LOW

6. **Error Handling Consistency**
   - **Archive**: Raises exceptions on missing data
   - **Greenfield**: Returns default values (Decimal(0))
   - **Impact**: Silent failures, harder debugging
   - **Priority**: MEDIUM

7. **MCX Session Times**
   - **Archive**: MCX-specific session times (09:00-23:30)
   - **Greenfield**: Hardcoded default (09:15-15:30)
   - **Impact**: Incorrect intraday candles for MCX instruments
   - **Priority**: HIGH (if MCX trading is needed)

### Architectural Improvements (Greenfield)

1. **Port-Based Design**
   - Protocols define contracts (`HistoricalPort`, `MarketDataPort`)
   - Adapters implement protocols (dependency inversion)
   - Enables easy broker swapping

2. **Service Layer with Caching**
   - `MarketDataService` adds TTL cache
   - Reduces API calls for repeated queries
   - Thread-safe implementation

3. **Frozen Entities**
   - Immutable dataclasses (thread-safe)
   - Decimal precision (no float rounding)
   - Explicit timezone handling

4. **Mapper Separation**
   - DTO → entity conversion isolated in `mapper.py`
   - Easier testing and maintenance

5. **Dual Format Parsing**
   - Handles both row and columnar response formats
   - More robust to API changes

6. **Multi-Path Lookup**
   - Multiple fallback paths for response extraction
   - Handles API response variations

---

## 7. Dependency Direction

```
┌─────────────────────────────────────────────────────────────┐
│                    DEPENDENCY FLOW                          │
│                                                             │
│  Phase 0 (config) ─────────┐                                │
│                            │                                │
│  Phase 1 (auth) ───────────┤                                │
│                            │                                │
│  Phase 2 (instruments) ────┤                                │
│                            │                                │
│  Phase 3 (HTTP) ───────────┤                                │
│                            │                                │
│  Phase 4 (invariants) ─────┤                                │
│                            │                                │
│                            ▼                                │
│                     ┌──────────────┐                        │
│                     │   PHASE 6    │                        │
│                     │              │                        │
│                     │  ports/      │◄─────── Protocol       │
│                     │     ▲        │                        │
│                     │     │        │                        │
│                     │     │ uses   │                        │
│                     │     │        │                        │
│                     │  adapters/   │◄─────── Implementation │
│                     │     ▲        │                        │
│                     │     │        │                        │
│                     │     │ uses   │                        │
│                     │     │        │                        │
│                     │  services/   │◄─────── Application    │
│                     │              │                        │
│                     └──────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Dependency Rule**: Dependencies point inward (adapters → ports → domain). The domain layer has zero external dependencies.

---

## 8. External Dependencies

### Python Standard Library
- `datetime` — Timestamp handling
- `decimal.Decimal` — Precision arithmetic
- `zoneinfo.ZoneInfo` — Timezone handling (Asia/Kolkata)
- `threading.Lock` — Thread safety
- `time.monotonic` — Cache TTL tracking
- `logging` — Structured logging

### Third-Party Libraries
- **Archive**: `pandas` — DataFrame for candle data
- **Greenfield**: None (pure Python)

### Dhan API Endpoints
- `/charts/historical` — Daily candles
- `/charts/intraday` — Intraday candles (via historical endpoint)
- `/marketfeed/ltp` — Last Traded Price
- `/marketfeed/quote` — Full quote + market depth
- `/marketfeed/ohlc` — OHLC data (not used in greenfield)

---

## 9. Circular Dependency Check

**Status**: ✅ No circular dependencies detected

**Verification**:
- `ports/` depends only on `domain/`
- `adapters/` depends on `ports/`, `domain/`, and infrastructure (`config`, `http`, `identity`, `invariants`)
- `services/` depends on `ports/` and `domain/`
- `domain/` has zero internal dependencies

---

## 10. Migration Checklist

### To Complete Phase 6 Greenfield

- [ ] **Implement batch LTP method** in `DhanMarketData`
  - Add `batch_ltp(symbols: list[str], exchange: str) -> dict[str, Decimal]`
  - Group symbols by segment
  - Single API call to `/marketfeed/ltp`
  
- [ ] **Implement batch quote method** in `DhanMarketData`
  - Add `batch_quote(symbols: list[str], exchange: str) -> dict[str, Quote]`
  - Group symbols by segment
  - Single API call to `/marketfeed/quote`
  
- [ ] **Implement OHLC method** in `DhanMarketData`
  - Add `ohlc(symbol: str, exchange: str) -> dict`
  - Call `/marketfeed/ohlc` endpoint
  
- [ ] **Add open interest to Candle entity** (if needed)
  - Add `oi: int = 0` field to `Candle` dataclass
  - Update `_parse()` in `DhanHistorical` to extract OI
  
- [ ] **Add change field to Quote entity** (optional)
  - Add `change: Decimal = Decimal("0")` field
  - Update `map_quote()` to extract `net_change`
  
- [ ] **Fix MCX session times** in `DhanHistorical`
  - Add session time lookup by exchange
  - MCX: 09:00:00 → 23:30:00
  - Default: 09:15:00 → 15:30:00
  
- [ ] **Standardize error handling**
  - Raise exceptions on missing data (like archive)
  - Or document default value behavior
  
- [ ] **Add integration tests**
  - Test batch operations
  - Test cache behavior
  - Test error scenarios

---

## 11. Summary

### Dependency Count

| Phase | Archive Dependencies | Greenfield Dependencies |
|-------|---------------------|-------------------------|
| Phase 0 | 2 (exceptions, symbols) | 2 (config, enums) |
| Phase 1 | 1 (identity) | 1 (identity) |
| Phase 2 | 1 (resolver via identity) | 1 (resolver) |
| Phase 3 | 1 (http_client) | 1 (http) |
| Phase 4 | 1 (invariants) | 1 (invariants) |
| Phase 6 (internal) | 3 (historical, market_data, datalake) | 6 (2 adapters, 2 ports, 1 service, 1 mapper) |

### Complexity Comparison

| Metric | Archive | Greenfield |
|--------|---------|------------|
| Total files | 3 | 7 |
| Total lines | 373 | 558 |
| Classes | 3 | 6 |
| Protocols | 0 | 2 |
| Services | 0 | 1 |
| Mappers | 0 | 1 (dedicated) |
| Domain entities | 3 (from domain) | 4 (Candle, Quote, MarketDepth, DepthLevel) |

### Key Takeaways

1. **Greenfield is more modular** — Separation of concerns (ports, adapters, services)
2. **Greenfield has better caching** — Service layer with TTL cache
3. **Greenfield is missing batch operations** — Critical performance gap
4. **Greenfield has improved robustness** — Dual format parsing, multi-path lookup
5. **Greenfield eliminates pandas** — Pure Python, lighter dependencies
6. **Greenfield uses immutable entities** — Thread-safe, predictable
