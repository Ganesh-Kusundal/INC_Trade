# Phase 1 Authentication — Greenfield Design

## Architecture Overview

The greenfield restructures authentication from a monolithic `AuthManager` into focused, composable modules:

```
Archive:                          Greenfield:
┌─────────────────────┐           ┌──────────────────────────────┐
│ AuthManager         │           │ resilience/                  │
│  - acquire()        │           │   TokenManager (Lock+cooldown)│
│  - ensure_valid()   │  ────►    │   TokenRefreshScheduler      │
│  - force_refresh()  │           │                              │
│  - revoke()         │           │ adapters/dhan/               │
│  - callbacks        │           │   DhanAuth (TokenState)      │
│  - NO LOCKS         │           │   TokenBroadcast             │
└─────────────────────┘           │                              │
                                  │ adapters/upstox/auth/        │
                                  │   UpstoxTokenManager (RLock) │
                                  │   UpstoxOAuthClient          │
                                  │   JsonTokenStateStore        │
                                  │   UpstoxTokenExpiry          │
                                  └──────────────────────────────┘
```

## Improvements Over Archive

### 1. Thread Safety (AuthManager → TokenManager)

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| State protection | None | `threading.Lock` on all access |
| Cooldown enforcement | External (`TotpCooldownGuard`) | Internal (`_cooldown` check) |
| TTL tracking | Via `TokenState.expires_at` | Via `_token_ttl` + `expires_at` |

### 2. Atomic File I/O

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| JSON store | `write_text()` + `chmod 0o600` (race) | `mkstemp` + `fchmod(0o600)` + `os.replace` |
| Env token | Temp file with default umask | Temp file with `fchmod(tmp_fd, 0o600)` |

### 3. Token Broadcast (ConnectionTokenManager → TokenBroadcast)

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Unregister | Not supported | `unregister_receiver()` added |
| Metrics | Static `{0, 0}` | Live `_refresh_count`, `_error_count` |
| Method detection | `isinstance(types.MethodType)` | `hasattr(__self__)` duck typing |
| Dead-ref cleanup | Inline during broadcast | Batch after broadcast |

### 4. Upstox Token Manager

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Attribute access | Direct (`s.is_totp`) | Defensive `getattr(s, "is_totp", False)` |
| TOTP error handling | Catches all → fallback | Re-raises `UpstoxAuthError` directly |
| Auth URL base | `self._oauth_client._base_url` (private) | `getattr(settings, "base_v2", ...)` |
| Error message | `performInteractiveOAuth()` (Java-ism) | `perform_interactive_oauth()` |

## Dropped Archive Behaviors (Gaps)

### Critical Gaps

| Gap | Archive Feature | Impact | Priority |
|-----|----------------|--------|----------|
| **G1**: No `should_generate_token()` | Standalone policy function with `broker_rejected` flag | Harder to audit "only expired triggers regen" | HIGH |
| **G2**: No `TokenPersistence.load_canonical()` | Env-vs-store reconciliation by JWT expiry score | Stale tokens possible if env has newer | HIGH |
| **G3**: No `DhanSessionManager` | Unified readiness probe + lifecycle state | No pre-trade gate | CRITICAL |
| **G4**: No `authenticated_readiness_probe()` | Token rejection detection + force refresh + retry | No reactive auth recovery | CRITICAL |
| **G5**: No `_redact_record_extras()` | Extra-field log redaction | Secrets in `extra={}` leak to logs | HIGH |

### Moderate Gaps

| Gap | Archive Feature | Impact |
|-----|----------------|--------|
| **G6**: No `on_error` callback | External error tracking impossible |
| **G7**: No `ManagedService` integration | Cannot register with `LifecycleManager` |
| **G8**: No `TokenPersistence.save()` in scheduler | Refreshed tokens not persisted to disk/.env |
| **G9**: Scheduler interval 60s vs 1200s | 20x more frequent checks → higher rate-limit risk |
| **G10**: No `login.py` interactive CLI | No standalone OAuth login script |
| **G11**: No `UpstoxFeedAuthorizer` | WS feed authorization not implemented |
| **G12**: No `TotpCooldownGuard` | No local cooldown; relies on server rate-limit response |

### Minor Gaps

| Gap | Detail |
|-----|--------|
| `TokenState.refresh_recommended()` | Missing short-lived token guard (archive L100-106) |
| `TokenState.remaining_seconds()` | Returns `inf` for no-expiry (archive returns `0.0`) |
| `TokenStateStore` | Concrete class with `NotImplementedError` vs proper ABC |
| `refresh_lock` property | Can return `None` (archive guarantees non-None) |
| `health()` return type | Plain dict vs structured `HealthState` enum |

## Design Principles Applied

1. **Separation of concerns**: Auth state (DhanAuth) separated from scheduling (TokenRefreshScheduler) separated from broadcast (TokenBroadcast)
2. **Defensive attribute access**: `getattr()` throughout Upstox token manager prevents `AttributeError`
3. **Atomic I/O**: All file writes use `mkstemp` + `fchmod` + `os.replace` pattern
4. **Weak references**: Token broadcast uses weak refs to prevent memory leaks
5. **Exception isolation**: Per-receiver failure isolation in broadcast; per-attempt isolation in scheduler
