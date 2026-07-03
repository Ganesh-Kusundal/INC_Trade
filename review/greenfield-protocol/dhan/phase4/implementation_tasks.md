# Phase 4 Implementation Tasks — Dhan Market Data

## Task Dependency Graph

```
Layer 0 (Foundation)
├─ T0.1: Binary depth parsing primitives
├─ T0.2: Domain entities (DepthLevel, MarketDepth)
└─ T0.3: Event bus integration foundation

Layer 1 (Critical Features)
├─ T1.1: Depth-20 binary parsing ← T0.1, T0.2
├─ T1.2: Depth-200 binary parsing ← T0.1, T0.2
├─ T1.3: Depth cache management ← T0.2
├─ T1.4: Symbol registration ← T0.2
└─ T1.5: Event publishing (TICK, DEPTH, ORDER) ← T0.3

Layer 2 (Reliability)
├─ T2.1: Connection admission control ← T1.5
├─ T2.2: Polling feed fallback ← T1.5
├─ T2.3: Resolver periodic refresh
└─ T2.4: Instrument limit enforcement ← T1.1, T1.2

Layer 3 (Robustness)
├─ T3.1: Strict-mode validation ← T1.5
├─ T3.2: Trade detection ← T1.5
├─ T3.3: Reconnection refinements ← T2.1
├─ T3.4: Batch REST API
└─ T3.5: Multiple callback support ← T1.5

Layer 4 (Observability)
├─ T4.1: Correlation ID generation ← T1.5
├─ T4.2: Health checks ← T2.1, T3.3
└─ T4.3: Metrics and counters ← T3.1, T3.2
```

## Detailed Task Specifications

### Layer 0: Foundation

#### T0.1: Binary Depth Parsing Primitives
**Priority**: P0 (BLOCKING)
**Gap Reference**: Evidence Matrix §3 (Depth Feed Data Flow) — PARTIAL
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Create `brokers/adapters/dhan/binary_parser.py`
2. Implement header parsing:
   - 12-byte header: response_code (offset 2), security_id/num_rows (offset 4 or 8)
   - Little-endian format (`<I` for unsigned int)
3. Implement level parsing:
   - 16-byte levels: price (8 bytes double), quantity (4 bytes uint), orders (4 bytes uint)
   - Loop for total_slots (20 or 200)
   - Filter zero-quantity levels
4. Implement bid/ask separation:
   - Response code 41 = bid
   - Response code 51 = ask
5. Add unit tests for header and level parsing

**Acceptance Criteria**:
- [ ] Can parse 12-byte header and extract response_code, security_id/num_rows
- [ ] Can parse N depth levels (20 or 200) from binary data
- [ ] Filters out zero-quantity levels
- [ ] Correctly identifies bid vs ask by response code
- [ ] Unit tests pass with sample binary packets

**Dependencies**: None

---

#### T0.2: Domain Entities (DepthLevel, MarketDepth)
**Priority**: P0 (BLOCKING)
**Gap Reference**: Evidence Matrix §3 — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Create `brokers/domain/entities.py` (if not exists)
2. Implement `DepthLevel` dataclass:
   ```python
   @dataclass
   class DepthLevel:
       price: Decimal
       quantity: int
       orders: int
   ```
3. Implement `MarketDepth` dataclass:
   ```python
   @dataclass
   class MarketDepth:
       symbol: str
       bids: list[DepthLevel]
       asks: list[DepthLevel]
       depth_type: str  # "DEPTH_5", "DEPTH_20", "DEPTH_200"
       timestamp: datetime | None = None
   ```
4. Add validation (price > 0, quantity >= 0)
5. Add unit tests

**Acceptance Criteria**:
- [ ] `DepthLevel` and `MarketDepth` entities exist
- [ ] Entities are immutable (frozen dataclass or properties)
- [ ] Validation prevents invalid data (negative prices)
- [ ] Unit tests pass

**Dependencies**: None

---

#### T0.3: Event Bus Integration Foundation
**Priority**: P0 (BLOCKING)
**Gap Reference**: Evidence Matrix §12 (Message Parsing) — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Check if `EventBus` exists in greenfield domain layer
2. If not, create minimal `EventBus` interface:
   ```python
   class EventBus:
       def publish(self, event: DomainEvent) -> None: ...
       def subscribe(self, event_name: str, callback: Callable) -> None: ...
   ```
