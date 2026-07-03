# Phase 3 — Greenfield Design Document: Rate Limiting & Resilience
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 3 — Rate Limiting & Resilience  
**Date:** 2026-07-03  
**Status:** Design Review  

---

## 1. Architecture Overview

### 1.1 Archive Architecture (Monolithic)

```
archive/brokers/dhan/
├── http_client.py (558 lines)
│   ├── Token refresh logic
│   ├── Retry loop (explicit attempt counter)
│   ├── Circuit breaker routing
│   ├── Rate limiter integration
│   ├── Adaptive throttle
│   └── Metrics instrumentation (inline)
│
├── resilience/
│   ├── circuit_breaker.py (120 lines) — Dhan-specific factory
│   ├── rate_limiter.py (218 lines) — MultiBucketRateLimiter + metrics
│   ├── retry_executor.py (178 lines) — Per-category retry policies
│   └── websocket_rate_limiter_simple.py (156 lines)
│
├── exceptions.py (144 lines) — Feature-specific exceptions
├── invariants.py (264 lines) — Payload identity assertions
├── metrics.py (43 lines) — Prometheus counters/histograms
└── status_mapper.py (41 lines) — Order status normalization
```

**Characteristics:**
- Single monolithic HTTP client with all resilience logic inline
- Dhan-specific factory classes for CB/RL configuration
- Explicit retry loop with attempt counter
- Metrics woven into request path
- Feature-specific exception hierarchy (SuperOrderError, ForeverOrderError, etc.)

### 1.2 Greenfield Architecture (Layered)

```
brokers/
├── adapters/dhan/
│   ├── http.py (272 lines) — Dhan-specific HTTP client
│   ├── config.py (116 lines) — Rate limits + endpoint prefixes
│   ├── exceptions.py (35 lines) — Dhan-specific exceptions
│   └── metrics.py (66 lines) — Prometheus metrics (decorator only)
│
├── resilience/
│   ├── http_client.py (138 lines) — Abstract base class
│   ├── circuit_breaker.py (139 lines) — Generic CB implementation
│   ├── rate_limiter.py (64 lines) — TokenBucketRateLimiter
│   └── retry.py (50 lines) — Generic RetryPolicy
│
├── infrastructure/resilience/
│   ├── circuit_breaker.py (70 lines) — DUPLICATE CB (unused)
│   ├── rate_limiter.py (52 lines) — DUPLICATE RL + MultiBucket (unused)
│   └── retry_executor.py (75 lines) — DUPLICATE retry executor (orphaned)
│
└── domain/
    └── exceptions.py (123 lines) — Generic broker exception hierarchy
```

**Characteristics:**
- Layered separation: adapter (Dhan-specific) → resilience (generic) → domain (exceptions)
- Abstract base class (BaseResilientHttpClient) provides resilience skeleton
- DhanHttpClient inherits and overrides specific behaviors
- Generic resilience classes reusable across brokers
- Duplicate implementations in infrastructure/ (not wired into adapter path)

---

## 2. Improvements Over Archive

### 2.1 Thread Safety — refresh_lock

**Archive:** No explicit multi-client token refresh coordination. If multiple DhanHttpClient instances share the same token_refresh_fn, concurrent refresh attempts can trigger Dhan's "Token can be generated once every 2 minutes" rate limit.

**Greenfield:** Introduces `refresh_lock: threading.Lock | None` parameter (http.py:57,66,236-244). Shared lock prevents concurrent refresh across clients.

```python
# Greenfield (http.py:236-244)
if self._refresh_lock is not None:
    acquired = self._refresh_lock.acquire(timeout=5.0)
    if not acquired:
        logger.debug("token_refresh_lock_timeout")
        return None
    try:
        return self._token_refresh_fn() if self._token_refresh_fn else None
    finally:
        self._refresh_lock.release()
```

**Verdict:** IMPROVED. Addresses a real concurrency bug in archive.

### 2.2 Abstract Base Class — Reusability

**Archive:** DhanHttpClient is a concrete class with all resilience logic inline. Cannot reuse for other brokers without duplication.

