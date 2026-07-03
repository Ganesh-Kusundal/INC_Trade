# PHASE 3+8 FORENSIC AUDIT — Rate Limiting + Cross-Cutting Concerns
## Greenfield Broker Replication Protocol

**Auditor:** Antigravity  
**Date:** 2026-07-03  
**Scope:** Dhan broker resilience stack — archive vs. greenfield  
**Oracle:** Archive test suite (test_chaos.py, test_circuit_breaker_regression.py, test_edge_cases.py, test_http_client.py, test_error_paths.py)

---

## 1. SOURCE AUDIT

### Archive Files Read (100% line coverage)

| File | Lines | Purpose |
|---|---|---|
| archive/brokers/dhan/http_client.py | 558 | Primary HTTP client — token refresh, retry, CB routing |
| archive/brokers/dhan/resilience/circuit_breaker.py | 120 | Dhan CB factory (orders/market_data/portfolio/admin) |
| archive/brokers/dhan/resilience/rate_limiter.py | 218 | Token-bucket factory + metrics |
| archive/brokers/dhan/resilience/retry_executor.py | 178 | Per-category retry policies |
| archive/brokers/dhan/resilience/websocket_rate_limiter_simple.py | 156 | WS connection rate limiting |
| archive/brokers/dhan/exceptions.py | 144 | Exception hierarchy |
| archive/brokers/dhan/invariants.py | 264 | Payload identity assertions |
| archive/brokers/dhan/metrics.py | 43 | Prometheus counters/histograms |
| archive/brokers/dhan/status_mapper.py | 41 | Order status normalization |
| archive/tests/unit/test_http_client.py | 81 | Unit oracle — HTTP lifecycle |
| archive/tests/unit/test_circuit_breaker_regression.py | 100 | DH-906 regression oracle |
| archive/tests/unit/test_chaos.py | 861 | Chaos oracle — CB/retry/RL integration |
| archive/tests/unit/test_edge_cases.py | 229 | Edge-case oracle |
| archive/tests/integration/test_error_paths.py | 134 | Integration oracle (live-env gated) |

### Greenfield Files Read (100% line coverage)

| File | Lines | Purpose |
|---|---|---|
| brokers/adapters/dhan/http.py | 272 | Greenfield Dhan HTTP client |
| brokers/resilience/http_client.py | 138 | Abstract BaseResilientHttpClient |
| brokers/resilience/circuit_breaker.py | 139 | Greenfield CB implementation |
| brokers/resilience/rate_limiter.py | 64 | Greenfield TokenBucketRateLimiter |
| brokers/resilience/retry.py | 50 | Greenfield RetryPolicy |
| brokers/infrastructure/resilience/circuit_breaker.py | 70 | DUPLICATE CB implementation |
| brokers/infrastructure/resilience/rate_limiter.py | 52 | DUPLICATE rate limiter + MultiBucketRateLimiter |
| brokers/infrastructure/resilience/retry_executor.py | 75 | DUPLICATE retry executor |
| brokers/adapters/dhan/exceptions.py | 35 | Greenfield Dhan exceptions |
| brokers/adapters/dhan/metrics.py | 66 | Greenfield Prometheus metrics |
| brokers/domain/exceptions.py | 123 | Greenfield domain exception hierarchy |
| brokers/adapters/dhan/config.py | 116 | Greenfield rate limits + endpoint prefixes |

---

## 2. RUNTIME SEQUENCE — Exact HTTP Request Lifecycle

### Archive Lifecycle (archive/brokers/dhan/http_client.py)

