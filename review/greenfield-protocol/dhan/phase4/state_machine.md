# Phase 4 — Market Data: State Machines

**Greenfield Broker Replication Protocol — Dhan**  
**Phase 4: Market Data Streaming & Instrument Resolution**

---

## 1. Connection Lifecycle State Machine

The `ConnectionLifecycle` class manages the lifecycle of all WebSocket services and the resolver refresher. It acts as a factory and orchestrator for market data components.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ConnectionLifecycle                           │
│                                                                  │
│  States:                                                         │
│    UNINITIALIZED ──► INITIALIZED ──► SERVICES_CREATED ──► CLOSED │
│                                                                  │
│  Transitions:                                                    │
│    UNINITIALIZED → INITIALIZED                                   │
│      Trigger: __init__() called                                  │
│      Action: Store client, instruments, event_bus references     │
│                                                                  │
│    INITIALIZED → SERVICES_CREATED                                │
│      Trigger: First factory method called                        │
│      Action: Create singleton service (market_feed, order_stream,│
│              depth_20_feed, depth_200_feed, polling_feed, or     │
│              resolver_refresher)                                 │
│      Side Effect: Register with LifecycleManager, register token │
│                   receiver                                       │
│                                                                  │
│    SERVICES_CREATED → SERVICES_CREATED                           │
│      Trigger: Additional factory method called                   │
│      Action: Create additional singleton service                 │
│      Note: Returns existing singleton if already created         │
│                                                                  │
│    SERVICES_CREATED → CLOSED                                     │
│      Trigger: close() called                                     │
│      Action: Stop all services in order:                         │
│              1. resolver_refresher.stop()                        │
│              2. market_feed.stop()                               │
│              3. order_stream.stop()                              │
│              4. polling_feed.stop()                              │
│              5. depth_20_feed.stop()                             │
│              6. depth_200_feed.stop()                            │
│              7. depth_200_pool.close_all()                       │
│      Timeout: 5.0 seconds per service (configurable)             │
│                                                                  │
│  Failure Paths:                                                  │
│    - Service stop() raises exception → log warning, continue     │
│    - LifecycleManager not present → skip registration            │
│    - Token receiver registration fails → propagate exception     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Singleton Enforcement

Each factory method enforces singleton pattern per connection:

```python
def create_market_feed(...) -> DhanMarketFeed:
    if self._market_feed is not None:
        return self._market_feed  # Return existing singleton
    # Create new instance
    self._market_feed = DhanMarketFeed(...)
    return self._market_feed
```

**Rationale:** Dhan rate-limits WebSocket connections per account. Singleton enforcement prevents accidental duplicate connections that would violate rate limits.

---

## 2. Depth Feed State Machine (20-level & 200-level)

Depth feeds (`DhanDepth20Feed`, `DhanDepth200Feed`) manage binary WebSocket connections for market depth data.

```
┌──────────────────────────────────────────────────────────────┐
│                    DepthFeedBase                              │
│                                                               │
│  States:                                                      │
│    IDLE ──► CONNECTING ──► ACTIVE ──► PAUSED ──► CLOSED       │
│                                                               │
│  Transitions:                                                 │
│    IDLE → CONNECTING                                          │
│      Trigger: start() or connect() called                     │
│      Action: Initialize WebSocket connection, start recv loop │
│      Precondition: instrument specified                      │
│                                                               │
│    CONNECTING → ACTIVE                                        │
│      Trigger: WebSocket handshake complete                    │
│      Action: Set _is_connected = True, start heartbeat        │
│              watchdog, send subscription message              │
│                                                               │
│    ACTIVE → ACTIVE                                            │
│      Trigger: Message received                                │
│      Action: Parse binary packet, dispatch to callbacks,      │
│              call _note_message_received()                    │
│                                                               │
│    ACTIVE → PAUSED                                            │
│      Trigger: Token expired or rate limit hit                 │
│      Action: Set _is_connected = False, pause recv loop       │
│      Recovery: Wait for token refresh, then → CONNECTING      │
│                                                               │
│    ACTIVE → CONNECTING (reconnect)                            │
│      Trigger: Connection lost, heartbeat timeout              │
│      Action: Exponential backoff (1.0s → 30.0s max),          │
│              increment _reconnect_count                       │
│                                                               │
│    ACTIVE → CLOSED                                            │
│      Trigger: stop() called                                   │
│      Action: Set _stop_event, join thread (5s timeout)        │
│                                                               │
│    PAUSED → CONNECTING                                        │
│      Trigger: Token refreshed via update_token()              │
│      Action: Resume connection attempt                        │
│                                                               │
│    *_STATE → CLOSED                                           │
│      Trigger: stop() called from any state                    │
│      Action: Deterministic shutdown                           │
│                                                               │
│  Failure Paths:                                               │
│    - Binary parse error → log warning, continue recv loop     │
│    - Heartbeat timeout (30s default) → trigger reconnect      │
│    - Max reconnect attempts (50) → cooldown (300s), reset     │
│    - WebSocket close with error → backoff, retry              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Depth200 Connection Pool

`Depth200ConnectionPool` manages multiple connections since Dhan's depth-200 API only supports 1 instrument per connection:

```
┌──────────────────────────────────────────────────────────────┐
│                Depth200ConnectionPool                         │
│                                                               │
│  State:                                                       │
│    POOL ──► {instrument_key: DhanDepth200Feed, ...}          │
│                                                               │
│  Transitions:                                                 │
│    get_feed(instrument)                                       │
│      If instrument not in pool:                               │
│        Create new DhanDepth200Feed for instrument             │
│        Add to pool                                            │
│        Return feed                                            │
│      Else:                                                    │
│        Return existing feed from pool                         │
│                                                               │
│    close_all()                                                │
│      For each feed in pool:                                   │
│        feed.stop(timeout=5.0)                                 │
│      Clear pool                                               │
│                                                               │
│  Constraints:                                                 │
│    - One WebSocket connection per instrument                  │
│    - Pool bounded by Dhan rate limits (5 concurrent WS)       │
│    - Thread-safe via connection lock                          │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Subscription State Machine