**Greenfield:** BaseResilientHttpClient (resilience/http_client.py) is an abstract base class defining the resilience skeleton:
- `_categorize(endpoint)` — abstract, broker-specific
- `_build_url(endpoint)` — abstract, broker-specific
- `_handle_response(resp)` — abstract, broker-specific
- `_request(method, endpoint)` — concrete, wires CB + RL + retry

**Verdict:** IMPROVED. Enables reuse for Upstox, Zerodha, etc.

### 2.3 TokenRefreshSignal Pattern

**Archive:** Token refresh occurs inline within retry loop:
```python
# Archive (http_client.py:435-440)
if resp.status_code == 401 and attempt == 1:
    self._try_refresh_token()
    continue  # retry loop
```

**Greenfield:** Token refresh raises TokenRefreshSignal, triggering one additional full `cb.call()` pass:
```python
# Greenfield (http.py:125)
raise TokenRefreshSignal("Token refreshed, retrying request")

# Greenfield (http_client.py:99-109)
except TokenRefreshSignal:
    return cb.call(lambda: self._retry.call(_do_request), ...)
```

**Verdict:** IMPROVED (structurally cleaner). Separates token refresh concern from retry loop. But introduces behavioral difference: archive retries within same CB invocation; greenfield makes a second CB invocation.

### 2.4 Generic Exception Hierarchy

**Archive:** Dhan-specific exceptions (SuperOrderError, ForeverOrderError, etc.) mixed with common exceptions.

**Greenfield:** Generic broker exceptions (BrokerError, BrokerServerError, RateLimitError) in domain layer. Dhan-specific exceptions (DhanError, DhanAuthenticationError) in adapter layer.

**Verdict:** IMPROVED. Cleaner separation. But loses feature-specific exceptions (see Dropped Behaviors).

---

## 3. Dropped Behaviors

### 3.1 Critical Gaps

#### 3.1.1 RATE_LIMITS Inversion Bug

**Archive:** Rate limits defined as requests-per-second:
```python
# Archive (rate_limiter.py:35-52)
ORDERS_RATE = 25  # requests per second
MARKET_DATA_RATE = 10  # requests per second
```

**Greenfield:** Rate limits defined as intervals (seconds between requests):
```python
# Greenfield (config.py:28-35)
RATE_LIMITS = {
    "/marketfeed/quote": 1.0,  # 1 req/s
    "/marketfeed/ltp": 0.15,  # ~6.7 req/s (documented 10 req/s)
    "/orders": 0.04,  # 25 req/s
}
```

**Bug:** Values passed as `rate_per_second` to TokenBucketRateLimiter:
```python
# Greenfield (http_client.py:51-53)
TokenBucketRateLimiter(rate_per_second=rate, capacity=max(int(rate), 1))
```

With `rate = 0.15` for `/marketfeed/ltp`:
- Intended: 6.7 rps (1 request per 0.15 seconds)
- Actual: 0.15 rps (1 request per 6.67 seconds)
- **Throughput reduced to 1/44th of intended**

**Root Cause:** Semantic confusion. Config values are intervals but consumed as rates.

**Fix:** Invert values before passing to TokenBucketRateLimiter:
```python
rate_per_second = 1.0 / interval if interval > 0 else 0
```

#### 3.1.2 HTTP 429 Not Retried

**Archive:** 429 responses retried with backoff:
```python
# Archive (http_client.py:444-473)
if resp.status_code == 429:
    retry_after = self._parse_retry_after(resp)  # returns float | None
    if attempt < max_attempts:
        delay = retry_after if retry_after else self._backoff_delay(attempt)
        time.sleep(delay)
        continue
    else:
        raise RateLimitError
```

**Greenfield:** 429 raises immediately, no retry:
```python
# Greenfield (http.py:128-140)
if resp.status_code == 429:
    retry_after = self._parse_retry_after(resp)  # returns float, default 30.0
    raise RateLimitError("Rate limit exceeded", retry_after=retry_after)
```

**Compounding Issue:** RateLimitError is in `ignored_exceptions` for CircuitBreaker (http_client.py:97), so RetryPolicy never retries it:
```python
# Greenfield (http_client.py:95-97)
cb.call(
    lambda: self._retry.call(_do_request),
    ignored_exceptions=(AuthenticationError, RateLimitError, BrokerError),
)
```

