# Brokers Module Rebuild — Multi-Agent Execution Plan

> **Goal**: Rebuild `brokers/` following Clean Architecture (Bob Martin) + TDD (Dr. Venkat Subramaniam)
> **Strategy**: Keep existing Phase 1+2 foundation (60 tests), extend with real API surface from archived code
> **Approach**: Multi-agent parallel execution with dependency-graph-driven scheduling

---

## 1. Current State

| Layer | Files | Tests | Status |
|---|---|---|---|
| `domain/entities.py` | 10 entities + 6 enums | 12 | ✅ Keep — needs extension |
| `domain/ports.py` | 3 Protocols + OrderRequest | 5 | ✅ Keep — needs extension |
| `infrastructure/resilience.py` | @rate_limit + @circuit_breaker | 19 | ✅ Keep |
| `infrastructure/health.py` | HealthRegistry + decorator | 12 | ✅ Keep |
| `infrastructure/logging.py` | StructuredLogger | 8 | ✅ Keep |
| `paper/` | empty `__init__.py` | 0 | ❌ Build |
| `dhan/` | empty `__init__.py` | 0 | ❌ Build |
| `upstox/` | empty `__init__.py` | 0 | ❌ Build |
| **Total** | **20 files** | **60 pass** | |

Reference code: `_archive/brokers_archive/` contains the old Dhan (50+ files) and Upstox (60+ files) implementations.

---

## 2. Target Architecture

```
brokers/
├── __init__.py                 # Public API re-exports
├── domain/
│   ├── __init__.py
│   ├── entities.py             # Extended: +Trade, +Holding, +OptionChain, +FutureChain, +Instrument
│   └── ports.py                # Extended: +get_trades, +get_holdings, +get_option_chain, +get_future_chain
├── infrastructure/
│   ├── __init__.py
│   ├── resilience.py           # Keep: @rate_limit, @circuit_breaker
│   ├── health.py               # Keep: HealthRegistry
│   ├── logging.py              # Keep: StructuredLogger
│   ├── rate_config.py          # NEW: Per-endpoint rate limit configs (Dhan/Upstox real limits)
│   └── http_client.py          # NEW: Base HTTP client (retry, token refresh, CB integration)
├── paper/
│   ├── __init__.py
│   └── adapter.py              # NEW: In-memory reference impl of all ports
├── dhan/
│   ├── __init__.py
│   ├── mapper.py               # NEW: Dhan JSON ↔ domain entities
│   ├── client.py               # NEW: Dhan HTTP client (auth, rate limits, endpoints)
│   └── adapter.py              # NEW: Implements TradingPort + MarketDataPort via client+mapper
├── upstox/
│   ├── __init__.py
│   ├── mapper.py               # NEW: Upstox JSON ↔ domain entities
│   ├── client.py               # NEW: Upstox HTTP client (Bearer auth, V2/V3 endpoints)
│   └── adapter.py              # NEW: Implements TradingPort + MarketDataPort via client+mapper
└── tests/
    ├── __init__.py
    ├── domain/
    │   ├── __init__.py
    │   ├── test_entities.py    # Extended: +Trade, +Holding, +OptionChain tests
    │   └── test_ports.py       # Extended: +new port method contract tests
    ├── infrastructure/
    │   ├── __init__.py
    │   ├── test_resilience.py  # Keep
    │   ├── test_health.py      # Keep
    │   ├── test_logging.py     # Keep
    │   ├── test_rate_config.py # NEW
    │   └── test_http_client.py # NEW
    └── adapters/
        ├── __init__.py
        ├── test_paper.py       # NEW
        ├── test_dhan.py        # NEW
        └── test_upstox.py      # NEW
```

**File count target: ~28 files (vs 200+ in old archive)**

---

## 3. API Surface (from archived code)

### Dhan REST API
| Endpoint | Method | Rate Limit | Purpose |
|---|---|---|---|
| `/orders` | POST | 25/s | Place order |
| `/orders/{id}` | PUT | 25/s | Modify order |
| `/orders/{id}` | DELETE | 25/s | Cancel order |
| `/orders` | GET | 25/s | Get orderbook |
| `/orders/{id}` | GET | 25/s | Get single order |
| `/trades` | GET | 25/s | Get trade book |
| `/marketfeed/ltp` | POST | 10/s | Get LTP |
| `/marketfeed/quote` | POST | **1/s** | Get quote (strictest) |
| `/marketfeed/ohlc` | POST | 10/s | Get OHLC |
| `/optionchain` | POST | ~3/s | Get option chain |
| `/charts/historical` | POST | 10/s | Historical daily |
| `/charts/intraday` | POST | 10/s | Historical intraday |
| `/positions` | GET | — | Get positions |
| `/holdings` | GET | — | Get holdings |
| `/fundlimit` | GET | — | Get balance/funds |