Subscriptions track which instruments are actively being received from the WebSocket.

```
┌──────────────────────────────────────────────────────────────┐
│                    Subscription State                         │
│                                                               │
│  States:                                                      │
│    UNSUBSCRIBED ──► PENDING ──► ACTIVE ──► STALE              │
│                                                               │
│  Transitions:                                                 │
│    UNSUBSCRIBED → PENDING                                     │
│      Trigger: subscribe(symbol, exchange) called              │
│      Action: Add to _subscriptions set, send subscribe msg    │
│      Note: If not connected, queue for later                  │
│                                                               │
│    PENDING → ACTIVE                                           │
│      Trigger: First message received for instrument           │
│      Action: Mark as active in internal tracking              │
│                                                               │
│    ACTIVE → ACTIVE                                            │
│      Trigger: Message received                                │
│      Action: Dispatch to callbacks, update freshness          │
│                                                               │
│    ACTIVE → STALE                                             │
│      Trigger: No message for heartbeat_timeout (30s)          │
│      Action: Log warning, mark stale                          │
│      Recovery: Reconnect triggers re-subscription             │
│                                                               │
│    ACTIVE → UNSUBSCRIBED                                      │
│      Trigger: unsubscribe(symbol, exchange) called            │
│      Action: Remove from _subscriptions set, send unsub msg   │
│                                                               │
│    STALE → UNSUBSCRIBED                                       │
│      Trigger: unsubscribe() called                            │
│      Action: Remove from tracking                             │
│                                                               │
│    *_STATE → UNSUBSCRIBED (on reconnect)                      │
│      Trigger: Connection lost                                 │
│      Action: Clear all subscriptions                          │
│      On reconnect: Re-subscribe all from _subscriptions set   │
│                                                               │
│  Thread Safety:                                               │
│    - _subscriptions set protected by _lock                    │
│    - Callback lists protected by _callback_lock (mixin)       │
│    - Snapshot callbacks before iteration to avoid holding lock│
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Reconnection State Machine

`ReconnectingServiceMixin` owns the reconnect logic for all WebSocket services.

```
┌──────────────────────────────────────────────────────────────┐
│              ReconnectingServiceMixin                         │
│                                                               │
│  States:                                                      │
│    CONNECTED ──► DISCONNECTED ──► BACKOFF ──► CONNECTING      │
│                                                               │
│  Transitions:                                                 │
│    CONNECTED → DISCONNECTED                                   │
│      Trigger: WebSocket close, error, or heartbeat timeout    │
│      Action: Set _is_connected = False,                       │
│              call _on_clean_disconnect() or                   │
│              _on_reconnect_failure(backoff)                   │
│                                                               │
│    DISCONNECTED → BACKOFF                                     │
│      Trigger: Immediate reconnect failed                      │
│      Action: Calculate backoff = min(current * 2, 30.0s)      │
│                                                               │
│    BACKOFF → CONNECTING                                       │
│      Trigger: _backoff_sleep(backoff) completes               │
│      Action: Attempt WebSocket connection                     │
│      Note: Sleep is interruptible via _stop_event             │
│                                                               │
│    CONNECTING → CONNECTED                                     │
│      Trigger: WebSocket handshake success                     │
│      Action: Set _is_connected = True,                        │
│              reset backoff to INITIAL_BACKOFF (1.0s),         │
│              re-subscribe all instruments                     │
│                                                               │
│    CONNECTING → BACKOFF (retry)                               │
│      Trigger: Connection attempt failed                       │
│      Action: Increment _reconnect_count,                      │
│              call _on_reconnect_failure(backoff),             │
│              emit reconnect metric                            │
│                                                               │
│    *_STATE → STOPPED                                          │
│      Trigger: _stop_event.set() called                        │
│      Action: Exit reconnect loop, join thread                 │
│                                                               │
│  Backoff Strategy:                                            │
│    - Initial: 1.0 second                                      │
│    - Multiplier: 2x (exponential)                             │
│    - Maximum: 30.0 seconds                                    │
│    - Reset: On clean disconnect or successful connect         │
│    - Jitter: None (deterministic)                             │
│                                                               │
│  Max Reconnect Attempts:                                      │
│    - Default: 50 attempts                                     │
│    - On exceed: Log critical, reset counter, cooldown 300s    │
│    - Env override: DHAN_MAX_RECONNECT_ATTEMPTS                │
│                                                               │
│  Heartbeat Watchdog:                                          │
│    - Timeout: 30.0 seconds (configurable)                     │
│    - Poll interval: 1.0 second                                │
│    - On timeout: Set _stop_event, trigger reconnect           │
│    - Disable: Set heartbeat_timeout_seconds = 0 or inf        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Backoff Arithmetic