```
caller → DhanHttpClient.post/get/put/delete(endpoint)
          |
          v
        _request(method, endpoint)
          |
          |-- [1] Circuit Breaker Pre-check
          |       _get_circuit_breaker(endpoint)          [line 384]
          |         └─ _categorize_endpoint(endpoint)     [lines 85-91]
          |               write_prefixes → "write"
          |               read_prefixes  → "read"
          |               else           → "admin"
          |       if cb.state == OPEN and not cb.allow_request():
          |           raise DhanError("Circuit breaker open: ...")  [line 386]
          |
          |-- [2] Token Bucket Rate Limiter
          |       _acquire_rate_limit_token(endpoint)     [line 389]
          |         └─ _rate_limit_bucket(endpoint)
          |               → category → bucket_map → bucket name
          |         └─ self._rate_limiter.acquire(category, tokens=1, timeout=5.0)
          |       if not acquired:
          |           raise DhanError("Rate limit timeout: ...")    [line 390]
          |
          |-- [3] Adaptive Throttle (interval-based)
          |       _throttle(endpoint)                     [line 392]
          |         └─ _match_rate_limit vs config.rate_limit.limits
          |         └─ max(static_interval, adaptive_interval)
          |         └─ time.sleep(remaining) if needed
          |
          |-- [4] URL construction                         [line 393]
          |
          |-- [5] Retry loop (max_attempts = config.retry.max_retries)
          |       for attempt in range(1, max_attempts + 1):
          |         |
          |         |-- _send_raw_http(method, url, json)  [line 407]
          |         |     └─ session.request(method, url, ...)
          |         |     └─ on RequestException: cb.on_failure(); raise DhanError
          |         |
          |         |-- HTTP 401                           [line 435]
          |         |     attempt==1 → _try_refresh_token() → continue
          |         |     else       → raise AuthenticationError
          |         |
          |         |-- HTTP 429                           [line 444]
          |         |     attempt < max → parse Retry-After
          |         |                     update _adaptive_intervals
          |         |                     time.sleep(delay); continue
          |         |     else → raise RateLimitError
          |         |
          |         |-- HTTP 5xx                           [line 477]
          |         |     cb.on_failure()
          |         |     attempt < max → time.sleep(backoff); continue
          |         |     else → raise DhanError
          |         |
          |         |-- HTTP 4xx with DH-906/DH-808        [lines 501-510]
          |         |     attempt==1 → _try_refresh_token() → continue
          |         |     else → raise AuthenticationError
          |         |
          |         |-- HTTP 4xx other                     [line 520]
          |         |     raise DhanError
          |         |
          |         └─ HTTP 2xx                           [lines 523-536]
          |               resp.json() or raise DhanError(invalid JSON)
          |               data["status"] == "failure" → cb.on_failure(); raise DhanError
          |               cb.on_success()
          |               return data
          |
          └─ Metrics: dhan_request_total.inc()            [line 399]
                       dhan_errors_total.inc() on exception [line 543]
                       dhan_request_duration_seconds.observe() always [line 546]
```

**Backoff formula** (_backoff_delay, line 550-554):
  delay_ms = min(base_delay_ms * 2^(attempt-1), max_delay_ms)
Defaults from DEFAULT_CONFIG: base_delay_ms=500, max_delay_ms=5000
→ Attempt 1: 500ms, Attempt 2: 1000ms, Attempt 3: 2000ms, cap 5000ms

---

### Greenfield Lifecycle (brokers/adapters/dhan/http.py + brokers/resilience/http_client.py)

```
caller → DhanHttpClient.get/post/put/delete(endpoint)
            (inherited from BaseResilientHttpClient)
          |
          v
        _request(method, endpoint)                      [http_client.py line 83]
          |
          |-- [1] Categorize endpoint                    [line 84]
          |       _categorize(endpoint)                 [http.py lines 105-112]
          |         READ_PREFIXES → "read"
          |         WRITE_PREFIXES → "write"
          |         else → "admin"
          |
          |-- [2] Circuit Breaker selection              [line 85]
          |       cb = _circuit_breakers[category]
          |       (read/write/admin hardcoded at init)  [http_client.py lines 55-59]
          |
          |-- [3] Rate Limiter (prefix-based, interval)  [line 87]
          |       _apply_rate_limit(endpoint)
          |         iterates self._rate_limiters dict
          |         if endpoint.startswith(prefix) → limiter.acquire(1, timeout=5.0)
          |
          |-- [4] cb.call(lambda: retry.call(_do_request), ...)  [line 95]
          |         └─ _do_request():
          |               url = _build_url(endpoint)   [http.py lines 114-117]
          |               resp = session.request(...)
          |               return _handle_response(resp) [http.py lines 119-179]
          |                        401 → _try_refresh_token()
          |                               → raise TokenRefreshSignal (triggers one retry pass)
          |                        429 → update _adaptive_intervals
          |                               → raise RateLimitError
          |                        5xx → raise BrokerServerError
          |                        4xx → check DH-906/DH-808 → AuthenticationError or BrokerError
          |                        2xx → parse json; check status=="failure"
          |
          |-- [5] On TokenRefreshSignal:                 [line 99]
          |       ONE additional pass: cb.call(retry.call(_do_request))
          |       (no loop — exactly one extra pass)
          |
          └─ Metrics: NOT wired into _request path
                       MetricsRegistry exists as decorator only [metrics.py lines 48-65]
```

