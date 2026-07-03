# Phase 1 Authentication — Runtime Sequence

## Dhan Token Lifecycle

### Startup / Bootstrap

```
DhanAuth.__init__(access_token, client_id, pin, totp_secret, token_store)
    │
    ├── access_token provided → store as STATIC, create TokenState
    │
    ├── token_store provided
    │   ├── store.load() → state.is_valid()? → reuse token + state
    │   └── store invalid/absent + pin+totp_secret → generate_token()
    │
    └── pin+totp_secret (no store) → generate_token()
```

### TOTP Generation

```
DhanAuth.generate_token()
    ├── validate pin + totp_secret present
    ├── pyotp.TOTP(totp_secret).now() → totp_code
    ├── urlencode({dhanClientId, pin, totp}) → URL query params
    ├── requests.post(url, timeout=15)
    │   ├── rate limit detected → raise TokenRateLimitError
    │   ├── status=error → raise AuthenticationError
    │   └── HTTP != 200 → raise AuthenticationError/TokenRateLimitError
    ├── extract accessToken from response
    └── create TokenState(source=TOTP, expires_at=now+86400s)
```

### Periodic Background Refresh

```
TokenRefreshScheduler._run() [daemon thread, every 1200s archive / 60s greenfield]
    │
    └── _do_refresh()
        ├── [1] Backoff: time.monotonic() < _backoff_until → return False
        ├── [2] Lock: _refresh_lock.acquire(blocking=False) → fail → return False
        ├── [3] State: auth.state.is_valid() → return True (skip)
        ├── [4] Policy: should_generate_token(state, allow_proactive=False)
        │       └── None/empty/expired → True; valid → False
        ├── [5] Refresh: auth.acquire() → new TokenState
        ├── [6] Token changed? → TokenPersistence.save(refreshed, store, env_file)
        ├── [7] Callback: on_refresh(new_access_token)
        ├── [8] Increment _refresh_count, clear _last_error, clear _backoff
        └── [9] On TotpRateLimitError → exponential backoff (120→240→480→600s cap)
```

### Token Broadcast

```
ConnectionTokenManager.broadcast(new_token)
    ├── snapshot = list(_token_receivers)  # copy for safe iteration
    ├── for each ref in snapshot:
    │   ├── ref.deref() → None? → cleanup dead ref, continue
    │   ├── receiver(new_token) → success → delivered++
    │   └── receiver raises? → log warning, continue (isolation)
    └── return delivered count
```

---

## Upstox Token Lifecycle

### Mode Determination at Startup

```
UpstoxTokenManager.__init__(settings)
    └── _build_initial_holder()
        ├── analytics_only → UpstoxAnalyticsTokenHolder
        ├── is_extended + extended_token → UpstoxExtendedTokenHolder
        ├── is_totp → placeholder "placeholder-totp-will-refresh"
        ├── is_static or access_token without refresh → UpstoxStaticTokenHolder
        ├── access_token + refresh_token → UpstoxStaticTokenHolder (bootstrap)
        └── no token → placeholder "placeholder-no-token"
```

### Bootstrap

```
bootstrap()
    ├── [TOTP] _bootstrap_totp_if_needed()
    │   ├── In-memory valid? → return cached
    │   ├── Persisted valid? → load + restore → return
    │   └── _bootstrap_totp()
    │       ├── UpstoxTotpClient.generate_token()
    │       ├── Parse JWT expiry (or 3:30 AM IST fallback)
    │       ├── _apply_token_state() → persist to JSON
    │       └── On failure: fallback to refresh_token if available, else raise
    │
    ├── [State store] load persisted
    │   ├── Valid? → _from_persisted() → restore → return
    │   └── Invalid/missing → _acquire_initial()
    │
    └── _acquire_initial()
        ├── access_token + refresh_token → fetch_profile expiry → OAUTH state
        ├── access_token only → JWT parse expiry → STATIC state
        └── No token → raise UpstoxAuthError
```

### Proactive Refresh

```
ensure_valid()
    ├── analytics_only → return (no-op)
    ├── is_extended → return (no-op)
    ├── !_needs_proactive_refresh() → return (token still good)
    │   └── now_ms < exp_ms - buffer_ms (default 30 min)
    ├── is_totp → _run_exclusive_refresh(_do_totp_force_refresh)
    └── has refresh_token → _run_exclusive_refresh(_do_oauth_refresh)
```

### Leader/Follower Refresh Coordination

```
_run_exclusive_refresh(action)
    ├── _refresh_lock: check _refresh_done Event
    │   ├── Event was set → clear it, leader = True
    │   └── Event was clear → leader = False
    ├── [Leader] → action() → finally: _refresh_done.set()
    └── [Follower] → _refresh_done.wait(timeout=30s)
        ├── Success → return self._state (under _lock)
        └── Timeout → log warning, return self._state (may be stale)
```

### Webhook Upgrade

```
upgrade_from_webhook(access_token, expires_at_ms)
    ├── Validate: non-blank token, positive expiry
    ├── should_replace = current is None OR expired OR new expiry > current
    ├── [Replace] → preserve refresh_token → new WEBHOOK state → persist → True
    └── [Skip] → log debug → False
```

---

## Cross-Cutting Sequences

### Token Expiry Detection

**Dhan**: `TokenState.is_valid()` → `remaining_seconds() > -30.0` (clock skew grace)
**Upstox**: `_needs_proactive_refresh()` → `now_ms >= exp_ms - buffer_ms`

### 3:30 AM IST Expiry (Upstox)

```
UpstoxTokenExpiry.next_expiry_epoch_ms()
    ├── now = datetime.now(IST) or provided
    ├── expiry_today = combine(now.date(), 3:30, IST)
    ├── now >= expiry_today? → expiry_today += 1 day
    └── return int(expiry_today.timestamp() * 1000)
```

### Token Persistence Reconciliation (Archive Only)

```
TokenPersistence.load_canonical(store, env_file)
    ├── Load from JSON store (normalize to naive UTC)
    ├── Load env token
    ├── Both absent → None
    ├── Only env → build TokenState from env token
    ├── Only store → return stored
    ├── Same token → return stored (enriched with JWT expiry)
    └── Different tokens → compare _expiry_score()
        ├── _expiry_score() = JWT exp claim or expires_at.timestamp() or 0
        └── Winner: token with later expiry
```
