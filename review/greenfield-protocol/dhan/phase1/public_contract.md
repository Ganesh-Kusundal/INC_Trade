# Phase 1 Authentication — Public Contract

## Dhan Auth Contract

### DhanAuth

| Method | Input | Output | Exceptions | Side Effects |
|--------|-------|--------|------------|--------------|
| `__init__` | `access_token, client_id, pin, totp_secret, token_lifetime_seconds, token_store` | — | — | Creates TokenState if token obtained |
| `state` (property) | — | `TokenState \| None` | — | Read-only |
| `get_token()` | — | `str` | — | Returns current access token |
| `is_valid()` | — | `bool` | — | Delegates to `TokenState.is_valid()` |
| `is_authenticated()` | — | `bool` | — | `bool(access_token)` |
| `generate_token()` | — | `str` | `AuthenticationError`, `TokenRateLimitError` | Creates new TokenState, updates `_access_token` |
| `refresh_token()` | — | `str` | — | Calls `generate_token()` if credentials present |
| `acquire()` | — | `TokenState \| None` | — | Calls `generate_token()`, returns state |
| `force_refresh()` | — | `TokenState \| None` | — | Delegates to `acquire()` |

### TokenRefreshScheduler

| Method | Input | Output | Exceptions | Side Effects |
|--------|-------|--------|------------|--------------|
| `start()` | — | `None` | — | Creates daemon thread; idempotent |
| `stop(timeout_seconds=10)` | — | `None` | — | Sets stop event, joins thread |
| `refresh_now()` | — | `bool` | — | Immediate refresh via `_do_refresh()` |
| `is_running` (property) | — | `bool` | — | Thread alive check |
| `refresh_count` (property) | — | `int` | — | Successful refresh count |
| `refresh_lock` (property) | — | `Lock \| None` | — | Shared lock for HTTP 401 handler |
| `health()` | — | `dict` | — | State + metrics |

### TokenBroadcast (Greenfield) / ConnectionTokenManager (Archive)

| Method | Input | Output | Exceptions | Side Effects |
|--------|-------|--------|------------|--------------|
| `register_receiver(receiver)` | `Callable[[str], None]` | Same receiver | — | Idempotent append |
| `unregister_receiver(receiver)` | `Callable[[str], None]` | `bool` | — | Greenfield only |
| `broadcast(new_token)` | `str` | `int` (delivered) | Per-receiver caught | Fan-out + dead-ref cleanup |
| `receiver_count` (property) | — | `int` | — | Cleans dead refs |
| `token_refresh_metrics` (property) | — | `dict[str, int]` | — | Archive: static; Greenfield: live |

### DhanSessionManager (Archive Only — NOT PORTED)

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `token_valid()` | — | `bool` | Never |
| `connection_state()` | — | `dict[str, bool]` | Never |
| `subscription_snapshot()` | — | `dict[str, Any]` | Never* |
| `lifecycle_state()` | — | `str` | Never |
| `is_ready_for_trading()` | — | `bool` | Never |
| `health_summary()` | — | `dict[str, Any]` | Never |

*If `subscription_engine` exists but its methods raise, those propagate.

---

## Upstox Auth Contract

### UpstoxTokenManager

| Method | Input | Output | Exceptions | Side Effects |
|--------|-------|--------|------------|--------------|
| `bearer_token()` | — | `str` | — | Calls `ensure_valid()` first |
| `current_token()` | — | `str \| None` | — | No refresh trigger |
| `current_state()` | — | `TokenSnapshot \| None` | — | Under `_lock` |
| `ensure_valid()` | — | `None` | Propagates from refresh | Proactive refresh if near expiry |
| `try_refresh_on_401()` | — | `bool` | Catches all → `False` | Reactive refresh |
| `force_refresh()` | — | `TokenSnapshot \| None` | `UpstoxAuthError` if no refresh_token | Unconditional refresh |
| `refresh_totp()` | — | `TokenSnapshot` | `UpstoxAuthError` if None | TOTP regeneration |
| `bootstrap()` | — | `TokenSnapshot` | `UpstoxAuthError` | One-time init |
| `perform_interactive_oauth(pkce, redirect, browser)` | PKCE + callbacks | `PkcePair` | — | Builds auth URL |
| `complete_interactive_oauth(code, pkce, redirect)` | Auth code + PKCE | `TokenSnapshot` | From `exchange_code` | Persists state |
| `upgrade_from_webhook(token, expiry)` | Token + expiry ms | `bool` | `ValueError` if invalid | Replaces if newer |
| `invalidate(access_token=None)` | Optional token | `bool` | — | Query only, no mutation |
| `create_extended(token)` (classmethod) | Token | `UpstoxExtendedTokenHolder` | — | Factory |
| `create_analytics(token)` (classmethod) | Token | `UpstoxAnalyticsTokenHolder` | — | Factory |
| `create_static(token)` (classmethod) | Token | `UpstoxStaticTokenHolder` | — | Factory |

### UpstoxOAuthClient

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `exchange_code(code, client_id, client_secret, redirect_uri, code_verifier)` | OAuth params | `TokenResponse` | `UpstoxAuthError` on non-2xx |
| `refresh_token(refresh_token, client_id, client_secret)` | Refresh grant | `TokenResponse` | `UpstoxAuthError` on non-2xx |
| `fetch_profile(access_token)` | Bearer token | `int` (expiry epoch ms) | — |
| `validate_read_only_token(access_token)` | Bearer token | `bool` | — |
| `trigger_token_request(client_id, client_secret, ...)` | Webhook request | `TokenResponse` | `UpstoxAuthError` |

### JsonTokenStateStore (Upstox)

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `__init__(path)` | `Path \| str \| None` | — | — |
| `load()` | — | `dict \| None` | Catches `JSONDecodeError`, `OSError` → `None` |
| `save(state: dict)` | Dict | `None` | Re-raises after cleanup |
| `clear()` | — | `None` | Catches `OSError` (greenfield) |

### UpstoxTokenExpiry

| Method | Input | Output |
|--------|-------|--------|
| `next_expiry_epoch_ms(now=None)` | Optional datetime | `int` (epoch ms) |

Computes next 3:30 AM IST. If past today's 3:30 AM, uses tomorrow.

---

## Cross-Cutting Contracts

### TokenState (Greenfield)

| Method | Contract |
|--------|----------|
| `is_valid()` | `remaining_seconds() > -30.0` (clock skew grace) |
| `remaining_seconds()` | `(expires_at - now).total_seconds()`; `inf` if no expiry |
| `refresh_recommended(buffer_seconds)` | `remaining_seconds() < buffer_seconds`; always `False` if no expiry |

### Authenticated Readiness (Archive Only)

| Function | Contract |
|----------|----------|
| `authenticated_readiness_probe(conn, auth, ...)` | Probe → detect rejection → force refresh → retry |
| `is_token_rejection(error)` | Heuristic: 401/403/DH-906/DH-808/"invalid token" |
| `AuthProbeResult` | Frozen dataclass: `is_authenticated, token_rejection, force_refreshed, error, status` |