**Auth**: `access-token` header + `client-id` header
**Base URL**: `https://api.dhan.co/v2`
**Rate limit categories**: read (market data), write (orders), admin (portfolio)

### Upstox REST API
| Endpoint | Method | Purpose |
|---|---|---|
| `/v2/order/place` | POST | Place order |
| `/v2/order/cancel` | DELETE | Cancel order |
| `/v2/order/modify` | PUT | Modify order |
| `/v2/order/retrieve-all` | GET | Get orderbook |
| `/v2/order/history` | GET | Get order history |
| `/v2/trades/trades-for-day` | GET | Get trade book |
| `/v2/market-quote/ltp` | GET | Get LTP |
| `/v2/market-quote/quotes` | GET | Get quote |
| `/v2/market-quote/ohlc` | GET | Get OHLC |
| `/v2/historical-candle/...` | GET | Historical candles |
| `/v2/option/chain` | GET | Option chain |
| `/v2/portfolio/short-term-positions` | GET | Get positions |
| `/v2/portfolio/long-term-holdings` | GET | Get holdings |
| `/v2/user/get-fund-and-margin` | GET | Get funds/balance |

**Auth**: `Bearer {access_token}` header
**Base URL**: `https://api.upstox.com`

### Domain Entities to Add/Extend

| Entity | Action | Key fields |
|---|---|---|
| `Trade` | **ADD** | trade_id, order_id, symbol, exchange, side, quantity, price, timestamp, product_type |
| `Holding` | **ADD** | symbol, exchange, quantity, available_quantity, avg_price, ltp, pnl |
| `OptionLeg` | **ADD** | ltp, oi, volume, iv, bid, ask, symbol, greeks |
| `OptionStrike` | **ADD** | strike (Decimal), call (OptionLeg), put (OptionLeg) |
| `OptionChain` | **ADD** | underlying, exchange, expiry, strikes (tuple), spot |
| `FutureContract` | **ADD** | symbol, expiry, ltp, oi, lot_size, underlying |
| `FutureChain` | **ADD** | underlying, exchange, expiries, contracts |
| `Instrument` | **ADD** | symbol, exchange, security_id, lot_size, tick_size, instrument_type |
| `Position` | **EXTEND** | +unrealized_pnl, +realized_pnl, +with_ltp(), +with_fill() |
| `Balance` | **EXTEND** | +sod_limit, +collateral_amount, +withdrawable_balance |
| `Order` | **EXTEND** | +correlation_id, +trigger_price as optional |
| `Quote` | **EXTEND** | +change (net change) |

### Ports to Extend

| Port | New methods |
|---|---|
| `TradingPort` | `get_trades() -> list[Trade]`, `get_holdings() -> list[Holding]` |
| `MarketDataPort` | `get_option_chain(underlying, exchange, expiry?) -> OptionChain`, `get_future_chain(underlying, exchange) -> FutureChain` |

---

## 4. Dependency Graph

