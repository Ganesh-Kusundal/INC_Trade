# Phase 1 Authentication — Implementation Tasks

## Gap Remediation Plan

Tasks derived from the 17 gaps identified in `greenfield_design.md`, dependency-ordered for maximum safe parallelism.

---

## Task Dependency Graph

```
Layer 0 (No deps — all parallel)
┌──────────────────────────────────────────────────────────┐
│ T1: Log redaction filter    T2: should_generate_token() │
│ T3: Scheduler interval fix  T4: TokenState edge cases   │
└──────────────────────────────────────────────────────────┘
         │                    │
Layer 1 (Depends on Layer 0)
┌──────────────────────────────────────────────────────────┐
│ T5: load_canonical() reconciliation                      │
│ T6: on_error callback + ManagedService integration       │
│ T7: TokenPersistence.save() in scheduler                 │
└──────────────────────────────────────────────────────────┘
         │                    │
Layer 2 (Depends on Layer 1)
┌──────────────────────────────────────────────────────────┐
│ T8: authenticated_readiness_probe()                       │
│ T9: DhanSessionManager                                   │
│ T10: TotpCooldownGuard                                   │
└──────────────────────────────────────────────────────────┘
         │
Layer 3 (Depends on Layer 2)
┌──────────────────────────────────────────────────────────┐
│ T11: UpstoxFeedAuthorizer                                │
│ T12: Interactive OAuth CLI                               │
└──────────────────────────────────────────────────────────┘
```

---

## Layer 0 — No Dependencies (FULLY PARALLEL)

### T1: Port Log Redaction Filter (G5)

**Priority**: HIGH  
**Gap**: Missing `_redact_record_extras()` — secrets in `extra={}` leak to logs  
**Archive reference**: `common/auth/token.py` — `_redact_record_extras()` strips token fields from log `extra` dicts  

**Implementation**:
- Create `brokers/infrastructure/log_redaction.py`
- Implement `redact_record_extras(extra: dict) -> dict` that strips keys matching `token`, `access_token`, `refresh_token`, `secret`, `pin`, `password`
- Integrate as `structlog` processor or `logging.Filter`

**Acceptance criteria**:
1. `extra={"token": "abc123"}` → logged as `extra={"token": "***REDACTED***"}`
2. Unit test covers all secret field names from auth module
3. No performance regression (>1000 calls/sec)

**Estimated effort**: 1 hour

---

### T2: Port `should_generate_token()` Policy Function (G1)

**Priority**: HIGH  
**Gap**: Standalone policy function dropped; logic embedded in scheduler  
**Archive reference**: `common/auth/token_policy.py` — pure function with priority: `broker_rejected` → `missing` → `expired` → `proactive` → `don't`

**Implementation**:
- Create `brokers/resilience/token_policy.py`
- Implement `should_generate_token(state: TokenState | None, *, allow_proactive: bool = True, broker_rejected: bool = False) -> bool`
- Use in `TokenRefreshScheduler._do_refresh()` as decision gate

**Acceptance criteria**:
1. Returns `True` when state is `None` (missing token)
2. Returns `True` when `not state.is_valid()` (expired)
3. Returns `True` when `allow_proactive=True` and `state.refresh_recommended(buffer)` (proactive)
4. Returns `False` when `broker_rejected=True` (server rejected)
5. Unit test covers all 5 decision paths (mirrors archive `test_token_policy.py`)

**Estimated effort**: 1 hour

---

### T3: Fix Scheduler Check Interval (G9)

**Priority**: MODERATE  
**Gap**: Greenfield uses 60s interval vs archive 1200s — 20x more frequent checks increase rate-limit risk  
**Archive reference**: `domain/constants/auth.py` — `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS = 1200`

**Implementation**:
- Change default interval in `TokenRefreshScheduler.__init__()` from 60s to 300s (5min compromise)
- Make configurable via constructor parameter
- Document tradeoff: shorter = faster recovery, longer = lower rate-limit risk

**Acceptance criteria**:
1. Default interval is 300s
2. Constructor accepts `check_interval_seconds: float = 300.0`
3. Existing tests updated for new default
4. Docstring documents rate-limit tradeoff

**Estimated effort**: 30 minutes

---

### T4: Fix TokenState Edge Cases (Minor Gaps)

**Priority**: LOW  
**Gap**: `remaining_seconds()` returns `inf` for no-expiry (archive returns `0.0`); `refresh_recommended()` missing short-lived token guard  

**Archive reference**: `common/auth/token.py` L100-106 — short-lived token guard in `refresh_recommended()`

**Implementation**:
- `TokenState.remaining_seconds()`: Return `0.0` when `expires_at is None` (match archive)
- `TokenState.refresh_recommended()`: Add guard — if `remaining_seconds() < 60`, always recommend refresh regardless of buffer
- `TokenStateStore`: Convert from concrete class with `NotImplementedError` to proper `abc.ABC` with `@abstractmethod`
- `refresh_lock` property: Guarantee non-None return (raise if not initialized)
- `health()` return: Add `HealthState` enum (HEALTHY, DEGRADED, UNHEALTHY)