**Impact:** Transient rate limits cause immediate failure instead of graceful backoff.

**Fix:** Remove RateLimitError from ignored_exceptions, or handle 429 retry within `_handle_response()`.

#### 3.1.3 Constructor Argument Order Swap

**Archive:**
```python
# Archive (http_client.py:116-134)
def __init__(self, client_id, access_token, base_url, ...):
```

**Greenfield:**
```python
# Greenfield (http.py:50-69)
def __init__(self, access_token, client_id, base_url, ...):
```

**Impact:** Code calling by positional arguments will silently swap tokens:
```python
# Archive caller
client = DhanHttpClient("CLIENT_ID", "ACCESS_TOKEN", ...)

# Same call in greenfield → access_token="CLIENT_ID", client_id="ACCESS_TOKEN"
# Silent data corruption
```

**Fix:** Restore archive order or use keyword-only arguments.

### 3.2 High-Severity Gaps

#### 3.2.1 Circuit Breaker success_threshold = 1 vs 3

**Archive:** Requires 3 consecutive successes in HALF_OPEN to close circuit:
```python
# Archive (circuit_breaker.py:31)
success_threshold=3
```

**Greenfield:** Defaults to 1:
```python
# Greenfield (circuit_breaker.py:41)
success_threshold: int = 1
```

**Impact:** Circuit closes after single probe success. Under intermittent faults, circuit flaps between CLOSED and OPEN.

**Fix:** Set `success_threshold=3` in BaseResilientHttpClient CB initialization.

#### 3.2.2 Metrics Not in Hot Path

**Archive:** Metrics incremented inline in request path:
```python
# Archive (http_client.py:399,543,546)
dhan_request_total.inc()
dhan_errors_total.inc()
dhan_request_duration_seconds.observe(duration)
```

**Greenfield:** Metrics exist as decorator only:
```python
# Greenfield (metrics.py:48-65)
@prometheus_metrics.track_request_duration
def my_method(): ...
```

No `inc()` or `observe()` calls in `_request()` path.

**Impact:** Observability blind spot. Dashboards show zero request counts.

**Fix:** Add metrics instrumentation to BaseResilientHttpClient._request().

#### 3.2.3 Duplicate Implementations (3 CB, 3 RL, 1 Orphaned RetryExecutor)

**Three Circuit Breaker Implementations:**
1. `brokers/resilience/circuit_breaker.py` — Used by BaseResilientHttpClient
2. `brokers/infrastructure/resilience/circuit_breaker.py` — Used by infrastructure RetryExecutor (orphaned)
3. Archive `brokers/common/resilience/circuit_breaker.py` — Used by archive DhanHttpClient

**Three Rate Limiter Implementations:**
1. `brokers/resilience/rate_limiter.py` — TokenBucketRateLimiter (used)
2. `brokers/infrastructure/resilience/rate_limiter.py` — TokenBucketRateLimiter + MultiBucketRateLimiter (unused)
3. Archive `brokers/common/resilience/rate_limiter.py` — MultiBucketRateLimiter (used)

**Orphaned RetryExecutor:**
- `brokers/infrastructure/resilience/retry_executor.py` — No callers in greenfield adapter path
- References infrastructure CB (different from BaseResilientHttpClient CB)
- Dead code

**Impact:** Maintenance burden, confusion about which implementation is canonical.

**Fix:** Delete infrastructure/ duplicates. Confirm they have no callers.

### 3.3 Medium-Severity Gaps

#### 3.3.1 Write CB open_duration = 60s vs 30s

**Archive:** All CBs use 30s recovery timeout:
```python
# Archive (circuit_breaker.py:28)
open_duration_ms=30000  # 30s for all categories
```

**Greenfield:** Write CB uses 60s:
```python
# Greenfield (http_client.py:57)
"write": CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
```

**Impact:** Write circuit stays open 2x longer, delaying recovery after transient failures.

**Fix:** Change to `recovery_timeout=30.0`.

#### 3.3.2 DH-906 Detection Narrower

**Archive:** Scans raw body text:
```python
# Archive (http_client.py:502)
if "DH-906" in body or "DH-808" in body:
```

