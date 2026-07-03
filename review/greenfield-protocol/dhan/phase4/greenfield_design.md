# Phase 4 Greenfield Design — Dhan Market Data

## Architecture Overview

### Archive Architecture (WebSocket-Heavy)

The archive implementation uses a **thick WebSocket layer** with multiple specialized services:

```
┌─────────────────────────────────────────────────────────────┐
│                     DhanConnection                          │
├─────────────────────────────────────────────────────────────┤
│  ConnectionLifecycle (creates, caches, manages all WS)     │
│  ├─ DhanMarketFeed (SDK-based, 1000 instruments)           │
│  ├─ DhanOrderStream (SDK-based)                            │
│  ├─ DhanDepth20Feed (raw websockets, 50 instruments)       │
│  ├─ DhanDepth200Feed (raw websockets, 1 instrument)        │
│  ├─ Depth200ConnectionPool (manages multiple depth-200)    │
│  ├─ PollingMarketFeed (REST fallback)                      │
│  └─ ResolverRefresher (background instrument reload)       │
│                                                             │
│  WebSocketConnectionManager (singleton enforcement)        │
│  MarketFeedConnectionAdmission (fcntl lock + 429 cooldown) │
│  SubscriptionEngine (ref-counting, callback management)    │
│  ReconnectingServiceMixin (shared reconnect logic)         │
│                                                             │
│  MarketDataAdapter (REST: LTP, quote, depth, OHLC, batch)  │
│  SymbolResolver (O(1) symbol → Instrument)                 │
└─────────────────────────────────────────────────────────────┘
```

**Key characteristics:**
- **SDK-dependent**: Market feed and order stream use Dhan SDK (`dhanhq.marketfeed.MarketFeed`, `dhanhq.orderupdate.OrderUpdate`)
- **Async depth feeds**: Binary depth feeds use `websockets` async library with manual event loop management (`asyncio.new_event_loop()`)
- **Multiple callback system**: Each service maintains callback lists with snapshot iteration
- **Event bus integration**: All services publish TICK, DEPTH, ORDER_UPDATED, TRADE events
- **Sophisticated admission control**: fcntl file locking + 429 cooldown with exponential backoff
- **Lifecycle management**: All services implement `ManagedService` interface for deterministic shutdown

### Greenfield Architecture (Thin Adapters)

The greenfield implementation uses a **thin adapter layer** with a common base class:

```
┌─────────────────────────────────────────────────────────────┐
│                  Greenfield Dhan Adapters                   │
├─────────────────────────────────────────────────────────────┤
│  BaseWebSocketStreaming (websocket-client, sync threading) │
│  ├─ DhanStreaming (market data ticks)                      │
│  ├─ DhanDepth20Stream (L2 depth)                           │
│  ├─ DhanDepth200Stream (L3 depth)                          │
│  └─ DhanOrderStream (order updates)                        │
│                                                             │
│  DhanMarketData (REST: LTP, quote, depth)                  │
│  DhanInstrumentResolver (symbol resolution)                │
└─────────────────────────────────────────────────────────────┘
```

**Key characteristics:**
- **SDK-independent**: All adapters use `websocket-client` library directly, no Dhan SDK dependency
- **Sync threading**: All WebSocket services use synchronous `websocket-client` with background threads
- **Single callback model**: Each adapter has single `on_tick` or `on_depth_update` callback
- **No event bus**: Callbacks only, no event publishing
- **No admission control**: No host-wide locking or rate-limit cooldown
- **No lifecycle management**: No `ManagedService` interface, no deterministic shutdown coordination

## Improvements Over Archive

### 1. Simplified Dependency Stack
**Archive**: Requires `dhanhq` SDK + `websockets` async library
**Greenfield**: Only requires `websocket-client` sync library

**Benefit**: Reduces external dependencies, easier to maintain, no SDK version compatibility issues.

### 2. Unified Base Class
**Archive**: Three separate implementations (SDK-based market feed, async depth feeds, SDK order stream)
**Greenfield**: Single `BaseWebSocketStreaming` base class with common connection management

**Benefit**: Consistent behavior across all WebSocket services, easier to understand and modify.

### 3. Cleaner REST API
**Archive**: `MarketDataAdapter` with identity assertions and complex response parsing
**Greenfield**: `DhanMarketData` with simpler response parsing and fallback key lookups

**Benefit**: More robust response handling (tries multiple key formats), cleaner separation of concerns.

### 4. Header-Based Authentication
**Archive**: Mix of URL params (`?token=...`) and SDK context
**Greenfield**: Consistent header-based auth (`access-token`, `client-id`)

**Benefit**: More secure (tokens not in URLs/logs), follows REST API best practices.