**Key structural differences:**
- Archive: explicit retry loop with attempt counter; _send_raw_http is the raw-HTTP boundary
- Greenfield: RetryPolicy.call() wraps _do_request; CircuitBreaker.call() wraps that
- Archive: CB checked BEFORE rate limiter; Greenfield: rate limiter BEFORE CB (inside cb.call)

---

## 3. STATE MACHINE — Circuit Breaker

### Archive CB (brokers/common/resilience/circuit_breaker.py, imported by archive factories)

> Note: Archive uses CircuitBreaker from brokers.common.resilience.circuit_breaker. The Dhan factory (archive/resilience/circuit_breaker.py) wraps it with category-specific configs.

**States:** CLOSED → OPEN → HALF_OPEN → CLOSED

```
CLOSED
  | on_failure() count reaches failure_threshold
  v
OPEN (fast-fail all requests)
  | after open_duration_ms elapses → allow_request() → True
  v
HALF_OPEN (probe state)
  | on_success() × success_threshold → CLOSED
  | on_failure() → OPEN (immediately)
  v
CLOSED
```

**Exact thresholds from archive (DhanCircuitBreakerFactory, lines 22-31):**

| Category | failure_threshold | success_threshold | open_duration_ms |
|---|---|---|---|
| orders | 3 | 3 | 30,000 ms |
| market_data | 5 | 3 | 30,000 ms |
| portfolio | 5 | 3 | 30,000 ms |
| admin | 5 | 3 | 30,000 ms |

**Test confirmation** (test_chaos.py lines 230-256):
- cb.config.failure_threshold == 3 for orders ✅
- cb.config.open_duration_ms == 30_000 ✅
- cb.config.success_threshold == 3 ✅

---

### Greenfield CB A — brokers/resilience/circuit_breaker.py

**Constructor signature** (lines 37-60):
  CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=1)

**Hardcoded in BaseResilientHttpClient** (http_client.py lines 55-59):
  "read":  CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
  "write": CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
  "admin": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

**Key deviations from archive:**
1. success_threshold=1 (default) vs archive success_threshold=3 — greenfield closes circuit after just 1 success in HALF_OPEN
2. recovery_timeout is in seconds (float) vs archive open_duration_ms in milliseconds (int) — different units, no bug if both resolve to same wall time
3. Write CB: recovery_timeout=60.0s vs archive 30,000ms (30s) — greenfield write CB doubles recovery time
4. HALF_OPEN check: archive reads _opened_at timestamp; greenfield reads _last_failure_time with time.monotonic() — both correct but reference points differ

---

### Greenfield CB B — brokers/infrastructure/resilience/circuit_breaker.py (DUPLICATE)

**Constructor signature** (lines 16-24):
  CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3)

Thresholds here are closer to archive (success_threshold=3), but this class is NOT wired into BaseResilientHttpClient or DhanHttpClient. The RetryExecutor in brokers/infrastructure/resilience/retry_executor.py references this CB class, but DhanHttpClient never instantiates RetryExecutor.

**State machine difference** (infrastructure CB, lines 32-69):
- Uses time.time() (wall clock) vs greenfield resilience CB which uses time.monotonic()
- allow_request() is a separate method (not call()), matching archive pattern

---

## 4. PUBLIC CONTRACT

### Archive DhanHttpClient Public API

| Method | Signature | Notes |
|---|---|---|
| __init__ | (client_id, access_token, base_url, timeout, token_refresh_fn, enable_retry, circuit_breaker, read_circuit_breaker, write_circuit_breaker, admin_circuit_breaker, session, _rate_limiter, _circuit_breakers, config) | Backward-compat: single circuit_breaker fans out to all 3 |
| post | (endpoint, json) → dict | Routes to _request("POST", ...) |
| get | (endpoint) → dict | |
| put | (endpoint, json) → dict | |
| delete | (endpoint) → dict | |
| update_token | (access_token) → None | Updates session header immediately |
| close | () → None | Closes requests.Session |
| _get_circuit_breaker | (endpoint) → CircuitBreaker | None | Routes by category |