```python
# Initial state
backoff = INITIAL_BACKOFF  # 1.0s

# On each reconnect failure
backoff = _on_reconnect_failure(backoff)  # Returns unchanged backoff
backoff = _backoff_sleep(backoff)          # Sleep, then return min(backoff * 2, MAX_BACKOFF)

# Sequence: 1.0s → 2.0s → 4.0s → 8.0s → 16.0s → 30.0s → 30.0s → ...

# On clean disconnect or successful connect
backoff = _on_clean_disconnect()  # Returns INITIAL_BACKOFF (1.0s)
```

---

## 5. Connection Admission State Machine

`MarketFeedConnectionAdmission` enforces host-wide lock and 429 cooldown for WebSocket connections.

```
┌──────────────────────────────────────────────────────────────┐
│            MarketFeedConnectionAdmission                      │
│                                                               │
│  States:                                                      │
│    ADMISSIBLE ──► THROTTLED ──► REJECTED                      │
│                                                               │
│  Transitions:                                                 │
│    ADMISSIBLE → ADMISSIBLE                                    │
│      Trigger: try_acquire() succeeds                          │
│      Action: Acquire fcntl lock (non-blocking),               │
│              return True                                      │
│      Precondition: No lock held by another process,           │
│                    cooldown period expired                    │
│                                                               │
│    ADMISSIBLE → THROTTLED                                     │
│      Trigger: HTTP 429 received from Dhan                     │
│      Action: Call record_rate_limit_cooldown(),               │
│              increment _consecutive_rate_limits,              │
│              calculate exponential cooldown:                  │
│                base * 2^(streak-1), capped at ceiling         │
│              Persist cooldown to JSON file                    │
│      Cooldown: 60s → 120s → 240s → 480s → 900s (max)        │
│                                                               │
│    THROTTLED → ADMISSIBLE                                     │
│      Trigger: Cooldown period expires                         │
│      Action: clear_cooldown() called after successful connect │
│              Reset _consecutive_rate_limits = 0               │
│              Delete cooldown JSON file                        │
│                                                               │
│    ADMISSIBLE → REJECTED                                     │
│      Trigger: try_acquire() fails (lock held by another)      │
│      Action: Set _blocked_by_lock = True, return False        │
│      Recovery: Retry after lock released                      │
│                                                               │
│    REJECTED → ADMISSIBLE                                      │
│      Trigger: Other process releases lock                     │
│      Action: Next try_acquire() succeeds                      │
│                                                               │
│  Lock Mechanism:                                              │
│    - File: runtime/dhan-{type}-{client_id}.lock               │
│    - Type: fcntl.flock(LOCK_EX | LOCK_NB)                     │
│    - Non-blocking: Returns False immediately if locked        │
│    - Release: On process exit or explicit release()           │
│                                                               │
│  Cooldown Persistence:                                        │
│    - File: runtime/dhan-{type}-{client_id}.cooldown.json      │
│    - Payload: {next_allowed_at, consecutive_rate_limits,      │
│                recorded_at, cooldown_seconds}                 │
│    - Survives process restarts                                │
│    - Streak resets after penalty window (3600s default)       │
│                                                               │
│  Connection Types:                                            │
│    - market-feed                                              │
│    - depth-20                                                 │
│    - depth-200                                                │
│    - order-stream                                             │
│    (Each type has independent lock and cooldown)              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### NoopAdmission (Test Double)

```
┌──────────────────────────────────────────────────────────────┐
│                    NoopAdmission                              │
│                                                               │
│  Purpose: Unit test double to avoid filesystem/fcntl          │
│                                                               │
│  Behavior:                                                    │
│    - try_acquire() → always returns True                      │
│    - lock_held → always True                                  │
│    - blocked_by_lock → always False                           │
│    - seconds_until_connect_allowed() → 0.0                    │
│    - record_rate_limit_cooldown() → no-op                     │
│    - clear_cooldown() → no-op                                 │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Order Stream State Machine

