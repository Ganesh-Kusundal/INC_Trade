# Phase 3 Rate Limiting — State Machine

## 1. Circuit Breaker State Machine

### State Diagram

```
                    failure_count >= threshold
    ┌─────────┐    ─────────────────────────►  ┌────────┐
    │ CLOSED  │                                 │  OPEN  │
    └─────────┘                                 └────┬───┘
        ▲                                            │
        │                                            │ time >= recovery_timeout
        │   success_count >= success_threshold       │
        │  ┌───────────┐                             ▼
        └──┤ HALF_OPEN │◄────────────────────  ┌───────────┐
           └───────────┘                       │  recovery  │
                      ▲                        │  elapsed?  │
                      │                        └───────────┘
                      │ failure in HALF_OPEN
                      │──────────────────────────────► OPEN
                      │         (immediate re-trip)
```

### Transition Table

| From | Event | To | Guard |
|------|-------|----|-------|
| CLOSED | `record_failure()` | OPEN | `_failure_count >= failure_threshold` |
| CLOSED | `record_success()` | CLOSED | Resets `_failure_count = 0` |
| OPEN | `state` / `call()` accessed | HALF_OPEN | `time.monotonic() - _last_failure_time >= recovery_timeout` |
| OPEN | `state` / `call()` accessed | OPEN (unchanged) | Recovery timeout not yet elapsed |
| HALF_OPEN | `record_success()` | CLOSED | `_success_count >= success_threshold` |
| HALF_OPEN | `record_failure()` | OPEN | Any failure; immediate re-trip |
| Any | `reset()` | CLOSED | Manual reset; clears all counters |

### Greenfield Thresholds (hardcoded in `BaseResilientHttpClient.__init__`)

| Category | `failure_threshold` | `recovery_timeout` (s) | `success_threshold` | Source |
|----------|--------------------:|-----------------------:|--------------------:|--------|
| read     | 5                   | 30.0                   | 1                   | `http_client.py:56` |
| write    | 3                   | 60.0                   | 1                   | `http_client.py:57` |
| admin    | 5                   | 30.0                   | 1                   | `http_client.py:58` |

### Archive Thresholds (`DhanCircuitBreakerConfig`)

| Category | `failure_threshold` | `recovery_timeout` (ms) | `success_threshold` | Source |
|----------|--------------------:|------------------------:|--------------------:|--------|
| orders (write)  | 3           | 30,000                  | 3                   | `config.py:147,149,150` |
| market_data (read) | 5        | 30,000                  | 3                   | `config.py:148,149,150` |
| portfolio       | 5           | 30,000                  | 3                   | `config.py:148,149,150` |
| admin           | 5           | 30,000                  | 3                   | `config.py:148,149,150` |

### Parity Gaps

| Parameter | Archive | Greenfield | Delta |
|-----------|---------|------------|-------|
| Write `success_threshold` | 3 | 1 | **2 fewer probes needed** |
| Read `success_threshold` | 3 | 1 | **2 fewer probes needed** |
| Write `recovery_timeout` | 30s | 60s | **Greenfield 2× longer** |
| Category count | 4 (orders/market_data/portfolio/admin) | 3 (read/write/admin) | Portfolio merged into admin |

### Thread Safety

- **Greenfield**: `threading.Lock`; all state mutations inside `with self._lock`.
- **Archive**: `threading.RLock`; all state mutations inside `with self._lock`.
- **Difference**: Archive uses `RLock` (reentrant), greenfield uses `Lock` (non-reentrant). No practical impact since no reentrant acquisition paths exist.

---

## 2. Rate Limiter Token Bucket State

### State Diagram

```
    ┌─────────────────────────────────────────────────────┐
    │                  Token Bucket                        │
    │                                                      │
    │  tokens ──► [0 ............... capacity]             │
    │               ▲                     │                │
    │               │ refill              │ acquire(n)     │
    │               │ rate × elapsed      │ tokens -= n    │
    │               │ (capped at capacity)│                │
    └───────────────┴─────────────────────┴────────────────┘

    acquire(tokens=1, timeout=T):
    ┌──────────┐   tokens >= 1    ┌────────────┐
    │  WAITING │────────────────►│  ACQUIRED  │  return True
    └────┬─────┘                  └────────────┘
         │
         │ tokens < 1
         ▼
    ┌──────────┐   timeout elapsed   ┌──────────┐
    │ SLEEPING │────────────────────►│ EXPIRED  │  return False
    └──────────┘                     └──────────┘
         │
         │ condition.wait(needed/rate)
         └──► loop back to WAITING
```

