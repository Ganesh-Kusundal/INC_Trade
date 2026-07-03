# Phase 4 — Market Data: Failure Analysis

**Greenfield Broker Replication Protocol — Dhan**  
**Phase 4: Market Data Streaming & Instrument Resolution**

---

## 1. Timeout Policies

### WebSocket Connection Timeouts

| Component | Timeout Type | Value | Configurable | Notes |
|-----------|--------------|-------|--------------|-------|
| **DhanStreaming** | Initial connect | Not specified | No | Relies on websocket-client library default |
| **DhanStreaming** | Ping interval | 30s | No | Hardcoded in BaseWebSocketStreaming |
| **DhanStreaming** | Ping timeout | 10s | No | Hardcoded in BaseWebSocketStreaming |
| **DhanOrderStream** | Initial connect | Not specified | No | Relies on websocket-client library default |
| **DhanDepth20Stream** | Initial connect | Not specified | No | Relies on websocket-client library default |
| **DhanDepth200Stream** | Initial connect | Not specified | No | Relies on websocket-client library default |

### Archive Timeouts (Dhan SDK)

| Component | Timeout Type | Value | Configurable | Notes |
|-----------|--------------|-------|--------------|-------|
| **DhanMarketFeed** | Heartbeat timeout | 30s | Yes | Reconnect if no message received |
| **DhanDepth20Feed** | Heartbeat timeout | 30s | Yes | Reconnect if no message received |
| **DhanDepth200Feed** | Heartbeat timeout | 30s | Yes | Reconnect if no message received |
| **DhanOrderStream** | Heartbeat timeout | 30s | Yes | Reconnect if no message received |
| **ConnectionLifecycle** | Service stop | 5s | Yes | Per service, total can be 6x |
| **ResolverRefresher** | Thread join | 10s | Yes | Logs warning if timeout |
| **MarketFeedConnectionAdmission** | Cooldown (1st) | 60s | Yes (env) | DHAN_WS_429_COOLDOWN_SECONDS |
| **MarketFeedConnectionAdmission** | Cooldown (max) | 900s | Yes (env) | DHAN_WS_429_COOLDOWN_MAX_SECONDS |
| **MarketFeedConnectionAdmission** | Penalty window | 3600s | Yes (env) | DHAN_WS_429_PENALTY_WINDOW_SECONDS |

### Message Receive Timeouts

| Component | Timeout Type | Value | Configurable | Notes |
|-----------|--------------|-------|--------------|-------|
| **PollingMarketFeed** | Poll interval | 2s | Yes | Default interval between batch polls |
| **ResolverRefresher** | Refresh interval | 86400s (24h) | Yes | Default daily refresh |

### Greenfield Gaps

**CRITICAL:**
- ❌ No heartbeat timeout in greenfield (archive has 30s watchdog)
- ❌ No ping timeout enforcement (relies on library default)
- ❌ No connection timeout configuration
- ❌ No message freshness monitoring

**MODERATE:**
- ⚠️ Reconnect backoff starts at 5s (archive starts at 1s)
- ⚠️ Max backoff 60s (archive max 30s)
- ⚠️ No max reconnect attempts (archive has 50)
- ⚠️ No cooldown after max attempts (archive has 300s)

---

## 2. Exception Hierarchy

### Archive Exception Hierarchy

```
Exception
├── InstrumentNotFoundError
│   └── Raised by SymbolResolver.resolve() when instrument not found
├── WebSocket errors (from websocket-client library)
│   ├── WebSocketException
│   ├── WebSocketConnectionClosedException
│   └── WebSocketTimeoutException
├── Dhan SDK errors (from dhanhq library)
│   ├── MarketFeed errors
│   └── OrderUpdate errors
├── fcntl errors (from file locking)
│   ├── BlockingIOError (lock held by another process)
│   └── OSError (lock file system error)
└── Generic exceptions
    ├── json.JSONDecodeError (message parsing)
    ├── struct.error (binary parsing)
    ├── KeyError (dict access)
    ├── ValueError (type conversion)
    └── Exception (catch-all for callback errors)
```

### Greenfield Exception Handling

**BaseWebSocketStreaming:**
```python
def _on_message(self, ws, message: str) -> None:
    try:
        data = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        return  # Silently ignore parse errors
    tick = self._parse_tick(data)
    if tick and self._on_tick:
        self._on_tick(tick)
```