`DhanOrderStream` manages real-time order/trade updates via WebSocket.

```
┌──────────────────────────────────────────────────────────────┐
│                    DhanOrderStream                            │
│                                                               │
│  States:                                                      │
│    STOPPED ──► STARTING ──► RUNNING ──► STOPPING              │
│                                                               │
│  Transitions:                                                 │
│    STOPPED → STARTING                                         │
│      Trigger: start() called                                  │
│      Action: Clear _stop_event, create OrderUpdate SDK obj,   │
│              start daemon thread                              │
│      Idempotent: No-op if thread already alive                │
│                                                               │
│    STARTING → RUNNING                                         │
│      Trigger: Thread starts, WebSocket connects               │
│      Action: Set _is_connected = True                         │
│                                                               │
│    RUNNING → RUNNING                                          │
│      Trigger: Order update received                           │
│      Action: _on_order_update() called,                       │
│              _note_message_received(),                        │
│              transform order data,                            │
│              dispatch to callbacks,                           │
│              publish ORDER_UPDATED event to EventBus          │
│      Side Effect: If fill detected, publish TRADE event       │
│                                                               │
│    RUNNING → STOPPING                                         │
│      Trigger: stop() called or connection lost                │
│      Action: Set _stop_event, set _is_connected = False       │
│                                                               │
│    STOPPING → STOPPED                                         │
│      Trigger: Thread joins (5s timeout)                       │
│      Action: Thread exits cleanly                             │
│                                                               │
│    RUNNING → STARTING (reconnect)                             │
│      Trigger: Connection error, heartbeat timeout             │
│      Action: Exponential backoff (1.0s → 30.0s),              │
│              increment _reconnect_count                       │
│                                                               │
│  Order Processing:                                            │
│    - Filter: Only process messages with Type == "order_alert" │
│    - Transform: Map SDK fields to canonical format            │
│    - Incremental Fill: Track cumulative filledQty per order   │
│      (TTLCache: maxsize=10000, ttl=3600s)                     │
│    - Trade Detection: If cumulative_filled > previous_filled, │
│      publish TRADE event with incremental quantity            │
│                                                               │
│  Health States:                                               │
│    - HEALTHY: thread_alive=True, is_connected=True            │
│    - DEGRADED: thread_alive=True, is_connected=False          │
│    - STOPPED: thread_alive=False                              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Polling Feed State Machine

`PollingMarketFeed` provides REST polling fallback when WebSocket is unavailable.

```
┌──────────────────────────────────────────────────────────────┐
│                    PollingMarketFeed                          │
│                                                               │
│  States:                                                      │
│    STOPPED ──► POLLING ──► STOPPED                            │
│                                                               │
│  Transitions:                                                 │
│    STOPPED → POLLING                                          │
│      Trigger: start() called                                  │
│      Action: Clear _stop_event, set _is_connected = True,     │
│              start daemon thread                              │
│      Idempotent: No-op if thread already alive                │
│                                                               │
│    POLLING → POLLING                                          │
│      Trigger: Poll interval elapsed (default 2.0s)            │
│      Action: Group instruments by segment,                    │
│              batch POST to /marketfeed/ltp (max 1000 per req),│
│              parse response, dispatch to callbacks,           │
│              call _note_message_received()                    │
│                                                               │
│    POLLING → STOPPED                                          │
│      Trigger: stop() called                                   │
│      Action: Set _stop_event, set _is_connected = False,      │
│              join thread (5s timeout)                         │
│                                                               │
│  Polling Loop:                                                │
│    while not _stop_event.is_set():                            │
│      try:                                                     │
│        _poll_batch()  # Batch POST to REST API                │
│      except Exception:                                        │
│        log warning, continue                                  │
│      _stop_event.wait(timeout=interval)                       │
│                                                               │
│  Batch Strategy:                                              │
│    - Group instruments by segment (NSE_EQ, NSE_FNO, etc.)     │
│    - Chunk into batches of 1000 security_ids                  │
│    - Single POST per segment per cycle                        │
│    - Reduces HTTP overhead from N requests to ceil(N/1000)    │
│                                                               │
│  Health States:                                               │
│    - HEALTHY: thread_alive=True, is_connected=True            │
│    - DEGRADED: thread_alive=True, is_connected=False          │
│    - STOPPED: thread_alive=False                              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. Resolver State Machine