### Greenfield Configuration (`BaseResilientHttpClient.__init__`)

| Endpoint Prefix | `rate_per_second` | `capacity` | Effective Rate | Source |
|-----------------|-------------------:|-----------:|----------------|--------|
| `/marketfeed/quote` | 1.0 | max(1,1)=1 | 1 req/s | `config.py:29` |
| `/marketfeed/ltp` | 0.15 | max(0,1)=1 | ~6.7 s interval | `config.py:30` |
| `/marketfeed/ohlc` | 0.15 | max(0,1)=1 | ~6.7 s interval | `config.py:31` |
| `/optionchain` | 0.35 | max(0,1)=1 | ~2.9 s interval | `config.py:32` |
| `/charts/` | 0.15 | max(0,1)=1 | ~6.7 s interval | `config.py:33` |
| `/orders` | 0.04 | max(0,1)=1 | 25 s interval | `config.py:34` |

**CRITICAL BUG — Rate Limit Inversion**: The `RATE_LIMITS` dict values are **minimum intervals in seconds** (e.g., `0.04` means "at most once per 0.04s = 25 req/s"). But `BaseResilientHttpClient.__init__` passes them as `rate_per_second` to `TokenBucketRateLimiter`. This means:
- `/orders` with value `0.04` creates a bucket that refills at 0.04 tokens/sec → **one request every 25 seconds** instead of 25 requests per second.
- `/marketfeed/quote` with value `1.0` creates 1 token/sec → correct by coincidence.

### Archive Configuration (`MultiBucketRateLimiter` via `DhanRateLimiterFactory`)

Archive uses the same interval values but routes them through `MultiBucketRateLimiter` with 4 buckets (`orders`, `market_data`, `portfolio`, `admin`). The `_throttle()` method applies intervals as **sleep durations** (correct semantic), while the token bucket is a separate acquisition gate.

### Refill Algorithm

```
_refill():
    now = time.monotonic()
    elapsed = now - _last_refill
    _tokens = min(_capacity, _tokens + elapsed * _rate)
    _last_refill = now
```

- **Greenfield**: Uses `threading.Condition(threading.Lock())`; `wait()` releases lock during sleep.
- **Archive infrastructure**: Uses `threading.Lock`; spin-loops with `time.sleep(0.01)`.

---

## 3. Retry State Machine

### State Diagram

```
    ┌───────────┐
    │ ATTEMPT 0 │◄──── initial call
    └─────┬─────┘
          │
          ├── success ──────────────────────────► RETURN result
          │
          └── retryable exception
                │
                ▼
          ┌─────────────────┐
          │ attempt < max?  │
          └────┬────────┬───┘
           YES │        │ NO
               ▼        └───────────────────────► RAISE last_exception
          ┌───────────┐
          │ COMPUTE   │
          │  DELAY    │
          │ delay =   │
          │ base×2^a  │
          │ capped    │
          │ + jitter  │
          └─────┬─────┘
                │ sleep(delay/1000)
                ▼
          ┌───────────┐
          │ ATTEMPT   │
          │  n + 1    │──────► loop back
          └───────────┘
```

### Greenfield RetryPolicy Defaults

| Parameter | Value | Source |
|-----------|-------|--------|
| `max_retries` | 3 | `http_client.py:62` |
| `base_delay_ms` | 500 | `http_client.py:63` |
| `max_delay_ms` | 5000 | `http_client.py:64` |
| `retryable_exceptions` | `(RequestException, BrokerServerError)` | `http_client.py:65-68` |

### Backoff Sequence

| Attempt | Base Delay | Jitter Range | Total Range |
|---------|-----------|--------------|-------------|
| 0 (1st retry) | 500 × 2⁰ = 500ms | 0–125ms | 500–625ms |
| 1 (2nd retry) | 500 × 2¹ = 1000ms | 0–250ms | 1000–1250ms |
| 2 (3rd retry) | 500 × 2² = 2000ms | 0–500ms | 2000–2500ms |
| Capped | min(delay, 5000ms) | 0–1250ms | 5000–6250ms |