**Greenfield:** Checks structured field:
```python
# Greenfield (http.py:204)
error_code = body.get("remarks", {}).get("errorCode", "")
if error_code in {"DH-906", "DH-808"}:
```

**Impact:** If Dhan returns DH-906 in non-standard structure (e.g., inline in error message), greenfield misses it.

**Fix:** Add text scan fallback: `or "DH-906" in resp.text`.

#### 3.3.3 No Portfolio CB Category

**Archive:** Four CB categories (orders, market_data, portfolio, admin):
```python
# Archive (circuit_breaker.py:74-88)
dhan-portfolio CB with failure_threshold=5
```

**Greenfield:** Three categories (read, write, admin). Portfolio endpoints map to "admin":
```python
# Greenfield (config.py:37-49)
READ_PREFIXES = ("/marketfeed/ltp", ...)
WRITE_PREFIXES = ("/orders", ...)
# Portfolio endpoints not listed → fall through to "admin"
```

**Impact:** Portfolio failures trip admin CB, blocking admin operations.

**Fix:** Add "portfolio" category with dedicated CB.

#### 3.3.4 No Invariants (Payload Identity Assertions)

**Archive:** Pre/post-condition assertions on order payloads:
```python
# Archive (invariants.py)
assert_order_identity(order_payload)
assert_exchange_segment(order_payload)
```

**Greenfield:** No invariant checks.

**Impact:** Silent payload corruption possible. No defensive programming.

**Fix:** Port invariant checks to DhanHttpClient.post/put.

#### 3.3.5 No WebSocket Rate Limiter

**Archive:** WS connection rate limiting:
```python
# Archive (websocket_rate_limiter_simple.py:34,38)
1-second interval between connection attempts
Max 5 concurrent connections
```

**Greenfield:** No WS rate limiting found.

**Impact:** WS adapter may overwhelm Dhan's connection limits.

**Fix:** Port WebSocketRateLimiter or implement equivalent.

#### 3.3.6 No DhanRateLimiterMetrics

**Archive:** Per-category RL metrics:
```python
# Archive (rate_limiter.py:126-218)
dhan_rate_limiter_acquisitions_total
dhan_rate_limiter_rejections_total
dhan_rate_limiter_queue_depth
```

**Greenfield:** No RL metrics.

**Impact:** Cannot observe rate limiter behavior.

**Fix:** Port DhanRateLimiterMetrics or add RL instrumentation to BaseResilientHttpClient.

### 3.4 Low-Severity Gaps

#### 3.4.1 Feature-Specific Exceptions Missing

**Archive:** Rich exception hierarchy:
```python
# Archive (exceptions.py:109-143)
SuperOrderError, ForeverOrderError, ConditionalTriggerError, LedgerError, ...
```

**Greenfield:** Generic exceptions only:
```python
# Greenfield (adapters/dhan/exceptions.py)
DhanError, DhanAuthenticationError, DhanRateLimitError, DhanOrderRejectedError, ...
```

**Impact:** Cannot distinguish order rejection reasons (super order limit vs forever order limit).

**Fix:** Port feature-specific exceptions if needed by business logic.

### 3.5 Unknown-Severity Gaps

#### 3.5.1 Status Mapper Not Ported

**Archive:** Order status normalization:
```python
# Archive (status_mapper.py:21)
"PLACED" → "OPEN"
```

**Greenfield:** No status mapper found.

**Impact:** Order status may not match expected enum values.

**Fix:** Port status mapper if order processing depends on it.

---

## 4. Duplicate Implementation Problem

### 4.1 Circuit Breaker Proliferation

| Location | Class | Interface | Used By | Status |
|---|---|---|---|---|
| `brokers/resilience/circuit_breaker.py` | CircuitBreaker | `.call(fn, ignored_exceptions)` | BaseResilientHttpClient | **ACTIVE** |
| `brokers/infrastructure/resilience/circuit_breaker.py` | CircuitBreaker | `.allow_request()`, `.record_success()`, `.record_failure()` | RetryExecutor | **ORPHANED** |
| Archive `brokers/common/resilience/circuit_breaker.py` | CircuitBreaker | `.state`, `.on_failure()`, `.on_success()`, `.allow_request()`, `.reset()` | Archive DhanHttpClient | **ARCHIVED** |

