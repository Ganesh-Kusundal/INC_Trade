# Phase 4 — Market Data: Public Contract

**Greenfield Broker Replication Protocol — Dhan**  
**Phase 4: Market Data Streaming & Instrument Resolution**

---

## 1. ConnectionLifecycle API

### Class: `ConnectionLifecycle`

**Purpose:** Manages lifecycle of all WebSocket services and resolver refresher. Acts as factory and orchestrator.

**Thread Safety:** Caller MUST hold connection mutex when calling factory methods.

---

### Constructor

```python
def __init__(
    self,
    client: DhanHttpClient,
    instruments: SymbolResolver,
    *,
    register_token_receiver: Callable[[Callable[[str], None]], None],
    connection_owner: Any,
    event_bus: EventBus | None = None,
    lifecycle: LifecycleManager | None = None,
    backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
) -> None
```

**Parameters:**
- `client`: DhanHttpClient instance for API calls
- `instruments`: SymbolResolver for instrument lookup
- `register_token_receiver`: Callback to register token update receivers
- `connection_owner`: The DhanConnection that owns this lifecycle
- `event_bus`: Optional EventBus for domain events
- `lifecycle`: Optional LifecycleManager for service registration
- `backfill_callback`: Optional callback for historical data backfill on reconnect

**Exceptions:** None  
**Side Effects:** Stores references, initializes all service slots to None

---

### Factory Methods

#### `create_market_feed()`

```python
def create_market_feed(
    self,
    access_token: str | None = None,
    instruments: list[tuple] | None = None,
    access_token_fn: Callable[[], str] | None = None,
) -> DhanMarketFeed
```

**Returns:** Singleton DhanMarketFeed instance  
**Exceptions:** None  
**Side Effects:**
- Creates DhanMarketFeed on first call
- Registers with LifecycleManager
- Registers token receiver via `register_token_receiver`

**Notes:** Returns existing singleton on subsequent calls

---

#### `create_order_stream()`

```python
def create_order_stream(
    self,
    access_token: str | None = None,
    access_token_fn: Callable[[], str] | None = None,
) -> DhanOrderStream
```

**Returns:** Singleton DhanOrderStream instance  
**Exceptions:** None  
**Side Effects:**
- Creates DhanOrderStream on first call
- Registers with LifecycleManager
- Registers token receiver

**Notes:** Returns existing singleton on subsequent calls

---

#### `create_depth_20_feed()`

```python
def create_depth_20_feed(
    self,
    access_token: str | None = None,
    instrument: tuple[str, str] | None = None,
) -> DhanDepth20Feed
```

**Returns:** Singleton DhanDepth20Feed instance  
**Exceptions:** None  
**Side Effects:**
- Creates DhanDepth20Feed on first call
- Registers with LifecycleManager
- Registers token receiver (if `update_token` method exists)
- Logs singleton creation/reuse

**Notes:** Enforces singleton pattern to prevent rate limit violations

---

#### `create_depth_200_feed()`

```python
def create_depth_200_feed(
    self,
    access_token: str | None = None,
    instrument: tuple[str, str] | None = None,
) -> DhanDepth200Feed
```

**Returns:** DhanDepth200Feed instance (from pool if instrument specified)  
**Exceptions:** None  
**Side Effects:**
- Creates Depth200ConnectionPool on first call
- Creates DhanDepth200Feed for instrument
- Registers with LifecycleManager
- Registers token receiver

**Notes:**
- If `instrument` is None, returns placeholder feed for backward compatibility
- If `instrument` is specified, gets/creates feed from connection pool
- Dhan depth-200 API supports only 1 instrument per connection

---

#### `create_polling_feed()`

```python
def create_polling_feed(
    self,
    instruments: list[tuple],
    interval_seconds: float = 2.0,
) -> PollingMarketFeed
```

**Returns:** PollingMarketFeed instance  
**Exceptions:** None  
**Side Effects:**
- Creates PollingMarketFeed
- Registers with LifecycleManager

**Notes:** Not a singleton — creates new instance on each call

---

#### `get_or_create_resolver_refresher()`

```python
def get_or_create_resolver_refresher(
    self,
    interval_seconds: int = 24 * 3600,
    on_success: Any = None,
    on_error: Any = None,
) -> ResolverRefresher
```

