# Phase 3 — Implementation Tasks: Rate Limiting & Resilience
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 3 — Rate Limiting & Resilience  
**Date:** 2026-07-03  
**Status:** Implementation Plan  

---

## 1. Task Dependency Graph

```
Layer 0 (No Dependencies) — Critical Foundation Fixes
├── T0.1: Fix RATE_LIMITS inversion bug
├── T0.2: Fix constructor arg order
└── T0.3: Fix CB success_threshold

Layer 1 (Depends on Layer 0) — Critical Behavior Fixes
├── T1.1: Fix 429 retry [depends on T0.1]
├── T1.2: Add metrics to hot path [depends on T0.1, T0.2]
└── T1.3: Consolidate CB implementations [depends on T0.3]

Layer 2 (Depends on Layer 1) — Missing Features
├── T2.1: Add portfolio CB category [depends on T1.3]
├── T2.2: Port invariants [depends on T1.1]
└── T2.3: Add WS rate limiter [depends on T1.3]

Layer 3 (Depends on Layer 2) — Observability & Polish
├── T3.1: Port status mapper [depends on T2.1]
└── T3.2: Add DhanRateLimiterMetrics [depends on T1.2, T2.3]
```

**Dependency Rationale:**
- Layer 0: Foundation fixes that affect all downstream tasks
- Layer 1: Critical behavior gaps that block production readiness
- Layer 2: Missing features that reduce robustness
- Layer 3: Observability and polish (can be deferred)

---

## 2. Layer 0 — No Dependencies (Critical Foundation Fixes)

### T0.1: Fix RATE_LIMITS Inversion Bug

**Priority:** CRITICAL  
**Gap Reference:** Evidence Matrix #7, #8; Design Doc Section 5  
**Estimated Effort:** 2 hours  

**Problem:**  
Config values are intervals (seconds between requests) but passed as `rate_per_second` to TokenBucketRateLimiter. Market data throttled to 1/44th of intended throughput.

**Implementation Steps:**

1. **Option A (Recommended): Invert in BaseResilientHttpClient**
   ```python
   # brokers/resilience/http_client.py:50-53
   for endpoint, interval in rate_limits.items():
       rate_per_second = 1.0 / interval if interval > 0 else 0
       self._rate_limiters[endpoint] = TokenBucketRateLimiter(
           rate_per_second=rate_per_second,
           capacity=max(int(rate_per_second), 1)
       )
   ```

2. **Option B: Rename config to clarify semantics**
   ```python
   # brokers/adapters/dhan/config.py
   RATE_LIMITS = {
       "/marketfeed/ltp": 6.67,  # requests per second (was 0.15 interval)
       "/orders": 25.0,  # requests per second (was 0.04 interval)
   }
   ```

3. **Add unit test**
   ```python
   # brokers/tests/test_rate_limiter_config.py
   def test_rate_limits_correct_throughput():
       client = DhanHttpClient(...)
       ltp_limiter = client._rate_limiters["/marketfeed/ltp"]
       assert ltp_limiter._rate == pytest.approx(6.67, rel=0.01)
   ```

**Acceptance Criteria:**
- [ ] `/marketfeed/ltp` achieves 6.67 rps (not 0.15 rps)
- [ ] `/orders` achieves 25 rps
- [ ] Unit test validates rate conversion
- [ ] No regression in existing tests

**Verification:**
```bash
pytest brokers/tests/test_rate_limiter_config.py -v
```

---

### T0.2: Fix Constructor Argument Order

**Priority:** CRITICAL  
**Gap Reference:** Evidence Matrix #26; Design Doc Section 3.1.3  
**Estimated Effort:** 1 hour  

**Problem:**  
Archive: `DhanHttpClient(client_id, access_token, ...)`. Greenfield: `DhanHttpClient(access_token, client_id, ...)`. Positional callers silently swap tokens.

**Implementation Steps:**

1. **Restore archive order**
   ```python
   # brokers/adapters/dhan/http.py:50-69
   def __init__(
       self,
       client_id: str,  # FIRST (was second)
       access_token: str,  # SECOND (was first)
       base_url: str = "",
       timeout: float = 10.0,
       token_refresh_fn: Callable[[], str | None] | None = None,
       refresh_lock: threading.Lock | None = None,
       refresh_cooldown_seconds: float = _REFRESH_COOLDOWN_SECONDS,
       rate_limit_backoff_seconds: float = _RATE_LIMIT_BACKOFF_SECONDS,
   ):
   ```

