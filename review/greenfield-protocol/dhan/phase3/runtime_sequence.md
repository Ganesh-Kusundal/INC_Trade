# Phase 3 — Rate Limiting · Runtime Sequence

> **Protocol:** Greenfield Broker Replication — Dhan  
> **Phase:** 3 (Rate Limiting, Circuit Breaking, Retry)  
> **Date:** 2026-07-03

---

## 1. Archive HTTP Request Lifecycle (11-Step Flow)

The archive `DhanHttpClient._request()` method implements an 11-step request lifecycle spanning circuit breaker pre-check, rate limiting, adaptive throttle, URL construction, retry loop with multi-status handling, and metrics observation.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DhanHttpClient._request(method, endpoint, json)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Step 1: CIRCUIT BREAKER PRE-CHECK                                         │
│  ├── cb = _get_circuit_breaker(endpoint)                                    │
│  ├── Route to read/write/admin CB by prefix matching                        │
│  ├── IF cb.state == OPEN AND NOT cb.allow_request():                        │
│  │   └── RAISE DhanError("Circuit breaker open: {method} {endpoint}")       │
│  │       (fast-fail, no HTTP call made)                                     │
│  │                                                                          │
│  Step 2: RATE LIMIT TOKEN ACQUISITION                                       │
│  ├── IF NOT _acquire_rate_limit_token(endpoint, timeout=5.0):               │
│  │   ├── category = _rate_limit_bucket(endpoint)                            │
│  │   ├── acquired = _rate_limiter.acquire(category, tokens=1, timeout=5.0)  │
│  │   ├── On success: _rate_metrics.record_request(category)                 │
│  │   ├── On timeout: _rate_metrics.record_rejection(category)               │
│  │   └── RAISE DhanError("Rate limit timeout: {method} {endpoint}")         │
│  │                                                                          │
│  Step 3: ADAPTIVE THROTTLE                                                  │
│  ├── _throttle(endpoint)                                                    │
│  ├── static_interval = match against config.rate_limit.limits               │
│  ├── adaptive_interval = match against _adaptive_intervals (from 429s)      │
│  ├── min_interval = max(static_interval, adaptive_interval)                 │
│  ├── IF elapsed < min_interval:                                             │
│  │   └── time.sleep(min_interval - elapsed)                                 │
│  └── Record _last_request_time[endpoint] = now                              │
│                                                                             │
│  Step 4: URL CONSTRUCTION                                                   │
│  ├── url = f"{base_url}{endpoint}" IF endpoint.startswith("/")              │
│  └── url = endpoint (if already absolute)                                   │
│                                                                             │
│  Step 5: METRICS — REQUEST START                                            │
│  ├── _start = time.monotonic()                                              │
│  └── dhan_request_total.inc()                                               │
│                                                                             │
│  Step 6: RETRY LOOP (attempts 1..max_attempts)                              │
│  ├── max_attempts = config.retry.max_retries (default 3) IF retry enabled   │
│  │                                                                          │
│  │  ┌── FOR attempt IN 1..max_attempts: ──────────────────────────────┐     │
│  │  │                                                                  │     │
│  │  │  Step 6a: SEND RAW HTTP                                         │     │
│  │  │  ├── resp = _send_raw_http(method, url, json)                   │     │
│  │  │  ├── session.request(method, url, json=json, timeout=timeout)   │     │
│  │  │  ├── ON RequestException:                                       │     │
│  │  │  │   ├── cb.on_failure()                                        │     │
│  │  │  │   └── RAISE DhanError("HTTP {method} {url} failed: {exc}")   │     │
│  │  │  │                                                              │     │
│  │  │  │  CATCH DhanError (network error):                            │     │
│  │  │  ├── IF attempt < max_attempts:                                 │     │
│  │  │  │   ├── delay = _backoff_delay(attempt)                        │     │
│  │  │  │   ├── time.sleep(delay)                                      │     │
│  │  │  │   └── CONTINUE (retry)                                       │     │
│  │  │  └── ELSE: RAISE last_exc                                       │     │
│  │  │                                                                  │     │
│  │  │  Step 6b: HTTP 401 — TOKEN EXPIRED                              │     │
│  │  │  ├── IF resp.status_code == 401:                                │     │
│  │  │  │   ├── IF attempt == 1 AND _try_refresh_token():              │     │
│  │  │  │   │   └── CONTINUE (retry with new token)                    │     │
│  │  │  │   └── ELSE: RAISE AuthenticationError("Token rejected")      │     │
│  │  │  │                                                              │     │
│  │  │  │  Step 6c: HTTP 429 — RATE LIMITED                            │     │
│  │  │  ├── IF resp.status_code == 429:                                │     │
│  │  │  │   ├── IF attempt < max_attempts:                             │     │
│  │  │  │   │   ├── retry_after = _parse_retry_after(resp)             │     │
│  │  │  │   │   ├── IF retry_after:                                    │     │
│  │  │  │   │   │   ├── _adaptive_intervals[key] = max(...)            │     │
│  │  │  │   │   │   └── delay = retry_after                            │     │
│  │  │  │   │   ├── ELSE: delay = _backoff_delay(attempt)             │     │
│  │  │  │   │   ├── time.sleep(delay)                                  │     │
│  │  │  │   │   └── CONTINUE (retry)                                   │     │
│  │  │  │   └── ELSE: RAISE RateLimitError("Rate limited: HTTP 429")   │     │
│  │  │  │                                                              │     │
│  │  │  │  Step 6d: HTTP 5xx — SERVER ERROR                            │     │
│  │  │  ├── IF resp.status_code >= 500:                                │     │
│  │  │  │   ├── cb.on_failure()                                        │     │
│  │  │  │   ├── IF attempt < max_attempts:                             │     │
│  │  │  │   │   ├── delay = _backoff_delay(attempt)                    │     │
│  │  │  │   │   ├── time.sleep(delay)                                  │     │
│  │  │  │   │   └── CONTINUE (retry)                                   │     │
│  │  │  │   └── ELSE: RAISE DhanError("HTTP {status} — {body[:200]}")  │     │
│  │  │  │                                                              │     │
│  │  │  │  Step 6e: HTTP 4xx — CLIENT ERROR (DH-906/DH-808 detection) │     │
│  │  │  ├── IF resp.status_code >= 400:                                │     │
│  │  │  │   ├── IF status==400 AND ("DH-906" OR "DH-808" OR            │     │
│  │  │  │   │   "Invalid Token" IN body):                              │     │
│  │  │  │   │   ├── IF attempt == 1 AND _try_refresh_token():          │     │
│  │  │  │   │   │   └── CONTINUE (retry with new token)                │     │
│  │  │  │   │   └── ELSE: RAISE AuthenticationError("DH-906")          │     │
│  │  │  │   └── ELSE: RAISE DhanError("HTTP {status} — {body[:300]}")  │     │
│  │  │  │                                                              │     │
│  │  │  │  Step 6f: HTTP 2xx — SUCCESS                                  │     │
│  │  │  ├── data = resp.json()                                         │     │
│  │  │  ├── IF data["status"] == "failure":                            │     │
│  │  │  │   ├── cb.on_failure()                                        │     │
│  │  │  │   └── RAISE DhanError("API failure: {remarks}")              │     │
│  │  │  ├── cb.on_success()                                            │     │
│  │  │  └── RETURN data                                                │     │
│  │  │                                                                  │     │
│  │  └── END FOR ──────────────────────────────────────────────────────┘     │
│  │                                                                          │
│  Step 7: METRICS — REQUEST END (in finally block)                           │
│  ├── ON any exception: dhan_errors_total.inc()                              │
│  └── FINALLY: dhan_request_duration_seconds.observe(time.monotonic() - _start)│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Archive Backoff Formula