**Problem:** Two active CB implementations with different interfaces. Infrastructure CB uses allow_request()/record_*() pattern (matches archive). Resilience CB uses call() pattern (cleaner but incompatible).

**Risk:** If any code instantiates infrastructure RetryExecutor, it will use a different CB instance than DhanHttpClient, causing failures to be counted in separate state machines.

### 4.2 Rate Limiter Proliferation

| Location | Class | Interface | Used By | Status |
|---|---|---|---|---|
| `brokers/resilience/rate_limiter.py` | TokenBucketRateLimiter | `.acquire(tokens, timeout)` → bool; uses `Condition.wait` | BaseResilientHttpClient | **ACTIVE** |
| `brokers/infrastructure/resilience/rate_limiter.py` | TokenBucketRateLimiter + MultiBucketRateLimiter | `.acquire(tokens, timeout)` → bool; uses `time.sleep(0.01)` spin | None | **ORPHANED** |
| Archive `brokers/common/resilience/rate_limiter.py` | MultiBucketRateLimiter | `.acquire(category, tokens, timeout)` | Archive DhanHttpClient | **ARCHIVED** |

**Problem:** Two active RL implementations. Infrastructure RL uses spin-wait (`time.sleep(0.01)`), resilience RL uses Condition.wait (more efficient).

**Risk:** Infrastructure RL is dead code but adds maintenance burden.

### 4.3 Orphaned RetryExecutor

**Location:** `brokers/infrastructure/resilience/retry_executor.py`

**Problem:** No callers in greenfield adapter path. DhanHttpClient uses RetryPolicy from `brokers/resilience/retry.py` via BaseResilientHttpClient.

**Risk:** Dead code. May confuse developers about which retry mechanism to use.

**Recommendation:** Delete infrastructure RetryExecutor after confirming no callers.

---

## 5. RATE_LIMITS Inversion Bug — Deep Dive

### 5.1 Symptom

Market data endpoints throttled to 1/44th of intended throughput:
- `/marketfeed/ltp`: intended 6.7 rps, actual 0.15 rps (1 req per 6.67s)
- `/marketfeed/ohlc`: intended 6.7 rps, actual 0.15 rps
- `/charts/`: intended 6.7 rps, actual 0.15 rps

### 5.2 Root Cause

**Config values are intervals (seconds between requests):**
```python
# config.py:30
"/marketfeed/ltp": 0.15,  # ~6.7 req/s (documented 10 req/s)
```

Comment says "~6.7 req/s", implying 0.15 is the interval (1/6.67 ≈ 0.15).

**Values passed as rate_per_second:**
```python
# http_client.py:51-53
TokenBucketRateLimiter(rate_per_second=rate, capacity=max(int(rate), 1))
```

With `rate = 0.15`:
- `rate_per_second = 0.15` → 0.15 requests per second
- `capacity = max(int(0.15), 1) = 1` → bucket holds 1 token
- Actual throughput: 1 token / 0.15 seconds per token = 0.15 rps

### 5.3 TokenBucketRateLimiter Behavior

```python
# brokers/resilience/rate_limiter.py
class TokenBucketRateLimiter:
    def __init__(self, rate_per_second: float, capacity: int):
        self._rate = rate_per_second  # tokens added per second
        self._capacity = capacity  # max tokens in bucket
        self._tokens = capacity  # start full
        self._last_refill = time.monotonic()
    
    def acquire(self, tokens: int, timeout: float) -> bool:
        # Wait until `tokens` are available, up to `timeout` seconds
        # Tokens refill at `self._rate` per second
```

With `rate_per_second=0.15, capacity=1`:
- Bucket starts with 1 token
- Each request consumes 1 token
- Bucket refills at 0.15 tokens/second (1 token per 6.67 seconds)
- After first request, must wait 6.67s for next token

### 5.4 Intended Behavior

If config values are intervals:
- `/marketfeed/ltp`: interval=0.15s → rate=1/0.15=6.67 rps
- `/orders`: interval=0.04s → rate=1/0.04=25 rps