```
                    ┌─────────────────────────────────────────────┐
                    │           PHASE A: Domain Extension          │
                    │  (No external deps — pure Python)            │
                    └─────────────────────────────────────────────┘

  ┌──────────────────────────────┐
  │   A1: entities.py            │  ← Agent 1 (TDD: test first)
  │   Add: Trade, Holding,       │
  │   OptionLeg, OptionStrike,   │
  │   OptionChain, FutureContract│
  │   FutureChain, Instrument    │
  │   Extend: Position, Balance, │
  │   Order, Quote               │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │   A2: ports.py               │  ← Agent 2 (after A1)
  │   Add: get_trades, holdings, │
  │   option_chain, future_chain │
  │   to protocols               │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │   A3: test_entities.py       │  ← Agent 3 (after A1)
  │   test_ports.py              │  ← (after A2)
  │   Extend existing tests      │
  └──────────────────────────────┘


                    ┌─────────────────────────────────────────────┐
                    │      PHASE B: Infrastructure Extension       │
                    │  (Depends on: nothing — parallel with A)     │
                    └─────────────────────────────────────────────┘

  ┌──────────────────────────────┐
  │   B1: rate_config.py         │  ← Agent 4 (TDD)
  │   DhanRateLimits: per-       │
  │   endpoint configs           │
  │   UpstoxRateLimits: same     │
  │   EndpointCategorizer        │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │   B2: http_client.py         │  ← Agent 5 (after B1)
  │   BaseHttpClient: retry,     │
  │   token refresh, CB hooks,   │
  │   rate limit integration     │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │   B3: test_rate_config.py    │  ← Agent 4 (with B1)
  │   test_http_client.py        │  ← Agent 5 (with B2)
  └──────────────────────────────┘


                    ┌─────────────────────────────────────────────┐
                    │        PHASE C: Paper Adapter                 │
                    │  (Depends on: A2 ports + B2 http_client)     │
                    └─────────────────────────────────────────────┘

  ┌──────────────────────────────┐
  │   C1: paper/adapter.py       │  ← Agent 6 (TDD)
  │   In-memory impl of ALL      │
  │   port methods               │
  │   PaperOrders, PaperPortfolio│
  │   PaperMarketData            │
  └──────────────┬───────────────┘
                 │
                 ▼
  ┌──────────────────────────────┐
  │   C2: test_paper.py          │  ← Agent 7 (after C1)
  │   Full port contract tests   │
   └──────────────────────────────┘


                    ┌─────────────────────────────────────────────┐
                    │   PHASE D: Broker Adapters (PARALLEL)        │
                    │  (Depends on: A2 ports + B2 http_client +    │
                    │   C1 paper as reference)                     │
                    │  Dhan and Upstox are INDEPENDENT → parallel  │
                    └─────────────────────────────────────────────┘

  ┌─────────────── DHAN ───────────────┐  ┌─────────────── UPSTOX ────────────────┐
  │                                     │  │                                       │
  │  D1: dhan/mapper.py    ← Agent 8   │  │  U1: upstox/mapper.py  ← Agent 9     │
  │  Dhan JSON → domain    TDD         │  │  Upstox JSON → domain  TDD           │
  │  entities                           │  │  entities                             │
  │         │                           │  │         │                             │
  │         ▼                           │  │         ▼                             │
  │  D2: dhan/client.py    ← Agent 10  │  │  U2: upstox/client.py  ← Agent 11    │
  │  DhanHttpClient: auth, rate         │  │  UpstoxHttpClient: Bearer auth,      │
  │  limits, retry, CB, endpoints       │  │  V2/V3 endpoints, retry, CB          │
  │         │                           │  │         │                             │
  │         ▼                           │  │         ▼                             │
  │  D3: dhan/adapter.py   ← Agent 12  │  │  U3: upstox/adapter.py ← Agent 13    │
  │  DhanAdapter: implements            │  │  UpstoxAdapter: implements            │
  │  TradingPort + MarketDataPort       │  │  TradingPort + MarketDataPort         │
  │  via client + mapper                │  │  via client + mapper                  │
  │         │                           │  │         │                             │
  │         ▼                           │  │         ▼                             │
  │  D4: test_dhan.py      ← Agent 14  │  │  U4: test_upstox.py    ← Agent 15    │
  │  Mocked HTTP, port contract         │  │  Mocked HTTP, port contract           │
  │  tests, mapper unit tests           │  │  tests, mapper unit tests             │
  └─────────────────────────────────────┘  └───────────────────────────────────────┘
         ↕ PARALLEL                              ↕ PARALLEL


                    ┌─────────────────────────────────────────────┐
                    │     PHASE E: Integration & Validation         │
                    │  (Depends on: ALL previous phases)            │
                    └─────────────────────────────────────────────┘

  ┌──────────────────────────────┐  ┌──────────────────────────────┐
  │  E1: Run all tests           │  │  E2: Code review             │
  │  Full pytest suite           │  │  Review all new files        │
  │  ← Agent 16                  │  │  ← Agent 17                  │
  └──────────────────────────────┘  └──────────────────────────────┘
         ↕ PARALLEL                       ↕ PARALLEL
```

---

## 5. Parallel Execution Schedule