### Greenfield DhanHttpClient Public API

| Method | Signature | Notes |
|---|---|---|
| __init__ | (access_token, client_id, base_url, timeout, token_refresh_fn, refresh_lock, refresh_cooldown_seconds, rate_limit_backoff_seconds) | Arg order SWAPPED: access_token first, then client_id |
| get | (endpoint, params) → dict | Has params kwarg — archive does NOT |
| post | (endpoint, json) → dict | |
| put | (endpoint, json) → dict | |
| delete | (endpoint, params) → dict | Has params kwarg — archive does NOT |
| update_token | (new_token) → None | Same behavior |
| close | () → None | |
| client_id | property | Returns self._client_id |
| access_token | property | Returns self._access_token |

**BREAKING API CHANGE:** Constructor arg order swapped. Archive: DhanHttpClient(client_id, access_token, ...). Greenfield: DhanHttpClient(access_token, client_id, ...). Code calling by positional args will silently swap tokens — a silent data corruption bug.

---

### Archive Exception Hierarchy

```
BrokerError (common)
  └─ DhanError
       ├─ InstrumentNotFoundError  (also _CommonInstrumentNotFoundError)
       ├─ MarketDataError
       ├─ OrderError               (also _CommonOrderError)
       ├─ AuthenticationError      (also _CommonAuthenticationError)
       ├─ ConfigurationError
       ├─ DhanIdentityError
       ├─ SuperOrderError
       ├─ ForeverOrderError
       ├─ ConditionalTriggerError
       ├─ LedgerError
       ├─ UserProfileError
       ├─ IPManagementError
       ├─ ExitAllError             (also _CommonExitAllError)
       └─ EDISError
RateLimitError  (re-exported alias to canonical; NOT subclass of DhanError)
```

### Greenfield Exception Hierarchy

```
TradeXV2Error (root)
  ├─ ConfigError
  ├─ DataError
  ├─ ValidationError
  └─ BrokerError
       ├─ RetryableError
       │    └─ NetworkError
       ├─ NonRetryableError
       ├─ BrokerServerError
       ├─ OrderRejectedError
       ├─ RateLimitError
       ├─ CircuitOpenError
       ├─ AuthenticationError
       ├─ TokenRateLimitError
       ├─ InstrumentNotFoundError
       ├─ NotSupportedError
       └─ BrokerDegradedError

Dhan-specific (brokers/adapters/dhan/exceptions.py):
  BrokerError → DhanError
  AuthenticationError → DhanAuthenticationError
  RateLimitError → DhanRateLimitError
  OrderRejectedError → DhanOrderRejectedError
  NetworkError → DhanConnectionError
  BrokerServerError → DhanServerError
```

**Gaps:**
- No DhanIdentityError in greenfield (invariant payload checking has no exception type)
- No SuperOrderError, ForeverOrderError, ConditionalTriggerError, LedgerError, UserProfileError, IPManagementError, EDISError, ExitAllError in greenfield
- Greenfield adds TradeXV2Error root, CircuitOpenError, TokenRateLimitError, BrokerDegradedError — not in archive

---

## 5. FAILURE ANALYSIS

### 5.1 HTTP 429 Handling

**Archive** (http_client.py lines 444-473):
1. Parse Retry-After header via _parse_retry_after() → returns float | None (None if absent)
2. If header present: update _adaptive_intervals[prefix_key] with max(retry_after, current) — ratchets up, never down
3. Backoff = retry_after (header value) OR _backoff_delay(attempt) if absent
4. time.sleep(delay) then continue (retry)
5. After all retries exhausted: raise RateLimitError

**Greenfield** (http.py lines 128-140):
1. Parse Retry-After via _parse_retry_after() → returns float, defaults to 30.0 if absent (archive returns None)
2. Update _adaptive_intervals[key]
3. IMMEDIATELY raises RateLimitError — does NOT retry
4. RetryPolicy in http_client.py retries BrokerServerError but RateLimitError is in ignored_exceptions (line 97) — so 429 is never retried in greenfield