3. Create `DomainEvent` dataclass:
   ```python
   @dataclass
   class DomainEvent:
       name: str
       data: dict
       symbol: str | None
       source: str
       correlation_id: str | None
       timestamp: datetime
   ```
4. Add dependency injection for EventBus in adapter constructors
5. Add unit tests for event publishing

**Acceptance Criteria**:
- [ ] EventBus interface exists (or port from archive)
- [ ] DomainEvent entity exists
- [ ] Adapters accept EventBus as optional dependency
- [ ] Can publish and subscribe to events
- [ ] Unit tests pass

**Dependencies**: None

---

### Layer 1: Critical Features

#### T1.1: Depth-20 Binary Parsing
**Priority**: P0 (BLOCKING)
**Gap Reference**: Evidence Matrix §3 — PARTIAL
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Update `DhanDepth20Stream._on_message()` to use binary parser
2. Parse 12-byte header (security_id at offset 4)
3. Parse 20 depth levels (16 bytes each)
4. Separate bid/ask by response code
5. Build `DepthLevel` entities
6. Call `on_depth_update()` with parsed data
7. Add integration tests with real binary packets

**Acceptance Criteria**:
- [ ] Can parse depth-20 binary packets
- [ ] Extracts 20 levels of bid/ask data
- [ ] Builds DepthLevel entities
- [ ] Calls on_depth_update with parsed data
- [ ] Integration tests pass

**Dependencies**: T0.1, T0.2

---

#### T1.2: Depth-200 Binary Parsing
**Priority**: P0 (BLOCKING)
**Gap Reference**: Evidence Matrix §3 — PARTIAL
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Update `DhanDepth200Stream._on_message()` to use binary parser
2. Parse 12-byte header (num_rows at offset 8, security_id implicit)
3. Parse up to 200 depth levels
4. Separate bid/ask by response code
5. Build `DepthLevel` entities
6. Call `on_depth_update()` with parsed data
7. Add integration tests

**Acceptance Criteria**:
- [ ] Can parse depth-200 binary packets
- [ ] Extracts up to 200 levels
- [ ] Handles implicit security_id (from subscription)
- [ ] Integration tests pass

**Dependencies**: T0.1, T0.2

---