**DhanOrderStream:**
```python
def _on_message(self, ws, message: str | bytes) -> None:
    try:
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        data = json.loads(message)
        order = self._parse_order_update(data)
        if order and self.on_order_update:
            self.on_order_update(order)
    except Exception as e:
        logger.warning(f"Failed to parse order stream message: {e}", exc_info=True)
```

**DhanDepth20Stream / DhanDepth200Stream:**
```python
def _on_message(self, ws, message: str | bytes) -> None:
    try:
        if isinstance(message, bytes):
            import struct
            if len(message) >= 12:
                header = struct.unpack("<HBBII", message[:12])
                data = {"raw_header": header, "is_binary": True}
                if self.on_depth_update:
                    self.on_depth_update(data)
        else:
            data = json.loads(message)
            if self.on_depth_update:
                self.on_depth_update(data)
    except Exception as e:
        logger.warning(f"Failed to parse depth stream message: {e}")
```

### Exception Handling Gaps

**CRITICAL:**
- ❌ No custom exception hierarchy in greenfield
- ❌ Silent exception swallowing in `_on_message` (no structured error reporting)
- ❌ No distinction between transient and permanent failures
- ❌ No exception context (correlation IDs, timestamps)
- ❌ No retry logic for transient failures

**MODERATE:**
- ⚠️ No InstrumentNotFoundError equivalent in greenfield
- ⚠️ No admission control exceptions (no fcntl)
- ⚠️ No rate limit exceptions (no 429 handling)

---

## 3. Race Conditions Inventory

### Race Condition #1: Concurrent Subscribe/Unsubscribe

**Scenario:**
```python
# Thread 1
streaming.subscribe("RELIANCE", "NSE")

# Thread 2 (simultaneously)
streaming.unsubscribe("RELIANCE", "NSE")
```

**Archive Mitigation:**
- ✅ `_subscriptions` set protected by `_lock`
- ✅ Callback lists protected by `_callback_lock` (mixin)
- ✅ Snapshot callbacks before iteration

**Greenfield Status:**
- ✅ `_subscriptions` set protected by `_lock` in BaseWebSocketStreaming
- ⚠️ No callback lock (single callback, not list)
- ❌ No snapshot mechanism

**Risk Level:** LOW (single callback in greenfield)

---

### Race Condition #2: Reconnect During Subscription

**Scenario:**
```python
# Thread 1: User subscribes
streaming.subscribe("RELIANCE", "NSE")

# Thread 2: WebSocket reconnects
# _on_open() fires, re-subscribes all instruments
# But Thread 1 is still in middle of subscribe()
```

**Archive Mitigation:**
- ✅ `_subscriptions` set updated under lock
- ✅ `_on_open()` snapshots subscriptions under lock
- ✅ Send subscribe message outside lock

**Greenfield Status:**
- ✅ `_subscriptions` set updated under lock
- ✅ `_on_open()` snapshots subscriptions under lock
- ✅ Send subscribe message outside lock

**Risk Level:** LOW (properly mitigated)

---

### Race Condition #3: Token Update During Connection

**Scenario:**
```python
# Thread 1: Token refresh
streaming.update_token("new_token")

# Thread 2: WebSocket reconnecting
# _get_ws_headers() called with old token
```

**Archive Mitigation:**
- ✅ `_DhanContext` stores both static token and token_fn
- ✅ `update_token()` updates context under lock
- ✅ OrderUpdate SDK object updated under lock

**Greenfield Status:**
- ⚠️ `update_token()` just assigns to `_access_token` (no lock)
- ⚠️ `_get_ws_headers()` reads `_access_token` (no lock)
- ❌ No atomic token swap

**Risk Level:** MEDIUM (token update may be partially visible during reconnect)

---

### Race Condition #4: Concurrent Service Creation

**Scenario:**
```python
# Thread 1
feed1 = connection_manager.get_market_feed()

# Thread 2 (simultaneously)
feed2 = connection_manager.get_market_feed()

# Both threads see _market_feed is None, both create new instances
```

**Archive Mitigation:**
- ✅ WebSocketConnectionManager uses `_lock` (RLock)
- ✅ Singleton check and creation under lock
- ✅ ConnectionLifecycle factory methods require caller to hold lock

**Greenfield Status:**
- ❌ No ConnectionLifecycle equivalent
- ❌ No singleton enforcement
- ❌ Caller must manage lifecycle