**Returns:** Singleton ResolverRefresher instance  
**Exceptions:** None  
**Side Effects:** Creates ResolverRefresher on first call

**Notes:** Returns existing singleton on subsequent calls

---

#### `register_resolver_refresher_with_lifecycle()`

```python
def register_resolver_refresher_with_lifecycle(
    self,
    interval_seconds: int = 24 * 3600,
) -> ResolverRefresher | None
```

**Returns:** ResolverRefresher instance or None if no LifecycleManager  
**Exceptions:** None  
**Side Effects:**
- Creates ResolverRefresher if needed
- Registers with LifecycleManager

**Notes:** Returns None if connection has no LifecycleManager

---

### Properties

```python
@property
def market_feed(self) -> DhanMarketFeed | None

@property
def order_stream(self) -> DhanOrderStream | None

@property
def depth_20_feed(self) -> DhanDepth20Feed | None

@property
def depth_200_feed(self) -> DhanDepth200Feed | None

@property
def depth_200_pool(self) -> Depth200ConnectionPool | None

@property
def polling_feed(self) -> PollingMarketFeed | None

@property
def resolver_refresher(self) -> ResolverRefresher | None
```

**Setters:** All properties except `depth_200_pool` and `resolver_refresher` have setters

---

### Shutdown

```python
def close(self, timeout_seconds: float = 5.0) -> None
```

**Exceptions:** None (all exceptions caught and logged)  
**Side Effects:**
- Stops resolver_refresher
- Stops all WebSocket services (market_feed, order_stream, polling_feed, depth_20_feed, depth_200_feed)
- Closes depth_200_pool

**Notes:** Timeout applies per service. Total shutdown time can be up to `6 * timeout_seconds`

---

## 2. MarketFeedConnectionAdmission API

### Class: `MarketFeedConnectionAdmission`

**Purpose:** Non-blocking host-wide lock + shared 429 cooldown for one WebSocket type per account.

**Thread Safety:** Thread-safe via fcntl file locking

---

### Constructor

```python
def __init__(
    self,
    client_id: str,
    state_dir: Path | None = None,
    connection_type: str = "market-feed",
) -> None
```

**Parameters:**
- `client_id`: Dhan client ID
- `state_dir`: Directory for lock/cooldown files (default: `runtime/`)
- `connection_type`: One of "market-feed", "depth-20", "depth-200", "order-stream"

**Exceptions:** None  
**Side Effects:**
- Creates state directory if not exists
- Sanitizes client_id and connection_type for filenames
- Loads persisted 429 streak from cooldown file

---

### Lock Management

#### `try_acquire()`

```python
def try_acquire(self) -> bool
```

**Returns:** True if lock acquired, False if blocked  
**Exceptions:** None  
**Side Effects:**
- Attempts non-blocking fcntl lock acquisition
- Sets `_lock_held` and `_blocked_by_lock` flags
- Logs lock acquisition/block

**Notes:** Idempotent — returns True if already holding lock

---

#### `release()`

