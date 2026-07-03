# Phase 1 Authentication — Source Audit

## Scope

Every source file implementing authentication behavior in the archive and greenfield broker codebases.

**Archive root**: `archive/brokers/`
**Greenfield root**: `brokers/`

---

## Common/Core Subsystems

### Token Core (`common/auth/token.py` — 477 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `TokenSource` | Enum | `STATIC`, `TOTP`, `OAUTH`, `INTERACTIVE` |
| `TokenState` | Dataclass | `access_token`, `refresh_token`, `source`, `issued_at`, `expires_at`; methods: `is_valid()`, `remaining_seconds()`, `refresh_recommended()` |
| `TokenStateStore` | ABC | `load() → dict | None`, `save(state: dict)`, `clear()` |
| `JsonTokenStateStore` | Class | File-backed `TokenStateStore` with `0o600` permissions |
| `AuthManager` | Class | Full lifecycle: `acquire()`, `ensure_valid()`, `ensure_fresh()`, `force_refresh()`, `revoke()`, expiry/refresh callbacks |
| `TotpGenerator` | Class | Custom HMAC-SHA1 TOTP implementation |

**Key finding**: `AuthManager` has **ZERO threading primitives** — no locks, no thread safety.

### Token Policy (`common/auth/token_policy.py` — 27 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `should_generate_token()` | Function | Decision gate: `broker_rejected → missing → expired → proactive_refresh → don't regenerate` |

Priority order: `broker_rejected` → `missing` → `expired` → `proactive refresh` → `don't regenerate`.
Proactive refresh is opt-in (`allow_proactive=False` default).

### Token Persistence (`common/auth/token_persistence.py` — 144 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `TokenPersistence.load_canonical()` | Static | Reconciles JSON store vs env token by comparing JWT expiry scores |
| `TokenPersistence.save()` | Static | Writes JSON store + mirrors to `.env` via `update_env_token()` |
| `_expiry_score()` | Static | JWT `exp` claim in epoch-ms for conflict resolution |
| `_normalize_token_state()` | Static | Strips timezone info for consistent comparison |

### Env Token (`common/auth/env_token.py` — 85 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `update_env_token()` | Function | Atomic `.env` file updates with `fcntl.LOCK_EX`, `fsync`, `os.replace` |

**Minor vulnerability**: tmp file created with default umask (world-readable briefly).

### JWT Expiry (`common/auth/jwt_expiry.py` — ~50 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `JwtExpiry.parse_expiry_epoch_ms()` | Static | Parse JWT `exp` claim → epoch milliseconds |
| `JwtExpiry.parse_expiry_datetime()` | Static | Parse JWT `exp` claim → datetime |
| `JwtExpiry.is_expired()` | Static | Check if JWT token has expired |

### Auth Constants (`domain/constants/auth.py` — 42 lines)

| Constant | Value | Purpose |
|----------|-------|---------|
| `TOKEN_CLOCK_SKEW_SECONDS` | 30.0 | Grace period for token expiry |
| `TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS` | 300.0 | Proactive refresh window |
| `DHAN_TOKEN_REFRESH_BUFFER_SECONDS` | 600.0 | Dhan-specific buffer |
| `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS` | 1200 | Scheduler check interval |
| `DHAN_TOKEN_LIFETIME_SECONDS` | 86400 | Token TTL |
| `DHAN_REFRESH_COOLDOWN_SECONDS` | 60 | Min time between refreshes |

---

## Dhan-Specific Subsystems

### Token Manager (`dhan/token_manager.py` — 38 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `generate_totp_token()` | Method | Delegates to `DhanTotpClient(settings).generate()` |
| `read_secret()` | Method | Env-var-first, file-path-fallback pattern |

### TOTP Client (`dhan/totp_client.py` — ~100 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `DhanTotpClient.generate()` | Method | TOTP code generation via `TotpCooldownGuard`, resolves credentials from env/files |
| `_resolve_credentials()` | Method | Reads PIN + TOTP secret from env or file |
| `_read_secret()` | Method | `read_secret(env_key, file_key)` helper |

**Security**: PIN/TOTP sent in **POST body** (not URL).

