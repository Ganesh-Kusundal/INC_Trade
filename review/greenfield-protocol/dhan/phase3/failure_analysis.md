# Phase 3 Rate Limiting — Failure Analysis

## 1. Timeout & Retry Policies

### HTTP Request Timeouts

| Parameter | Archive | Greenfield | Delta |
|-----------|---------|------------|-------|
| Default timeout | 15.0s | 10.0s | Greenfield 5s shorter |
| Rate limit acquire timeout | 5.0s | 5.0s | Match |
| Token refresh lock timeout | N/A (no lock) | 5.0s | Greenfield only |
| Token refresh cooldown | 60s (configurable) | 60s (hardcoded) | Match |
| Token rate limit backoff | 130s (configurable) | 130s (hardcoded) | Match |

### Retry Configuration

| Parameter | Archive | Greenfield | Delta |
|-----------|---------|------------|-------|
| Max retries | 3 (configurable) | 3 (hardcoded) | Match |
| Base delay | 500ms | 500ms | Match |
| Max delay | 5000ms | 5000ms | Match |
| Jitter | None (deterministic) | `randint(0, delay//4)` | Greenfield adds ±25% jitter |
| Backoff formula | `base × 2^(attempt-1)` capped at max | `base × 2^attempt` capped at max | Archive is 1-indexed; greenfield is 0-indexed |
| Retryable exceptions | All `DhanError` from network | `(RequestException, BrokerServerError)` | **Different scope** |

### Backoff Sequence Comparison

| Attempt | Archive Delay | Greenfield Delay |
|---------|--------------|-----------------|
| 1st retry | 500ms | 500–625ms |
| 2nd retry | 1000ms | 1000–1250ms |
| 3rd retry | 2000ms | 2000–2500ms |
| 4th+ (capped) | 4000ms | 4000–5000ms (capped at 5000) |

### HTTP 429 Handling

| Behavior | Archive | Greenfield |
|----------|---------|------------|
| On 429 received | Parse Retry-After; sleep; retry | Raise `RateLimitError` immediately |
| Adaptive interval update | Yes (`_adaptive_intervals[key] = max(retry_after, current)`) | Yes (same logic) |
| Retry after backoff | Yes (within max_retries) | **No** — exception propagates |
| Final 429 | `RateLimitError` raised | `RateLimitError` raised |

**CRITICAL**: Greenfield never retries HTTP 429. The `RateLimitError` is in the CB's `ignored_exceptions` list AND not in `RetryPolicy`'s `retryable_exceptions`. The request fails immediately.

---

## 2. Exception Hierarchy with Exact Messages

### Greenfield Exceptions Raised by HTTP Client

| Exception | Message Pattern | Code | Trigger |
|-----------|----------------|------|---------|
| `RateLimitError` | `"Rate limit exceeded"` | `RATE_LIMITED` | HTTP 429 |
| `AuthenticationError` | `"Token expired or invalid"` | `AUTH_ERROR` | HTTP 401, no refresh possible |
| `AuthenticationError` | `"Token rejected: {msg}"` | `AUTH_ERROR` | 4xx with DH-906/DH-808, refresh failed |
| `BrokerServerError` | `"HTTP {code}: {msg}"` | `str(code)` | HTTP 5xx |
| `BrokerError` | `"HTTP {code}: {msg}"` | `str(code)` | 4xx (non-token) |
| `BrokerError` | `"API failure: {remarks}"` | `""` | 2xx with `status=failure` |
| `CircuitOpenError` | `"Circuit breaker is open"` | `CIRCUIT_OPEN` | CB state is OPEN |
| `BrokerError` | `str(exc)` (wrapped) | `""` | Non-BrokerError exception from pipeline |
| `TokenRefreshSignal` | `"Token refreshed, retrying request"` | N/A | Internal signal (not propagated) |

### Archive Exceptions Raised by HTTP Client