**Formula**: `delay = min(base_delay_ms × 2^attempt, max_delay_ms) + randint(0, delay//4)`

### Archive Retry

| Parameter | Value | Source |
|-----------|-------|--------|
| `max_retries` | 3 (configurable via `DhanRetryConfig`) | `config.py:68` |
| `base_delay_ms` | 500 | `config.py:69` |
| `max_delay_ms` | 5000 | `config.py:70` |
| Jitter | None (deterministic) | `http_client.py:548-554` |

### Exception Filtering

| Exception | Greenfield Retry? | Archive Retry? |
|-----------|:-:|:-:|
| `requests.RequestException` (network) | Yes | Yes |
| `BrokerServerError` (5xx) | Yes | Yes |
| `AuthenticationError` (401) | No (ignored by CB) | No (handled separately) |
| `RateLimitError` (429) | No (ignored by CB) | Yes (with backoff) |
| `BrokerError` (4xx) | No | No |

**CRITICAL**: Greenfield raises `RateLimitError` immediately on HTTP 429 — it is in `ignored_exceptions` for the CB and NOT in `retryable_exceptions` for the retry policy. Archive retries 429s with backoff.

---

## 4. HTTP Request Lifecycle State Machine

### Full Pipeline

```
    ┌──────────┐
    │  CALLER  │  client.get/post/put/delete(endpoint, ...)
    └────┬─────┘
         ▼
    ┌──────────────────┐
    │ 1. CATEGORIZE    │  endpoint → read | write | admin
    │    (prefix scan) │  READ_PREFIXES → WRITE_PREFIXES → "admin"
    └────┬─────────────┘
         ▼
    ┌──────────────────┐
    │ 2. CB SELECT     │  category → circuit_breakers[category]
    │                  │  fallback → circuit_breakers["admin"]
    └────┬─────────────┘
         ▼
    ┌──────────────────┐
    │ 3. RATE LIMIT    │  prefix match → TokenBucketRateLimiter.acquire(1, timeout=5s)
    │    (token bucket)│  no match → skip
    └────┬─────────────┘
         ▼
    ┌──────────────────────────────────────────────────┐
    │ 4. cb.call( retry.call( _do_request ) )          │
    │                                                  │
    │    ┌─────────────────────────────────────┐       │
    │    │ CB: state == OPEN?                  │       │
    │    │   YES → raise CircuitOpenError      │       │
    │    │   NO  → check recovery timeout      │       │
    │    │         OPEN + elapsed >= timeout   │       │
    │    │           → transition HALF_OPEN    │       │
    │    └────┬────────────────────────────────┘       │
    │         ▼                                        │
    │    ┌─────────────────────────────────────┐       │
    │    │ RETRY LOOP (max 3 retries)          │       │
    │    │                                     │       │
    │    │  _do_request():                     │       │
    │    │    url = _build_url(endpoint)       │       │
    │    │    resp = session.request(...)      │       │
    │    │    return _handle_response(resp)    │       │
    │    │                                     │       │
    │    │  On retryable exception:            │       │
    │    │    compute backoff → sleep → retry  │       │
    │    │  On non-retryable: raise immediately│       │
    │    └────┬────────────────────────────────┘       │
    │         ▼                                        │
    │    CB records success/failure based on outcome   │
    └────┬─────────────────────────────────────────────┘
         ▼
    ┌──────────────────────────────────────────────────┐
    │ 5. RESPONSE HANDLING (_handle_response)          │
    │                                                  │
    │    2xx → parse JSON → check status=="failure"    │
    │         → success: return data                   │
    │         → failure: raise BrokerError             │
    │                                                  │
    │    401 → _try_refresh_token()                    │
    │         → success: raise TokenRefreshSignal      │
    │         → failure: raise AuthenticationError     │
    │                                                  │
    │    429 → parse Retry-After                       │
    │         → update adaptive intervals              │
    │         → raise RateLimitError                   │
    │                                                  │
    │    5xx → raise BrokerServerError                 │
    │         → CB records failure                     │
    │         → RetryPolicy retries                    │
    │                                                  │
    │    4xx → check DH-906/DH-808 in errorCode       │
    │         → token error? → refresh or raise        │
    │         → else: raise BrokerError                │
    └──────────────────────────────────────────────────┘
         │
         ▼
    ┌──────────────────────────────────────────────────┐
    │ 6. TOKEN REFRESH SIGNAL HANDLING                 │
    │                                                  │
    │    TokenRefreshSignal caught → ONE extra pass:   │
    │      cb.call( retry.call( _do_request ) )        │
    │    Second failure → wraps in BrokerError         │
    └──────────────────────────────────────────────────┘
```