**PARITY GAP — CRITICAL:**
- Archive retries 429 with backoff up to max_retries-1 times
- Greenfield raises immediately on first 429, with no retry
- Greenfield _parse_retry_after defaults to 30.0s if Retry-After header absent (http.py line 197)
- Archive defaults to None — falls back to exponential backoff formula
- Greenfield without header: immediately claims 30s Retry-After in error object but doesn't retry

---

### 5.2 DH-906 Token Rejection Handling

**Archive** (http_client.py lines 497-510):
- Detects: resp.status_code == 400 AND ("DH-906" in body OR "DH-808" in body OR "Invalid Token" in body)
- On attempt 1: calls _try_refresh_token() → if success, continues retry loop
- On attempt > 1 or refresh fails: raises AuthenticationError

**Greenfield** (http.py lines 158-165):
- _is_token_error(status_code, error_code, msg) (lines 199-210):
  - Checks error_code in {"DH-906", "DH-808"} — but error_code is extracted from body["remarks"]["errorCode"]
  - Archive checks body text directly ("DH-906" in body) — more permissive, catches inline error codes
- On detection: calls _try_refresh_token() → if success, raises TokenRefreshSignal
- TokenRefreshSignal triggers exactly ONE additional complete request attempt (lines 99-109)
- If second attempt also triggers TokenRefreshSignal, it is NOT caught again — raises as BrokerError

**PARITY GAP:**
- Archive checks body (raw text) for DH-906; greenfield checks structured body["remarks"]["errorCode"]
- If Dhan returns DH-906 in a non-standard body structure, greenfield detection will miss it
- Archive: refresh → retry in same loop; greenfield: refresh → TokenRefreshSignal → second full cb.call() pass

---

### 5.3 Circuit Breaker Trip Behavior

**Archive:**
- Three independent CBs: read_circuit_breaker, write_circuit_breaker, admin_circuit_breaker
- CB pre-check BEFORE rate limiter (lines 384-386)
- CB fires on_failure() on: 5xx response (line 479), json parse failure + API status=failure (line 531), network error in _send_raw_http (line 376)
- CB fires on_success() on: successful 2xx with valid json (line 535)
- DH-906 regression: Open read CB does NOT block write endpoint — explicitly tested and passing

**Greenfield:**
- Three CBs hardcoded in BaseResilientHttpClient.__init__: read, write, admin (lines 55-59)
- CircuitBreaker.call() wraps the retry loop
- BrokerServerError forces CB failure even when in ignored_exceptions (circuit_breaker.py line 84-85)
- AuthenticationError and RateLimitError never trip the CB (in ignored_exceptions)
- Write CB threshold=3 matches archive orders CB
- No tests exist for the DH-906 regression scenario in greenfield

---

### 5.4 Duplicate Implementations

Three separate, incompatible circuit breaker implementations exist:

| Location | Class | Interface | Used By |
|---|---|---|---|
| brokers/resilience/circuit_breaker.py | CircuitBreaker | .call(fn, ignored_exceptions) | BaseResilientHttpClient, DhanHttpClient |
| brokers/infrastructure/resilience/circuit_breaker.py | CircuitBreaker | .allow_request(), .record_success(), .record_failure() | RetryExecutor in infrastructure |
| brokers/common/resilience/circuit_breaker.py (archive) | CircuitBreaker | .state, .on_failure(), .on_success(), .allow_request(), .reset() | DhanHttpClient (archive) |

Three separate rate limiter implementations:

| Location | Class | Interface |
|---|---|---|
| brokers/resilience/rate_limiter.py | TokenBucketRateLimiter | .acquire(tokens, timeout) → bool; uses Condition.wait |
| brokers/infrastructure/resilience/rate_limiter.py | TokenBucketRateLimiter + MultiBucketRateLimiter | .acquire(tokens, timeout) → bool; uses time.sleep(0.01) spin |
| brokers/common/resilience/rate_limiter.py (archive) | MultiBucketRateLimiter | .acquire(category, tokens, timeout) |

CRITICAL RISK: Neither DhanHttpClient nor BaseResilientHttpClient uses or imports the infrastructure RetryExecutor. The infrastructure executor is orphaned — it has no caller in the greenfield adapter path.

---

## 6. EVIDENCE MATRIX