## Dropped Behaviors (Gaps)

### Critical Gaps

#### 1. Binary Depth Parsing (CRITICAL)
**Archive**: Full binary packet parsing with 12-byte header, 16-byte depth levels, bid/ask separation, quantity filtering, depth cache management
**Greenfield**: Placeholder header-only parsing, no level extraction, no cache

**Impact**: Depth-20 and depth-200 streams are non-functional. Cannot extract price/quantity/orders from binary packets.

**Severity**: **CRITICAL** — Core market data feature completely missing.

#### 2. Event Bus Integration (CRITICAL)
**Archive**: All services publish domain events (TICK, DEPTH, ORDER_UPDATED, TRADE) to EventBus
**Greenfield**: No event bus, callbacks only

**Impact**: Cannot integrate with event-driven architecture, no correlation tracking, no event sourcing.

**Severity**: **CRITICAL** — Architectural mismatch with event-driven design.

#### 3. Connection Admission Control (CRITICAL)
**Archive**: fcntl file locking for single-connection-per-account, 429 rate-limit cooldown with exponential backoff, persisted cooldown state
**Greenfield**: No admission control

**Impact**: Multiple broker instances can violate Dhan's connection limits, no protection against rate-limit bans.

**Severity**: **CRITICAL** — Production deployment risk.

#### 4. Depth Cache and Domain Entities (CRITICAL)
**Archive**: Per-security_id depth cache with bid/ask merge, `DepthLevel` and `MarketDepth` domain entities
**Greenfield**: No cache, no domain entities

**Impact**: Cannot query latest depth, no type-safe depth data, no symbol-to-depth mapping.

**Severity**: **CRITICAL** — Core market data feature incomplete.

### High-Priority Gaps

#### 5. Polling Feed Fallback (HIGH)
**Archive**: `PollingMarketFeed` polls REST API at configurable interval, same callback interface as WebSocket
**Greenfield**: Not implemented

**Impact**: No fallback when WebSocket unavailable, reduced reliability.

**Severity**: **HIGH** — Reliability feature missing.

#### 6. Resolver Periodic Refresh (HIGH)
**Archive**: `ResolverRefresher` reloads instruments every 24h with atomic swap
**Greenfield**: Not implemented

**Impact**: Long-running processes have stale instrument data, new listings not available.

**Severity**: **HIGH** — Data staleness risk.

#### 7. Batch REST API (HIGH)
**Archive**: `get_batch_ltp()`, `get_batch_quote()` for efficient multi-symbol queries
**Greenfield**: Not implemented

**Impact**: Inefficient bulk queries (N requests instead of 1), higher API usage.

**Severity**: **HIGH** — Performance regression.

#### 8. Trade Detection (HIGH)
**Archive**: Detects fills via cumulative filledQty delta, publishes TRADE events with incremental quantity
**Greenfield**: Not implemented

**Impact**: Position manager cannot track fills, no trade events for downstream processing.

**Severity**: **HIGH** — Order management incomplete.

### Medium-Priority Gaps

#### 9. Instrument Limit Enforcement (MEDIUM)
**Archive**: Enforces MAX_INSTRUMENTS (1000 for market feed, 50 for depth-20, 1 for depth-200)
**Greenfield**: No limit checks

**Impact**: Can exceed broker limits, connection rejections.

**Severity**: **MEDIUM** — Runtime error risk.

#### 10. Strict-Mode Validation (MEDIUM)
**Archive**: Drops ticks with missing/zero LTP, drops depth with empty both sides or zero top-of-book
**Greenfield**: No validation

**Impact**: Malformed data propagated to downstream consumers.

**Severity**: **MEDIUM** — Data quality risk.

#### 11. Multiple Callbacks (MEDIUM)
**Archive**: Callback lists with snapshot iteration, multiple subscribers per event
**Greenfield**: Single callback per adapter

**Impact**: Cannot have multiple consumers (e.g., logging + strategy + metrics).

**Severity**: **MEDIUM** — Flexibility limitation.

#### 12. Reconnection Refinements (MEDIUM)
**Archive**: Jitter in backoff, interruptible sleep, max reconnect attempts with cooldown
**Greenfield**: Basic exponential backoff only

**Impact**: Less robust reconnection, potential for rapid reconnect storms.

**Severity**: **MEDIUM** — Reliability degradation.

### Low-Priority Gaps

#### 13. OHLC REST Endpoint (LOW)
**Archive**: `get_ohlc()` method
**Greenfield**: Not implemented

**Impact**: Cannot fetch OHLC data via REST (available in quote endpoint).

**Severity**: **LOW** — Minor feature gap.