`SymbolResolver` manages the instrument master cache with atomic swap on refresh.

```
┌──────────────────────────────────────────────────────────────┐
│                    SymbolResolver                             │
│                                                               │
│  States:                                                      │
│    UNLOADED ──► LOADED ──► REFRESHING ──► LOADED              │
│                                                               │
│  Transitions:                                                 │
│    UNLOADED → LOADED                                          │
│      Trigger: load_from_rows(rows) called                     │
│      Action: Parse CSV rows, build lookup dictionaries,       │
│              atomic swap under _lock                          │
│      Side Effect: Set _loaded = True                          │
│                                                               │
│    LOADED → REFRESHING                                        │
│      Trigger: ResolverRefresher triggers refresh              │
│      Action: Build new resolver in memory (not yet swapped)   │
│                                                               │
│    REFRESHING → LOADED                                        │
│      Trigger: New resolver fully built                        │
│      Action: Atomic swap: _by_symbol = new_by_symbol,         │
│              _by_security_id = new_by_sid,                    │
│              _by_underlying = new_by_underlying               │
│      Note: Readers see old or new, never half-loaded          │
│                                                               │
│  Lookup Strategy (resolve):                                   │
│    1. Direct lookup: (normalized_symbol, exchange)            │
│    2. Stripped lookup: remove spaces, dashes, underscores     │
│    3. Option format: CALL → CE, PUT → PE                      │
│    4. Stripped option format                                  │
│    5. Index fallback: try Exchange.INDEX                      │
│    6. Hardcoded index: use config.indices fallback            │
│                                                               │
│  Thread Safety:                                               │
│    - _lock (RLock) protects all dictionary swaps              │
│    - Readers can proceed concurrently                         │
│    - Writers acquire lock for atomic swap                     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. Resolver Refresher State Machine

`ResolverRefresher` periodically refreshes the instrument master cache.

```
┌──────────────────────────────────────────────────────────────┐
│                    ResolverRefresher                          │
│                                                               │
│  States:                                                      │
│    STOPPED ──► RUNNING ──► STOPPED                            │
│                                                               │
│  Transitions:                                                 │
│    STOPPED → RUNNING                                          │
│      Trigger: start() called                                  │
│      Action: Clear _stop_event, start daemon thread           │
│      Idempotent: No-op if thread already alive                │
│                                                               │
│    RUNNING → RUNNING                                          │
│      Trigger: Interval elapsed (default 86400s = 24h)         │
│      Action: Call _do_refresh(),                              │
│              connection.load_instruments(use_cache=True),     │
│              atomic swap resolver                             │
│      On Success: Increment _refresh_count, clear _last_error  │
│      On Failure: Increment _error_count, log warning/error    │
│                                                               │
│    RUNNING → STOPPED                                          │
│      Trigger: stop() called                                   │
│      Action: Set _stop_event, join thread (10s timeout)       │
│                                                               │
│  Health States:                                               │
│    - HEALTHY: running=True, last_error=None                   │
│    - DEGRADED: running=True, last_error!=None                 │
│    - STOPPED: running=False                                   │
│                                                               │
│  Failure Handling:                                            │
│    - Exception in _do_refresh() → log, increment error_count  │
│    - 3+ consecutive failures → log error with hint            │
│    - Loop continues on next tick (never crashes)              │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 10. WebSocket Connection Manager State Machine