**Risk Level:** HIGH (if caller doesn't manage properly)

---

### Race Condition #5: Resolver Refresh During Resolve

**Scenario:**
```python
# Thread 1: User resolves instrument
instrument = resolver.resolve("RELIANCE", "NSE")

# Thread 2: ResolverRefresher atomic swap
# resolver._by_symbol = new_by_symbol
```

**Archive Mitigation:**
- ✅ `load_from_rows()` builds new dicts in memory
- ✅ Atomic swap under `_lock` (RLock)
- ✅ Readers see old or new, never half-loaded

**Greenfield Status:**
- ❌ No ResolverRefresher in greenfield
- ❌ No atomic swap mechanism

**Risk Level:** N/A (not implemented in greenfield)

---

### Race Condition #6: Heartbeat Watchdog During Reconnect

**Scenario:**
```python
# Thread 1: Watchdog detects timeout
# Sets _stop_event

# Thread 2: Reconnect loop
# Checks _stop_event.is_set() → True
# Exits loop

# Thread 3: User calls stop()
# Sets _stop_event (already set)
# Joins thread
```

**Archive Mitigation:**
- ✅ `_stop_event` is thread-safe (threading.Event)
- ✅ Watchdog sets event once, then exits
- ✅ Reconnect loop checks event before each attempt
- ✅ `stop()` joins thread with timeout

**Greenfield Status:**
- ❌ No heartbeat watchdog in greenfield
- ⚠️ Reconnect loop checks `_running` flag (not thread-safe Event)

**Risk Level:** LOW (greenfield doesn't have watchdog)

---

## 4. Recovery Paths

### Recovery Path #1: WebSocket Disconnect

**Trigger:** WebSocket connection closed (network error, server restart, etc.)

**Archive Recovery:**
```
1. _on_close() callback fires
2. Set _is_connected = False
3. Log warning
4. Enter reconnect loop
5. Backoff: 1.0s → 2.0s → 4.0s → ... → 30.0s
6. Attempt reconnect
7. On success: Reset backoff, re-subscribe all instruments
8. On failure: Increment reconnect_count, emit metric, retry
9. After 50 attempts: Cooldown 300s, reset counter
```

**Greenfield Recovery:**
```
1. _on_close() callback fires
2. Log disconnect
3. Call on_disconnect callback
4. Exit run_forever()
5. Check _running flag
6. Sleep for backoff delay
7. Create new WebSocketApp
8. run_forever() again
9. _on_open() fires, re-subscribe all instruments
```

**Gaps:**
- ❌ No max reconnect attempts
- ❌ No cooldown after max attempts
- ❌ No heartbeat watchdog to detect ghost connections
- ❌ No reconnect metric emission
- ❌ No exponential backoff jitter

---

### Recovery Path #2: Message Parse Failure

**Trigger:** Invalid JSON or binary data received

**Archive Recovery:**
```
1. Exception caught in message handler
2. Log warning with error details
3. Continue recv loop (don't disconnect)
4. Next message processed normally
```

**Greenfield Recovery:**
```
1. Exception caught in _on_message()
2. Log warning with error details
3. Return from handler
4. Next message processed normally
```

**Gaps:**
- ⚠️ No structured error reporting (no correlation ID, timestamp)
- ⚠️ No parse error metric
- ⚠️ No distinction between transient and permanent parse failures

---

### Recovery Path #3: Subscription Rejection

**Trigger:** Dhan rejects subscription (invalid instrument, rate limit, etc.)

**Archive Recovery:**
```
1. SDK fires error callback
2. Log error with instrument details
3. Continue recv loop
4. Instrument remains in _subscriptions set
5. On reconnect, re-subscribe (may fail again)
```

**Greenfield Recovery:**
```
1. No explicit rejection handling
2. Subscribe message sent, no response expected
3. If server rejects, no error propagated to client
4. Instrument remains in _subscriptions set
5. On reconnect, re-subscribe (may fail again)
```

**Gaps:**
- ❌ No subscription acknowledgment mechanism
- ❌ No rejection error propagation
- ❌ No retry logic for failed subscriptions
- ❌ No way to detect stale subscriptions

---

### Recovery Path #4: Resolver Stale

**Trigger:** Instrument not found in resolver (new listing, expiry, etc.)

**Archive Recovery:**
```
1. SymbolResolver.resolve() raises InstrumentNotFoundError
2. Caller handles exception (retry, skip, alert)
3. ResolverRefresher runs daily (or on-demand)
4. Atomic swap of resolver dictionaries
5. Next resolve() uses fresh data
```

**Greenfield Recovery:**
```
1. No resolver in greenfield
2. Caller must manage instrument cache
3. No automatic refresh mechanism
```

**Gaps:**
- ❌ No resolver in greenfield
- ❌ No automatic refresh
- ❌ No stale data detection
- ❌ No atomic swap mechanism

---

### Recovery Path #5: Token Expiry

**Trigger:** Access token expires (typically 24h)

**Archive Recovery:**
```
1. WebSocket connection fails with auth error
2. Reconnect loop detects 401/403
3. Token refresh scheduler runs (before expiry)
4. update_token() called on all registered receivers
5. Context updated with new token
6. Reconnect with new token succeeds
```

**Greenfield Recovery:**
```
1. WebSocket connection fails with auth error
2. Reconnect loop retries
3. Caller must manually call update_token()
4. _access_token updated
5. Next reconnect uses new token
```

**Gaps:**
- ❌ No automatic token refresh in greenfield
- ❌ No token expiry detection
- ❌ No registered receivers mechanism
- ❌ Caller must manage token lifecycle

---

## 5. Backoff Strategies

### Archive Backoff Strategy

**Algorithm:** Exponential backoff with hard cap

```python
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 30.0

def _backoff_sleep(self, current: float) -> float:
    wait = min(current, self.MAX_BACKOFF)
    self._stop_event.wait(timeout=wait)  # Interruptible
    return min(current * 2, self.MAX_BACKOFF)
```

**Sequence:** 1.0s → 2.0s → 4.0s → 8.0s → 16.0s → 30.0s → 30.0s → ...

**Properties:**
- ✅ Deterministic (no jitter)
- ✅ Interruptible via `_stop_event`
- ✅ Resets on clean disconnect
- ✅ Resets on successful reconnect
- ✅ Hard cap at 30s

**Max Reconnect Attempts:**
```python
max_reconnect_attempts = int(os.getenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50"))
cooldown_seconds = float(os.getenv("DHAN_RECONNECT_COOLDOWN_SECONDS", "300"))

if self._reconnect_count >= max_reconnect_attempts:
    logger.critical("max_reconnect_attempts_exceeded")
    self._reconnect_count = 0
    self._stop_event.wait(timeout=cooldown_seconds)  # 300s cooldown
```

---

### Greenfield Backoff Strategy

**Algorithm:** Exponential backoff with hard cap

```python
def _run(self) -> None:
    delay = self._reconnect_delay  # Default 5.0s
    while self._running:
        self._ws = websocket.WebSocketApp(...)
        self._ws.run_forever(ping_interval=30, ping_timeout=10)
        if self._running:
            time.sleep(delay)  # NOT interruptible
            delay = min(delay * 2, self._max_reconnect_delay)  # Default 60.0s
```

**Sequence:** 5.0s → 10.0s → 20.0s → 40.0s → 60.0s → 60.0s → ...

**Properties:**
- ✅ Deterministic (no jitter)
- ❌ NOT interruptible (uses `time.sleep`)
- ❌ No reset on clean disconnect
- ❌ No reset on successful reconnect
- ✅ Hard cap at 60s
- ❌ No max reconnect attempts
- ❌ No cooldown after max attempts

---

### Backoff Comparison

| Property | Archive | Greenfield |
|----------|---------|------------|
| Initial delay | 1.0s | 5.0s |
| Max delay | 30.0s | 60.0s |
| Multiplier | 2x | 2x |
| Jitter | None | None |
| Interruptible | Yes | No |
| Reset on disconnect | Yes | No |
| Reset on reconnect | Yes | No |
| Max attempts | 50 (configurable) | Unlimited |
| Cooldown after max | 300s | None |

---

### Recommended Improvements

**CRITICAL:**
1. Add jitter to prevent thundering herd
   ```python
   import random
   delay = min(delay * 2, max_delay)
   jitter = random.uniform(0, delay * 0.1)  # 10% jitter
   time.sleep(delay + jitter)
   ```

2. Make backoff interruptible
   ```python
   # Instead of time.sleep(delay)
   stop_event.wait(timeout=delay)
   ```

3. Reset backoff on successful reconnect
   ```python
   def _on_open(self, ws):
       self._backoff_delay = self._initial_backoff  # Reset
   ```

4. Add max reconnect attempts
   ```python
   if self._reconnect_count >= max_attempts:
       logger.critical("max_reconnect_attempts_exceeded")
       # Cooldown or give up
   ```

---

## 6. Connection Pool Exhaustion Scenarios

### Scenario #1: Depth200 Connection Proliferation

**Archive Context:**
- Dhan depth-200 API supports only 1 instrument per connection
- Depth200ConnectionPool manages multiple connections
- Dhan rate limit: 5 concurrent WebSocket connections per account

**Exhaustion Path:**
```
1. User subscribes to 10 instruments for depth-200
2. ConnectionPool creates 10 DhanDepth200Feed instances
3. Each instance opens 1 WebSocket connection
4. Total: 10 connections (exceeds 5 connection limit)
5. Dhan rejects connections with 429
6. Admission control triggers cooldown
7. Connections enter reconnect loop
8. All connections back off simultaneously
9. Reconnect attempts fail (still over limit)
10. System stuck in reconnect loop
```

**Archive Mitigation:**
- ✅ Depth200ConnectionPool tracks all connections
- ✅ Admission control enforces rate limits
- ✅ Exponential cooldown on 429
- ⚠️ No connection limit enforcement in pool

**Greenfield Status:**
- ❌ No connection pool in greenfield
- ❌ No rate limit enforcement
- ❌ Caller must manage connections
- ❌ Easy to accidentally exceed limits

**Risk Level:** HIGH

**Recommendation:**
```python
class DhanDepth200Pool:
    MAX_CONNECTIONS = 5  # Dhan limit
    
    def get_stream(self, instrument):
        if len(self._streams) >= self.MAX_CONNECTIONS:
            raise ConnectionPoolExhausted(
                f"Max {self.MAX_CONNECTIONS} depth-200 connections allowed"
            )
        # Create or return existing stream
```

---

### Scenario #2: Multiple Market Feed Instances

**Archive Context:**
- ConnectionLifecycle enforces singleton for market feed
- WebSocketConnectionManager enforces singleton

**Exhaustion Path:**
```
1. Bug in code creates multiple DhanMarketFeed instances
2. Each instance opens 1 WebSocket connection
3. Total: N connections (exceeds 5 connection limit)
4. Dhan rejects connections with 429
5. System stuck in reconnect loop
```

**Archive Mitigation:**
- ✅ Singleton enforcement in ConnectionLifecycle
- ✅ Singleton enforcement in WebSocketConnectionManager
- ✅ Admission control with fcntl locks

**Greenfield Status:**
- ❌ No singleton enforcement
- ❌ Caller must manage lifecycle
- ❌ Easy to accidentally create multiple instances

**Risk Level:** MEDIUM

**Recommendation:**
- Document singleton requirement
- Provide factory function with singleton enforcement
- Add connection count monitoring

---

### Scenario #3: Reconnect Storm

**Trigger:** Network outage causes all connections to drop simultaneously

**Exhaustion Path:**
```
1. Network outage drops all 5 WebSocket connections
2. All connections enter reconnect loop
3. All connections back off: 1s → 2s → 4s → ...
4. Network recovers
5. All connections attempt reconnect simultaneously
6. Dhan rate limits (5 connections in quick succession)
7. Some connections get 429
8. Connections enter cooldown
9. Cooldown expires, retry simultaneously
10. Cycle repeats
```

**Archive Mitigation:**
- ✅ Exponential backoff (staggered reconnects)
- ⚠️ No jitter (all connections back off identically)
- ✅ Admission control with fcntl locks

**Greenfield Status:**
- ✅ Exponential backoff
- ❌ No jitter
- ❌ No admission control

**Risk Level:** MEDIUM

**Recommendation:**
```python
# Add jitter to stagger reconnects
import random
delay = min(delay * 2, max_delay)
jitter = random.uniform(0, delay * 0.5)  # 50% jitter
time.sleep(delay + jitter)
```

---

## 7. Memory Leak Risks

### Risk #1: Unsubscribed Feeds

**Scenario:**
```python
# User subscribes to instrument
streaming.subscribe("RELIANCE", "NSE")

# User unsubscribes
streaming.unsubscribe("RELIANCE", "NSE")

# But _subscriptions set still holds reference
# WebSocket continues to receive data (if server doesn't honor unsub)
# Callback still registered
```

**Archive Mitigation:**
- ✅ `unsubscribe()` removes from `_subscriptions` set
- ✅ Sends unsubscribe message to server
- ⚠️ Callbacks not automatically removed

**Greenfield Status:**
- ✅ `unsubscribe()` removes from `_subscriptions` set
- ✅ Sends unsubscribe message to server
- ⚠️ Callbacks not automatically removed

**Risk Level:** LOW (server should honor unsubscribe)

**Recommendation:**
- Document that callbacks must be manually removed
- Add `clear_callbacks()` method

---

### Risk #2: Dead References in Callback Lists

**Scenario:**
```python
# User registers callback
def my_callback(tick):
    process(tick)

streaming.on_tick = my_callback

# User deletes callback function
del my_callback

# But streaming still holds reference
# Callback never garbage collected
```

**Archive Mitigation:**
- ✅ Callback lists use weak references (via mixin)
- ✅ `_unregister_callback()` removes callback

**Greenfield Status:**
- ⚠️ Single callback (not list)
- ⚠️ Strong reference (not weak)
- ❌ No unregister mechanism for on_tick

**Risk Level:** LOW (single callback, easy to manage)

**Recommendation:**
- Document that callback must be set to None to release
- Add `clear_callbacks()` method

---

### Risk #3: TTLCache in OrderStream

**Scenario:**
```python
# Archive DhanOrderStream uses TTLCache
self._last_cumulative_filled = TTLCache(maxsize=10000, ttl=3600)

# Cache grows to 10000 entries
# After 1 hour, entries expire
# But if no new entries, old entries remain
```

**Archive Mitigation:**
- ✅ TTLCache has maxsize (10000)
- ✅ TTLCache has ttl (3600s = 1 hour)
- ✅ Entries automatically expire

**Greenfield Status:**
- ❌ No TTLCache in greenfield
- ❌ No filled quantity tracking

**Risk Level:** N/A (not implemented in greenfield)

---

### Risk #4: Resolver Dictionary Growth

**Scenario:**
```python
# Resolver loads 50000 instruments
self._by_symbol = {(symbol, exchange): instrument for ...}
self._by_security_id = {sid: instrument for ...}
self._by_underlying = {(underlying, exchange): [instruments] for ...}

# Resolver refresh builds new dictionaries
# Old dictionaries not garbage collected until swap completes
# During swap, 2x memory usage
```

**Archive Mitigation:**
- ✅ Atomic swap (old dicts replaced, not merged)
- ✅ Old dicts garbage collected after swap
- ⚠️ Temporary 2x memory usage during swap

**Greenfield Status:**
- ❌ No resolver in greenfield

**Risk Level:** N/A (not implemented in greenfield)

---

### Risk #5: WebSocket Thread Leak

**Scenario:**
```python
# User calls start() multiple times
streaming.start()
streaming.start()
streaming.start()

# Each call creates new thread
# Old threads not joined
# Thread leak
```

**Archive Mitigation:**
- ✅ `start()` checks if thread already alive
- ✅ Idempotent (no-op if already running)

**Greenfield Status:**
- ✅ `start()` checks `_running` flag
- ✅ Idempotent (no-op if already running)

**Risk Level:** LOW (properly mitigated)

---

## 8. Secret Exposure Risks

### Risk #1: Access Token in Logs

**Scenario:**
```python
# WebSocket connection fails
logger.warning("ws_error", extra={"error": str(error)})

# Error message contains access token
# Token logged in plaintext
```

**Archive Mitigation:**
- ✅ No token in error messages
- ✅ Token passed via headers (not logged)
- ⚠️ `_DhanContext.get_access_token()` logs on token_fn failure
  ```python
  logger.error("dhan_ws_access_token_fn_failed", extra={
      "exception_type": type(exc).__name__,
      "exception_message": str(exc),  # May contain token
  })
  ```

**Greenfield Status:**
- ⚠️ No explicit token logging
- ⚠️ Error messages may contain token (depends on websocket-client library)

**Risk Level:** MEDIUM

**Recommendation:**
- Never log token values
- Mask token in error messages
- Use structured logging with token field excluded

---

### Risk #2: Access Token in Exception Tracebacks

**Scenario:**
```python
# Token refresh fails
def get_token():
    token = fetch_token_from_vault()  # Raises exception
    return token

# Exception traceback contains token
logger.exception("token_refresh_failed")
```

**Archive Mitigation:**
- ✅ Token not stored in exception context
- ⚠️ Token may be in local variables (visible in traceback)

**Greenfield Status:**
- ⚠️ Token stored in `_access_token` attribute
- ⚠️ May be visible in traceback

**Risk Level:** LOW (tracebacks not typically logged in production)

**Recommendation:**
- Use `__slots__` to prevent token in `__dict__`
- Clear token on shutdown
- Use secret management library

---

### Risk #3: Access Token in WebSocket URL

**Scenario:**
```python
# WebSocket URL contains token
ws_url = f"wss://api.dhan.co/ws?token={access_token}"

# URL logged on connection
logger.info("ws_connecting", extra={"url": ws_url})
```

**Archive Mitigation:**
- ✅ Token passed via headers (not URL)
- ✅ URL logged without token

**Greenfield Status:**
- ✅ Token passed via headers (not URL)
- ✅ URL logged without token

**Risk Level:** LOW (properly mitigated)

---

### Risk #4: Client ID in Lock Files

**Scenario:**
```python
# Lock file created
runtime/dhan-market-feed-{client_id}.lock

# Client ID is sensitive (identifies account)
# File visible to other users on system
```

**Archive Mitigation:**
- ✅ Client ID sanitized (alphanumeric only)
- ⚠️ Lock file contains client ID in filename
- ⚠️ File permissions not explicitly set

**Greenfield Status:**
- ❌ No lock files (no admission control)

**Risk Level:** LOW (client ID not highly sensitive)

**Recommendation:**
- Set file permissions to 0600 (owner only)
- Use hash of client ID instead of plaintext

---

## 9. Greenfield Gaps Summary

### CRITICAL GAPS

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| ❌ No heartbeat watchdog | Ghost connections not detected | Add 30s heartbeat timeout |
| ❌ No custom exception hierarchy | No structured error handling | Define MarketDataException hierarchy |
| ❌ No max reconnect attempts | Infinite reconnect loop | Add max attempts + cooldown |
| ❌ No connection pool for depth-200 | Easy to exceed rate limits | Implement Depth200Pool with limit |
| ❌ No resolver refresher | Stale instrument data | Implement periodic refresh |
| ❌ No admission control | No rate limit enforcement | Implement fcntl locks or equivalent |

### MODERATE GAPS

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| ⚠️ No backoff jitter | Thundering herd on reconnect | Add 10-50% jitter |
| ⚠️ Backoff not interruptible | Slow shutdown | Use Event.wait() instead of sleep |
| ⚠️ No backoff reset on reconnect | Suboptimal recovery | Reset to initial on success |
| ⚠️ No token auto-refresh | Token expiry causes disconnect | Implement token refresh scheduler |
| ⚠️ No subscription acknowledgment | No way to detect failed subs | Implement ack mechanism |
| ⚠️ No parse error metrics | No visibility into data quality | Add parse error counter |

### LOW GAPS

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| ⚠️ No callback unregister | Callback leak | Add clear_callbacks() method |
| ⚠️ No connection count monitoring | No visibility into pool usage | Add connection stats |
| ⚠️ No structured logging | Hard to debug | Add correlation IDs, timestamps |
| ⚠️ No health reporting | No visibility into service state | Implement health() method |

---

## 10. Recommendations

### Priority 1: Critical Fixes

1. **Add heartbeat watchdog**
   - Detect ghost connections
   - Trigger reconnect on silence > 30s

2. **Add max reconnect attempts**
   - Prevent infinite reconnect loop
   - Cooldown after max attempts (300s)

3. **Implement connection pool for depth-200**
   - Enforce 5 connection limit
   - Raise exception on exhaustion

4. **Add backoff jitter**
   - Prevent thundering herd
   - Use 10-50% random jitter

### Priority 2: Moderate Improvements

5. **Make backoff interruptible**
   - Use Event.wait() instead of time.sleep()
   - Allow fast shutdown

6. **Reset backoff on reconnect**
   - Start at initial delay after success
   - Faster recovery

7. **Implement token auto-refresh**
   - Refresh before expiry
   - Update all connections

8. **Add custom exception hierarchy**
   - MarketDataException
   ├── ConnectionException
   ├── SubscriptionException
   ├── ParseException
   └── RateLimitException

### Priority 3: Low Priority

9. **Add structured logging**
   - Correlation IDs
   - Timestamps
   - Context fields

10. **Implement health reporting**
    - health() method for each service
    - Report connection state, message count, last message age

11. **Add connection monitoring**
    - Track connection count
    - Expose stats via API

---

**End of Failure Analysis Document**