**Acceptance criteria**:
1. `TokenState(expires_at=None).remaining_seconds() == 0.0`
2. Short-lived token (< 60s remaining) always recommends refresh
3. `TokenStateStore` is proper ABC — cannot instantiate directly
4. `refresh_lock` raises `RuntimeError` if accessed before initialization
5. All existing tests pass with updated behavior

**Estimated effort**: 2 hours

---

## Layer 1 — Depends on Layer 0 (FULLY PARALLEL)

### T5: Port `load_canonical()` Reconciliation (G2)

**Priority**: HIGH  
**Gap**: Env-vs-store reconciliation by JWT expiry score dropped  
**Archive reference**: `common/auth/token_persistence.py` — `load_canonical()` compares JSON store vs .env file, picks token with latest JWT expiry  
**Depends on**: T2 (token policy uses reconciled state)

**Implementation**:
- Add `load_canonical()` method to `brokers/infrastructure/token_persistence.py`
- Implement JWT expiry comparison: parse `exp` claim from both sources, pick later
- Call during `TokenRefreshScheduler.start()` before first refresh check

**Acceptance criteria**:
1. When JSON store has newer token than .env → returns JSON token
2. When .env has newer token than JSON store → returns .env token
3. When either source is missing → returns the other
4. When both missing → returns `None`
5. Unit test with mock JWT tokens at different expiry times

**Estimated effort**: 2 hours

---

### T6: Port `on_error` Callback + ManagedService Integration (G6, G7)

**Priority**: MODERATE  
**Gap**: No external error tracking; cannot register with `LifecycleManager`  
**Archive reference**: `dhan/token_scheduler.py` — `on_error` callback with exception isolation  
**Depends on**: T2 (policy function used in error path)

**Implementation**:
- Add `on_error: Callable[[Exception], None] | None = None` to `TokenRefreshScheduler.__init__()`
- Wrap callback in try/except (archive pattern: buggy callbacks cannot crash scheduler)
- Add `ManagedService` protocol compliance: `start()`, `stop()`, `health()` methods
- Register with `LifecycleManager` if available

