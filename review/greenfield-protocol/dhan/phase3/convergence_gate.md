# Phase 3 — Convergence Gate: Rate Limiting & Resilience
## Greenfield Broker Replication Protocol — Dhan Broker

**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 3 — Rate Limiting & Resilience  
**Status:** CONVERGED ✓  
**Date:** 2026-07-03  

---

## Exit Criteria Validation

| # | Criterion | Requirement | Actual | Status |
|---|-----------|-------------|--------|--------|
| 1 | Source files inspected | 100% of files in scope | 21/21 files (9 archive + 12 greenfield) | ✅ PASS |
| 2 | Public APIs documented | Every public API has behavioral contract | 43 APIs documented in `public_contract.md` | ✅ PASS |
| 3 | Externally observable behavior evidenced | Every behavior has evidence | 26 behaviors catalogued in `evidence_matrix.md` | ✅ PASS |
| 4 | State transitions documented | Every state machine complete | 5 state machines in `state_machine.md` (388 lines) | ✅ PASS |
| 5 | Exception paths documented | Every exception path traced | 12 failure modes in `failure_analysis.md` (409 lines) | ✅ PASS |
| 6 | Retry policies documented | Every retry policy complete | Archive + greenfield retry policies in `runtime_sequence.md` | ✅ PASS |
| 7 | Configuration options documented | Every config option listed | Rate limits, CB thresholds, retry policies in `source_audit.md` | ✅ PASS |
| 8 | Dependencies mapped | Every dependency traced | 35+ dependencies in `dependency_graph.md` (498 lines) | ✅ PASS |
| 9 | Open questions resolved/recorded | All OQs addressed | 8 OQs recorded in `evidence_matrix.md` | ✅ PASS |
| 10 | No undocumented behavior | All behaviors captured | 15 gaps documented in `greenfield_design.md` | ✅ PASS |
| 11 | Mandatory verification confirmed | All 7 items checked | 7/7 items verified in `evidence_matrix.md` | ✅ PASS |
| 12 | Archived tests analyzed | Test coverage mapped | 5 test suites (89 tests) analyzed | ✅ PASS |

**Overall Status:** ✅ **CONVERGED** — All 12 exit criteria satisfied

---

## Deliverables Summary

| # | Deliverable | File | Lines | Status |
|---|-------------|------|-------|--------|
| 1 | Source Audit | `source_audit.md` | 390 | ✅ Complete |
| 2 | Runtime Sequence | `runtime_sequence.md` | 490 | ✅ Complete |
| 3 | Dependency Graph | `dependency_graph.md` | 498 | ✅ Complete |
| 4 | State Machine | `state_machine.md` | 388 | ✅ Complete |
| 5 | Public Contract | `public_contract.md` | 318 | ✅ Complete |
| 6 | Failure Analysis | `failure_analysis.md` | 409 | ✅ Complete |
| 7 | Evidence Matrix | `evidence_matrix.md` | 222 | ✅ Complete |
| 8 | Greenfield Design | `greenfield_design.md` | 809 | ✅ Complete |
| 9 | Implementation Tasks | `implementation_tasks.md` | 936 | ✅ Complete |

**Total documentation:** 4,460 lines across 9 deliverables

---

## Key Findings Summary

### Critical Gaps (3)

1. **RATE_LIMITS inversion bug** — Config values are intervals (seconds/request) but passed as `rate_per_second` to TokenBucketRateLimiter. Throughput reduced to 1/44th of intended rate for market data endpoints.
   - **Impact:** Market data throttled to 0.15 rps instead of 6.7 rps
   - **Fix:** Invert values in `brokers/adapters/dhan/config.py` (0.15 → 6.67, 0.04 → 25.0)
   - **Priority:** P0 — blocks production

2. **HTTP 429 not retried** — Archive retries 429 with exponential backoff; greenfield raises `RateLimitError` immediately with no retry.
   - **Impact:** Transient rate limits cause immediate failure instead of graceful backoff
   - **Fix:** Add 429 to retryable exceptions in `RetryPolicy`, implement backoff
   - **Priority:** P0 — blocks production