| Behavior | Archive File:Line | Greenfield File:Line | Match? |
|---|---|---|---|
| CB splits read/write/admin | http_client.py:44-69 | http_client.py:55-59 | YES — structure matches |
| CB write threshold = 3 | circuit_breaker.py:22 | http_client.py:57 | YES |
| CB read/admin threshold = 5 | circuit_breaker.py:25 | http_client.py:56,58 | YES |
| CB success_threshold = 3 | circuit_breaker.py:31 | circuit_breaker.py:41 (default=1) | NO — PARITY GAP |
| CB open_duration = 30s | circuit_breaker.py:28 | http_client.py:56 (30.0s) | YES |
| CB write open_duration = 30s | circuit_breaker.py:28 | http_client.py:57 (60.0s) | NO — PARITY GAP |
| Orders rate = 25 rps | rate_limiter.py:35 | Not wired (interval-based only) | NO — PARITY GAP |
| Market data rate = 10 rps | rate_limiter.py:39 | config.py /marketfeed/ltp:0.15 | Partial (different mechanism) |
| Admin rate = 10 rps | rate_limiter.py:51 | Not defined | MISSING |
| Portfolio rate = 20 rps | rate_limiter.py:47 | Not defined | MISSING |
| Token bucket acquire timeout=5s | http_client.py:249 | http_client.py:122 | YES |
| 429 retry with backoff | http_client.py:444-473 | http.py:128-140 (no retry) | NO — CRITICAL GAP |
| 429 Retry-After default None | http_client.py:294-300 | http.py:196 (default 30.0) | NO — different default |
| DH-906 detection (text scan) | http_client.py:502 | http.py:204 (structured only) | NO — narrower detection |
| DH-906 refresh + retry | http_client.py:504-509 | http.py:160-164 (signal) | Partial |
| Metrics: request counter | metrics.py:6-9 | metrics.py:15-17 | Different names |
| Metrics: duration histogram | metrics.py:10-14 | metrics.py:25-27 | Different labels |
| Metrics in request path | http_client.py:399,543,546 | NOT in _request path | NO — PARITY GAP |
| WS connection rate limit | websocket_rate_limiter_simple.py:34 (1s interval) | NOT IMPLEMENTED | MISSING |
| WS max 5 concurrent connections | websocket_rate_limiter_simple.py:38 | NOT IMPLEMENTED | MISSING |
| Payload identity assertions | invariants.py (all) | NOT IMPLEMENTED | MISSING |
| Status mapper (PLACED→OPEN) | status_mapper.py:21 | NOT IMPLEMENTED | UNKNOWN |
| Adaptive interval ratchet | http_client.py:451-453 | http.py:133-135 | YES |
| Token refresh cooldown 60s | DEFAULT_CONFIG.token | http.py:47 (60.0) | YES |
| Token refresh backoff 130s | DEFAULT_CONFIG.token | http.py:48 (130.0) | YES |
| refresh_lock (multi-client) | NOT in archive | http.py:57,66,236-244 | Greenfield-only addition |
| params kwarg on get/delete | NOT in archive | http_client.py:71,81 | Greenfield-only addition |
| exception hierarchy root | BrokerError (common) | TradeXV2Error (domain) | Different roots |
| DhanIdentityError | exceptions.py:102 | NOT DEFINED | MISSING |

---

## 7. PARITY GAPS

### 7.1 Split READ/WRITE Circuit Breakers — Status: PARTIAL

Does greenfield have split READ/WRITE circuit breakers?
YES — structurally. BaseResilientHttpClient.__init__ (line 55-59) creates three separate CircuitBreaker instances keyed "read", "write", "admin". _categorize() routes endpoints.

But with wrong thresholds:
- success_threshold: archive requires 3 consecutive successes in HALF_OPEN to close; greenfield uses 1 (default). Greenfield circuits close after a single probe success — flap risk under intermittent faults.
- Write CB recovery_timeout=60.0s vs archive 30.0s — write breaker stays open twice as long.
- No dedicated portfolio CB — greenfield maps portfolio reads to "admin". Archive has a separate dhan-portfolio CB with its own thresholds.

DH-906 regression test: No equivalent test exists in greenfield. The regression that caused order blockage by read CB is NOT regression-tested in greenfield.

---

### 7.2 Rate Limits — Status: PARTIALLY CORRECT, MECHANISM DIFFERS