### Token Scheduler (`dhan/token_scheduler.py` — 220 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `TokenRefreshScheduler` | Class (ManagedService) | Background daemon thread for expired-token refresh |
| `start()` | Method | Creates daemon thread; idempotent |
| `stop(timeout_seconds)` | Method | Sets stop event, joins thread |
| `refresh_now()` | Method | Immediate refresh via `_do_refresh()` |
| `_do_refresh()` | Private | Backoff → lock → state check → `should_generate_token` → `acquire` → persist → callback |
| `health()` | Method | Returns `HealthState.STOPPED/DEGRADED/HEALTHY` |

**Key features**: Shared `refresh_lock` with HTTP 401 handler; exponential backoff (120s→600s cap); `on_error` callback; `TokenPersistence.save()` integration.

### Connection Token Manager (`dhan/connection_token_manager.py` — 186 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `ConnectionTokenManager` | Class | Token-receiver registry + broadcast |
| `TokenReceiverRef` | Class | Weak-reference wrapper for idempotent registration |
| `register_receiver()` | Method | Idempotent; returns receiver unchanged |
| `broadcast(new_token)` | Method | Fan-out to all receivers; per-receiver exception isolation; dead-ref cleanup |

**Thread safety**: Single-threaded (asyncio event loop). No locks.

### Session Manager (`dhan/session_manager.py` — 74 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `DhanSessionManager` | Class | Unified auth/connection/subscription view |
| `token_valid()` | Method | Triple-`getattr` defensive check |
| `connection_state()` | Method | `{"market_feed": bool, "order_stream": bool}` |
| `lifecycle_state()` | Method | `AUTH_REQUIRED → DISCONNECTED → DEGRADED → HEALTHY` |
| `is_ready_for_trading()` | Method | `token_valid() AND order_stream connected` |

---

## Upstox-Specific Subsystems

### Login (`upstox/auth/login.py` — 242 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `perform_login()` | Function | Full interactive OAuth PKCE flow with CLI-runnable `main()` |
| `build_auth_url()` | Function | Authorization URL with PKCE params |
| `redirect_server` | Class | Local HTTP server to capture auth code (timeout 300s) |
| `_persist_state()` | Function | JSON file with `0o600` permissions |

**Archive-only** — no greenfield counterpart.

### OAuth Client (`upstox/auth/oauth_client.py` — 178 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `UpstoxOAuthClient.exchange_code()` | Method | Authorization code → tokens (PKCE) |
| `UpstoxOAuthClient.refresh_token()` | Method | Refresh token grant |
| `UpstoxOAuthClient.fetch_profile()` | Method | Get token expiry from profile API |
| `UpstoxOAuthClient.validate_read_only_token()` | Method | Validate extended token |
| `UpstoxOAuthClient.trigger_token_request()` | Method | Webhook token upgrade |

**FULL PARITY** with greenfield — line-for-line functional clone.

### Token Manager (`upstox/auth/token_manager.py` — 570 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `UpstoxTokenManager` | Class | Full token lifecycle across 6 modes |
| `bootstrap()` | Method | Acquire initial state (persisted → settings → TOTP) |
| `ensure_valid()` | Method | Proactive refresh if within buffer window |
| `try_refresh_on_401()` | Method | Reactive refresh after HTTP 401/403 |
| `force_refresh()` | Method | Unconditional refresh |
| `upgrade_from_webhook()` | Method | Replace state if newer expiry |
| `invalidate()` | Method | Query validity (does NOT clear state) |
| `_run_exclusive_refresh()` | Private | Leader/follower coordination with Lock + Event |

**Modes**: STATIC, OAUTH, EXTENDED, WEBHOOK, INTERACTIVE, TOTP.

### JSON Token State Store (`upstox/auth/json_token_state_store.py` — 65 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `JsonTokenStateStore` | Class | Atomic JSON file persistence with `mkstemp` + `fchmod(0o600)` + `os.replace` |

### Token Expiry (`upstox/auth/token_expiry.py` — 35 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `UpstoxTokenExpiry.next_expiry_epoch_ms()` | Static | Compute next 3:30 AM IST expiry epoch ms |

---

## Connection/WS Auth

### Authenticated Readiness (`common/connection/authenticated_readiness.py` — 244 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `AuthProbeResult` | Dataclass | Frozen: `is_authenticated`, `token_rejection`, `force_refreshed`, `error`, `status` |
| `authenticated_readiness_probe()` | Function | Probe → detect rejection → force refresh → retry |
| `is_token_rejection()` | Function | Heuristic classifier (401/403/DH-906/DH-808/invalid token) |

