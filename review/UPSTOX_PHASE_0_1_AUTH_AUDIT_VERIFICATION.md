# Upstox Phase 0+1 Auth Audit — Re-Verification Report

**Date:** 2026-07-03  
**Source audit:** `review/UPSTOX_PHASE_0_1_AUTH_AUDIT.md`  
**Modern tree:** `brokers/adapters/upstox/`

## Summary

| Gap | Original Claim | Re-Verification | Status |
|-----|----------------|-----------------|--------|
| G1 | Missing `redirect_server.py` | Present with 7 unit tests | **STALE — REMEDIATED** |
| G2 | Missing `totp_scheduler.py` | Present; gateway wires when TOTP + auto_refresh | **STALE — REMEDIATED** |
| G3 | Missing `login.py` CLI | Present with unit tests | **STALE — REMEDIATED** |
| G4 | Missing `context.py` DI | Still absent; `BaseResilientHttpClient` used instead | **STILL VALID** |
| G5 | Static HTTP token | Callable provider + per-request refresh in `http.py` | **STALE — REMEDIATED** |
| G6 | No 401 retry | Retry exists but wired to `force_refresh` not `try_refresh_on_401`; 403 not retried | **PARTIALLY VALID — FIX IN PROGRESS** |
| G7 | TOTP skips refresh fallback | `_bootstrap_totp` catches Exception and falls back | **STALE — NOT A REGRESSION** |
| G8 | Wrong market-status URL | Uses `/v2/market/status/NSE` | **STALE — REMEDIATED** |
| G9 | No URL resolver | `brokers/config/endpoints.py` exists; adapter uses local `config.ENDPOINTS` | **PARTIALLY VALID** |
| G10 | No settings loader | `UpstoxSettingsLoader` exists; `UpstoxAuth` hardcodes `analytics_only=False` | **PARTIALLY VALID — FIX IN PROGRESS** |
| G11 | Truncated expiry guidance | Full guidance text present in `holders.py` | **STALE — REMEDIATED** |

## Remaining Auth Gaps (Post-Verification)

1. HTTP 401 handler must call `try_refresh_on_401()` not `force_refresh()`.
2. `analytics_only` from settings must propagate to `UpstoxAuth` and order guards.
3. WS token must refresh on `on_token_change` (streaming layer).
4. `UpstoxFeedAuthorizer` not ported (deferred in Phase 1 QA).

## Verdict

Original audit is **~55% stale** (6/11 gaps remediated since writing). Remaining items are tracked in the parity implementation backlog.