**Archive mechanism:** Two-layer system
1. Token bucket (MultiBucketRateLimiter) with per-category buckets (orders/market_data/portfolio/admin) enforcing rps limits
2. Adaptive interval throttle (_throttle()) with endpoint-specific intervals from config

**Greenfield mechanism:** One-layer interval throttle
- _apply_rate_limit() in BaseResilientHttpClient uses TokenBucketRateLimiter per endpoint-prefix
- Rate is set from RATE_LIMITS dict which stores intervals (seconds between requests), not rps

**Config values in brokers/adapters/dhan/config.py RATE_LIMITS (lines 28-35):**

| Endpoint | Interval | Implied rps | Archive target rps | Match? |
|---|---|---|---|---|
| /marketfeed/quote | 1.0s | 1 rps | 1 rps (QUOTE_RATE) | YES |
| /marketfeed/ltp | 0.15s | ~6.7 rps | 10 rps | NO — too conservative |
| /marketfeed/ohlc | 0.15s | ~6.7 rps | 10 rps | NO — too conservative |
| /optionchain | 0.35s | ~2.9 rps | 3 rps | Approx OK |
| /charts/ | 0.15s | ~6.7 rps | 10 rps | NO — too conservative |
| /orders | 0.04s | 25 rps | 25 rps | YES |

**Missing from greenfield rate limits:**
- No admin rate limit (archive: 10 rps)
- No portfolio rate limit (archive: 20 rps)
- No WebSocket connection rate limiting

**CRITICAL SEMANTIC BUG — RATE_LIMITS INVERSION:**

BaseResilientHttpClient.__init__ (line 51-53):
  TokenBucketRateLimiter(rate_per_second=rate, capacity=max(int(rate), 1))

With rate = RATE_LIMITS[endpoint] = e.g. 0.15 for /marketfeed/ltp:
  → rate_per_second=0.15, capacity=max(int(0.15), 1) = capacity=1
  → Actual throughput: 0.15 requests/second = 1 request per 6.67 seconds

The config comment says "~6.7 req/s" (intended rate) but value 0.15 is being used as rate_per_second,
giving 0.15 rps, not 6.67 rps. The values appear to be seconds-per-request (intervals) but are
passed as rate_per_second. This is a semantic inversion bug that throttles market data to
1/44th of intended throughput.

---

### 7.3 Additional Parity Gaps Summary

| Gap | Severity | Archive Evidence | Greenfield Status |
|---|---|---|---|
| success_threshold=1 vs 3 | HIGH | circuit_breaker.py:31, test_chaos.py:235 | circuit_breaker.py:41 |
| Write CB open_duration 60s vs 30s | MEDIUM | circuit_breaker.py:28 | http_client.py:57 |
| RATE_LIMITS interval vs rps inversion bug | CRITICAL | rate_limiter.py:35-52 | config.py:28-35 + http_client.py:51-53 |
| 429 not retried in greenfield | CRITICAL | http_client.py:444-473 | http_client.py:97 |
| Metrics not in request hot path | HIGH | http_client.py:399,543,546 | metrics.py decorator only |
| No DhanRateLimiterMetrics (observability) | MEDIUM | rate_limiter.py:126-218 | NOT IMPLEMENTED |
| DH-906 text scan vs structured key | MEDIUM | http_client.py:502 | http.py:204 |
| No portfolio CB category | MEDIUM | circuit_breaker.py:74-88 | mapped to admin |
| No invariants (payload identity check) | MEDIUM | invariants.py full | NOT IMPLEMENTED |
| WS rate limiter absent | MEDIUM | websocket_rate_limiter_simple.py | NOT IMPLEMENTED |
| 3 duplicate CB implementations | HIGH | N/A | resilience/, infrastructure/, common/ |
| 3 duplicate RL implementations | HIGH | N/A | same 3 locations |
| Infrastructure RetryExecutor orphaned | HIGH | N/A | no caller in adapter path |
| Constructor arg order swapped | CRITICAL | http_client.py:116-134 | http.py:50-69 |
| Feature-specific exceptions missing | LOW | exceptions.py:109-143 | NOT IMPLEMENTED |
| Status mapper not ported | UNKNOWN | status_mapper.py | NOT FOUND in greenfield |
| DhanRateLimiterMetrics.snapshot() | MEDIUM | rate_limiter.py:192-203 | NOT IMPLEMENTED |
| WS max 5 connections pool | MEDIUM | websocket_rate_limiter_simple.py:38 | NOT IMPLEMENTED |