**NOT PORTED** to greenfield.

### WS Auth Coordinator (`common/connection/websocket_auth_coordinator.py` — 39 lines)

| Symbol | Kind | Purpose |
|--------|------|---------|
| `WebSocketAuthCoordinator.request_reconnect_on_token_change()` | Static | Update token + request reconnect on a feed |
| `WebSocketAuthCoordinator.notify_depth_feeds()` | Static | Force reconnect on 4 hardcoded depth feed attributes |

---

## Greenfield Counterparts

| Greenfield File | Lines | Archive Equivalent | Parity |
|----------------|-------|-------------------|--------|
| `resilience/token_manager.py` | 73 | `common/auth/token.py` (AuthManager) | PARTIAL — adds Lock + cooldown |
| `resilience/token_scheduler.py` | 221 | `dhan/token_scheduler.py` | PARTIAL — drops on_error, persistence, policy |
| `infrastructure/token_persistence.py` | 299 | `common/auth/token.py` + `token_persistence.py` + `env_token.py` | IMPROVED — atomic writes; LOST — no reconciliation |
| `adapters/dhan/auth.py` | 240 | `common/auth/token.py` (AuthManager) + `dhan/token_manager.py` | PARTIAL — DhanAuth with TokenState |
| `adapters/dhan/token_broadcast.py` | 183 | `dhan/connection_token_manager.py` | HIGH PARITY — rename + enhancements |
| `adapters/upstox/auth/oauth_client.py` | 155 | `upstox/auth/oauth_client.py` | FULL PARITY |
| `adapters/upstox/auth/token_manager.py` | 556 | `upstox/auth/token_manager.py` | NEAR-IDENTICAL |
| `adapters/upstox/auth/json_token_store.py` | 64 | `upstox/auth/json_token_state_store.py` | FUNCTIONALLY EQUIVALENT |
| `adapters/upstox/auth/token_expiry.py` | 29 | `upstox/auth/token_expiry.py` | IDENTICAL |

---

## Test Inventory

### Archived Tests (92 total, 91 pass)

| Test File | Tests | Status | Scope |
|-----------|-------|--------|-------|
| `common/auth/tests/test_token_policy.py` | 6 | ALL PASS | `should_generate_token()` decisions |
| `common/auth/tests/test_credential_resolver.py` | 8 | ALL PASS | Credential resolution |
| `common/auth/tests/test_credential_validator_upstox_files.py` | 1 | PASS | Upstox file validation |
| `common/auth/tests/test_environment_bootstrap.py` | 4 | ALL PASS | Env file loading |
| `common/auth/tests/test_totp_cooldown.py` | 5 | ALL PASS | TOTP rate limiting |
| `dhan/tests/unit/test_token_bootstrap_policy.py` | 2 | ALL PASS | Bootstrap dedup |
| `dhan/tests/unit/test_token_scheduler.py` | 13 | ALL PASS | Scheduler behavior |
| `dhan/tests/unit/test_token_scheduler_lifecycle.py` | 6 | ALL PASS | Lifecycle integration |
| `dhan/tests/unit/test_factory_auth.py` | 11 | ALL PASS | AuthManager integration |
| `upstox/tests/unit/test_login.py` | 8 | ALL PASS | Login flow |
| `upstox/tests/unit/test_oauth_client.py` | 7 | ALL PASS | OAuth client |
| `common/connection/tests/test_authenticated_readiness.py` | 11 | 10 PASS, 1 FAIL | Readiness probe (1 fail: `ModuleNotFoundError: cli`) |
| `common/connection/tests/test_websocket_auth_coordinator.py` | 8 | ALL PASS | WS auth coordination |

### Greenfield Tests (53 total, ALL PASS)

| Test File | Tests | Scope |
|-----------|-------|-------|
| `tests/unit/test_dhan_auth_state.py` | 12 | DhanAuth token lifecycle |
| `tests/unit/test_token_broadcast.py` | 11 | TokenBroadcast registry |
| `tests/unit/test_token_persistence.py` | 16 | TokenState, JsonTokenStateStore, update_env_token |
| `tests/unit/test_token_scheduler.py` | 10 | TokenRefreshScheduler |
