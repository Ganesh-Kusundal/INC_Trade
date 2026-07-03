# Phase 1 Authentication — State Machine

## Dhan Token States

```
┌──────────┐
│ NO_TOKEN │◄──── initial (no credentials)
└────┬─────┘
     │ generate_token() / store.load()
     ▼
┌──────────┐    is_valid()=true    ┌────────┐
│ IN_USE   │◄─────────────────────│REFRESHED│
└────┬─────┘                      └─────────┘
     │ is_valid()=false                ▲
     ▼                                 │
┌──────────┐    TOTP success     ┌──────────┐
│ EXPIRED  │────────────────────►│GENERATING│
└──────────┘                     └────┬─────┘
     ▲                                │
     │                          ┌─────┴──────┐
     │                          ▼            ▼
     │                   [SUCCESS]    [RATE_LIMITED]
     │                       │              │
     │                  persist +       backoff 120→600s
     │                  broadcast            │
     │                       │              │
     │                       └──────► IN_USE ◄┘
     │
     └── static token: no refresh possible → stays EXPIRED
```

### Dhan Scheduler States

| State | Condition | Signal |
|-------|-----------|--------|
| STOPPED | Thread not alive | `not is_running` |
| RUNNING (healthy) | Thread alive, no error, no backoff | `health() = HEALTHY` |
| BACKOFF | Rate-limited, cooldown active | `_backoff_until > now` |
| DEGRADED | Thread alive, `_last_error` set | `health() = DEGRADED` |

```
STOPPED ───start()──────────► RUNNING(healthy)
RUNNING ───stop()───────────► STOPPED
RUNNING ───TotpRateLimitError► BACKOFF
BACKOFF ───backoff_elapsed──► RUNNING(healthy)
RUNNING ───generic error─────► DEGRADED
DEGRADED ──success───────────► RUNNING(healthy)
```

## Upstox Token States

```
┌──────────┐    bootstrap()     ┌─────────────┐
│ NO_TOKEN │───────────────────►│ BOOTSTRAPPED│
└──────────┘                    └──────┬──────┘
                                       │ ensure_valid()
                                       ▼
                                ┌─────────────┐
                         ┌──────│    VALID     │◄──── refresh / webhook
                         │      └──────┬──────┘
                         │             │ now >= exp - buffer
                         │             ▼
                         │      ┌─────────────┐
                         │      │   EXPIRING   │──→ proactive refresh
                         │      └──────┬──────┘
                         │             │ refresh completes
                         │             ▼
                         │      ┌─────────────┐
                         │      │  REFRESHED   │──→ back to VALID
                         │      └──────┬──────┘
                         │             │ invalidate() or 401
                         │             ▼
                         │      ┌─────────────┐
                         └──────│ INVALIDATED  │
                                └─────────────┘
```

### Upstox Mode-Specific Paths

| Mode | Entry | Refresh | Terminal |
|------|-------|---------|----------|
| STATIC | BOOTSTRAPPED → VALID | None | Expires → no recovery |
| OAUTH | BOOTSTRAPPED → VALID → EXPIRING → REFRESHED | `_refresh_now()` via OAuth grant | refresh_token exhausted → error |
| EXTENDED | BOOTSTRAPPED → VALID (permanent) | None (skipped) | Never expires |
| WEBHOOK | NO_TOKEN → BOOTSTRAPPED (via webhook) | None (passive) | Superseded by newer |
| INTERACTIVE | NO_TOKEN → BOOTSTRAPPED (via browser) | Via subsequent OAUTH | User completes flow |
| TOTP | NO_TOKEN → BOOTSTRAPPED → VALID → EXPIRING | `_bootstrap_totp()` | Config invalid + no refresh → error |

## Dhan Session Lifecycle States

```
AUTH_REQUIRED ──token valid──► DISCONNECTED ──streams connect──► HEALTHY
      ▲                            │                               │
      │                            ├──partial connect──► DEGRADED ──┘
      │                            │                       │
      └──────token expires─────────┴───────────────────────┘
```

**Note**: This is a *computed* state machine — `lifecycle_state()` re-derives on every call.

## Token Refresh Coordination (Upstox)

```
┌──────────────────────────────────────────────────┐
│ _refresh_done Event                              │
│                                                  │
│ Thread A (leader):                               │
│   _refresh_lock → clear Event → action() → set   │
│                                                  │
│ Thread B (follower):                             │
│   _refresh_lock → Event already clear → wait(30s)│
│   → Event set → read state under _lock           │
└──────────────────────────────────────────────────┘
```