| Exception | Message Pattern | Trigger |
|-----------|----------------|---------|
| `DhanError` | `"Circuit breaker open: {method} {endpoint}"` | CB state OPEN |
| `DhanError` | `"Rate limit timeout: {method} {endpoint}"` | Rate limit acquire timeout |
| `DhanError` | `"HTTP {method} {url} failed: {exc}"` | Network error (`RequestException`) |
| `AuthenticationError` | `"Token rejected: HTTP 401 on {method} {endpoint}"` | HTTP 401, refresh failed |
| `AuthenticationError` | `"Token rejected: DH-906 on {method} {endpoint}"` | DH-906, refresh failed |
| `RateLimitError` | `"Rate limited: HTTP 429 on {method} {endpoint}"` | HTTP 429, retries exhausted |
| `DhanError` | `"Dhan API {method} {url} failed: HTTP {code} — {body}"` | 5xx retries exhausted |
| `DhanError` | `"Dhan API {method} {url} failed: HTTP {code} — {body}"` | 4xx (non-token) |
| `DhanError` | `"API failure: {remarks}"` | 2xx with `status=failure` |
| `DhanError` | `"Invalid JSON from {method} {url}"` | JSON parse failure |
| `DhanError` | `"Request failed after {max} attempts: {method} {url}"` | All retries exhausted (network) |

---

## 3. Race Conditions Inventory

### R1: Concurrent Token Refresh on 401

**Components**: Multiple threads calling `_request()` simultaneously, both receive 401.

**Archive**: `_try_refresh_token()` has no lock; two threads can call `token_refresh_fn()` concurrently. The `_last_refresh_time` check provides soft serialization via cooldown.

**Greenfield**: `_try_refresh_token()` acquires `_refresh_lock` (shared `threading.Lock`) with 5s timeout. Only one thread refreshes; the other either waits or times out.

**Risk**: MEDIUM — Double TOTP generation triggers Dhan's 2-minute rate limit.

**Mitigation gap**: Archive has no shared lock at the HTTP client level (lock exists in `ConnectionTokenManager` but not in `DhanHttpClient`).

### R2: Token Read During Update

**Components**: Thread A reads `_access_token` while Thread B calls `update_token()`.

**Archive**: `self.access_token = access_token` + `self._session.headers["access-token"] = access_token` — not atomic. A thread could read the old `access_token` attribute but the new header, or vice versa.

**Greenfield**: Same pattern: `self._access_token = new_token` then `self._session.headers["access-token"] = new_token`. Same non-atomicity.

**Risk**: LOW — `requests.Session` headers are read at request-send time, so the window is tiny. GIL provides partial protection.

### R3: Adaptive Interval Update During Read

**Components**: Thread A reads `_adaptive_intervals[key]` in `_match_prefix()` while Thread B writes it in `_handle_response()`.

**Archive**: Protected by `_rate_lock` in `_throttle()` but NOT in `_handle_response()` where the write occurs.

**Greenfield**: No lock around `_adaptive_intervals` writes at all.

**Risk**: LOW — dict assignment is atomic in CPython (GIL), but max() read-modify-write is not.

### R4: Circuit Breaker State Torn Read

**Components**: Thread A checks `cb.state` (reads `_state` under lock), Thread B calls `record_failure()` (writes `_state` under lock).

**Archive**: `RLock` — safe. But `allow_request()` and `record_failure()` are separate calls; state can change between them.

**Greenfield**: `call()` wraps the entire check+execute in one method — safer. But `state` property reads under lock then releases before `call()` acquires again.

**Risk**: LOW — both implementations hold locks during state transitions. The window between separate calls is the vulnerability.

### R5: Rate Limiter Token Drain

**Components**: Multiple threads competing for the same `TokenBucketRateLimiter`.

**Greenfield**: `threading.Condition` — threads sleep efficiently and are woken by refill or other threads.

**Archive infrastructure**: Spin-loop with `time.sleep(0.01)` — wastes CPU under contention.

**Risk**: LOW (correctness) / MEDIUM (performance under archive) — token bucket is thread-safe in both.

### R6: TokenRefreshSignal Lost on Second Failure

**Components**: `_request()` catches `TokenRefreshSignal`, retries once. If the retry also raises `TokenRefreshSignal`, it falls into the generic `except Exception` handler and gets wrapped as `BrokerError`.

```python
try:
    return cb.call(lambda: self._retry.call(_do_request))
except TokenRefreshSignal:
    # One extra pass
    try:
        return cb.call(lambda: self._retry.call(_do_request))
    except Exception as exc:       # ← catches second TokenRefreshSignal
        if isinstance(exc, BrokerError):
            raise
        raise BrokerError(str(exc)) from exc   # ← wraps as generic BrokerError
```

**Risk**: MEDIUM — The second `TokenRefreshSignal` is silently converted to `BrokerError`, losing the semantic meaning. The caller cannot distinguish "token still bad after refresh" from "generic API failure."

---

## 4. Lock Hierarchy / Deadlock Analysis

### Greenfield Lock Inventory