2. **Update all callers**
   ```bash
   grep -r "DhanHttpClient(" brokers/ --include="*.py"
   ```
   Update any positional callers to use new order.

3. **Add deprecation warning (if needed)**
   ```python
   # Temporary: detect swapped args
   if access_token.startswith("CLIENT_") or client_id.startswith("eyJ"):
       logger.warning("Constructor args may be swapped")
   ```

**Acceptance Criteria:**
- [ ] Constructor signature matches archive: `(client_id, access_token, ...)`
- [ ] All callers updated
- [ ] No silent token/client_id swap
- [ ] Unit test validates arg order

**Verification:**
```bash
pytest brokers/tests/test_dhan_http_client.py::test_constructor_arg_order -v
```

---

### T0.3: Fix Circuit Breaker success_threshold

**Priority:** HIGH  
**Gap Reference:** Evidence Matrix #4; Design Doc Section 3.2.1  
**Estimated Effort:** 30 minutes  

**Problem:**  
Greenfield defaults to `success_threshold=1`. Archive requires 3 consecutive successes in HALF_OPEN to close circuit. Single success closes circuit → flap risk under intermittent faults.

**Implementation Steps:**

1. **Set success_threshold=3 in BaseResilientHttpClient**
   ```python
   # brokers/resilience/http_client.py:55-59
   self._circuit_breakers = {
       "read": CircuitBreaker(
           failure_threshold=5,
           recovery_timeout=30.0,
           success_threshold=3  # Added
       ),
       "write": CircuitBreaker(
           failure_threshold=3,
           recovery_timeout=30.0,  # Also fix: was 60.0
           success_threshold=3
       ),
       "admin": CircuitBreaker(
           failure_threshold=5,
           recovery_timeout=30.0,
           success_threshold=3
       ),
   }
   ```

2. **Add regression test**
   ```python
   # brokers/tests/test_circuit_breaker_thresholds.py
   def test_success_threshold_matches_archive():
       cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0, success_threshold=3)
       assert cb._success_threshold == 3
   ```