```python
# http_client.py._backoff_delay()
delay_ms = min(base_delay_ms × 2^(attempt - 1), max_delay_ms)
# Default: base_delay_ms=500, max_delay_ms=5000
# Attempt 1: 500ms, Attempt 2: 1000ms, Attempt 3: 2000ms, capped at 5000ms
return delay_ms / 1000.0  # Convert to seconds
```

### 1.2 Archive Token Refresh Flow

```
_try_refresh_token()
├── Check _refresh_backoff_until (rate limit backoff active?)
│   └── IF now < _refresh_backoff_until: RETURN False
├── Check cooldown (config.token.refresh_cooldown_seconds)
│   └── IF now - _last_refresh_time < cooldown: RETURN False
├── IF _token_refresh_fn is None: RETURN False
├── TRY:
│   ├── new_token = _token_refresh_fn()
│   ├── IF new_token:
│   │   ├── _last_refresh_time = now
│   │   ├── update_token(new_token)  # Updates session header
│   │   ├── Clear _refresh_backoff_if set
│   │   └── RETURN True
│   └── ELSE (returned None — likely rate limited):
│       ├── _refresh_backoff_until = now + rate_limit_backoff_seconds
│       └── RETURN False
├── CATCH Exception:
│   ├── IF "once every 2 minutes" OR "rate limit" in error:
│   │   ├── _refresh_backoff_until = now + rate_limit_backoff_seconds
│   │   └── RETURN False
│   └── ELSE: log warning, RETURN False
└── RETURN False (fallback)
```