```python
def release(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Releases fcntl lock
- Closes lock file handle
- Resets `_lock_held` and `_blocked_by_lock` flags

**Notes:** Idempotent — no-op if not holding lock

---

### Cooldown Management

#### `seconds_until_connect_allowed()`

```python
def seconds_until_connect_allowed(self) -> float
```

**Returns:** Seconds to wait before next connect attempt (0.0 if allowed)  
**Exceptions:** None  
**Side Effects:** None

---

#### `next_connect_allowed_at()`

```python
def next_connect_allowed_at(self) -> datetime | None
```

**Returns:** UTC datetime when next connect is allowed, or None if no cooldown  
**Exceptions:** None  
**Side Effects:** None

---

#### `record_rate_limit_cooldown()`

```python
def record_rate_limit_cooldown(self) -> datetime
```

**Returns:** UTC datetime when next connect is allowed  
**Exceptions:** None  
**Side Effects:**
- Increments `_consecutive_rate_limits`
- Calculates exponential cooldown: `base * 2^(streak-1)`, capped at ceiling
- Persists cooldown to JSON file
- Logs warning with cooldown details

**Cooldown Progression:**
- 1st: 60s (base)
- 2nd: 120s
- 3rd: 240s
- 4th: 480s
- 5th+: 900s (ceiling)

---

#### `clear_cooldown()`

```python
def clear_cooldown(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Resets `_consecutive_rate_limits` to 0
- Deletes cooldown JSON file

---

### Status

#### `status()`

```python
def status(self) -> dict[str, Any]
```

**Returns:** Dictionary with:
- `connection_type`: str
- `connection_lock_acquired`: bool
- `connection_blocked_by_lock`: bool
- `next_connect_allowed_at`: str | None (ISO format)
- `seconds_until_connect_allowed`: float
- `consecutive_rate_limits`: int
- `admission_lock_path`: str

**Exceptions:** None  
**Side Effects:** None

---

### Properties

```python
@property
def lock_held(self) -> bool

@property
def blocked_by_lock(self) -> bool
```

---

## 3. NoopAdmission API

### Class: `NoopAdmission`

**Purpose:** Test double for MarketFeedConnectionAdmission. Always permits connects.

---

### Methods

All methods mirror `MarketFeedConnectionAdmission` but are no-ops:

```python
def try_acquire(self) -> bool  # Always returns True
def release(self) -> None  # No-op
def seconds_until_connect_allowed(self) -> float  # Always returns 0.0
def next_connect_allowed_at(self) -> None  # Always returns None
def record_rate_limit_cooldown(self) -> datetime  # Returns current time
def clear_cooldown(self) -> None  # No-op
def status(self) -> dict[str, Any]  # Returns noop status dict
```

**Properties:**
```python
@property
def lock_held(self) -> bool  # Always True

@property
def blocked_by_lock(self) -> bool  # Always False
```

---

## 4. ReconnectingServiceMixin API

### Class: `ReconnectingServiceMixin[Generic[_CallbackT]]`

**Purpose:** Mixin that owns reconnect/message-tracking plumbing for all WebSocket services.

**Thread Safety:** Thread-safe via internal locks

---

### Initialization

#### `_init_reconnect_state()`

```python
def _init_reconnect_state(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Initializes `_stop_event`, `_is_connected`, `_reconnect_count`, `_last_message_at`, `_message_count`, `_callback_lock`, `_watchdog_thread`

**Notes:** MUST be called from subclass `__init__`

---

### Callback Management

#### `_register_callback()`

```python
def _register_callback(self, callback_list: list[_CallbackT], callback: _CallbackT) -> None
```

**Exceptions:** None  
**Side Effects:** Appends callback to list under lock

**Notes:** Subclasses pass their own callback list

---

#### `_unregister_callback()`

```python
def _unregister_callback(self, callback_list: list[_CallbackT], callback: _CallbackT) -> None
```

**Exceptions:** None  
**Side Effects:** Removes callback from list under lock

---

#### `_snapshot_callbacks()`

```python
def _snapshot_callbacks(self, callback_list: list[_CallbackT]) -> list[_CallbackT]
```

**Returns:** Snapshot of callback list  
**Exceptions:** None  
**Side Effects:** None

**Notes:** Returns copy for safe iteration outside lock

---

### Message Tracking

#### `_note_message_received()`

```python
def _note_message_received(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Updates `_last_message_at` to current UTC time
- Resets `_last_monotonic_at` for heartbeat watchdog
- Increments `_message_count`

**Notes:** MUST be called by subclass on every message receive

---

### Heartbeat Watchdog

#### `_start_heartbeat_watchdog()`

```python
def _start_heartbeat_watchdog(self) -> None
```

**Exceptions:** None  
**Side Effects:** Starts background watchdog thread

**Notes:** Idempotent — no-op if already running. Disabled if `heartbeat_timeout_seconds` is 0 or inf.

---

#### `_stop_heartbeat_watchdog()`

```python
def _stop_heartbeat_watchdog(self) -> None
```

**Exceptions:** None  
**Side Effects:** Stops and joins watchdog thread (3s timeout)

---

### Backoff

#### `_backoff_sleep()`

```python
def _backoff_sleep(self, current: float) -> float
```

**Returns:** Next backoff value (current * 2, capped at MAX_BACKOFF)  
**Exceptions:** None  
**Side Effects:** Sleeps for `min(current, MAX_BACKOFF)` seconds

**Notes:** Sleep is interruptible via `_stop_event`

---

#### `_on_clean_disconnect()`

```python
def _on_clean_disconnect(self) -> float
```

**Returns:** INITIAL_BACKOFF (1.0s)  
**Exceptions:** None  
**Side Effects:** Increments `_reconnect_count`

**Notes:** Resets backoff to initial value

---

#### `_on_reconnect_failure()`

```python
def _on_reconnect_failure(self, current: float) -> float
```

**Returns:** Unchanged current backoff  
**Exceptions:** None  
**Side Effects:**
- Increments `_reconnect_count`
- Emits reconnect metric

**Notes:** Subclasses can override for custom handling

---

### Correlation ID

#### `next_correlation_id()`

```python
@classmethod
def next_correlation_id(cls, prefix: str = "ws") -> str
```

**Returns:** Monotonic correlation ID (e.g., "ws-1234567890-1")  
**Exceptions:** None  
**Side Effects:** None

**Notes:** Class method, shared counter across all instances

---

### Constants

```python
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 30.0  # seconds
heartbeat_timeout_seconds = 30.0  # configurable per instance
```

---

## 5. DhanOrderStream API

### Class: `DhanOrderStream(ReconnectingServiceMixin, ManagedService)`

**Purpose:** Real-time order/trade updates via Dhan SDK WebSocket.

**Thread Safety:** Thread-safe via internal locks

---

### Constructor

```python
def __init__(
    self,
    client_id: str,
    access_token: str | None = None,
    access_token_fn: Callable[[], str] | None = None,
    event_bus: EventBus | None = None,
)
```

**Parameters:**
- `client_id`: Dhan client ID
- `access_token`: Static access token
- `access_token_fn`: Callable returning current token
- `event_bus`: Optional EventBus for domain events

**Exceptions:** None  
**Side Effects:**
- Initializes `_DhanContext`
- Initializes reconnect state via mixin
- Creates empty callback list
- Creates TTLCache for filled quantity tracking (maxsize=10000, ttl=3600s)

---

### Token Management

#### `update_token()`

```python
def update_token(self, access_token: str) -> None
```

**Exceptions:** None  
**Side Effects:**
- Updates context with new token
- Updates OrderUpdate SDK object if exists

**Notes:** No-op if token is empty or unchanged

---

### Lifecycle

#### `start()`

```python
def start(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Clears `_stop_event`
- Creates OrderUpdate SDK object
- Starts daemon thread for order stream

**Notes:** Idempotent — no-op if thread already alive

---

#### `stop()`

```python
def stop(self, timeout_seconds: float = 5.0) -> None
```

**Exceptions:** None  
**Side Effects:**
- Sets `_stop_event`
- Sets `_is_connected = False`
- Joins thread with timeout

**Notes:** Idempotent

---

#### `connect()` / `disconnect()`

**Deprecated aliases** for `start()` / `stop()`

---

### Callbacks

#### `on_order_update()`

```python
def on_order_update(self, callback: Callable[[dict], None]) -> None
```

**Exceptions:** None  
**Side Effects:** Registers callback under lock

---

#### `off_order_update()`

```python
def off_order_update(self, callback: Callable[[dict], None]) -> None
```

**Exceptions:** None  
**Side Effects:** Unregisters callback under lock

---

### Health

#### `health()`

```python
def health(self) -> HealthStatus
```

**Returns:** HealthStatus with:
- `state`: HEALTHY | DEGRADED | STOPPED
- `service`: "dhan.order_stream"
- `detail`: Human-readable status
- `metrics`: Dict with connected, thread_alive, reconnect_count, message_count, last_message_age_seconds

**Exceptions:** None  
**Side Effects:** None

---

### Properties

```python
@property
def is_connected(self) -> bool
```

---

## 6. PollingMarketFeed API

### Class: `PollingMarketFeed(ReconnectingServiceMixin, ManagedService)`

**Purpose:** REST polling fallback for market data when WebSocket is unavailable.

---

### Constructor

```python
def __init__(
    self,
    http_client,
    resolver,
    instruments: list[tuple],
    interval_seconds: float = 2.0,
)
```

**Parameters:**
- `http_client`: DhanHttpClient instance
- `resolver`: SymbolResolver for security_id → symbol lookup
- `instruments`: List of (exchange_str, security_id_str, mode_str) tuples
- `interval_seconds`: Polling interval (default 2.0s)

**Exceptions:** None  
**Side Effects:** Initializes reconnect state via mixin

---

### Lifecycle

#### `start()`

```python
def start(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Clears `_stop_event`
- Sets `_is_connected = True`
- Starts daemon thread for polling loop

**Notes:** Idempotent

---

#### `stop()`

```python
def stop(self, timeout_seconds: float = 5.0) -> None
```

**Exceptions:** None  
**Side Effects:**
- Sets `_stop_event`
- Sets `_is_connected = False`
- Joins thread with timeout

**Notes:** Idempotent

---

### Callbacks

#### `on_quote()`

```python
def on_quote(self, callback: Callable[[dict], None]) -> None
```

**Exceptions:** None  
**Side Effects:** Registers callback under lock

---

### Health

#### `health()`

```python
def health(self) -> HealthStatus
```

**Returns:** HealthStatus with:
- `state`: HEALTHY | DEGRADED | STOPPED
- `service`: "dhan.polling_market_feed"
- `metrics`: Dict with connected, thread_alive

---

### Properties

```python
@property
def is_connected(self) -> bool
```

---

## 7. SymbolResolver API

### Class: `SymbolResolver`

**Purpose:** Thread-safe O(1) symbol → Instrument resolver backed by dictionaries.

**Thread Safety:** Thread-safe via RLock for atomic swaps

---

### Constructor

```python
def __init__(self) -> None
```

**Exceptions:** None  
**Side Effects:** Initializes empty dictionaries and lock

---

### Resolution

#### `resolve()`

```python
def resolve(
    self,
    symbol: str,
    exchange: str,
    *,
    expected_segment: str | None = None,
) -> Instrument
```

**Returns:** Instrument instance  
**Exceptions:** `InstrumentNotFoundError` if not found  
**Side Effects:** None

**Lookup Strategy:**
1. Direct lookup with normalized symbol
2. Stripped lookup (remove spaces, dashes, underscores)
3. Option format standardization (CALL → CE, PUT → PE)
4. Stripped option format
5. Index fallback (try Exchange.INDEX)
6. Hardcoded index fallback (config.indices)

**Notes:** `expected_segment` prevents index-vs-derivative misroutes

---

#### `get_by_symbol()`

```python
def get_by_symbol(self, symbol: str, exchange: str) -> Instrument | None
```

**Returns:** Instrument or None  
**Exceptions:** None (catches all exceptions)  
**Side Effects:** None

---

#### `get_by_security_id()`

```python
def get_by_security_id(self, security_id: str) -> Instrument | None
```

**Returns:** Instrument or None  
**Exceptions:** None  
**Side Effects:** None

---

#### `get_futures()`

```python
def get_futures(self, underlying: str, exchange: str) -> list[Instrument]
```

**Returns:** List of futures contracts sorted by expiry  
**Exceptions:** None  
**Side Effects:** None

---

#### `get_futures_expiries()`

```python
def get_futures_expiries(self, underlying: str, exchange: str) -> list[str]
```

**Returns:** List of unique expiry dates  
**Exceptions:** None  
**Side Effects:** None

---

#### `get_lot_size()`

```python
def get_lot_size(self, symbol: str, exchange: str) -> int
```

**Returns:** Lot size  
**Exceptions:** `InstrumentNotFoundError` if not found  
**Side Effects:** None

---

### Loading

#### `load_from_rows()`

```python
def load_from_rows(self, rows: Iterable[dict]) -> dict[str, int | float]
```

**Returns:** Dict with keys: total, skipped, skip_rate  
**Exceptions:** None (skips malformed rows)  
**Side Effects:**
- Parses CSV rows
- Builds lookup dictionaries
- Atomic swap under lock
- Sets `_loaded = True`
- Logs high skip rate warning (>1%)

**Notes:** Thread-safe atomic swap

---

### Utilities

#### `stats()`

```python
def stats(self) -> dict
```

**Returns:** Dict with keys: loaded (bool), total (int)  
**Exceptions:** None  
**Side Effects:** None

---

#### `all_instruments()`

```python
def all_instruments(self) -> list[Instrument]
```

**Returns:** List of all loaded instruments  
**Exceptions:** None  
**Side Effects:** None

---

## 8. ResolverRefresher API

### Class: `ResolverRefresher(ManagedService)`

**Purpose:** Background scheduler that periodically refreshes the instrument resolver.

---

### Constructor

```python
def __init__(
    self,
    connection,
    interval_seconds: int = 24 * 3600,
    on_success=None,
    on_error=None,
)
```

**Parameters:**
- `connection`: DhanConnection instance
- `interval_seconds`: Refresh interval (default 86400s = 24h)
- `on_success`: Optional callback after successful refresh
- `on_error`: Optional callback after failed refresh

**Exceptions:** None  
**Side Effects:** Stores references

---

### Lifecycle

#### `start()`

```python
def start(self) -> None
```

**Exceptions:** None  
**Side Effects:** Starts daemon thread for refresh loop

**Notes:** Idempotent

---

#### `stop()`

```python
def stop(self, timeout_seconds: float = 10.0) -> None
```

**Exceptions:** None  
**Side Effects:**
- Sets `_stop_event`
- Joins thread with timeout
- Logs warning if thread didn't stop

**Notes:** Idempotent

---

### Manual Refresh

#### `refresh_now()`

```python
def refresh_now(self) -> bool
```

**Returns:** True if successful, False if failed  
**Exceptions:** None (catches all exceptions)  
**Side Effects:**
- Calls `connection.load_instruments(use_cache=True)`
- Atomic swap of resolver
- Increments refresh_count or error_count
- Calls on_success or on_error callback

**Notes:** Blocks until refresh complete

---

### Health

#### `health()`

```python
def health(self)
```

**Returns:** HealthStatus with:
- `state`: HEALTHY | DEGRADED | STOPPED
- `service`: "dhan.resolver_refresher"
- `metrics`: Dict with refresh_count, error_count, interval_seconds, last_refresh_at

---

### Properties

```python
@property
def refresh_count(self) -> int

@property
def error_count(self) -> int

@property
def is_running(self) -> bool
```

---

## 9. WebSocketConnectionManager API

### Class: `WebSocketConnectionManager`

**Purpose:** Centralized manager for WebSocket connections with singleton enforcement.

**Thread Safety:** All methods thread-safe via RLock

---

### Constructor

```python
def __init__(self, client_id: str, access_token: str | None = None, event_bus: Any = None)
```

**Parameters:**
- `client_id`: Dhan client ID
- `access_token`: Optional access token
- `event_bus`: Optional EventBus

**Exceptions:** None  
**Side Effects:** Initializes connection slots and stats

---

### Connection Access

#### `get_market_feed()`

```python
def get_market_feed(
    self,
    instruments: list[tuple] | None = None,
    access_token_fn: Callable[[], str] | None = None,
    backfill_callback: Callable[[str, Any, Any], list[dict]] | None = None,
) -> DhanMarketFeed
```

**Returns:** Singleton DhanMarketFeed instance  
**Exceptions:** None  
**Side Effects:**
- Creates DhanMarketFeed on first call
- Updates connection stats

**Notes:** Returns existing singleton on subsequent calls

---

#### `get_order_stream()`

```python
def get_order_stream(
    self,
    access_token_fn: Callable[[], str] | None = None,
) -> DhanOrderStream
```

**Returns:** Singleton DhanOrderStream instance  
**Exceptions:** None  
**Side Effects:**
- Creates DhanOrderStream on first call
- Updates connection stats

**Notes:** Returns existing singleton on subsequent calls

---

### Lifecycle

#### `start_all()`

```python
def start_all(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Starts all existing connections
- Updates connection stats

---

#### `stop_all()`

```python
def stop_all(self, timeout_seconds: float = 5.0) -> None
```

**Exceptions:** None (catches all exceptions)  
**Side Effects:**
- Stops all existing connections
- Updates connection stats

---

#### `close_all()`

```python
def close_all(self) -> None
```

**Exceptions:** None  
**Side Effects:**
- Calls `stop_all()`
- Sets all connection slots to None

---

### Utilities

#### `get_connection_stats()`

```python
def get_connection_stats(self) -> dict[str, Any]
```

**Returns:** Dict with:
- `market_feed`: Dict with exists, connected, created, start_count
- `order_stream`: Dict with exists, connected, created, start_count
- `total_connections`: int

**Exceptions:** None  
**Side Effects:** None

---

#### `ensure_single_connections()`

```python
def ensure_single_connections(self) -> None
```

**Exceptions:** `RuntimeError` if multiple connections detected  
**Side Effects:** None

**Notes:** For testing/validation

---

### Properties

```python
@property
def client_id(self) -> str

@property
def access_token(self) -> str | None

@access_token.setter
def access_token(self, value: str) -> None
```

**Setter Side Effects:** Propagates token to existing connections

---

## 10. Greenfield Equivalents

### DhanStreaming (Greenfield)

**Equivalent to:** Archive DhanMarketFeed + ConnectionLifecycle  
**Simplification:** Direct WebSocket without SDK wrapper

```python
class DhanStreaming(BaseWebSocketStreaming):
    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        ws_url: str = WS_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    )
    
    def subscribe(self, symbol: str, exchange: str = "NSE") -> None
    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None
    def update_token(self, new_token: str) -> None
```

**Key Differences:**
- No singleton enforcement (caller manages lifecycle)
- No admission control (no fcntl locks)
- No connection pool
- Simpler backoff (no jitter, no max attempts)
- Direct WebSocket protocol (no SDK abstraction)

---

### DhanOrderStream (Greenfield)

**Equivalent to:** Archive DhanOrderStream  
**Simplification:** Direct WebSocket without SDK wrapper

```python
class DhanOrderStream(BaseWebSocketStreaming):
    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        ws_url: str = WS_ORDER_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    )
    
    def update_token(self, new_token: str) -> None
    on_order_update: Callable[[Order], Any] | None
```

**Key Differences:**
- No TTLCache for filled quantity tracking
- No incremental fill calculation
- No TRADE event publishing
- Simpler callback (single callback, not list)
- Direct Order entity mapping

---

### DhanDepth20Stream (Greenfield)

**Equivalent to:** Archive DhanDepth20Feed  
**Simplification:** Direct WebSocket without connection pool

```python
class DhanDepth20Stream(BaseWebSocketStreaming):
    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        ws_url: str = WS_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    )
    
    def subscribe(self, symbol: str, exchange: str = "NSE") -> None
    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None
    def update_token(self, new_token: str) -> None
    on_depth_update: Callable[[dict], Any] | None