| Wave | Duration | Agents | Tasks | Dependencies | Type |
|---|---|---|---|---|---|
| **1a** | ~3 min | Agent 1 | `entities.py` extension | None | Solo |
| **1b** | ~2 min | Agent 4 | `rate_config.py` + tests | None | **Parallel with 1a** |
| **2a** | ~2 min | Agent 2 | `ports.py` extension + tests | entities (1a) | Sequential |
| **2b** | ~3 min | Agent 5 | `http_client.py` + tests | rate_config (1b) | **Parallel with 2a** |
| **3** | ~4 min | Agents 6+7 | `paper/adapter.py` + `test_paper.py` | ports (2a) + http (2b) | Parallel pair |
| **4** | ~5 min | Agents 8,9,10,11 | Dhan `mapper.py` + `client.py` + Upstox `mapper.py` + `client.py` | ports + http + paper | **4 agents parallel** |
| **5** | ~5 min | Agents 12,13,14,15 | Dhan `adapter.py` + tests + Upstox `adapter.py` + tests | mappers + clients (4) | **4 agents parallel** |
| **6** | ~2 min | Agents 16+17 | Full test run + code review | All | Parallel pair |

**Total: 17 agents across 6 waves**
**Estimated wall-clock time: ~20 minutes** (vs ~2 hours sequential)
**Parallelism factor: ~4x speedup**

---

## 6. TDD Protocol (Every Agent Follows)

Each agent MUST follow this sequence:

```
1. RED: Write failing test(s) first
2. GREEN: Write minimum code to pass tests
3. REFACTOR: Clean up, remove duplication
4. VERIFY: Run tests — must pass
```

### Test Strategy by Layer

| Layer | Test Type | Mock Strategy |
|---|---|---|
| Domain entities | Unit — value equality, immutability, factories | No mocks — pure data |
| Domain ports | Contract — verify Protocol shapes, runtime_checkable | No mocks — Protocol only |
| Infrastructure | Unit — token bucket, circuit breaker, HTTP retry | Mock `requests.Session` |
| Paper adapter | Unit — in-memory state transitions | No mocks — pure logic |
| Broker mappers | Unit — JSON → entity transformation | No mocks — pure functions |
| Broker clients | Unit — auth headers, rate limits, retry logic | Mock `requests.Session` |
| Broker adapters | Contract — verify port compliance + integration | Mock HTTP client |
| Integration | E2E — all adapters pass shared contract suite | Mock or live (flag) |

---

## 7. Agent Assignment Details

### Wave 1a — Agent 1: Domain Entities Extension
**Files**: `brokers/domain/entities.py`, `brokers/tests/domain/test_entities.py`
**Input**: Existing entities.py + archived entity definitions
**Task**:
- Add `Trade`, `Holding`, `OptionLeg`, `OptionStrike`, `OptionChain`, `FutureContract`, `FutureChain`, `Instrument`
- Extend `Position` (add `unrealized_pnl`, `realized_pnl`, `with_ltp()`, `with_fill()`)
- Extend `Balance` (add `sod_limit`, `collateral_amount`, `withdrawable_balance`)
- Extend `Order` (add `correlation_id`)
- Extend `Quote` (add `change`)
- Write tests FIRST, then implement
- Update `brokers/domain/__init__.py` and `brokers/__init__.py` re-exports
- Run tests: `pytest brokers/tests/domain/test_entities.py -v`

### Wave 1b — Agent 4: Rate Config
**Files**: `brokers/infrastructure/rate_config.py`, `brokers/tests/infrastructure/test_rate_config.py`
**Input**: Archived Dhan rate limits from `_archive/brokers_archive/dhan/config.py`
**Task**:
- `DhanRateLimits` class: per-endpoint rate limit mapping
  - `/marketfeed/quote`: 1/s
  - `/marketfeed/ltp`: 10/s
  - `/marketfeed/ohlc`: 10/s
  - `/orders`: 25/s
  - `/optionchain`: ~3/s
  - `/charts/`: 10/s
- `UpstoxRateLimits` class: per-endpoint rate limit mapping
- `EndpointCategorizer`: categorize endpoints as read/write/admin
- `RateLimitConfig` frozen dataclass: limits dict + categorize method
- Write tests FIRST, then implement
- Run tests: `pytest brokers/tests/infrastructure/test_rate_config.py -v`