---

## 2. Greenfield HTTP Request Lifecycle (5-Step Flow)

The greenfield `BaseResilientHttpClient._request()` implements a streamlined 5-step flow that delegates to the CB's `call()` wrapper around the retry's `call()` wrapper.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BaseResilientHttpClient._request(method, endpoint, **kwargs)               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Step 1: CATEGORIZE ENDPOINT                                                │
│  ├── category = self._categorize(endpoint)                                  │
│  │   (DhanHttpClient: checks READ_PREFIXES, WRITE_PREFIXES, defaults admin)│
│  └── cb = self._circuit_breakers.get(category, self._circuit_breakers["admin"])│
│                                                                             │
│  Step 2: RATE LIMIT                                                         │
│  ├── self._apply_rate_limit(endpoint)                                       │
│  ├── FOR prefix, limiter IN self._rate_limiters.items():                    │
│  │   ├── IF endpoint.startswith(prefix):                                    │
│  │   │   ├── matched = limiter                                              │
│  │   │   └── BREAK                                                          │
│  └── IF matched: matched.acquire(1, timeout=5.0)                            │
│                                                                             │
│  Step 3: DEFINE INNER REQUEST FUNCTION                                      │
│  └── def _do_request() -> dict:                                             │
│      ├── url = self._build_url(endpoint)                                    │
│      ├── resp = self._session.request(method, url, timeout=self._timeout)   │
│      └── return self._handle_response(resp)                                 │
│                                                                             │
│  Step 4: EXECUTE WITH CB + RETRY WRAPPERS                                   │
│  ├── TRY:                                                                   │
│  │   └── RETURN cb.call(                                                    │
│  │         lambda: self._retry.call(_do_request),                           │
│  │         ignored_exceptions=(AuthenticationError, RateLimitError,         │
│  │                             BrokerError),                                │
│  │       )                                                                  │
│  │                                                                          │
│  │  CATCH TokenRefreshSignal:                                                │
│  │  ├── Log "token_refreshed_retrying"                                      │
│  │  └── TRY:                                                                │
│  │  │   └── RETURN cb.call(                                                 │
│  │  │         lambda: self._retry.call(_do_request),  # Full retry again    │
│  │  │         ignored_exceptions=(...),                                     │
│  │  │       )                                                               │
│  │  └── CATCH Exception: RAISE BrokerError(str(exc))                        │
│  │                                                                          │
│  │  CATCH Exception:                                                        │
│  └── IF isinstance(exc, BrokerError): RAISE                                 │
│      ELSE: RAISE BrokerError(str(exc)) from exc                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Greenfield Response Handling (`DhanHttpClient._handle_response`)

```
_handle_response(resp)
├── IF resp.status_code == 401:
│   ├── IF _token_refresh_fn is not None:
│   │   ├── new_token = _try_refresh_token()
│   │   ├── IF new_token:
│   │   │   ├── update_token(new_token)
│   │   │   └── RAISE TokenRefreshSignal("Token refreshed, retrying request")
│   └── RAISE AuthenticationError("Token expired or invalid")
│
├── IF resp.status_code == 429:
│   ├── retry_after = _parse_retry_after(resp)  # Defaults to 30.0 if missing
│   ├── IF retry_after: update _adaptive_intervals
│   └── RAISE RateLimitError("Rate limit exceeded", retry_after=retry_after)
│       (NOTE: RateLimitError is in ignored_exceptions for CB, but NOT retried)
│
├── IF resp.status_code >= 500:
│   └── RAISE BrokerServerError("HTTP {status}: {msg}", code=str(status))
│       (NOTE: BrokerServerError IS retryable via RetryPolicy.retryable_exceptions)
│
├── IF resp.status_code >= 400:
│   ├── IF _is_token_error(status_code, error_code, msg):
│   │   ├── IF _token_refresh_fn is not None:
│   │   │   ├── new_token = _try_refresh_token()
│   │   │   ├── IF new_token:
│   │   │   │   ├── update_token(new_token)
│   │   │   │   └── RAISE TokenRefreshSignal(...)
│   │   └── RAISE AuthenticationError("Token rejected: {msg}")
│   └── RAISE BrokerError("HTTP {status}: {msg}", code=str(status))
│
├── TRY: data = resp.json()
│   CATCH: RETURN {"data": resp.text}
│
├── IF data["status"] == "failure":
│   └── RAISE BrokerError("API failure: {remarks}")
│
└── RETURN data
```