3. **Constructor arg order swapped** — Archive: `DhanHttpClient(client_id, access_token, ...)`. Greenfield: `DhanHttpClient(access_token, client_id, ...)`. Code calling by position will silently swap tokens.
   - **Impact:** Silent data corruption — authentication failures or wrong-account access
   - **Fix:** Reorder constructor params to match archive, or use keyword-only args
   - **Priority:** P0 — blocks production

### High Severity Gaps (4)

4. **CB success_threshold=1 vs 3** — Greenfield closes circuit after 1 success in HALF_OPEN; archive requires 3. Flap risk under intermittent faults.
5. **Metrics not in request hot path** — Archive increments counters/histograms on every request; greenfield metrics are decorator-only, not wired into `_request()`.
6. **3 duplicate CB implementations** — `brokers/resilience/`, `brokers/infrastructure/resilience/`, and archive `brokers/common/resilience/` have incompatible APIs.
7. **Infrastructure RetryExecutor orphaned** — Not wired into DhanHttpClient; failures counted in RetryExecutor would not trip the correct CB.

### Medium Severity Gaps (6)

8. **Write CB open_duration 60s vs 30s** — Write breaker stays open twice as long in greenfield.
9. **DH-906 narrower detection** — Archive scans body text; greenfield checks structured `errorCode` field only.
10. **No portfolio CB category** — Greenfield maps portfolio reads to "admin"; archive has separate portfolio CB.
11. **No invariants (payload identity check)** — Archive validates request/response identity; greenfield has no equivalent.
12. **No WS rate limiter** — Archive limits WS connections (1s interval, max 5 concurrent); greenfield has none.
13. **No DhanRateLimiterMetrics** — Archive tracks per-category rps, queue depth, rejections; greenfield has no observability.

### Improvements Over Archive (4)

1. **refresh_lock** — Greenfield adds shared lock to prevent concurrent token refresh across multiple HTTP clients.
2. **Abstract base class** — `BaseResilientHttpClient` provides reusable resilience pattern; archive is monolithic.
3. **TokenRefreshSignal** — Clean exception-based retry signal; archive uses inline loop with attempt counter.
4. **Generic exception hierarchy** — `TradeXV2Error` root supports multi-broker architecture; archive is Dhan-specific.

---

## Mandatory Verification Checklist

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | Only expired tokens trigger regeneration | **PRESERVED** | Token refresh cooldown (60s) + backoff (130s) in `http.py:47-48` |
| 2 | Refresh is thread safe | **IMPROVED** | `refresh_lock` in `http.py:57,66,236-244` prevents concurrent refresh across clients |
| 3 | Refresh storms are prevented | **PRESERVED** | Cooldown + backoff + lock triple-protection |
| 4 | Duplicate logins are impossible | **PRESERVED** | Single `_try_refresh_token()` path with lock |
| 5 | Concurrent requests synchronize correctly | **IMPROVED** | `threading.Lock` in CircuitBreaker, TokenBucketRateLimiter |
| 6 | Authentication retries are bounded | **DEGRADED** | Archive: 429 retried with backoff; Greenfield: 429 raises immediately (CRITICAL GAP) |
| 7 | Secrets never leak | **PRESERVED** | No token logging in request path; `update_token()` logs only event name |

**Summary:** 6/7 PRESERVED or IMPROVED, 1/7 DEGRADED (429 retry — CRITICAL)

---

## Test Coverage Analysis

### Archived Test Suites (5 files, 89 tests)

| Test File | Lines | Tests | Coverage |
|-----------|-------|-------|----------|
| `test_http_client.py` | 81 | ~5 | HTTP lifecycle, token refresh |
| `test_circuit_breaker_regression.py` | 100 | ~8 | DH-906 regression (read CB open does not block write) |
| `test_chaos.py` | 861 | ~45 | CB/retry/RL integration, edge cases, failure cascades |
| `test_edge_cases.py` | 229 | ~15 | Boundary conditions, malformed responses |
| `test_error_paths.py` | 134 | ~16 | Integration tests (live-env gated) |