---

## 8. OPEN QUESTIONS

### OQ-1: Which CB implementation does DhanHttpClient actually use at runtime?

The greenfield DhanHttpClient inherits from BaseResilientHttpClient which uses brokers/resilience/circuit_breaker.py::CircuitBreaker. The brokers/infrastructure/resilience/circuit_breaker.py exists as a standalone and is only used by the infrastructure RetryExecutor. If any code instantiates RetryExecutor from infrastructure (not seen in files reviewed), it would use a DIFFERENT CB instance from what DhanHttpClient uses, meaning failures counted in RetryExecutor would NOT trip DhanHttpClient's CB. The wiring must be verified end-to-end in the factory/DI layer.

### OQ-2: Is brokers/adapters/dhan/config.py::RATE_LIMITS intended as rps or interval?

The comment on /marketfeed/ltp: 0.15 says "~6.7 req/s", implying the values are intervals (seconds between requests). But TokenBucketRateLimiter.__init__ uses them as rate_per_second. If the intent is 6.7 rps, the config should contain 6.67, not 0.15. This must be clarified with the author before production. Current behavior: 0.15 rps for ltp/ohlc/charts (1 request per 6.67 seconds).

### OQ-3: Does the greenfield DhanHttpClient have a factory that wires up all CBs and RLs?

No factory file was in scope. If DhanHttpClient is instantiated directly by callers, all three CBs are auto-created inside BaseResilientHttpClient.__init__ — which is correct. But the infrastructure RetryExecutor and Dhan-specific factory classes (DhanCircuitBreakerFactory, DhanRetryExecutorFactory) from the archive have no greenfield equivalents, meaning per-category tuning (orders CB threshold=3) is only encoded in BaseResilientHttpClient hardcoded values.

### OQ-4: Where is the WS adapter rate limiting?

archive/brokers/dhan/resilience/websocket_rate_limiter_simple.py provides:
- 1-second minimum interval between WS connection attempts
- Max 5 concurrent depth-200 connections

No equivalent was found in any greenfield file read. If the WS adapter is in a file not in scope (e.g., brokers/adapters/dhan/websocket.py), this may be implemented there. UNKNOWN — requires follow-up.

### OQ-5: Is DhanRateLimiterMetrics required by any interface contract?

The archive DhanRateLimiterMetrics is used inside DhanHttpClient._acquire_rate_limit_token() to record per-category rps, rejections, and queue depth. The greenfield has no equivalent. If the metrics dashboard or health check system reads these metrics, greenfield will produce zeroes/missing data.

### OQ-6: What triggers BrokerServerError vs DhanError in the circuit breaker failure path?

In brokers/resilience/circuit_breaker.py::call() (line 83-88), the is_ignored logic has a non-obvious override: if an exception IS in ignored_exceptions but is ALSO a BrokerServerError, it is forced to count as a failure (line 84-85). This means BrokerServerError always trips the CB regardless of whether it's in the ignored list. RateLimitError and AuthenticationError (in ignored_exceptions) will never trip the CB. Is this the intended behavior? The archive's simpler on_failure()/on_success() model is more explicit.

### OQ-7: Why does RetryPolicy._compute_delay() add jitter ON TOP of the capped delay?

In brokers/resilience/retry.py line 48: jitter = random.randint(0, delay // 4) is ADDED to delay (line 49: return delay + jitter). This means the maximum delay is max_delay_ms + max_delay_ms/4. With max_delay_ms=5000, maximum actual delay = 6250ms. The archive caps at exactly max_delay_ms. Intended?

### OQ-8: Is there a test suite for the greenfield resilience stack?

No greenfield test files were in scope. The archive test oracle (test_chaos.py, test_circuit_breaker_regression.py) tests archive-specific classes (brokers.common.resilience.*, brokers.dhan.resilience.*). It is UNKNOWN whether equivalent tests exist for brokers.resilience.* and brokers.infrastructure.resilience.*. Without them, the DH-906 regression and rate-limit behavior are untested in greenfield.

---

*End of PHASE_3_8_RESILIENCE_AUDIT.md*