### 2.2 Greenfield Backoff Formula

```python
# retry.py._compute_delay()
delay = base_delay_ms × 2^attempt  # attempt starts at 0
delay = min(delay, max_delay_ms)
jitter = random.randint(0, delay // 4)
return delay + jitter

# Default: base_delay_ms=500, max_delay_ms=5000
# Attempt 0: 500ms + jitter(0-125ms)
# Attempt 1: 1000ms + jitter(0-250ms)
# Attempt 2: 2000ms + jitter(0-500ms)
# Capped at 5000ms
```

### 2.3 Greenfield Token Refresh Flow

```
_try_refresh_token() -> str | None
├── Check _refresh_backoff_until
│   └── IF now < _refresh_backoff_until: RETURN None
├── Check cooldown (_refresh_cooldown_seconds, default 60.0)
│   └── IF now - _last_refresh_time < cooldown: RETURN None
├── Define _do_refresh():
│   ├── IF _refresh_lock is not None:
│   │   ├── acquired = _refresh_lock.acquire(timeout=5.0)
│   │   ├── IF NOT acquired: RETURN None
│   │   ├── TRY: RETURN _token_refresh_fn()
│   │   └── FINALLY: _refresh_lock.release()
│   └── ELSE: RETURN _token_refresh_fn()
├── TRY:
│   ├── new_token = _do_refresh()
│   ├── IF new_token:
│   │   ├── _last_refresh_time = now
│   │   ├── _refresh_backoff_until = 0.0
│   │   └── RETURN new_token
│   └── ELSE:
│       ├── _refresh_backoff_until = now + _rate_limit_backoff_seconds
│       └── RETURN None
├── CATCH Exception:
│   ├── IF "once every 2 minutes" OR "rate limit" in error:
│   │   ├── _refresh_backoff_until = now + _rate_limit_backoff_seconds
│   │   └── RETURN None
│   └── ELSE: log warning, RETURN None
└── RETURN None
```

---

## 3. Key Structural Differences

### 3.1 Architecture Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Request flow | Explicit 11-step in `_request()` | Composed: `cb.call(retry.call(_do_request))` |
| CB check | Pre-check before retry loop | Inside `cb.call()` wrapper |
| Rate limit | Token bucket + adaptive throttle (2 layers) | Token bucket only (1 layer) |
| Retry loop | Explicit `for attempt in range()` | `RetryPolicy.call()` wrapper |
| 429 handling | Retried with adaptive backoff | Raises `RateLimitError` (not retried) |
| 401 handling | Retried once after token refresh | `TokenRefreshSignal` → full retry of `cb.call(retry.call())` |
| DH-906 detection | Text scan: `"DH-906" in body` | Structured: `error_code in {"DH-906", "DH-808"}` |
| Metrics | Inline in `_request()` (hot path) | Decorator-based (not in hot path) |
| CB categories | 4 (orders/market_data/portfolio/admin) | 3 (read/write/admin) |
| Retry policies | Per-category (4 policies) | Single global policy |

### 3.2 Retry Behavior Comparison

| Status Code | Archive Behavior | Greenfield Behavior |
|-------------|------------------|---------------------|
| 2xx (success) | `cb.on_success()`, return data | Return data (CB records success via `call()`) |
| 2xx (status=failure) | `cb.on_failure()`, raise `DhanError` | Raise `BrokerError` (CB records failure via `call()`) |
| 401 | Retry once after token refresh | `TokenRefreshSignal` → full re-execution |
| 429 | Retry with adaptive backoff | Raise `RateLimitError` (not retried) |
| 4xx (DH-906/DH-808) | Retry once after token refresh | `TokenRefreshSignal` → full re-execution |
| 4xx (other) | Raise `DhanError` immediately | Raise `BrokerError` (not retried) |
| 5xx | `cb.on_failure()`, retry with backoff | Raise `BrokerServerError` (retried via `RetryPolicy`) |
| Network error | `cb.on_failure()`, retry with backoff | Not caught by `_handle_response`; propagated as `RequestException` (retried) |