**Acceptance criteria**:
1. `on_error` callback invoked on every refresh failure
2. Exception in callback caught and logged (does not crash scheduler)
3. `ManagedService` protocol: `start()` idempotent, `stop(timeout)` joins thread
4. `health()` returns structured `HealthState` enum
5. Unit test verifies callback isolation (buggy callback doesn't stop scheduler)

**Estimated effort**: 2 hours

---

### T7: Port `TokenPersistence.save()` in Scheduler (G8)

**Priority**: MODERATE  
**Gap**: Refreshed tokens not persisted to disk/.env after refresh  
**Archive reference**: `dhan/token_scheduler.py` — calls `TokenPersistence.save(token)` after successful refresh  
**Depends on**: T5 (load_canonical needs persistence layer)

**Implementation**:
- Add `token_persistence: TokenPersistence | None = None` to `TokenRefreshScheduler.__init__()`
- After successful refresh in `_do_refresh()`, call `token_persistence.save(new_token)`
- Handle persistence failure gracefully (log + continue; don't crash scheduler)

**Acceptance criteria**:
1. After successful refresh, token written to disk
2. Persistence failure logged but does not stop scheduler
3. `save()` uses atomic write pattern (mkstemp + fchmod + os.replace)
4. Unit test with mock persistence verifies save called after refresh

**Estimated effort**: 1.5 hours

---

## Layer 2 — Depends on Layer 1 (FULLY PARALLEL)

### T8: Implement `authenticated_readiness_probe()` (G4)

**Priority**: CRITICAL  
**Gap**: No reactive auth recovery — token rejection not detected  
**Archive reference**: `common/connection/authenticated_readiness.py` — `authenticated_readiness_probe()`, `is_token_rejection()`, `AuthProbeResult`  
**Depends on**: T6 (ManagedService integration for lifecycle hooks)

**Implementation**:
- Create `brokers/resilience/authenticated_readiness.py`
- Implement `AuthProbeResult` frozen dataclass: `is_authenticated, token_rejection, force_refreshed, error, status`
- Implement `is_token_rejection(error) -> bool`: heuristic for 401/403/DH-906/DH-808/"invalid token"
- Implement `authenticated_readiness_probe(conn, auth, ...) -> AuthProbeResult`
- Integrate with connection lifecycle: probe on first message after connect

**Acceptance criteria**:
1. `is_token_rejection()` detects HTTP 401, 403, DH-906, DH-808, "invalid token" string
2. Probe returns `AuthProbeResult` with correct fields
3. On token rejection: force refresh attempted, result reflects outcome
4. Unit test mirrors archive `test_authenticated_readiness.py` (11 tests)
5. Integration test: probe after simulated 401 triggers refresh

**Estimated effort**: 4 hours

---

### T9: Implement DhanSessionManager (G3)

**Priority**: CRITICAL  
**Gap**: No unified readiness probe + lifecycle state  
**Archive reference**: `dhan/session_manager.py` — `lifecycle_state()`, `is_ready_for_trading()`, `health_summary()`  
**Depends on**: T8 (authenticated_readiness_probe used by session manager)

**Implementation**:
- Create `brokers/adapters/dhan/session_manager.py`
- Implement lifecycle states: `AUTH_REQUIRED → DISCONNECTED → DEGRADED → HEALTHY`
- Implement `is_ready_for_trading() -> bool` — pre-trade gate
- Implement `health_summary() -> dict` — unified auth/connection/subscription view
- Integrate with `TokenBroadcast` for token state updates

**Acceptance criteria**:
1. Lifecycle state transitions match archive state machine
2. `is_ready_for_trading()` returns `True` only in `HEALTHY` state
3. `health_summary()` includes auth, connection, subscription status
4. Unit test covers all state transitions
5. Pre-trade gate blocks order submission when not `HEALTHY`

**Estimated effort**: 4 hours

---

### T10: Implement TotpCooldownGuard (G12)

**Priority**: MODERATE  
**Gap**: No local cooldown; relies entirely on server rate-limit response  
**Archive reference**: `common/auth/token.py` — `TotpCooldownGuard` class with 120s cooldown  
**Depends on**: T6 (ManagedService integration)

**Implementation**:
- Create `brokers/resilience/totp_cooldown.py`
- Implement `TotpCooldownGuard(cooldown_seconds=120)`
- Add `can_attempt() -> bool` and `record_attempt()` methods
- Integrate with `DhanAuth.generate_token()` — check cooldown before HTTP call
- Raise `TokenRateLimitError` if cooldown not elapsed

**Acceptance criteria**:
1. First attempt succeeds
2. Second attempt within 120s raises `TokenRateLimitError`
3. Attempt after 120s succeeds
4. Cooldown resets on successful token generation
5. Unit test verifies timing (mock `time.monotonic()`)

**Estimated effort**: 2 hours

---

## Layer 3 — Depends on Layer 2 (SEQUENTIAL)

### T11: Implement UpstoxFeedAuthorizer (G11)

**Priority**: MODERATE  
**Gap**: WS feed authorization not implemented  
**Archive reference**: `upstox/websocket/feed_authorizer.py` — hardcoded 4 depth feed attributes  
**Depends on**: T8 (authenticated_readiness_probe for WS auth)

**Implementation**:
- Create `brokers/adapters/upstox/websocket/feed_authorizer.py`
- Implement `authorize_feed(ws_connection, token, feed_type) -> bool`
- Port hardcoded depth feed attributes: `depth`, `oi`, `s oi`, `b oi`, `s b oi`
- Integrate with WebSocket connection setup

**Acceptance criteria**:
1. Feed authorization sends correct auth message format
2. Depth feed attributes match archive (4 fields)
3. Unauthorized feed type returns `False`
4. Unit test with mock WebSocket connection

**Estimated effort**: 2 hours

**Note**: May be deferred to Phase 3 (WebSocket) if WS implementation not yet started.

---

### T12: Implement Interactive OAuth CLI (G10)

**Priority**: LOW  
**Gap**: No standalone OAuth login script  
**Archive reference**: `upstox/auth/login.py` — interactive OAuth PKCE CLI with local redirect server  
**Depends on**: T9 (session manager for post-login state)

**Implementation**:
- Create `brokers/scripts/upstox_login.py`
- Port OAuth PKCE flow: generate code_verifier, open browser, start local server, exchange code
- Implement local redirect server (port 8080, 300s timeout)
- Save token state via `JsonTokenStateStore`

**Acceptance criteria**:
1. Script opens browser to Upstox auth URL
2. Local server receives redirect callback
3. Code exchanged for token via `UpstoxOAuthClient.exchange_code()`
4. Token persisted to JSON store
5. Manual test: complete OAuth flow end-to-end

**Estimated effort**: 3 hours

**Note**: Low priority — OAuth tokens typically obtained via automated flow in production.

---

## Execution Summary

| Layer | Tasks | Parallelism | Total Effort |
|-------|-------|-------------|--------------|
| 0 | T1, T2, T3, T4 | 4 agents | 4.5 hours |
| 1 | T5, T6, T7 | 3 agents | 5.5 hours |
| 2 | T8, T9, T10 | 3 agents | 10 hours |
| 3 | T11, T12 | 1 agent (sequential) | 5 hours |
| **Total** | **12 tasks** | **Max 4 parallel** | **~25 hours** |

**Critical path**: T2 → T5 → T8 → T9 (token policy → reconciliation → readiness probe → session manager)

---

## Recommended Execution Order

```
Batch 1 (parallel): T1 + T2 + T3 + T4
    ↓
Batch 2 (parallel): T5 + T6 + T7
    ↓
Batch 3 (parallel): T8 + T9 + T10
    ↓
Batch 4 (sequential): T11 → T12
```

**Defer to Phase 3**: T11 (UpstoxFeedAuthorizer), T12 (Interactive OAuth CLI)  
**Must complete before Phase 2**: T1-T10 (all auth-critical gaps)