### Wave 2a — Agent 2: Ports Extension
**Files**: `brokers/domain/ports.py`, `brokers/tests/domain/test_ports.py`
**Depends on**: Agent 1 (entities extended)
**Task**:
- Add `get_trades() -> list[Trade]` to TradingPort
- Add `get_holdings() -> list[Holding]` to TradingPort
- Add `get_option_chain(underlying: str, exchange: Exchange, expiry: str | None = None) -> OptionChain` to MarketDataPort
- Add `get_future_chain(underlying: str, exchange: Exchange) -> FutureChain` to MarketDataPort
- Update test_ports.py with new method signatures
- Run tests: `pytest brokers/tests/domain/test_ports.py -v`

### Wave 2b — Agent 5: Base HTTP Client
**Files**: `brokers/infrastructure/http_client.py`, `brokers/tests/infrastructure/test_http_client.py`
**Depends on**: Agent 4 (rate_config)
**Input**: Archived `_archive/brokers_archive/dhan/http_client.py` patterns
**Task**:
- `BaseHttpClient` class with:
  - `__init__(base_url, headers, timeout, rate_config, retry_config)`
  - `_request(method, endpoint, json)` — core request with retry, rate limit, circuit breaker
  - `get(endpoint)`, `post(endpoint, json)`, `put(endpoint, json)`, `delete(endpoint)`
  - Token refresh hook (`update_token()`)
  - 429 handling with `Retry-After` header
  - Exponential backoff: 500ms → 1s → 2s → 4s (capped at 5s)
  - 401 → try token refresh once
  - 5xx → retry with backoff
  - 4xx → raise immediately (except 401/429)
- Write tests FIRST with mocked `requests.Session`
- Run tests: `pytest brokers/tests/infrastructure/test_http_client.py -v`

### Wave 3 — Agents 6+7: Paper Adapter
**Files**: `brokers/paper/adapter.py`, `brokers/tests/adapters/test_paper.py`
**Depends on**: Agent 2 (ports) + Agent 5 (http_client)
**Task**:
- `PaperAdapter` implementing ALL port methods:
  - `place_order`, `cancel_order`, `modify_order` — in-memory order book
  - `get_positions`, `get_balances`, `get_orderbook`, `get_trades`, `get_holdings`
  - `get_ltp`, `get_quote`, `get_depth`, `get_history`, `search_instruments`
  - `get_option_chain`, `get_future_chain`
  - `subscribe_quotes`, `subscribe_orders` — async generators yielding from queue
- Thread-safe with `threading.Lock`
- Deterministic: `PaperAdapter(seed=42)` for reproducible tests
- Write tests FIRST — full port contract verification
- Run tests: `pytest brokers/tests/adapters/test_paper.py -v`

### Wave 4 — Agents 8-11: Broker Mappers + Clients (PARALLEL)

**Agent 8 — Dhan Mapper**: `brokers/dhan/mapper.py` + tests
- `DhanMapper` class with static methods:
  - `map_order(raw: dict) -> Order`
  - `map_trade(raw: dict) -> Trade`
  - `map_position(raw: dict) -> Position`
  - `map_holding(raw: dict) -> Holding`
  - `map_balance(raw: dict) -> Balance`
  - `map_quote(raw: dict) -> Quote`
  - `map_depth(raw: dict) -> MarketDepth`
  - `map_option_chain(raw: dict) -> OptionChain`
  - `map_future_chain(raw: list) -> FutureChain`
  - `build_order_payload(request: OrderRequest, security_id: str, segment: str) -> dict`
- Pure functions, no network calls
- Tests with sample Dhan JSON fixtures

**Agent 9 — Upstox Mapper**: `brokers/upstox/mapper.py` + tests
- `UpstoxMapper` class with same method set as DhanMapper
- Handles Upstox's different JSON shapes (e.g., `data` wrapper, `instrument_key`)
- Tests with sample Upstox JSON fixtures

**Agent 10 — Dhan Client**: `brokers/dhan/client.py` + tests
- `DhanHttpClient(BaseHttpClient)`:
  - Auth: `access-token` + `client-id` headers
  - Base URL: `https://api.dhan.co/v2`
  - Endpoint methods: `place_order()`, `cancel_order()`, `get_orderbook()`, `get_ltp()`, `get_quote()`, etc.
  - Rate limits from `DhanRateLimits`
  - Circuit breaker categories: read/write/admin
- Tests with mocked HTTP

**Agent 11 — Upstox Client**: `brokers/upstox/client.py` + tests
- `UpstoxHttpClient(BaseHttpClient)`:
  - Auth: `Bearer {access_token}` header
  - Base URL: `https://api.upstox.com`
  - Endpoint methods: same set as Dhan
  - Rate limits from `UpstoxRateLimits`