| Lock | Owner | Scope | Acquisition Sites |
|------|-------|-------|-------------------|
| `CircuitBreaker._lock` | `Lock` | Per-CB (3 instances) | `state`, `call()`, `record_success()`, `record_failure()`, `reset()` |
| `TokenBucketRateLimiter._condition._lock` | `Lock` | Per-limiter (6 instances) | `available_tokens`, `acquire()` |
| `DhanHttpClient._refresh_lock` | `Lock` | Shared (optional) | `_try_refresh_token()` |

### Lock Ordering (Greenfield)

```
Level 1: _refresh_lock (token refresh coordination)
    └── Level 2: CircuitBreaker._lock (inside cb.call())
        └── Level 3: TokenBucketRateLimiter._condition._lock (inside acquire())
```

**No circular dependency exists.** `_refresh_lock` is only acquired in `_try_refresh_token()`, which is called from `_handle_response()`, which runs inside `cb.call()` → `retry.call()` → `_do_request()`. The CB lock is never held when `_refresh_lock` is acquired.

### Archive Lock Inventory

| Lock | Owner | Scope |
|------|-------|-------|
| `CircuitBreaker._lock` | `RLock` | Per-CB |
| `TokenBucketRateLimiter._lock` | `Lock` | Per-bucket |
| `DhanHttpClient._rate_lock` | `Lock` | Per-client |
| `ConnectionTokenManager._lock` | `Lock` | Per-connection (if present) |

### Deadlock Risk Assessment

| Scenario | Risk | Reason |
|----------|------|--------|
| CB lock + rate limiter lock | NONE | Never nested; rate limit acquired before CB call |
| Refresh lock + CB lock | NONE | Refresh lock acquired inside CB call, not vice versa |
| Rate lock + any other lock | NONE | `_rate_lock` only used in archive `_throttle()`, no nesting |
| Recursive CB lock (archive RLock) | NONE | No reentrant paths exist |

---

## 5. Recovery Paths

### HTTP 429 (Rate Limited)

```
HTTP 429 received
├── ARCHIVE:
│   ├── Parse Retry-After header (default: None → use exponential backoff)
│   ├── Update _adaptive_intervals[key] = max(retry_after, current)
│   ├── Sleep(delay) → retry (up to max_retries)
│   └── All retries exhausted → raise RateLimitError
│
└── GREENFIELD:
    ├── Parse Retry-After header (default: 30.0s)
    ├── Update _adaptive_intervals[key] = max(retry_after, current)
    ├── raise RateLimitError(retry_after=retry_after)
    └── NO RETRY — caller must handle
        └── RateLimitError is in CB ignored_exceptions → no CB failure recorded
```

**PARITY GAP**: Archive retries 429s; greenfield does not. This is the most critical behavioral difference.

### HTTP 401 (Authentication)

```
HTTP 401 received
├── _handle_response() checks _token_refresh_fn is not None
│   ├── _try_refresh_token()
│   │   ├── Check backoff → skip if active
│   │   ├── Check cooldown → skip if active
│   │   ├── Acquire _refresh_lock (timeout 5s) → skip if timeout
│   │   ├── Call token_refresh_fn()
│   │   │   ├── Returns token → update_token() → raise TokenRefreshSignal
│   │   │   ├── Returns None → set backoff 130s → return None
│   │   │   └── Raises exception → handle rate limit / generic failure
│   │   └── Returns None → raise AuthenticationError
│   └── TokenRefreshSignal caught in _request()
│       └── ONE extra pass through cb.call(retry.call(_do_request))
│           ├── Success → return data
│           └── Failure → raise (wrapped in BrokerError if not already)
│
└── _token_refresh_fn is None
    └── raise AuthenticationError("Token expired or invalid")
```

### DH-906 (Token Error in 4xx Body)

```
HTTP 4xx received (status 400-499, not 401)
├── Parse JSON body
├── Extract errorCode from body.remarks.errorCode
├── _is_token_error(status_code, error_code, message):
│   ├── status_code == 401 → True (handled above)
│   ├── error_code in {"DH-906", "DH-808"} → True
│   ├── "invalid token" in message.lower() → True
│   └── else → False
│
├── IS token error:
│   ├── _token_refresh_fn not None → _try_refresh_token()
│   │   ├── Success → raise TokenRefreshSignal → one retry
│   │   └── Failure → raise AuthenticationError("Token rejected: {msg}")
│   └── _token_refresh_fn is None → raise AuthenticationError
│
└── NOT token error:
    └── raise BrokerError("HTTP {code}: {msg}")
```

