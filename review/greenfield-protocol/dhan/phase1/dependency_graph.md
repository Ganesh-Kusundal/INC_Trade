# Phase 1 Authentication — Dependency Graph

## Internal Dependencies

```
Wave 0 (Leaves — zero internal deps)
┌──────────────────────────────────────────────────────────────────┐
│ [Auth Constants]  [JWT Expiry]  [Env Token]  [WS Auth Coord]   │
│ [Token Core]      [Feed Auth]                                    │
└──────────────────────────────────────────────────────────────────┘
       │              │             │
Wave 1 (Depends on Wave 0)
┌──────────────────────────────────────────────────────────────────┐
│ [Token Persistence]  [Dhan Token Mgr]  [Upstox Login]           │
│ [Upstox OAuth]  [Authenticated Readiness]                        │
└──────────────────────────────────────────────────────────────────┘
       │              │                │
Wave 2 (Integration — depends on Wave 0 + 1)
┌──────────────────────────────────────────────────────────────────┐
│ [Dhan Token Scheduler]  [Dhan Conn Token Mgr]  [Upstox Token Mgr]│
│ [Dhan Session Manager]                                            │
└──────────────────────────────────────────────────────────────────┘
```

## Dependency Edge Table

| Subsystem | Depends On | Blocked By |
|-----------|-----------|------------|
| Auth Constants | nothing | — |
| JWT Expiry | nothing | — |
| Env Token | nothing | — |
| WS Auth Coordinator | nothing | — |
| Feed Authorizer | nothing | — |
| Token Core | Auth Constants | Auth Constants |
| Token Policy | Token Core (TokenState) | Token Core |
| Token Persistence | Token Core, Env Token | Token Core, Env Token |
| Dhan Token Manager | Token Core, Env Token | Token Core, Env Token |
| Upstox Login | OAuth Client | OAuth Client |
| Upstox OAuth Client | nothing | — |
| Authenticated Readiness | Token Core | Token Core |
| Dhan Token Scheduler | Token Core, Dhan Token Mgr, Token Persistence, Token Policy | Token Core, Dhan Token Mgr |
| Dhan Connection Token Mgr | nothing (pure registry) | — |
| Upstox Token Manager | Token Core, Upstox OAuth, JSON Token State Store, JWT Expiry | Token Core, Upstox OAuth |
| Dhan Session Manager | Token Core (AuthManager) | Token Core |

## External Dependencies

| Auth Module | External Dependency | Purpose |
|-------------|-------------------|---------|
| Dhan TOTP Client | `pyotp` library | TOTP code generation |
| Dhan Auth | `requests` library | HTTP POST to Dhan API |
| Upstox OAuth Client | `requests` library | HTTP calls to Upstox API |
| Env Token | `fcntl` (Unix) | File locking |
| All | `threading` (stdlib) | Locks, Events, Threads |
| All | `logging` (stdlib) | Structured logging |
| Archive Scheduler | `ManagedService` ABC | Lifecycle integration |
| Archive AuthManager | `TotpCooldownGuard` | Rate limit protection |

## Greenfield Dependency Changes

| Change | Archive | Greenfield | Impact |
|--------|---------|------------|--------|
| AuthManager split | Monolithic `AuthManager` | `DhanAuth` + `TokenManager` + `TokenRefreshScheduler` | Better separation of concerns |
| Token persistence | `TokenPersistence` orchestration layer | Direct store access in `DhanAuth.__init__` | Lost reconciliation logic |
| Policy function | Standalone `should_generate_token()` | Inlined in `_do_refresh()` | Lost `broker_rejected` path |
| ManagedService | `ManagedService` ABC + `HealthState` enum | Plain class + dict health | Lost lifecycle integration |
| TOTP generation | Custom `TotpGenerator` (HMAC-SHA1) | `pyotp` library | External dependency added |
| Import paths | `brokers.common.auth.*` | `brokers.adapters.*` + `brokers.resilience.*` | Reorganized |