**Fix:**
```python
# http_client.py:50-53 (FIXED)
for endpoint, interval in rate_limits.items():
    rate_per_second = 1.0 / interval if interval > 0 else 0
    self._rate_limiters[endpoint] = TokenBucketRateLimiter(
        rate_per_second=rate_per_second,
        capacity=max(int(rate_per_second), 1)
    )
```

### 5.5 Alternative Interpretation

If config values are actually intended as rates (not intervals):
- `/marketfeed/ltp`: 0.15 rps → 1 request per 6.67 seconds (too conservative)
- `/orders`: 0.04 rps → 1 request per 25 seconds (absurdly slow)

This interpretation contradicts the comments ("~6.7 req/s", "25 req/s"), so config values must be intervals.

---

## 6. Design Principles Applied

### 6.1 Separation of Concerns

**Greenfield:** Adapter (Dhan-specific) → Resilience (generic) → Domain (exceptions)

**Example:**
- `DhanHttpClient` knows about Dhan endpoints, auth, error codes
- `BaseResilientHttpClient` knows about CB/RL/retry orchestration
- `CircuitBreaker`, `TokenBucketRateLimiter`, `RetryPolicy` are broker-agnostic

**Benefit:** Reusable across brokers. Upstox adapter can inherit BaseResilientHttpClient.

### 6.2 Abstract Base Class

**Greenfield:** BaseResilientHttpClient defines resilience skeleton with abstract hooks:
- `_categorize(endpoint)` — broker-specific
- `_build_url(endpoint)` — broker-specific
- `_handle_response(resp)` — broker-specific

**Benefit:** Enforces consistent interface across brokers.

### 6.3 Thread Safety

**Greenfield:** Introduces `refresh_lock` for multi-client token refresh coordination.

**Benefit:** Prevents concurrent refresh attempts that trigger Dhan's rate limit.

### 6.4 Generic Exception Hierarchy

**Greenfield:** Domain exceptions (BrokerError, BrokerServerError) separate from adapter exceptions (DhanError).

**Benefit:** Reusable across brokers. DhanError extends BrokerError.

### 6.5 TokenRefreshSignal Pattern

**Greenfield:** Token refresh raises signal instead of inline retry.

**Benefit:** Cleaner separation of concerns. Retry loop doesn't know about token refresh.

---

## 7. Recommended Architecture

### 7.1 Consolidate to Single CB/RL Implementation

**Action:**
1. Delete `brokers/infrastructure/resilience/circuit_breaker.py`
2. Delete `brokers/infrastructure/resilience/rate_limiter.py`
3. Delete `brokers/infrastructure/resilience/retry_executor.py`
4. Confirm no callers via grep/import search

**Rationale:** Infrastructure duplicates are orphaned. Maintaining two CB/RL implementations creates confusion.

### 7.2 Fix RATE_LIMITS Inversion

**Action:** Invert interval values before passing to TokenBucketRateLimiter:
```python
# brokers/resilience/http_client.py:50-53
for endpoint, interval in rate_limits.items():
    rate_per_second = 1.0 / interval if interval > 0 else 0
    self._rate_limiters[endpoint] = TokenBucketRateLimiter(
        rate_per_second=rate_per_second,
        capacity=max(int(rate_per_second), 1)
    )
```

**Alternative:** Rename config to clarify semantics:
```python
# brokers/adapters/dhan/config.py
RATE_LIMITS = {
    "/marketfeed/ltp": 6.67,  # requests per second
    "/orders": 25.0,  # requests per second
}
```

### 7.3 Add Metrics to Hot Path

**Action:** Instrument BaseResilientHttpClient._request():
```python
# brokers/resilience/http_client.py:83-113
def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict:
    start_time = time.monotonic()
    category = self._categorize(endpoint)
    cb = self._circuit_breakers.get(category, self._circuit_breakers["admin"])
    
    self._apply_rate_limit(endpoint)
    
    def _do_request() -> dict:
        url = self._build_url(endpoint)
        resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        return self._handle_response(resp)
    
    try:
        result = cb.call(
            lambda: self._retry.call(_do_request),
            ignored_exceptions=(AuthenticationError, RateLimitError, BrokerError),
        )
        # Metrics: success
        self._metrics.inc_request_success(category, method, endpoint)
        return result
    except Exception as exc:
        # Metrics: failure
        self._metrics.inc_request_failure(category, method, endpoint, type(exc).__name__)
        raise
    finally:
        # Metrics: duration
        duration = time.monotonic() - start_time
        self._metrics.observe_request_duration(category, method, duration)
```