**PARITY GAP (MEDIUM)**: Archive scans raw body text (`"DH-906" in body`); greenfield checks structured `errorCode` field. If Dhan changes response format, archive may still match via text; greenfield will silently stop detecting.

### Circuit Breaker Trip

```
CB failure count reaches threshold
├── CLOSED → OPEN transition
│   ├── _last_failure_time = time.monotonic()
│   ├── metrics.state_changes += 1
│   └── All subsequent cb.call() → raise CircuitOpenError immediately
│
├── OPEN state persists for recovery_timeout seconds
│   ├── read: 30s, write: 60s, admin: 30s
│   └── All requests fast-fail with CircuitOpenError
│
├── recovery_timeout elapsed → OPEN → HALF_OPEN (lazy check)
│   ├── _success_count = 0
│   ├── Next cb.call() allows one request through
│   │   ├── Success → _success_count++ → >= threshold → CLOSED
│   │   └── Failure → immediately → OPEN (reset _last_failure_time)
│   └── Greenfield threshold: 1 success → CLOSED
│       Archive threshold: 3 successes → CLOSED
│
└── Recovery complete → CLOSED
    ├── _failure_count = 0
    ├── _success_count = 0
    └── Normal operation resumes
```

### Network Timeout

```
requests.Session.request() raises RequestException
├── GREENFIELD:
│   ├── Exception propagates out of _do_request()
│   ├── RetryPolicy catches (RequestException is retryable)
│   │   ├── attempt 0: sleep 500-625ms → retry
│   │   ├── attempt 1: sleep 1000-1250ms → retry
│   │   ├── attempt 2: sleep 2000-2500ms → retry
│   │   └── attempt 3: raise last exception
│   ├── CB does NOT record failure (exception not from fn() result path)
│   │   └── Actually: cb.call() catches Exception → record_failure()
│   │       └── BUT: RequestException is not in ignored_exceptions
│   │       └── So CB DOES record failure ✓
│   └── After RetryPolicy exhausted → _request() wraps in BrokerError
│
└── ARCHIVE:
    ├── _send_raw_http() catches RequestException → raises DhanError
    ├── CB records failure (cb.on_failure() in _send_raw_http)
    ├── Retry loop catches DhanError → sleep → retry
    └── After max_retries → raise last DhanError
```

### Token Refresh Failure

```
_try_refresh_token() fails
├── "once every 2 minutes" in error_msg
│   └── _refresh_backoff_until = now + 130s
│       └── All 401/DH-906 requests fail for 130s
│           └── AuthenticationError raised to caller
│           └── After 130s: next 401 will attempt refresh again
│
├── "rate limit" in error_msg.lower()
│   └── Same as above (130s backoff)
│
├── Returns None (no token)
│   └── _refresh_backoff_until = now + 130s
│       └── Same cascade
│
├── Lock timeout (5s)
│   └── return None → no backoff set (greenfield)
│       └── Next 401 will immediately retry refresh
│
└── Generic exception (not rate-limit)
    ├── GREENFIELD: return None → no backoff set
    │   └── Next 401 will immediately retry (potential rapid fire)
    └── ARCHIVE: return False → no backoff set (same behavior)
```

---

## 6. Secret Exposure Risks

| # | Vector | Severity | Detail |
|---|--------|----------|--------|
| S1 | `BrokerError` wraps exception message | MEDIUM | `raise BrokerError(str(exc))` may include URL with query params containing tokens |
| S2 | `_handle_response` error messages | LOW | `f"HTTP {code}: {msg}"` — `msg` from `remarks.error_msg` could echo request data |
| S3 | `AuthenticationError` includes response text | MEDIUM | `f"Token rejected: {msg}"` — msg from response body |
| S4 | Log `extra={"client_id": ...}` | LOW | Client ID logged in plaintext (expected, but worth noting) |
| S5 | `TokenRefreshSignal` message | LOW | `"Token refreshed, retrying request"` — no secret in message |
| S6 | No log redaction in greenfield | HIGH | Archive has `_redact_record_extras()` for sensitive log fields; greenfield has no equivalent |
| S7 | Session headers in error | MEDIUM | If `requests` raises with response attached, `resp.request.headers` contains `access-token` |
| S8 | `BrokerServerError` includes body text | LOW | `f"HTTP {code}: {msg}"` where msg from `remarks.error_msg` or `resp.text` |

---

## 7. Duplicate Implementation Risks

### D1: Three Circuit Breaker Implementations