#### T1.3: Depth Cache Management
**Priority**: P0
**Gap Reference**: Evidence Matrix §3 — NOT_PORTED
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Add `_depth_cache: dict[int, dict[str, list[DepthLevel]]]` to depth adapters
2. Implement cache update logic:
   - Key by security_id
   - Store bids and asks separately
   - Merge one-sided packets (don't wipe other side)
3. Add `latest_depth(security_id)` method
4. Add thread-safe cache access (lock)
5. Add unit tests for cache merge logic

**Acceptance Criteria**:
- [ ] Depth cache stores per-security_id bids/asks
- [ ] One-sided packets don't wipe other side
- [ ] `latest_depth()` returns cached MarketDepth
- [ ] Thread-safe cache access
- [ ] Unit tests pass

**Dependencies**: T0.2

---

#### T1.4: Symbol Registration
**Priority**: P0
**Gap Reference**: Evidence Matrix §8 (Resolver Integration) — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Add `_sec_id_to_symbol: dict[int, str]` to depth adapters
2. Implement `register_symbol(security_id, symbol)` method
3. Use symbol in MarketDepth construction
4. Add unit tests

**Acceptance Criteria**:
- [ ] Can register security_id → symbol mapping
- [ ] Symbol used in MarketDepth.symbol
- [ ] Unit tests pass

**Dependencies**: T0.2

---

#### T1.5: Event Publishing (TICK, DEPTH, ORDER)
**Priority**: P0
**Gap Reference**: Evidence Matrix §12 — NOT_PORTED
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Add EventBus dependency to all adapters
2. Publish TICK events in `DhanStreaming._parse_tick()`
3. Publish DEPTH events in depth adapters after cache update
4. Publish ORDER_UPDATED events in `DhanOrderStream._on_message()`
5. Generate correlation IDs for each event
6. Add unit tests for event publishing

**Acceptance Criteria**:
- [ ] TICK events published with quote data
- [ ] DEPTH events published with MarketDepth data
- [ ] ORDER_UPDATED events published with Order data
- [ ] All events have correlation IDs
- [ ] Unit tests pass

**Dependencies**: T0.3

---

### Layer 2: Reliability

#### T2.1: Connection Admission Control
**Priority**: P1
**Gap Reference**: Evidence Matrix §5 (Admission Control) — NOT_PORTED
**Estimated Effort**: 1.5 days

**Implementation Steps**:
1. Port `MarketFeedConnectionAdmission` from archive
2. Implement fcntl file locking for single-connection-per-account
3. Implement 429 rate-limit cooldown with exponential backoff
4. Persist cooldown state to JSON file
5. Integrate admission check in WebSocket connection loop
6. Add unit tests (with NoopAdmission for tests)

**Acceptance Criteria**:
- [ ] fcntl lock prevents multiple connections per account
- [ ] 429 cooldown waits with exponential backoff
- [ ] Cooldown state persists across restarts
- [ ] Admission check integrated in connection loop
- [ ] Unit tests pass

**Dependencies**: T1.5

---

#### T2.2: Polling Feed Fallback
**Priority**: P1
**Gap Reference**: Evidence Matrix §7 (Polling Feed) — NOT_PORTED
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Create `DhanPollingMarketFeed` adapter
2. Implement batch LTP API (1000 symbols per request)
3. Group instruments by segment for batch requests
4. Poll at configurable interval (default 2s)
5. Same callback interface as WebSocket (`on_tick`)
6. Add unit tests

**Acceptance Criteria**:
- [ ] Polls `/marketfeed/ltp` at configurable interval
- [ ] Batches up to 1000 symbols per request
- [ ] Groups by segment
- [ ] Same callback interface as WebSocket
- [ ] Unit tests pass

**Dependencies**: T1.5

---

#### T2.3: Resolver Periodic Refresh
**Priority**: P1
**Gap Reference**: Evidence Matrix §9 (Resolver Refresh) — NOT_PORTED
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Create `ResolverRefresher` service
2. Background thread with configurable interval (default 24h)
3. Reload instruments from CSV
4. Atomic swap of resolver
5. Expose refresh_count, error_count metrics
6. Add unit tests

**Acceptance Criteria**:
- [ ] Background thread reloads instruments periodically
- [ ] Atomic swap prevents partial reads
- [ ] Metrics exposed (refresh_count, error_count)
- [ ] Unit tests pass

**Dependencies**: None

---

#### T2.4: Instrument Limit Enforcement
**Priority**: P1
**Gap Reference**: Evidence Matrix §2 (Subscription) — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Add MAX_INSTRUMENTS constant to each adapter
2. Check limit in `subscribe()` method
3. Raise ValueError when limit exceeded
4. Add unit tests

**Acceptance Criteria**:
- [ ] Market feed: 1000 instrument limit
- [ ] Depth-20: 50 instrument limit
- [ ] Depth-200: 1 instrument limit
- [ ] ValueError raised when exceeded
- [ ] Unit tests pass

**Dependencies**: T1.1, T1.2

---

### Layer 3: Robustness

#### T3.1: Strict-Mode Validation
**Priority**: P2
**Gap Reference**: Evidence Matrix §12 — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Add validation in tick publishing:
   - Drop ticks with missing/zero LTP
   - Drop ticks with missing symbol
2. Add validation in depth publishing:
   - Drop depth with empty both sides
   - Drop depth with zero top-of-book price
3. Track dropped event counts
4. Add unit tests

**Acceptance Criteria**:
- [ ] Invalid ticks dropped and counted
- [ ] Invalid depth dropped and counted
- [ ] Dropped counts exposed via metrics
- [ ] Unit tests pass

**Dependencies**: T1.5

---

#### T3.2: Trade Detection
**Priority**: P2
**Gap Reference**: Evidence Matrix §6 (Order Stream) — NOT_PORTED
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Add TTLCache for cumulative filledQty per order
2. Detect fills via delta (current - previous)
3. Publish TRADE events with incremental quantity
4. Add unit tests

**Acceptance Criteria**:
- [ ] Tracks cumulative filledQty per order
- [ ] Detects fills via delta
- [ ] Publishes TRADE events
- [ ] TTLCache prevents memory leaks
- [ ] Unit tests pass

**Dependencies**: T1.5

---

#### T3.3: Reconnection Refinements
**Priority**: P2
**Gap Reference**: Evidence Matrix §4 (Reconnection) — DIVERGENT
**Estimated Effort**: 1 day

**Implementation Steps**:
1. Add jitter to backoff (`+ random.uniform(0, 1.0)`)
2. Use interruptible sleep (`Event.wait(timeout=backoff)`)
3. Add max reconnect attempts (default 50)
4. Add cooldown after max attempts (default 300s)
5. Add unit tests

**Acceptance Criteria**:
- [ ] Jitter prevents reconnect storms
- [ ] Interruptible sleep allows immediate stop
- [ ] Max attempts prevents infinite reconnect
- [ ] Cooldown after max attempts
- [ ] Unit tests pass

**Dependencies**: T2.1

---

#### T3.4: Batch REST API
**Priority**: P2
**Gap Reference**: Evidence Matrix §10 (REST API) — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Add `get_batch_ltp(symbols, exchange)` to `DhanMarketData`
2. Add `get_batch_quote(symbols, exchange)` to `DhanMarketData`
3. Group by segment, chunk into 1000-symbol batches
4. Add unit tests

**Acceptance Criteria**:
- [ ] Batch LTP fetches multiple symbols in one request
- [ ] Batch quote fetches multiple quotes in one request
- [ ] Groups by segment, chunks by 1000
- [ ] Unit tests pass

**Dependencies**: None

---

#### T3.5: Multiple Callback Support
**Priority**: P2
**Gap Reference**: Evidence Matrix §12 — DIVERGENT
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Change single callback to callback list in base class
2. Snapshot iteration for thread safety
3. Add `on_tick`, `off_tick` methods
4. Add unit tests

**Acceptance Criteria**:
- [ ] Multiple callbacks per event type
- [ ] Thread-safe callback registration
- [ ] Snapshot iteration prevents blocking
- [ ] Unit tests pass

**Dependencies**: T1.5

---

### Layer 4: Observability

#### T4.1: Correlation ID Generation
**Priority**: P3
**Gap Reference**: Evidence Matrix §12 — NOT_PORTED
**Estimated Effort**: 0.25 days

**Implementation Steps**:
1. Add monotonic counter to base class
2. Generate correlation IDs (`{prefix}-{timestamp}-{counter}`)
3. Stamp all events with correlation ID
4. Add unit tests

**Acceptance Criteria**:
- [ ] Monotonic correlation IDs
- [ ] All events have correlation ID
- [ ] Unit tests pass

**Dependencies**: T1.5

---

#### T4.2: Health Checks
**Priority**: P3
**Gap Reference**: Evidence Matrix §11 (Connection Pool) — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Add `health()` method to each adapter
2. Return connection state, reconnect count, message age
3. Add unit tests

**Acceptance Criteria**:
- [ ] `health()` returns connection state
- [ ] Returns reconnect count
- [ ] Returns message age
- [ ] Unit tests pass

**Dependencies**: T2.1, T3.3

---

#### T4.3: Metrics and Counters
**Priority**: P3
**Gap Reference**: Evidence Matrix §12 — NOT_PORTED
**Estimated Effort**: 0.5 days

**Implementation Steps**:
1. Add published/dropped event counts
2. Add reconnect count
3. Add subscription count
4. Expose via health() method
5. Add unit tests

**Acceptance Criteria**:
- [ ] Published/dropped counts tracked
- [ ] Reconnect count tracked
- [ ] Subscription count tracked
- [ ] Exposed via health()
- [ ] Unit tests pass

**Dependencies**: T3.1, T3.2

---

## Parallelization Opportunities

### Fully Parallel (No Dependencies)
- **T0.1** (binary parser) ‖ **T0.2** (domain entities) ‖ **T0.3** (event bus)
- **T2.3** (resolver refresh) ‖ **T3.4** (batch REST)

### Sequential (Must Wait)
- **T1.1-T1.5** depend on Layer 0
- **T2.1-T2.4** depend on Layer 1
- **T3.1-T3.5** depend on Layer 2
- **T4.1-T4.3** depend on Layer 3

### Optimal Parallelization Strategy

**Day 1**: T0.1 ‖ T0.2 ‖ T0.3 (3 foundation tasks in parallel)
**Day 2**: T1.1 ‖ T1.2 (depth parsing in parallel)
**Day 3**: T1.3 ‖ T1.4 ‖ T1.5 (cache, symbol reg, events in parallel)
**Day 4**: T2.1 ‖ T2.3 (admission control ‖ resolver refresh)
**Day 5**: T2.2 ‖ T2.4 (polling feed ‖ limit enforcement)
**Day 6**: T3.1 ‖ T3.2 ‖ T3.3 (validation ‖ trade detection ‖ reconnection)
**Day 7**: T3.4 ‖ T3.5 ‖ T4.1 ‖ T4.2 ‖ T4.3 (remaining tasks)

**Total with parallelization**: 7 days (vs 10+ days sequential)

---

## Critical Path Analysis

### Critical Path (Longest Chain)
```
T0.1 (0.5d) → T1.1 (1d) → T2.1 (1.5d) → T3.3 (1d) → T4.2 (0.5d)
Total: 4.5 days
```

**Bottleneck**: Connection admission control (T2.1) is on the critical path and has the longest single-task duration (1.5 days).

### Secondary Critical Path
```
T0.3 (0.5d) → T1.5 (1d) → T3.2 (1d) → T4.3 (0.5d)
Total: 3 days
```

### Non-Critical Tasks (Can Slip)
- **T2.2** (polling feed) — 1 day slack
- **T2.3** (resolver refresh) — 1 day slack
- **T3.4** (batch REST) — 2 days slack
- **T3.5** (multiple callbacks) — 1 day slack

---

## Execution Summary

### Phase Breakdown

| Phase | Tasks | Effort | Priority | Status |
|-------|-------|--------|----------|--------|
| **4A: Critical Gap Closure** | T0.1-T0.3, T1.1-T1.5 | 5.5 days | P0 | BLOCKING |
| **4B: Reliability** | T2.1-T2.4 | 4 days | P1 | Required |
| **4C: Robustness** | T3.1-T3.5 | 3.5 days | P2 | Recommended |
| **4D: Observability** | T4.1-T4.3 | 1.25 days | P3 | Nice-to-have |

### Risk Mitigation

**High-Risk Tasks**:
1. **T1.1/T1.2 (Binary parsing)** — Risk: Wire format may differ from archive
   - Mitigation: Test with real Dhan WebSocket data early
2. **T2.1 (Admission control)** — Risk: fcntl not available on Windows
   - Mitigation: Port NoopAdmission for Windows dev environments
3. **T1.5 (Event bus)** — Risk: Greenfield may not have EventBus infrastructure
   - Mitigation: Port minimal EventBus from archive if needed

### Success Criteria

**Phase 4 Complete when**:
- ✅ Depth-20 and depth-200 feeds parse binary packets correctly
- ✅ Event bus integration complete (TICK, DEPTH, ORDER events)
- ✅ Connection admission control prevents rate-limit violations
- ✅ Strict-mode validation drops malformed data
- ✅ Health checks and metrics exposed for observability

### Recommended Team Allocation

**Solo Developer**:
- Follow critical path: T0.1 → T1.1 → T2.1 → T3.3 → T4.2
- Complete Phase 4A before moving to 4B/4C/4D
- Estimated: 10-12 days

**Pair of Developers**:
- Dev 1: Depth feeds (T0.1, T1.1-T1.4)
- Dev 2: Event bus + admission control (T0.3, T1.5, T2.1)
- Merge at T3.x (robustness tasks)
- Estimated: 7-8 days

**Team of 3**:
- Dev 1: Depth feeds (T0.1, T1.1-T1.4)
- Dev 2: Event bus + reliability (T0.3, T1.5, T2.1-T2.4)
- Dev 3: Robustness + observability (T3.1-T3.5, T4.1-T4.3)
- Estimated: 5-6 days

---

## Summary

**Total tasks**: 19
**Total effort**: 14.25 days (sequential), 7 days (parallelized)
**Critical path**: 4.5 days
**Blocking tasks**: T0.1, T0.2, T0.3, T1.1, T1.2, T1.5

**Immediate next steps**:
1. Start with Layer 0 foundation tasks (T0.1, T0.2, T0.3) in parallel
2. Move to Layer 1 critical features (depth parsing, event publishing)
3. Add reliability features (admission control, polling fallback)
4. Complete with robustness and observability

**Phase 4 exit criteria**: All P0 tasks complete, depth feeds functional, event bus integrated, admission control operational.