#### 14. Correlation ID Generation (LOW)
**Archive**: Monotonic correlation IDs for event tracing
**Greenfield**: Not implemented

**Impact**: Cannot trace events across system, harder debugging.

**Severity**: **LOW** — Observability gap.

## Key Architectural Decisions

### 1. WebSocket Library Choice

**Decision**: Use `websocket-client` (sync) instead of `websockets` (async) or Dhan SDK.

**Rationale**:
- **Simplicity**: Sync API is easier to understand and debug than async
- **No SDK dependency**: Removes `dhanhq` version compatibility concerns
- **Consistent threading model**: All services use same thread-per-feed pattern
- **Better control**: Direct access to WebSocket lifecycle, no SDK abstraction layer

**Trade-offs**:
- ❌ Cannot leverage async I/O for high-frequency data
- ❌ No SDK-provided reconnection logic
- ❌ Must implement binary parsing manually
- ✅ Full control over connection behavior
- ✅ Easier to test and mock

**Recommendation**: **ACCEPT** — Sync model is appropriate for this use case. Dhan's WebSocket is not high-frequency enough to require async.

### 2. Threading Model

**Decision**: Thread-per-feed (each WebSocket runs in its own daemon thread).

**Rationale**:
- **Isolation**: Each feed has independent failure domain
- **Simplicity**: No complex async event loop management
- **Matches archive**: Depth feeds already used this pattern
- **Easier debugging**: Thread-per-concern is easier to reason about

**Trade-offs**:
- ❌ More threads (4-5 for full market data)
- ❌ Thread synchronization needed for shared state
- ❌ Harder to coordinate shutdown
- ✅ Simpler code, easier to understand
- ✅ Matches existing archive pattern

**Recommendation**: **ACCEPT** — Thread-per-feed is appropriate for this scale.

### 3. Subscription Management

**Decision**: Simple subscription set in base class, replay on reconnect.

**Rationale**:
- **Simplicity**: Single source of truth (`_subscriptions` set)
- **Automatic replay**: Base class replays on reconnect
- **Matches archive**: Market feed already used this pattern