### Greenfield Test Coverage

**Status:** UNKNOWN — No greenfield resilience test files were in scope for this audit.

**Recommendation:** Port archived test suites to greenfield, prioritizing:
1. `test_circuit_breaker_regression.py` — DH-906 regression test is critical
2. `test_chaos.py` — Integration tests for CB/retry/RL
3. `test_http_client.py` — Basic HTTP lifecycle

---

## Implementation Priority

### P0 — Blocks Production (3 tasks, ~8 hours)

1. Fix RATE_LIMITS inversion bug
2. Fix constructor arg order
3. Fix 429 retry behavior

### P1 — High Priority (4 tasks, ~10 hours)

4. Fix CB success_threshold (1 → 3)
5. Add metrics to request hot path
6. Consolidate duplicate CB implementations
7. Wire infrastructure RetryExecutor or remove it

### P2 — Medium Priority (6 tasks, ~12 hours)

8. Fix write CB open_duration (60s → 30s)
9. Broaden DH-906 detection (add text scan fallback)
10. Add portfolio CB category
11. Port invariants
12. Add WS rate limiter
13. Add DhanRateLimiterMetrics

### P3 — Low Priority (2 tasks, ~4 hours)

14. Port status mapper
15. Add feature-specific exceptions

**Total estimated effort:** 34 hours across 15 tasks  
**Critical path:** T0.1 → T1.1 → T2.2 (RATE_LIMITS → 429 retry → invariants)

---

## Open Questions

| # | Question | Impact | Resolution |
|---|----------|--------|------------|
| OQ-1 | Which CB implementation does DhanHttpClient use? | HIGH | Verified: uses `brokers/resilience/circuit_breaker.py` via BaseResilientHttpClient |
| OQ-2 | RATE_LIMITS intended as rps or interval? | CRITICAL | Confirmed: values are intervals but passed as rps (BUG) |
| OQ-3 | Does greenfield have a factory for CBs/RLs? | MEDIUM | No factory; hardcoded in BaseResilientHttpClient.__init__ |
| OQ-4 | Where is WS adapter rate limiting? | MEDIUM | Not implemented; defer to Phase 4 (WebSocket) |
| OQ-5 | Is DhanRateLimiterMetrics required? | LOW | Archive has it; greenfield missing. Recommend port for observability parity. |
| OQ-6 | BrokerServerError override in CB ignored_exceptions? | MEDIUM | Intentional: BrokerServerError always trips CB even if in ignored list |
| OQ-7 | RetryPolicy jitter added on top of capped delay? | LOW | Yes: max delay = max_delay_ms + max_delay_ms/4 = 6250ms (archive caps at 5000ms) |
| OQ-8 | Is there a greenfield resilience test suite? | HIGH | UNKNOWN — no test files in scope. Recommend port archived tests. |

---

## Phase 3 Exit Sign

**Phase 3 is CONVERGED.**

All exit criteria satisfied. 9 deliverables produced (4,460 lines). 15 gaps identified (3 CRITICAL, 4 HIGH, 6 MEDIUM, 2 LOW). Implementation plan ready with 15 tasks across 4 layers.

**Recommendation:** Proceed to **Phase 4 (Market Data)** after P0 gaps are addressed.

**Phase 4 scope:**
- `archive/brokers/dhan/market_data.py` — Market data service
- `archive/brokers/dhan/depth_feed_base.py` — Depth feed base class
- `archive/brokers/dhan/depth_20.py`, `depth_200.py` — Depth feed implementations
- `archive/brokers/dhan/subscription_engine.py` — Subscription management
- `archive/brokers/dhan/websocket/` — WebSocket connection handling
- Estimated ~30-40 source files (largest phase)

---

*End of Phase 3 Convergence Gate*
