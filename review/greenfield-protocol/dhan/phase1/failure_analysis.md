# Phase 1 Authentication — Failure Analysis

## Timeout & Retry Policies

### Dhan Token Generation

| Parameter | Value | Source |
|-----------|-------|--------|
| HTTP request timeout | 15s | `requests.post(url, timeout=15)` |
| TOTP cooldown | 120s (server-enforced) | `"once every 2 minutes"` in response |
| Scheduler backoff initial | 120s | `self._backoff_seconds = 120` |
| Scheduler backoff max | 600s | `min(self._backoff_seconds * 2, 600)` |
| Scheduler backoff sequence | 120 → 240 → 480 → 600 → 600 → ... | Exponential with cap |
| Scheduler backoff reset | On successful refresh | `_backoff_until = None` |
| Scheduler check interval | 1200s (archive) / 60s (greenfield) | `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS` |
| Stop timeout | `DEFAULT_STOP_TIMEOUT_SECONDS` (archive) / 10s (greenfield) | Thread join timeout |

### Upstox Token Refresh

| Parameter | Value | Source |
|-----------|-------|--------|
| Follower wait timeout | 30s | `_REFRESH_WAIT_SECONDS = 30.0` |
| Proactive refresh buffer | 30 min (default) | `refresh_buffer_minutes` setting |
| Login redirect server timeout | 300s | `upstox/auth/login.py` |
| Token expiry | 3:30 AM IST daily | `UpstoxTokenExpiry.next_expiry_epoch_ms()` |

## Exception Hierarchy

### Dhan

```
Exception
├── AuthenticationError (greenfield: brokers.domain.exceptions)
│   └── "pin and totp_secret are required"
│   └── "Token generation failed: {message}"
│   └── "Token generation failed: HTTP {code}"
│   └── "Token generation failed: no token in response"
└── TokenRateLimitError (greenfield: brokers.domain.exceptions)
    └── "Dhan token rate limit: {message}"
    └── "Dhan token rate limit: {body_text}"
```

### Upstox

```
Exception
└── UpstoxAuthError
    └── "Cannot refresh token: no refresh token available"
    └── "TOTP configuration incomplete..."
    └── "TOTP authentication failed..."
    └── "Token endpoint returned {status}: {text}"
    └── "No Upstox access token available..."
```

### Archive-Specific

```
TotpRateLimitError (brokers.common.auth.totp_cooldown)
└── Raised by TotpCooldownGuard when TOTP attempted within cooldown window
```

## Race Conditions

### Identified Race Conditions

| # | Race | Components | Risk | Mitigation |
|---|------|-----------|------|------------|
| R1 | Concurrent TOTP generation | Scheduler + HTTP 401 handler | Double TOTP → rate limit | Shared `refresh_lock` |
| R2 | Token read during refresh | `bearer_token()` + `_refresh_now()` | Stale token returned | Upstox: `RLock`; Dhan: GIL |
| R3 | Broadcast during teardown | `broadcast()` + receiver GC | Dead ref in broadcast | `list()` copy + dead-ref cleanup |
| R4 | Webhook vs proactive refresh | `upgrade_from_webhook()` + `ensure_valid()` | Token overwrite | Upstox: `_lock` serializes both |
| R5 | Bootstrap vs concurrent ensure_valid | `bootstrap()` + `ensure_valid()` | Duplicate TOTP generation | Upstox: `_run_exclusive_refresh` |
| R6 | `_refresh_now()` reads state without `_lock` | Upstox token manager | Torn read of `_state` | Low risk — single-leader pattern prevents concurrent mutation |

### Lock Hierarchy (Deadlock Analysis)

```
Upstox lock ordering (strict):
  Level 1: _refresh_lock (plain Lock) — leader election
  Level 2: _lock (RLock) — state access
  Level 3: _state_store._lock (RLock) — file I/O

No circular wait possible → deadlock-free.

Dhan: single _refresh_lock → no hierarchy needed.
Greenfield TokenManager: single _lock → no hierarchy needed.
```

## Recovery Paths

### Dhan Token Refresh Failure

```
TOTP generation fails
├── Rate limit ("once every 2 minutes")
│   └── TokenRateLimitError → exponential backoff (120→600s)
│       └── After backoff: next scheduler tick retries
├── Authentication error (bad PIN/secret)
│   └── AuthenticationError → logged, on_error callback, stays expired
│       └── No automatic recovery (needs credential fix)
├── Network timeout (15s)
│   └── AuthenticationError → same as auth error
└── HTTP non-200
    └── AuthenticationError or TokenRateLimitError → depends on response body
```

### Upstox Token Refresh Failure

```
OAuth refresh fails
├── No refresh_token → UpstoxAuthError (no recovery)
├── OAuth client exception → propagates to _run_exclusive_refresh
│   └── _refresh_done.set() in finally → followers unblocked
│       └── Followers return stale state
├── Follower timeout (30s) → log warning, return stale state
│   └── Next ensure_valid() call retries
└── TOTP fails
    ├── Has refresh_token → fallback to _acquire_initial()
    └── No refresh_token → UpstoxAuthError (no recovery)
```

## Secret Exposure Risks

| # | Vector | Severity | Detail |
|---|--------|----------|--------|
| V-001 | `TokenState` dataclass `__repr__` | HIGH | Auto-generated repr includes `access_token` and `refresh_token` |
| V-002 | `TokenSnapshot` dataclass `__repr__` | HIGH | Same issue — frozen dataclass exposes tokens |
| V-003 | Archive `env_token.py` temp file | MEDIUM | Temp file written with default umask (brief world-readable) |
| V-004 | `AuthenticationError` includes response body | MEDIUM | `f"...no token in response: {body}"` — body may contain partial tokens |
| V-005 | `UpstoxAuthError` includes `resp.text` | LOW | Error response could theoretically contain echoed secrets |
| V-006 | No `SecretStr` wrapper for PINs/secrets | LOW | Plain `str` in memory; no `mlock()` protection |
| V-007 | Greenfield missing `_redact_record_extras()` | HIGH | Archive's extra-field redaction not ported; `extra={"token": ...}` leaks |

## Error Callback Isolation

### Archive Scheduler
```python
if self._on_error:
    try:
        self._on_error(exc)
    except Exception as exc2:
        logger.debug("token_refresh_error_callback_failed: %s", exc2)
```
Buggy callbacks cannot crash the scheduler thread.

### Greenfield Scheduler
No `on_error` callback. Errors only logged. `on_refresh` callback IS isolated:
```python
if self._on_refresh is not None:
    try:
        self._on_refresh(token)
    except Exception as exc:
        logger.warning("token_refresh_callback_failed", ...)
```