**Trade-offs**:
- ❌ No ref-counting (archive's `SubscriptionEngine` had ref-counting)
- ❌ No mode tracking (LTP/QUOTE/FULL)
- ❌ No instrument limit enforcement
- ✅ Simpler implementation
- ✅ Easier to understand

**Recommendation**: **ACCEPT with improvements** — Add instrument limit enforcement and mode tracking.

### 4. Reconnection Strategy

**Decision**: Basic exponential backoff (5s → 60s) without jitter or max attempts.

**Rationale**:
- **Simplicity**: Minimal reconnection logic
- **Matches base class**: `BaseWebSocketStreaming` provides basic backoff

**Trade-offs**:
- ❌ No jitter (reconnect storms possible)
- ❌ No max attempts (infinite reconnect)
- ❌ No interruptible sleep (stop() blocks)
- ❌ No admission control (429 cooldown)
- ✅ Simpler code
- ✅ Easier to understand

**Recommendation**: **REJECT** — Must add jitter, interruptible sleep, and admission control for production.

## Design Principles Applied

### 1. Single Responsibility
Each adapter has one clear purpose:
- `DhanStreaming` — market data ticks
- `DhanDepth20Stream` — L2 depth
- `DhanDepth200Stream` — L3 depth
- `DhanOrderStream` — order updates
- `DhanMarketData` — REST market data

**Status**: ✅ **APPLIED** — Clean separation of concerns.

### 2. DRY (Don't Repeat Yourself)
Common WebSocket logic extracted to `BaseWebSocketStreaming`:
- Connection management
- Subscription tracking
- Reconnection loop
- Callback invocation

**Status**: ✅ **APPLIED** — Base class eliminates duplication.

### 3. Dependency Inversion
Adapters depend on abstractions:
- `StreamingPort` interface (domain layer)
- `DhanInstrumentResolver` (abstraction, not concrete)
- `DhanHttpClient` (abstraction, not concrete)

**Status**: ✅ **APPLIED** — Adapters depend on ports, not infrastructure.

### 4. Interface Segregation
Each adapter implements only what it needs:
- `DhanStreaming` — `on_tick`, `subscribe`, `unsubscribe`
- `DhanDepth20Stream` — `on_depth_update`, `subscribe`, `unsubscribe`
- `DhanOrderStream` — `on_order_update`, `update_token`

**Status**: ✅ **APPLIED** — No fat interfaces.

### 5. Open/Closed
Base class is open for extension, closed for modification:
- Subclasses override `_build_subscribe_message()`, `_parse_tick()`, etc.
- Base class provides connection management, reconnection, subscription tracking

**Status**: ✅ **APPLIED** — Easy to add new stream types.

### 6. Fail-Fast
Identity assertions on every REST call:
- `assert_valid_dhan_payload(payload, context)` catches malformed requests early

**Status**: ✅ **APPLIED** — REST API validates before sending.

### 7. Defense in Depth
Multiple layers of validation:
- Resolver validates symbol/exchange
- Identity assertion validates payload
- Response parsing handles multiple key formats

**Status**: ✅ **APPLIED** — REST API is robust.

## Recommended Architecture for Greenfield Market Data

### Phase 4A: Critical Gap Closure

**Goal**: Make depth feeds functional and integrate with event bus.

**Changes**:
1. **Implement binary depth parsing** in `DhanDepth20Stream` and `DhanDepth200Stream`
   - Parse 12-byte header (response code, security_id/num_rows)
   - Parse 16-byte depth levels (price, quantity, orders)
   - Filter zero-quantity levels
   - Separate bid/ask by response code (41 = bid, 51 = ask)

2. **Add depth cache** to depth adapters
   - Per-security_id cache with bid/ask merge
   - Handle one-sided packets (don't wipe other side)
   - Expose `latest_depth(security_id)` method

3. **Create domain entities** (`DepthLevel`, `MarketDepth`)
   - Match archive's entity structure
   - Use in depth adapters

4. **Integrate event bus**
   - Add `EventBus` dependency to all adapters
   - Publish TICK, DEPTH, ORDER_UPDATED events
   - Generate correlation IDs

5. **Add symbol registration** to depth adapters
   - `register_symbol(security_id, symbol)` method
   - Use for depth cache key and MarketDepth.symbol

**Estimated effort**: 2-3 days

### Phase 4B: Reliability Features

**Goal**: Add admission control, polling fallback, and resolver refresh.

**Changes**:
1. **Implement connection admission control**
   - Port `MarketFeedConnectionAdmission` from archive
   - fcntl file locking for single-connection-per-account
   - 429 rate-limit cooldown with exponential backoff
   - Persisted cooldown state

2. **Add polling feed fallback**
   - Port `PollingMarketFeed` from archive
   - Batch LTP API (1000 symbols per request)
   - Same callback interface as WebSocket

3. **Implement resolver periodic refresh**
   - Port `ResolverRefresher` from archive
   - Background thread with configurable interval
   - Atomic swap of resolver

4. **Add instrument limit enforcement**
   - MAX_INSTRUMENTS check in `subscribe()`
   - Raise ValueError when limit exceeded

**Estimated effort**: 2 days

### Phase 4C: Robustness Improvements

**Goal**: Add strict-mode validation, trade detection, and reconnection refinements.

**Changes**:
1. **Add strict-mode validation**
   - Drop ticks with missing/zero LTP
   - Drop depth with empty both sides or zero top-of-book
   - Track dropped event counts

2. **Implement trade detection**
   - Track cumulative filledQty per order
   - Detect fills via delta
   - Publish TRADE events with incremental quantity

3. **Improve reconnection**
   - Add jitter to backoff
   - Use interruptible sleep (Event.wait)
   - Add max reconnect attempts with cooldown

4. **Add batch REST API**
   - `get_batch_ltp(symbols, exchange)`
   - `get_batch_quote(symbols, exchange)`

5. **Support multiple callbacks**
   - Change single callback to callback list
   - Snapshot iteration for thread safety

**Estimated effort**: 2 days

### Phase 4D: Observability

**Goal**: Add correlation IDs, health checks, and metrics.

**Changes**:
1. **Add correlation ID generation**
   - Monotonic counter per adapter
   - Stamp all events with correlation ID

2. **Implement health checks**
   - `health()` method on each adapter
   - Return connection state, reconnect count, message age

3. **Add metrics**
   - Published/dropped event counts
   - Reconnect count
   - Subscription count

**Estimated effort**: 1 day

## Summary

The greenfield implementation makes good architectural choices (sync threading, unified base class, no SDK dependency) but has **critical gaps** in depth feed parsing, event bus integration, and connection admission control.

**Recommended path forward**:
1. **Phase 4A** (2-3 days): Close critical gaps — depth parsing, event bus, domain entities
2. **Phase 4B** (2 days): Add reliability features — admission control, polling fallback, resolver refresh
3. **Phase 4C** (2 days): Improve robustness — strict validation, trade detection, reconnection refinements
4. **Phase 4D** (1 day): Add observability — correlation IDs, health checks, metrics

**Total estimated effort**: 7-8 days

**Priority**: Phase 4A is **BLOCKING** — depth feeds are non-functional without binary parsing.