`WebSocketConnectionManager` centralizes singleton enforcement for WebSocket connections.

```
┌──────────────────────────────────────────────────────────────┐
│              WebSocketConnectionManager                       │
│                                                               │
│  State:                                                       │
│    {                                                          │
│      market_feed: DhanMarketFeed | None,                      │
│      order_stream: DhanOrderStream | None,                    │
│      connection_stats: {...}                                  │
│    }                                                          │
│                                                               │
│  Transitions:                                                 │
│    get_market_feed()                                          │
│      If _market_feed is None:                                 │
│        Create new DhanMarketFeed singleton                    │
│        Update stats: created=True, start_count+=1             │
│        Return feed                                            │
│      Else:                                                    │
│        Update stats: connected=feed.is_connected              │
│        Return existing feed                                   │
│                                                               │
│    get_order_stream()                                         │
│      If _order_stream is None:                                │
│        Create new DhanOrderStream singleton                   │
│        Update stats: created=True, start_count+=1             │
│        Return stream                                          │
│      Else:                                                    │
│        Update stats: connected=stream.is_connected            │
│        Return existing stream                                 │
│                                                               │
│    start_all()                                                │
│      For each connection:                                     │
│        If exists and not connected: start()                   │
│        Update stats: start_count+=1                           │
│                                                               │
│    stop_all(timeout_seconds=5.0)                              │
│      For each connection:                                     │
│        If exists: stop(timeout_seconds)                       │
│        Update stats: connected=False                          │
│                                                               │
│    close_all()                                                │
│      stop_all()                                               │
│      Set _market_feed = None, _order_stream = None            │
│                                                               │
│  Thread Safety:                                               │
│    - All methods protected by _lock (RLock)                   │
│    - Singleton enforcement is atomic                          │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Summary: State Machine Interactions

```
┌──────────────────────────────────────────────────────────────┐
│                    System-Level Flow                          │
│                                                               │
│  1. ConnectionLifecycle created                              │
│     └─► State: UNINITIALIZED → INITIALIZED                   │
│                                                               │
│  2. Factory method called (e.g., create_market_feed)         │
│     └─► WebSocketConnectionManager.get_market_feed()         │
│         └─► Create singleton DhanMarketFeed                  │
│     └─► ConnectionLifecycle state: SERVICES_CREATED          │
│     └─► Register with LifecycleManager                       │
│     └─► Register token receiver                              │
│                                                               │
│  3. LifecycleManager.start_all()                             │
│     └─► DhanMarketFeed.start()                               │
│         └─► MarketFeedConnectionAdmission.try_acquire()      │
│             └─► State: ADMISSIBLE (lock acquired)            │
│         └─► ReconnectingServiceMixin state: CONNECTING       │
│         └─► WebSocket connect                                │
│         └─► State: CONNECTED                                 │
│         └─► Subscribe instruments                            │
│             └─► Subscription state: UNSUBSCRIBED → ACTIVE    │
│                                                               │
│  4. Message received                                          │
│     └─► _note_message_received()                             │
│     └─► Dispatch to callbacks                                │
│     └─► Publish to EventBus                                  │
│                                                               │
│  5. Connection lost                                           │
│     └─► State: CONNECTED → DISCONNECTED                      │
│     └─► Backoff: 1.0s → 2.0s → 4.0s → ... → 30.0s          │
│     └─► State: BACKOFF → CONNECTING                          │
│     └─► Reconnect success                                    │
│         └─► State: CONNECTED                                 │
│         └─► Re-subscribe all instruments                     │
│                                                               │
│  6. HTTP 429 rate limit                                       │
│     └─► MarketFeedConnectionAdmission.record_cooldown()      │
│         └─► State: ADMISSIBLE → THROTTLED                    │
│         └─► Cooldown: 60s → 120s → 240s → ... → 900s        │
│     └─► Wait for cooldown expiry                             │
│     └─► State: THROTTLED → ADMISSIBLE                        │
│                                                               │
│  7. Resolver refresh (daily)                                  │
│     └─► ResolverRefresher triggers                           │
│         └─► State: LOADED → REFRESHING → LOADED              │
│         └─► Atomic swap of resolver dictionaries             │
│                                                               │
│  8. Shutdown                                                  │
│     └─► ConnectionLifecycle.close()                          │
│         └─► State: SERVICES_CREATED → CLOSED                 │
│         └─► Stop all services in order                       │
│         └─► Release all locks                                │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

**End of State Machines Document**