```

**Key Differences:**
- No singleton enforcement
- No connection pool
- Binary parsing placeholder (not fully implemented)
- Simpler lifecycle

---

### DhanDepth200Stream (Greenfield)

**Equivalent to:** Archive DhanDepth200Feed + Depth200ConnectionPool  
**Simplification:** Single connection per stream (caller manages pool)

```python
class DhanDepth200Stream(BaseWebSocketStreaming):
    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        ws_url: str = WS_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    )
    
    def subscribe(self, symbol: str, exchange: str = "NSE") -> None
    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None
    def update_token(self, new_token: str) -> None
    on_depth_update: Callable[[dict], Any] | None
```

**Key Differences:**
- No connection pool (caller must create multiple instances)
- Enforces 1 instrument per connection in `_build_subscribe_message()`
- Binary parsing placeholder (not fully implemented)

---

## Summary: Archive vs Greenfield

| Feature | Archive | Greenfield |
|---------|---------|------------|
| Singleton Enforcement | Yes (ConnectionLifecycle) | No (caller manages) |
| Admission Control | Yes (fcntl locks) | No |
| Connection Pool | Yes (Depth200ConnectionPool) | No (caller manages) |
| Reconnect Backoff | Exponential (1s → 30s) | Exponential (5s → 60s) |
| Max Reconnect Attempts | 50 (configurable) | Unlimited |
| Heartbeat Watchdog | Yes (30s timeout) | No |
| Token Refresh | Automatic via receivers | Manual via update_token() |
| Resolver Refresher | Yes (daily) | No (not implemented) |
| Polling Fallback | Yes (PollingMarketFeed) | No |
| EventBus Integration | Yes | No |
| LifecycleManager | Yes (ManagedService) | No |
| Health Reporting | Yes (HealthStatus) | No |
| Backoff Jitter | No | No |
| Binary Parsing | Full implementation | Placeholder |

---

**End of Public Contract Document**