### Failure Paths Summary

| HTTP Status | Exception Raised | CB Effect | Retry Effect | Token Refresh |
|-------------|-----------------|-----------|--------------|---------------|
| 2xx (status=success) | None | `record_success()` | Returns result | No |
| 2xx (status=failure) | `BrokerError` | None (not a server error) | Not retryable | No |
| 401 | `AuthenticationError` or `TokenRefreshSignal` | Ignored by CB | Not retryable | Yes (one attempt) |
| 429 | `RateLimitError` | Ignored by CB | Not retryable | No |
| 4xx (DH-906/DH-808) | `AuthenticationError` or `TokenRefreshSignal` | Ignored by CB | Not retryable | Yes (one attempt) |
| 4xx (other) | `BrokerError` | None | Not retryable | No |
| 5xx | `BrokerServerError` | `record_failure()` | Retryable (3×) | No |
| Network error | `RequestException` | None (raised before CB) | Retryable (3×) | No |
| CB open | `CircuitOpenError` | N/A | Not retryable | No |

---

## 5. Token Refresh State Machine

### State Diagram

```
    ┌────────────┐
    │   IDLE     │◄──── last_refresh > cooldown ago
    └──────┬─────┘      AND now > refresh_backoff_until
           │
           │ HTTP 401 or DH-906 received
           ▼
    ┌──────────────┐
    │  COOLDOWN    │──── now - last_refresh < 60s ────► SKIP (return None)
    │   CHECK      │
    └──────┬───────┘
           │ cooldown elapsed
           ▼
    ┌──────────────┐
    │  BACKOFF     │──── now < refresh_backoff_until ──► SKIP (return None)
    │   CHECK      │
    └──────┬───────┘
           │ backoff elapsed
           ▼
    ┌──────────────┐
    │  LOCK        │
    │  ACQUIRE     │──── refresh_lock.acquire(timeout=5s)
    │              │    timeout → SKIP (return None)
    └──────┬───────┘
           │ acquired
           ▼
    ┌──────────────┐
    │   REFRESH    │──── token_refresh_fn()
    │   ATTEMPT    │
    └──┬───┬───┬───┘
       │   │   │
       │   │   └── exception with "once every 2 minutes"
       │   │       └── refresh_backoff_until = now + 130s
       │   │           return None
       │   │
       │   └── returns None (no token)
       │       └── refresh_backoff_until = now + 130s
       │           return None
       │
       └── returns new_token
           └── last_refresh_time = now
               refresh_backoff_until = 0.0
               update_token(new_token)
               raise TokenRefreshSignal
```

### Timing Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Refresh cooldown | 60s | `DhanHttpClient._REFRESH_COOLDOWN_SECONDS` |
| Rate limit backoff | 130s | `DhanHttpClient._RATE_LIMIT_BACKOFF_SECONDS` |
| Lock acquire timeout | 5s | `_try_refresh_token()` |
| Token error codes | `DH-906`, `DH-808` | `_is_token_error()` |

### Failure Cascade

```
Token refresh failure
├── Rate limit ("once every 2 minutes")
│   └── backoff 130s → all 401s/DH-906s fail during backoff
│       └── AuthenticationError raised to caller
├── Returns None
│   └── backoff 130s → same cascade
├── Lock timeout (5s)
│   └── return None → backoff 130s
└── Generic exception
    └── logged, return None → NO backoff set (bug?)
```

**Note**: In the greenfield `_try_refresh_token()`, a generic exception (not rate-limit-related) does NOT set `_refresh_backoff_until`, meaning the next 401 will immediately retry. This differs from the archive which always sets backoff on any failure.