**Acceptance Criteria:**
- [ ] All CBs use `success_threshold=3`
- [ ] Write CB uses `recovery_timeout=30.0` (not 60.0)
- [ ] Unit test validates thresholds
- [ ] DH-906 regression test passes (open read CB doesn't block writes)

**Verification:**
```bash
pytest brokers/tests/test_circuit_breaker_thresholds.py -v
```

---

## 3. Layer 1 — Depends on Layer 0 (Critical Behavior Fixes)

### T1.1: Fix HTTP 429 Retry

**Priority:** CRITICAL  
**Gap Reference:** Evidence Matrix #12; Design Doc Section 3.1.2  
**Estimated Effort:** 3 hours  
**Depends On:** T0.1 (RATE_LIMITS fix)  

**Problem:**  
Archive retries 429 with backoff. Greenfield raises RateLimitError immediately. RateLimitError is in CB ignored_exceptions, so RetryPolicy never retries it.

**Implementation Steps:**

1. **Remove RateLimitError from ignored_exceptions**
   ```python
   # brokers/resilience/http_client.py:95-97
   cb.call(
       lambda: self._retry.call(_do_request),
       ignored_exceptions=(AuthenticationError, BrokerError),  # Removed RateLimitError
   )
   ```

2. **Add RateLimitError to RetryPolicy retryable_exceptions**
   ```python
   # brokers/resilience/http_client.py:61-69
   self._retry = RetryPolicy(
       max_retries=3,
       base_delay_ms=500,
       max_delay_ms=5000,
       retryable_exceptions=(
           requests.exceptions.RequestException,
           BrokerServerError,
           RateLimitError,  # Added
       ),
   )
   ```

3. **Fix _parse_retry_after default**
   ```python
   # brokers/adapters/dhan/http.py:189-197
   @staticmethod
   def _parse_retry_after(resp: requests.Response) -> float | None:
       """Parse Retry-After header, returning None if absent."""
       try:
           val = resp.headers.get("Retry-After")
           if val is not None:
               return max(0.01, float(val))
       except (ValueError, TypeError):
           pass
       return None  # Was 30.0, now None to match archive
   ```

4. **Add 429 retry test**
   ```python
   # brokers/tests/test_http_429_retry.py
   def test_429_retried_with_backoff():
       # Mock 429 response, verify retry occurs
       pass
   ```

**Acceptance Criteria:**
- [ ] 429 responses retried up to max_retries-1 times
- [ ] Retry-After header respected (or exponential backoff if absent)
- [ ] RateLimitError raised only after all retries exhausted
- [ ] Unit test validates retry behavior

**Verification:**
```bash
pytest brokers/tests/test_http_429_retry.py -v
```

---

### T1.2: Add Metrics to Hot Path

**Priority:** HIGH  
**Gap Reference:** Evidence Matrix #16, #17; Design Doc Section 3.2.2  
**Estimated Effort:** 4 hours  
**Depends On:** T0.1, T0.2  

**Problem:**  
Metrics exist as decorator only. No inc()/observe() calls in `_request()` path. Observability blind spot.

**Implementation Steps:**

1. **Add metrics instrumentation to BaseResilientHttpClient._request()**
   ```python
   # brokers/resilience/http_client.py:83-113
   import time
   
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
               ignored_exceptions=(AuthenticationError, BrokerError),
           )
           # Metrics: success
           self._record_metric("request_success", category, method, endpoint)
           return result
       except Exception as exc:
           # Metrics: failure
           self._record_metric("request_failure", category, method, endpoint, type(exc).__name__)
           raise
       finally:
           # Metrics: duration
           duration = time.monotonic() - start_time
           self._record_metric("request_duration", category, method, duration=duration)
   
   def _record_metric(self, metric_type: str, category: str, method: str, 
                      endpoint: str = None, error_type: str = None, duration: float = None):
       """Override in subclass to integrate with Prometheus/statsd."""
       pass
   ```

2. **Override _record_metric in DhanHttpClient**
   ```python
   # brokers/adapters/dhan/http.py (add method)
   def _record_metric(self, metric_type: str, category: str, method: str, 
                      endpoint: str = None, error_type: str = None, duration: float = None):
       if metric_type == "request_success":
           dhan_request_total.labels(method=method, category=category).inc()
       elif metric_type == "request_failure":
           dhan_errors_total.labels(method=method, category=category, error=error_type).inc()
       elif metric_type == "request_duration":
           dhan_request_duration_seconds.labels(method=method, category=category).observe(duration)
   ```

3. **Add metrics test**
   ```python
   # brokers/tests/test_metrics_instrumentation.py
   def test_metrics_recorded_in_request_path():
       # Mock request, verify metrics incremented
       pass
   ```

**Acceptance Criteria:**
- [ ] Request success/failure counted in _request() path
- [ ] Request duration observed in _request() path
- [ ] Metrics match archive schema (method, category labels)
- [ ] Unit test validates metrics recording

**Verification:**
```bash
pytest brokers/tests/test_metrics_instrumentation.py -v
```

---

### T1.3: Consolidate Circuit Breaker Implementations

**Priority:** HIGH  
**Gap Reference:** Design Doc Section 4.1  
**Estimated Effort:** 2 hours  
**Depends On:** T0.3  

**Problem:**  
Three CB implementations exist. Infrastructure CB is orphaned (no callers). Maintenance burden.

**Implementation Steps:**

1. **Confirm no callers of infrastructure CB**
   ```bash
   grep -r "from brokers.infrastructure.resilience.circuit_breaker" brokers/ --include="*.py"
   grep -r "import.*infrastructure.*circuit_breaker" brokers/ --include="*.py"
   ```

2. **Delete infrastructure CB**
   ```bash
   rm brokers/infrastructure/resilience/circuit_breaker.py
   ```

3. **Delete infrastructure RL**
   ```bash
   rm brokers/infrastructure/resilience/rate_limiter.py
   ```

4. **Delete orphaned RetryExecutor**
   ```bash
   rm brokers/infrastructure/resilience/retry_executor.py
   ```

5. **Update __init__.py**
   ```python
   # brokers/infrastructure/resilience/__init__.py
   # Remove imports of deleted modules
   ```

6. **Add integration test**
   ```python
   # brokers/tests/test_cb_consolidation.py
   def test_only_one_cb_implementation():
       # Verify only brokers.resilience.circuit_breaker exists
       pass
   ```

**Acceptance Criteria:**
- [ ] Only one CB implementation remains (brokers/resilience/circuit_breaker.py)
- [ ] Only one RL implementation remains (brokers/resilience/rate_limiter.py)
- [ ] No orphaned RetryExecutor
- [ ] No import errors
- [ ] All tests pass

**Verification:**
```bash
pytest brokers/tests/ -v
```

---

## 4. Layer 2 — Depends on Layer 1 (Missing Features)

### T2.1: Add Portfolio CB Category

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #10; Design Doc Section 3.3.3  
**Estimated Effort:** 2 hours  
**Depends On:** T1.3  

**Problem:**  
Archive has 4 CB categories (orders, market_data, portfolio, admin). Greenfield has 3 (read, write, admin). Portfolio endpoints map to "admin", causing portfolio failures to trip admin CB.

**Implementation Steps:**

1. **Add PORTFOLIO_PREFIXES to config**
   ```python
   # brokers/adapters/dhan/config.py
   PORTFOLIO_PREFIXES = (
       "/positions",
       "/holdings",
       "/fundlimit",
       "/tradebook",
   )
   ```

2. **Update _categorize() in DhanHttpClient**
   ```python
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
   ```

3. **Add portfolio CB to BaseResilientHttpClient**
   ```python
   # brokers/resilience/http_client.py:55-59
   self._circuit_breakers = {
       "read": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3),
       "write": CircuitBreaker(failure_threshold=3, recovery_timeout=30.0, success_threshold=3),
       "portfolio": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3),
       "admin": CircuitBreaker(failure_threshold=5, recovery_timeout=30.0, success_threshold=3),
   }
   ```

4. **Add test**
   ```python
   # brokers/tests/test_portfolio_cb.py
   def test_portfolio_endpoints_use_portfolio_cb():
       client = DhanHttpClient(...)
       assert client._categorize("/positions") == "portfolio"
   ```

**Acceptance Criteria:**
- [ ] Portfolio endpoints categorized as "portfolio"
- [ ] Portfolio CB exists with failure_threshold=5
- [ ] Portfolio failures don't trip admin CB
- [ ] Unit test validates categorization

**Verification:**
```bash
pytest brokers/tests/test_portfolio_cb.py -v
```

---

### T2.2: Port Invariants (Payload Identity Assertions)

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #20; Design Doc Section 3.3.4  
**Estimated Effort:** 3 hours  
**Depends On:** T1.1  

**Problem:**  
Archive has pre/post-condition assertions on order payloads. Greenfield has no invariant checks. Silent payload corruption possible.

**Implementation Steps:**

1. **Port invariant functions**
   ```python
   # brokers/adapters/dhan/invariants.py (new file)
   def assert_order_identity(payload: dict) -> None:
       """Validate order payload has required fields."""
       required = ["exchangeSegment", "transactionType", "quantity", "productType"]
       for field in required:
           if field not in payload:
               raise ValueError(f"Missing required field: {field}")
   
   def assert_exchange_segment(payload: dict) -> None:
       """Validate exchange segment is valid."""
       valid_segments = {"NSE_EQ", "BSE_EQ", "NSE_FNO", "BSE_FNO", "MCX_COMM", "NSE_CD", "IDX_I"}
       segment = payload.get("exchangeSegment")
       if segment not in valid_segments:
           raise ValueError(f"Invalid exchange segment: {segment}")
   ```

2. **Call invariants in DhanHttpClient.post/put**
   ```python
   # brokers/adapters/dhan/http.py
   def post(self, endpoint: str, json: dict | None = None) -> dict:
       if endpoint.startswith("/orders") and json:
           assert_order_identity(json)
           assert_exchange_segment(json)
       return super().post(endpoint, json=json)
   ```

3. **Add invariant tests**
   ```python
   # brokers/tests/test_invariants.py
   def test_order_identity_validation():
       with pytest.raises(ValueError):
           assert_order_identity({})  # Missing fields
   ```

**Acceptance Criteria:**
- [ ] Invariants validate order payloads
- [ ] Invalid payloads raise ValueError before HTTP request
- [ ] Unit tests validate invariant logic
- [ ] No regression in existing tests

**Verification:**
```bash
pytest brokers/tests/test_invariants.py -v
```

---

### T2.3: Add WebSocket Rate Limiter

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #18, #19; Design Doc Section 3.3.5  
**Estimated Effort:** 4 hours  
**Depends On:** T1.3  

**Problem:**  
Archive has WS connection rate limiting (1s interval, max 5 concurrent). Greenfield has no WS rate limiting.

**Implementation Steps:**

1. **Port WebSocketRateLimiter**
   ```python
   # brokers/adapters/dhan/websocket_rate_limiter.py (new file)
   import threading
   import time
   
   class WebSocketRateLimiter:
       def __init__(self, min_interval: float = 1.0, max_concurrent: int = 5):
           self._min_interval = min_interval
           self._max_concurrent = max_concurrent
           self._last_connection_time = 0.0
           self._active_connections = 0
           self._lock = threading.Lock()
       
       def acquire_connection(self) -> bool:
           with self._lock:
               now = time.monotonic()
               if now - self._last_connection_time < self._min_interval:
                   return False
               if self._active_connections >= self._max_concurrent:
                   return False
               self._last_connection_time = now
               self._active_connections += 1
               return True
       
       def release_connection(self):
           with self._lock:
               self._active_connections -= 1
   ```

2. **Integrate into WS adapter**
   ```python
   # brokers/adapters/dhan/websocket.py (if exists)
   rate_limiter = WebSocketRateLimiter(min_interval=1.0, max_concurrent=5)
   
   def connect():
       if not rate_limiter.acquire_connection():
           raise Exception("WS rate limit exceeded")
       try:
           # connect logic
           pass
       finally:
           rate_limiter.release_connection()
   ```

3. **Add test**
   ```python
   # brokers/tests/test_ws_rate_limiter.py
   def test_ws_rate_limiter_max_concurrent():
       limiter = WebSocketRateLimiter(max_concurrent=2)
       assert limiter.acquire_connection()
       assert limiter.acquire_connection()
       assert not limiter.acquire_connection()  # Third fails
   ```

**Acceptance Criteria:**
- [ ] WS connections rate-limited to 1 per second
- [ ] Max 5 concurrent WS connections
- [ ] Unit test validates rate limiting
- [ ] No regression in WS adapter tests

**Verification:**
```bash
pytest brokers/tests/test_ws_rate_limiter.py -v
```

---

## 5. Layer 3 — Depends on Layer 2 (Observability & Polish)

### T3.1: Port Status Mapper

**Priority:** LOW  
**Gap Reference:** Evidence Matrix #21; Design Doc Section 3.5.1  
**Estimated Effort:** 1 hour  
**Depends On:** T2.1  

**Problem:**  
Archive has order status normalization (PLACED→OPEN). Greenfield has no status mapper.

**Implementation Steps:**

1. **Port status mapper**
   ```python
   # brokers/adapters/dhan/status_mapper.py (new file)
   STATUS_MAP = {
       "PLACED": "OPEN",
       "OPEN": "OPEN",
       "COMPLETE": "FILLED",
       "CANCELLED": "CANCELLED",
       "REJECTED": "REJECTED",
   }
   
   def map_status(archive_status: str) -> str:
       return STATUS_MAP.get(archive_status, archive_status)
   ```

2. **Use in order processing**
   ```python
   # brokers/adapters/dhan/order_service.py (if exists)
   from .status_mapper import map_status
   
   def get_order(order_id: str) -> dict:
       order = http_client.get(f"/orders/{order_id}")
       order["status"] = map_status(order["status"])
       return order
   ```

3. **Add test**
   ```python
   # brokers/tests/test_status_mapper.py
   def test_status_mapping():
       assert map_status("PLACED") == "OPEN"
       assert map_status("COMPLETE") == "FILLED"
   ```

**Acceptance Criteria:**
- [ ] Status mapper normalizes order statuses
- [ ] PLACED→OPEN mapping works
- [ ] Unit test validates mapping

**Verification:**
```bash
pytest brokers/tests/test_status_mapper.py -v
```

---

### T3.2: Add DhanRateLimiterMetrics

**Priority:** MEDIUM  
**Gap Reference:** Evidence Matrix #16; Design Doc Section 3.3.6  
**Estimated Effort:** 3 hours  
**Depends On:** T1.2, T2.3  

**Problem:**  
Archive has per-category RL metrics (acquisitions, rejections, queue depth). Greenfield has no RL metrics.

**Implementation Steps:**

1. **Add RL metrics class**
   ```python
   # brokers/adapters/dhan/metrics.py (extend existing)
   from prometheus_client import Counter, Gauge
   
   dhan_rl_acquisitions_total = Counter(
       "dhan_rl_acquisitions_total",
       "Total rate limiter acquisitions",
       ["category"]
   )
   
   dhan_rl_rejections_total = Counter(
       "dhan_rl_rejections_total",
       "Total rate limiter rejections",
       ["category"]
   )
   
   dhan_rl_queue_depth = Gauge(
       "dhan_rl_queue_depth",
       "Current rate limiter queue depth",
       ["category"]
   )
   ```

2. **Instrument TokenBucketRateLimiter**
   ```python
   # brokers/resilience/rate_limiter.py
   class TokenBucketRateLimiter:
       def __init__(self, rate_per_second: float, capacity: int, metrics=None):
           self._metrics = metrics
           # ...
       
       def acquire(self, tokens: int, timeout: float) -> bool:
           # ... acquire logic
           if acquired:
               if self._metrics:
                   self._metrics.inc_acquisitions(category)
           else:
               if self._metrics:
                   self._metrics.inc_rejections(category)
           return acquired
   ```

3. **Pass metrics from DhanHttpClient**
   ```python
   # brokers/adapters/dhan/http.py
   def __init__(self, ...):
       super().__init__(rate_limits=RATE_LIMITS, timeout=timeout)
       # Inject metrics into rate limiters
       for prefix, limiter in self._rate_limiters.items():
           limiter._metrics = DhanRateLimiterMetrics(category=prefix)
   ```

4. **Add test**
   ```python
   # brokers/tests/test_rl_metrics.py
   def test_rl_metrics_recorded():
       # Mock RL acquire, verify metrics incremented
       pass
   ```

**Acceptance Criteria:**
- [ ] RL acquisitions counted per category
- [ ] RL rejections counted per category
- [ ] Queue depth tracked
- [ ] Unit test validates metrics

**Verification:**
```bash
pytest brokers/tests/test_rl_metrics.py -v
```

---

## 6. Execution Summary

### 6.1 Task Count by Layer

| Layer | Tasks | Total Effort | Parallelism |
|---|---|---|---|
| Layer 0 | 3 tasks | 3.5 hours | All 3 can run in parallel |
| Layer 1 | 3 tasks | 9 hours | T1.1 and T1.3 can run in parallel; T1.2 depends on both |
| Layer 2 | 3 tasks | 9 hours | All 3 can run in parallel |
| Layer 3 | 2 tasks | 4 hours | Both can run in parallel |
| **Total** | **11 tasks** | **25.5 hours** | — |

### 6.2 Parallelism Opportunities

**Layer 0 (100% parallel):**
- T0.1, T0.2, T0.3 are independent
- 3 developers can work simultaneously

**Layer 1 (66% parallel):**
- T1.1 (429 retry) and T1.3 (CB consolidation) are independent
- T1.2 (metrics) depends on T0.1 and T0.2, so must wait

**Layer 2 (100% parallel):**
- T2.1, T2.2, T2.3 are independent

**Layer 3 (100% parallel):**
- T3.1, T3.2 are independent

### 6.3 Critical Path

**Longest sequential chain:**
```
T0.1 (2h) → T1.1 (3h) → T2.2 (3h) → T3.1 (1h) = 9 hours
```

**Alternative critical path:**
```
T0.1 (2h) → T1.2 (4h) → T3.2 (3h) = 9 hours
```

**Minimum time with 3 developers:**
- Layer 0: 2 hours (parallel)
- Layer 1: 4 hours (T1.2 is longest)
- Layer 2: 4 hours (T2.3 is longest)
- Layer 3: 3 hours (T3.2 is longest)
- **Total: 13 hours** (vs 25.5 hours sequential)

### 6.4 Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| T0.1 breaks existing RL tests | Medium | High | Run full test suite after fix |
| T0.2 breaks callers | Low | High | Grep for all callers, update systematically |
| T1.1 retry loop causes timeout | Medium | Medium | Add timeout to RetryPolicy |
| T1.3 deletion breaks imports | Low | High | Confirm no callers before deletion |
| T2.2 invariants break existing orders | Medium | Medium | Add invariants gradually, behind feature flag |

### 6.5 Recommended Execution Order

**Sprint 1 (Day 1): Layer 0**
- T0.1: Fix RATE_LIMITS inversion (2h)
- T0.2: Fix constructor arg order (1h)
- T0.3: Fix CB success_threshold (0.5h)
- **Total: 3.5 hours**

**Sprint 2 (Day 2): Layer 1**
- T1.1: Fix 429 retry (3h)
- T1.3: Consolidate CB implementations (2h)
- T1.2: Add metrics to hot path (4h)
- **Total: 9 hours**

**Sprint 3 (Day 3): Layer 2**
- T2.1: Add portfolio CB category (2h)
- T2.2: Port invariants (3h)
- T2.3: Add WS rate limiter (4h)
- **Total: 9 hours**

**Sprint 4 (Day 4): Layer 3**
- T3.1: Port status mapper (1h)
- T3.2: Add DhanRateLimiterMetrics (3h)
- **Total: 4 hours**

**Buffer (Day 5): Integration testing & bug fixes**
- Run full test suite
- Fix any regressions
- Performance testing

---

## 7. Acceptance Criteria Summary

### 7.1 Functional Criteria

- [ ] All 26 behaviors from evidence matrix have matching greenfield implementations
- [ ] RATE_LIMITS achieve intended throughput (6.7 rps for market data, 25 rps for orders)
- [ ] 429 responses retried with backoff
- [ ] Constructor args match archive order
- [ ] CB success_threshold=3 for all categories
- [ ] Metrics recorded in request hot path
- [ ] Portfolio endpoints use dedicated CB
- [ ] Order payloads validated with invariants
- [ ] WS connections rate-limited

### 7.2 Non-Functional Criteria

- [ ] No regression in existing tests
- [ ] All new code has unit tests
- [ ] Code review approved by 2 reviewers
- [ ] Performance test validates throughput
- [ ] Observability dashboards show metrics

### 7.3 Integration Criteria

- [ ] DhanHttpClient passes archive test oracle (test_http_client, test_chaos)
- [ ] DH-906 regression test passes
- [ ] Rate limiter stress test passes (1000 req/s for 60s)
- [ ] Circuit breaker trip/recovery test passes

---

## 8. Open Questions Requiring Resolution

| ID | Question | Blocking Task | Resolution Owner |
|---|---|---|---|
| OQ-1 | Which CB implementation does DhanHttpClient use? | T1.3 | Architecture team |
| OQ-2 | RATE_LIMITS intended as rps or interval? | T0.1 | Config author |
| OQ-4 | Where is WS adapter rate limiting? | T2.3 | WS adapter owner |
| OQ-5 | Is DhanRateLimiterMetrics required? | T3.2 | Ops/monitoring team |
| OQ-8 | Is there a greenfield resilience test suite? | All tasks | QA team |

---

## 9. Success Metrics

### 9.1 Parity Score

**Current:** 38.5% IDENTICAL (10/26 behaviors)  
**Target:** 85% IDENTICAL (22/26 behaviors) after all tasks

### 9.2 Gap Reduction

**Current:** 15 parity gaps (3 CRITICAL, 4 HIGH, 6 MEDIUM, 1 LOW, 2 UNKNOWN)  
**Target:** 0 CRITICAL, 0 HIGH, 2 MEDIUM (deferred), 0 LOW, 0 UNKNOWN

### 9.3 Test Coverage

**Current:** 0% (no greenfield resilience tests)  
**Target:** 80% (all critical paths tested)

---

*End of implementation_tasks.md*