### 3.3 Rate Limiting Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Token bucket | `MultiBucketRateLimiter` (4 buckets) | Per-prefix `TokenBucketRateLimiter` (6 limiters) |
| Bucket categories | orders/market_data/portfolio/admin | Per-endpoint prefix |
| Adaptive throttle | `_throttle()` with `_adaptive_intervals` | `_adaptive_intervals` dict (updated but not enforced in `_request()`) |
| Rate limit values | Correct: `rate_per_second=25.0` for orders | **BUG**: `rate_per_second=0.04` for `/orders` (inverted) |
| Timeout behavior | 5s timeout, raises `DhanError` on timeout | 5s timeout, blocks in `acquire()` |
| Metrics | `DhanRateLimiterMetrics` (RPS, queue depth, rejections) | No RL-specific metrics |

### 3.4 Circuit Breaker Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| API style | Pull-based: `cb.state`, `cb.allow_request()`, `cb.on_success()`, `cb.on_failure()` | Push-based: `cb.call(fn, ignored_exceptions)` |
| Success threshold | 3 (requires 3 consecutive successes to close) | 1 (single success closes) |
| Write open duration | 30,000ms (30s) | 60.0s |
| Categories | 4 named CBs | 3 hardcoded CBs |
| Ignored exceptions | N/A (manual recording) | `(AuthenticationError, RateLimitError, BrokerError)` — but `BrokerServerError` is NOT ignored |
| Metrics | `CircuitBreakerMetrics` (total_calls, success_count, failure_count, state_changes) | `CircuitBreakerMetrics` (same fields) |

### 3.5 Token Refresh Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Cooldown | `config.token.refresh_cooldown_seconds` | `_REFRESH_COOLDOWN_SECONDS = 60.0` |
| Rate limit backoff | `config.token.rate_limit_backoff_seconds` | `_RATE_LIMIT_BACKOFF_SECONDS = 130.0` |
| Concurrency safety | No shared lock | Optional `refresh_lock: threading.Lock` |
| Return shape | `bool` (success/failure) | `str \| None` (new token or None) |
| Caller updates token | `update_token()` called inside `_try_refresh_token()` | Caller calls `update_token()` after receiving token |

---

## 4. Sequence Diagrams

### 4.1 Archive: Successful Request

```
Client              DhanHttpClient           CircuitBreaker        RateLimiter          Dhan API
  │                      │                        │                    │                    │
  │── get("/orders") ───▶│                        │                    │                    │
  │                      │── _get_circuit_breaker ─▶│                   │                    │
  │                      │◀── cb (write) ─────────│                    │                    │
  │                      │── cb.state? ───────────▶│                    │                    │
  │                      │◀── CLOSED ─────────────│                    │                    │
  │                      │── acquire("orders") ───────────────────────▶│                    │
  │                      │◀── True ───────────────────────────────────│                    │
  │                      │── _throttle("/orders") │                    │                    │
  │                      │── sleep if needed      │                    │                    │
  │                      │── _send_raw_http ─────────────────────────────────────────────▶│
  │                      │◀── 200 OK ────────────────────────────────────────────────────│
  │                      │── cb.on_success() ────▶│                    │                    │
  │                      │── return data ────────▶│                    │                    │
  │◀── {"data": ...} ────│                        │                    │                    │
```

### 4.2 Archive: 429 → Adaptive Backoff → Retry

```
Client              DhanHttpClient           RateLimiter          Dhan API
  │                      │                       │                    │
  │── post("/quote") ───▶│                       │                    │
  │                      │── acquire ───────────▶│                    │
  │                      │◀── True ─────────────│                    │
  │                      │── _throttle ──────────│                    │
  │                      │── HTTP POST ─────────────────────────────▶│
  │                      │◀── 429 Too Many Requests ────────────────│
  │                      │── parse Retry-After ──│                    │
  │                      │── _adaptive_intervals[key] = retry_after   │
  │                      │── sleep(retry_after) ─│                    │
  │                      │── HTTP POST (retry) ─────────────────────▶│
  │                      │◀── 200 OK ────────────────────────────────│
  │                      │── cb.on_success() ────│                    │
  │◀── data ─────────────│                       │                    │
```