### 7.4 Fix 429 Retry

**Option A:** Remove RateLimitError from ignored_exceptions:
```python
# brokers/resilience/http_client.py:95-97
cb.call(
    lambda: self._retry.call(_do_request),
    ignored_exceptions=(AuthenticationError, BrokerError),  # Removed RateLimitError
)
```

**Option B:** Handle 429 retry within _handle_response():
```python
# brokers/adapters/dhan/http.py:128-140
if resp.status_code == 429:
    retry_after = self._parse_retry_after(resp)
    # Update adaptive intervals
    # Raise RetryableError instead of RateLimitError
    raise RetryableError(f"Rate limited, retry after {retry_after}s")
```

**Recommendation:** Option A. Simpler, aligns with archive behavior.

### 7.5 Fix Constructor Arg Order

**Action:** Restore archive order:
```python
# brokers/adapters/dhan/http.py:50-69
def __init__(
    self,
    client_id: str,  # FIRST
    access_token: str,  # SECOND
    base_url: str = "",
    ...
):
```

**Alternative:** Use keyword-only arguments to prevent positional swap:
```python
def __init__(
    self,
    *,
    client_id: str,
    access_token: str,
    base_url: str = "",
    ...
):
```

**Recommendation:** Restore archive order for compatibility.

### 7.6 Fix CB success_threshold

**Action:** Set success_threshold=3 in BaseResilientHttpClient:
```python
# brokers/resilience/http_client.py:55-59
self._circuit_breakers = {
    "read": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3),
    "write": CircuitBreaker(failure_threshold=3, recovery_timeout=30.0, success_threshold=3),
    "admin": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3),
}
```

### 7.7 Add Portfolio CB Category

**Action:** Add "portfolio" category:
```python
# brokers/adapters/dhan/config.py
PORTFOLIO_PREFIXES = (
    "/positions",
    "/holdings",
    "/fundlimit",
    "/tradebook",
)

# brokers/adapters/dhan/http.py:105-112
def _categorize(self, endpoint: str) -> str:
    for prefix in READ_PREFIXES:
        if endpoint.startswith(prefix):
            return "read"
    for prefix in WRITE_PREFIXES:
        if endpoint.startswith(prefix):
            return "write"
    for prefix in PORTFOLIO_PREFIXES:
        if endpoint.startswith(prefix):
            return "portfolio"
    return "admin"

# brokers/resilience/http_client.py:55-59
self._circuit_breakers = {
    "read": CircuitBreaker(...),
    "write": CircuitBreaker(...),
    "portfolio": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3),
    "admin": CircuitBreaker(...),
}
```

---

## 8. Summary

**Greenfield Architecture:** Layered, reusable, thread-safe. Improvements: abstract base class, refresh_lock, TokenRefreshSignal pattern, generic exception hierarchy.

**Critical Gaps:**
1. RATE_LIMITS inversion bug (throughput reduced to 1/44th)
2. 429 not retried (immediate failure on transient rate limits)
3. Constructor arg swap (silent data corruption)

**High-Severity Gaps:**
4. success_threshold=1 vs 3 (circuit flap risk)
5. Metrics not in hot path (observability blind spot)
6. 3 duplicate CB/RL implementations (maintenance burden)
7. Orphaned RetryExecutor (dead code)

**Recommendations:**
- Consolidate to single CB/RL implementation (delete infrastructure/ duplicates)
- Fix RATE_LIMITS inversion (invert intervals to rates)
- Fix 429 retry (remove RateLimitError from ignored_exceptions)
- Fix constructor arg order (restore archive order)
- Add metrics to hot path (instrument _request())
- Fix CB success_threshold (set to 3)
- Add portfolio CB category

**Next Steps:** See implementation_tasks.md for prioritized task list with dependencies.

---

*End of greenfield_design.md*