| Implementation | Module | Lock | Time Source | API |
|---------------|--------|------|-------------|-----|
| Greenfield CB | `brokers.resilience.circuit_breaker` | `Lock` | `monotonic()` | `call(fn)` wrapper |
| Archive common CB | `brokers.common.resilience.circuit_breaker` (via `brokers.infrastructure`) | `RLock` | `time()` | `allow_request()` manual |
| Archive infra CB | `brokers.infrastructure.resilience.circuit_breaker` | `RLock` | `time()` | `allow_request()` manual |

**Risk**: HIGH — Different default thresholds (`success_threshold=1` vs `3`), different time sources (`monotonic` vs `time` — `time()` is affected by NTP adjustments), different APIs. Bugs fixed in one may not propagate to others.

### D2: Three Rate Limiter Implementations

| Implementation | Module | Blocking | Validation |
|---------------|--------|----------|------------|
| Greenfield RL | `brokers.resilience.rate_limiter` | `Condition.wait()` | `ValueError` |
| Archive infra RL | `brokers.infrastructure.resilience.rate_limiter` | `sleep(0.01)` spin | None |
| Archive Dhan RL | `archive.brokers.dhan.resilience.rate_limiter` | Async support | Metrics |

**Risk**: HIGH — Constructor parameter order reversed (`rate_per_second, capacity` vs `capacity, rate_per_second`). A developer copying code between implementations will silently create misconfigured limiters.

### D3: Two Retry Implementations

| Implementation | Module | Exception Filter | Jitter |
|---------------|--------|-----------------|--------|
| Greenfield RetryPolicy | `brokers.resilience.retry` | Type-based | Yes (randint) |
| Archive RetryExecutor | `brokers.infrastructure.resilience.retry_executor` | Heuristic (string match) | Yes (uniform) |

**Risk**: MEDIUM — `RetryExecutor` uses string matching on error messages to classify transient errors (`"5" in error_msg and "error" in error_msg`). This is fragile and will misclassify errors with "5" in non-HTTP-context.

---

## 8. Critical Parity Gaps

| # | Gap | Severity | Detail |
|---|-----|----------|--------|
| P1 | HTTP 429 not retried | **CRITICAL** | Archive retries 429s with Retry-After backoff; greenfield raises immediately. Under Dhan's rate limiting, greenfield will fail requests that archive would recover from transparently. |
| P2 | Rate limit inversion | **CRITICAL** | `RATE_LIMITS` values are intervals (seconds) but passed as `rate_per_second` to `TokenBucketRateLimiter`. `/orders` at 0.04 means 1 req/25s instead of 25 req/s. |
| P3 | Constructor arg swap | **CRITICAL** | `(client_id, access_token)` → `(access_token, client_id)`. Positional callers silently swap credentials. |
| P4 | Metrics not wired | **HIGH** | `MetricsRegistry` exists in greenfield but is never called in the request path. Archive increments `dhan_request_total`, `dhan_errors_total`, `dhan_request_duration_seconds` on every request. |
| P5 | Duplicate CB/RL/Retry | **HIGH** | 3 CB, 3 RL, 2 retry implementations. Fixes in one are not propagated. |
| P6 | CB threshold mismatch | **MEDIUM** | Greenfield `success_threshold=1`; archive `success_threshold=3`. Greenfield closes circuits faster but with less confidence the server has recovered. |
| P7 | CB recovery timeout mismatch | **MEDIUM** | Greenfield write CB: 60s; archive write CB: 30s. Greenfield blocks order placement for 2× longer after a failure storm. |
| P8 | DH-906 detection method | **MEDIUM** | Archive: text scan (`"DH-906" in body`); greenfield: structured field (`errorCode == "DH-906"`). Format changes break greenfield silently. |
| P9 | No `DhanResilienceConfig` in greenfield | **MEDIUM** | All thresholds hardcoded. Cannot tune without code change. Archive supports runtime config via `DhanResilienceConfig.from_dict()`. |
| P10 | Generic token refresh failure no backoff | **LOW** | Both implementations skip backoff on non-rate-limit refresh exceptions, allowing rapid retry storms. |
| P11 | `get()` signature differs | **LOW** | Archive: `get(endpoint)`. Greenfield: `get(endpoint, params=None)`. Archive `get()` has no `params` support. |
| P12 | Category count mismatch | **LOW** | Archive: 4 CB categories (orders, market_data, portfolio, admin). Greenfield: 3 (read, write, admin). Portfolio merged into admin — a portfolio failure storm can trip the admin CB, blocking order-book reads. |