- Tests with mocked HTTP

### Wave 5 — Agents 12-15: Broker Adapters + Tests (PARALLEL)

**Agent 12 — Dhan Adapter**: `brokers/dhan/adapter.py`
- `DhanAdapter` implementing `TradingPort` + `MarketDataPort`:
  - `__init__(client: DhanHttpClient, mapper: DhanMapper)`
  - Each method: call client → map response → return domain entity
  - Instrument resolution: symbol → security_id (via instrument cache)
  - Error handling: catch broker errors → return `OrderResponse.fail()`

**Agent 13 — Upstox Adapter**: `brokers/upstox/adapter.py`
- `UpstoxAdapter` implementing `TradingPort` + `MarketDataPort`:
  - Same structure as Dhan
  - Instrument resolution: symbol → instrument_key

**Agent 14 — Dhan Tests**: `brokers/tests/adapters/test_dhan.py`
- Mocked HTTP client tests
- Port contract verification (same as paper)
- Mapper unit tests
- Edge cases: empty responses, error payloads, rate limit simulation

**Agent 15 — Upstox Tests**: `brokers/tests/adapters/test_upstox.py`
- Same structure as Dhan tests

### Wave 6 — Agents 16+17: Integration + Review

**Agent 16**: Run full test suite
```bash
python -m pytest brokers/tests/ -v --tb=short
```

**Agent 17**: Code review all new files

---

## 8. Critical Design Decisions

### 8.1 Sync vs Async
**Decision**: Sync first, async later.
**Rationale**: The archived code is entirely sync (`requests` library). The old async HTTP client (`DhanAsyncHttpClient`) was a thin wrapper. Keep it simple — add async support in a future phase if needed.

### 8.2 Instrument Resolution
**Decision**: Each broker adapter owns its own instrument resolution (symbol → broker ID).
**Rationale**: Dhan uses `security_id` (numeric), Upstox uses `instrument_key` (e.g., `NSE_EQ|INE002A01018`). These are fundamentally different — no shared resolver.

### 8.3 Rate Limiting Architecture
**Decision**: Per-endpoint rate limit config passed to `BaseHttpClient`, enforced via token bucket + adaptive backoff.
**Rationale**: Dhan's quote endpoint is 1/s (very strict). Orders are 25/s. A single rate limiter would either throttle orders too aggressively or allow quote flooding. Per-endpoint is the only correct approach.

### 8.4 Circuit Breaker Categories
**Decision**: Three categories: `read` (market data), `write` (orders), `admin` (portfolio).
**Rationale**: A storm of failed market-data reads must NOT block order placement. This was a P0 bug in the old code (single CB for everything) and was fixed by splitting into categories.

### 8.5 No Factory Classes
**Decision**: Simple constructor injection: `DhanAdapter(client=..., mapper=...)`.
**Rationale**: The old code had 6-phase Builders, BrokerInfrastructure containers, and factory factories. This is unnecessary complexity. Clean Architecture says: depend on abstractions, inject via constructor.

### 8.6 Streaming (Deferred)
**Decision**: `StreamingPort` stays as Protocol definition but paper/broker adapters implement it as a stub returning empty async generators.
**Rationale**: WebSocket streaming is complex (protobuf for Upstox, JSON for Dhan) and not needed for the core trading loop. Build it in Phase 2 after the REST API is solid.

---

## 9. Execution Checklist

- [ ] Wave 1a: Agent 1 — Extend domain entities + tests
- [ ] Wave 1b: Agent 4 — Rate config + tests (parallel with 1a)
- [ ] Wave 2a: Agent 2 — Extend ports + tests
- [ ] Wave 2b: Agent 5 — Base HTTP client + tests (parallel with 2a)
- [ ] Wave 3: Agents 6+7 — Paper adapter + tests
- [ ] Wave 4: Agents 8-11 — Dhan + Upstox mappers and clients (4 parallel)
- [ ] Wave 5: Agents 12-15 — Dhan + Upstox adapters and tests (4 parallel)
- [ ] Wave 6: Agents 16+17 — Full test run + code review
- [ ] Update `brokers/__init__.py` re-exports
- [ ] All tests pass: `pytest brokers/tests/ -v`
- [ ] Code review approved