### 4.3 Greenfield: TokenRefreshSignal Flow

```
Client              DhanHttpClient        BaseResilientHttpClient    CircuitBreaker     RetryPolicy      Dhan API
  │                      │                        │                      │                 │                │
  │── get("/holdings") ─▶│                        │                      │                 │                │
  │                      │── _categorize ────────▶│                      │                 │                │
  │                      │◀── "admin" ───────────│                      │                 │                │
  │                      │── _apply_rate_limit ──▶│                      │                 │                │
  │                      │                        │── cb.call(lambda) ──▶│                 │                │
  │                      │                        │                      │── retry.call() ─▶│               │
  │                      │                        │                      │                 │── _do_request()│
  │                      │                        │                      │                 │── HTTP GET ───▶│
  │                      │                        │                      │                 │◀── 401 ───────│
  │                      │                        │                      │                 │── _handle_response
  │                      │◀── TokenRefreshSignal ─│                      │                 │
  │                      │── _try_refresh_token() │                      │                 │
  │                      │── update_token() ──────│                      │                 │
  │                      │                        │                      │                 │
  │                      │                        │── cb.call(lambda) ──▶│                 │                │
  │                      │                        │                      │── retry.call() ─▶│               │
  │                      │                        │                      │                 │── _do_request()│
  │                      │                        │                      │                 │── HTTP GET ───▶│
  │                      │                        │                      │                 │◀── 200 ───────│
  │                      │                        │                      │                 │── return data ─▶│
  │◀── data ─────────────│                        │                      │                 │                │
```

### 4.4 Greenfield: 5xx Retry via RetryPolicy

```
Client              BaseResilientHttpClient    CircuitBreaker     RetryPolicy      Dhan API
  │                        │                      │                 │                │
  │── get("/positions") ──▶│                      │                 │                │
  │                        │── cb.call(lambda) ──▶│                 │                │
  │                        │                      │── retry.call() ─▶│               │
  │                        │                      │                 │── _do_request()│
  │                        │                      │                 │── HTTP GET ───▶│
  │                        │                      │                 │◀── 500 ───────│
  │                        │                      │                 │── _handle_response
  │                        │                      │                 │── RAISE BrokerServerError
  │                        │                      │                 │── sleep(500ms+jitter)
  │                        │                      │                 │── _do_request()│
  │                        │                      │                 │── HTTP GET ───▶│
  │                        │                      │                 │◀── 200 ───────│
  │                        │                      │                 │── return data ─▶│
  │                        │                      │── record_success▶│               │
  │◀── data ───────────────│                      │                 │                │
```

---

## 5. Critical Behavioral Gaps

### 5.1 429 Not Retried (CRITICAL)

**Archive:** On HTTP 429, the archive retries with adaptive backoff:
1. Parses `Retry-After` header
2. Updates `_adaptive_intervals` for future throttle adjustment
3. Sleeps for `retry_after` or exponential backoff
4. Retries the request

**Greenfield:** On HTTP 429:
1. Parses `Retry-After` header
2. Updates `_adaptive_intervals` (but this is never read in `_request()`)
3. Raises `RateLimitError` immediately — **no retry**

The `RateLimitError` is in `ignored_exceptions` for the CB, so it doesn't trip the breaker, but the retry loop in `RetryPolicy` only catches `retryable_exceptions=(RequestException, BrokerServerError)`. `RateLimitError` is NOT in this tuple, so it propagates to the caller.

### 5.2 Adaptive Throttle Not Enforced (HIGH)

**Archive:** `_throttle()` is called on every request, enforcing both static and adaptive intervals.

**Greenfield:** `_adaptive_intervals` is updated in `_handle_response()` but never read or enforced anywhere in the request path. The `_apply_rate_limit()` method only uses the static `RATE_LIMITS` dict.

### 5.3 Metrics Not in Hot Path (HIGH)

**Archive:** `dhan_request_total.inc()` and `dhan_request_duration_seconds.observe()` are called inline in `_request()`.

**Greenfield:** Metrics are collected via the `observe_metrics` decorator in `metrics.py`, but this decorator is never applied to `DhanHttpClient._request()` or any method in the request path. The `MetricsRegistry` methods exist but are not called from the HTTP client.
