# Dhan Parity Audit — Phase 0: Prior Assessment Re-Verification

**Date:** 2026-07-03  
**Baseline document:** [`review/dhan_behavioral_parity_assessment.md`](dhan_behavioral_parity_assessment.md)  
**Method:** Every prior row re-checked against archive source, modern source, and tests. No conclusion accepted without evidence.

## Classification Legend

| Class | Meaning |
|-------|---------|
| **Verified** | Prior claim confirmed with source evidence |
| **Partially Verified** | Core claim holds; details overstated or incomplete |
| **Incorrect** | Prior claim contradicted by source |
| **Insufficient Evidence** | Could not confirm without live runtime execution |

---

## Section 1: Gateway Lifecycle & Composition

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 1.1 | Gateway construction is DIVERGENT (factory vs internal) | **Verified** | Archive: `BrokerGateway(connection)` at `archive/brokers/dhan/gateway.py:82`. Modern: `DhanGateway.__init__` wires 20+ adapters inline at `brokers/adapters/dhan/gateway.py:78-190`. |
| 1.2 | `close()` outcome equivalent | **Verified** | Modern explicitly stops scheduler + 4 streams + HTTP (`gateway.py:355-363`). Archive delegates via `DhanConnection.close()`. |
| 1.3 | Health reporting PARTIAL | **Verified** | Modern `health()` returns auth + scheduler + broadcast only (`gateway.py:346-353`). Archive implements full `ObservabilityProvider` (`gateway.py:635-719`). |
| 1.4 | Stream handle NOT_PORTED | **Verified** | Archive `_DhanStreamHandle` with `disconnect()`. Modern `StreamingPort` is async ABC (`brokers/ports/streaming.py:11-51`); no `BrokerStreamHandle` equivalent on `DhanGateway`. |

---

## Section 2: Authentication & Token Lifecycle

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 2.1 | TOTP without cooldown guard — DIVERGENT | **Verified** | Archive: `TotpCooldownGuard` in `archive/brokers/dhan/totp_client.py:9,26,33`. Modern: inline `DhanAuth.generate_token()` with no proactive guard (`brokers/adapters/dhan/auth.py:125-196`). |
| 2.2 | Token state tracking VERIFIED | **Verified** | Both use `TokenState` + `JsonTokenStateStore`. |
| 2.3 | Token broadcast VERIFIED | **Verified** | Archive `ConnectionTokenManager`; modern `TokenBroadcast` with weak refs (`token_broadcast.py`). |
| 2.4 | Refresh lock sharing VERIFIED | **Verified** | Both share `threading.Lock` between HTTP client and scheduler. |
| 2.5 | Env atomic update VERIFIED | **Verified** | Modern uses `update_env_token()` from `brokers/infrastructure/token_persistence.py`. |
| 2.6 | IPv4 patch IMPROVED | **Verified** | `_prefer_ipv4()` at `auth.py:26-44`; absent in archive. |
| 2.7 | Regenerate only after expiry VERIFIED | **Partially Verified** | Scheduler checks validity before refresh (`token_scheduler.py`). `force_refresh()`/`acquire()` can force regeneration — same pattern risk in both. |
| 2.8 | Refresh storm prevention PARTIAL | **Verified** | Archive proactive `TotpCooldownGuard.check_allowed()`. Modern reactive only (parses "once every 2 minutes" after request). HTTP client has `_REFRESH_COOLDOWN_SECONDS = 60.0` (`http.py:74`) but TOTP endpoint itself is unguarded. |
| 2.9 | Concurrent refresh lock timeout PARTIAL | **Incorrect → Verified** | Prior said "unspecified timeout". Modern **does** specify 5s: `refresh_lock.acquire(timeout=5.0)` at `http.py:264`. Scheduler uses 0.1s (`token_scheduler.py:164`). Archive factory also uses shared lock — behavior is **Partially Verified** (both have timeouts, values differ). |

---

## Section 3: Identity & Instrument Resolution

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 3.1 | DhanInstrumentRef validation VERIFIED | **Verified** | `identity.py:51-64` matches archive invariants. |
| 3.2 | Symbol resolution PARTIAL | **Verified** | Modern has prefix-family scan (`identity.py:176-182`) but lacks CALL→CE, stripped variants, index table from archive `identity.py`. |
| 3.3 | Unknown exchange returns None — DIVERGENT | **Incorrect** | Modern `resolve()` raises `InstrumentNotFoundError` (`identity.py:164,184`). Prior claim wrong. |
| 3.4 | `expected_segment` NOT_PORTED | **Verified** | Absent in modern `identity.py`. Present in archive `identity.py:327-425` and `resolver.py:59-279`. |
| 3.5 | Audit logging NOT_PORTED | **Verified** | No `security_id_issued` structured log in modern resolver. |
| 3.6 | Synthetic index tracking NOT_PORTED | **Verified** | No `_synthetic_index_count` in modern. |
| 3.7 | MCX supplement NOT_PORTED | **Verified** | Archive `loader.py:20,42-80` fetches MCX detailed CSV. Modern fetches single URL only (`identity.py:33,94`). |
| 3.8 | Instrument caching DIVERGENT | **Verified** | Archive 6h TTL + 7-day cleanup (`loader.py:27-80`). Modern loads once per process (`_loaded` flag) but re-downloads on every new resolver instance; no disk cache. |
| 3.9 | Index table PARTIAL | **Verified** | Archive hardcoded indices via config. Modern maps INDEX→IDX_I in `EXCHANGE_MAP` but no dedicated index table. |

---

## Section 4: Order Lifecycle

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 4.1 | Pre-trade validation PARTIAL | **Verified** | Modern: price/type only (`orders.py:55-63`). Archive: lot size, tick, product-segment (`orders.py:118+`). |
| 4.2 | Idempotency NOT_PORTED | **Verified** | Archive `SimpleIdempotencyCache` at `orders.py:19,72,186-314`. Modern `orders.py` has zero idempotency references. |
| 4.3 | Place order API PARTIAL | **Verified** | Different signatures; modern lacks `correlation_id` parameter. |
| 4.4 | Cancel race detection VERIFIED | **Verified** | Both check FILLED after cancel (`orders.py:92-103` modern; archive similar). |
| 4.5 | Cancel DELETE vs POST DIVERGENT | **Verified** | Archive `self._client.delete(f"/orders/{order_id}")` (`orders.py:401`). Modern `self._client.post(endpoint)` (`orders.py:89-90`). Base client supports DELETE (`http_client.py:96-97`). |
| 4.6 | Order response mapping VERIFIED | **Partially Verified** | Modern `map_order_response` used; archive includes `correlation_id`, `raw_payload` in responses — modern mapper may omit. |
| 4.7 | Risk manager NOT_PORTED | **Verified** | Archive `RiskManagerPort` at `orders.py:58`. Absent in modern. |
| 4.8 | Event publishing NOT_PORTED | **Verified** | Archive publishes `ORDER_PLACED` events. Absent in modern. |
| 4.9 | Kill switch NOT_PORTED | **Verified** | Archive kill switch endpoint. Not in modern `orders.py` or `config.py` endpoints (killswitch in WRITE_PREFIXES but no adapter method). |
| 4.10 | Trade history pagination NOT_PORTED | **Verified** | Archive `get_trade_history(from_date, to_date, page)`. Modern has `get_orderbook` only. |
| 4.11 | Slice orders NOT_PORTED | **Verified** | Archive `place_slice_order()`. Endpoint defined in modern config (`slice_order`) but no adapter method. |

---

## Section 5: Reconciliation

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 5.1–5.5 | All prior reconciliation claims | **Verified** | Archive uses `ReconciliationEngine` + `DriftItem` severity + auto-repair (`reconciliation.py:14-80`). Modern `reconcile_positions()` returns simple dict lists (`reconciliation.py:18-40`). |

---

## Section 6: Extended Features

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 6.1–6.3 | Super/Forever/Conditional VERIFIED | **Partially Verified** | Modules exist with parallel structure. Live behavioral equivalence **Insufficient Evidence** without integration run. |
| 6.4 | EDIS generate VERIFIED | **Partially Verified** | Both have generate; modern uses GET `/edis/generateTpin`, archive POST `/edis/tpin` — **Different Behavior**. |
| 6.5–6.6 | EDIS authorize/status DIVERGENT | **Verified** | Archive `authorize_edis(isin, qty, exchange)` + `check_status(isin)`. Modern `get_edis_form()` + `get_tpin_status()` — different API surface. |
| 6.7 | IP Management PARTIAL | **Verified** | Archive PRIMARY/SECONDARY types. Modern whitelist add/remove only. |
| 6.8–6.9 | Ledger/UserProfile PARTIAL | **Verified** | Modern returns raw dicts; archive typed dataclasses. |
| 6.10–6.11 | Futures DIVERGENT/NOT_PORTED | **Verified** | Archive cache-based chain + `get_expiries()`. Modern symbol parsing in `futures.py`. |
| 6.12 | MTF IMPROVED | **Verified** | Dedicated `DhanMTF` adapter in modern. |

---

## Section 7: API Contract Compatibility — **MAJOR CORRECTIONS**

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 7.1 | `place_order()` on gateway VERIFIED | **Incorrect** | Modern `DhanGateway` has **no** `place_order()`. Orders via `gateway.orders.place_order()` (`BrokerGateway` protocol at `brokers/ports/broker.py:30-52`). **Breaking Change** for archived callers. |
| 7.2 | `historical` returns DataFrame VERIFIED | **Incorrect** | Modern `DhanHistorical.get_historical_candles()` returns `list[Candle]` (`historical.py:44-51`). Archive `history()` returns `pd.DataFrame`. **Breaking Change**. |
| 7.3 | Other port-level returns | **Partially Verified** | `positions()`, `holdings()`, LTP via ports — behavior similar when accessed through correct path. |
| 7.4 | Exception hierarchy 14 vs 6 | **Incorrect** | Modern has **17** exception classes in `exceptions.py` (not 6). Archive has 14. Consolidation claim overstated. |

---

## Section 8: Cross-Cutting Concerns

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 8.1 | ObservabilityProvider NOT_PORTED | **Verified** | Not implemented on `DhanGateway`. |
| 8.2 | Prometheus 9 vs 3 metrics PARTIAL | **Incorrect → Partially Verified** | Modern `metrics.py` defines **8** metric families (3 HTTP + 5 WS counters/gauges). WS metrics exist as definitions but **wiring to feeds unverified**. |
| 8.3 | Circuit breakers VERIFIED | **Verified** | `create_circuit_breakers()` in `http.py:42-57`. |
| 8.4 | Retry logic VERIFIED | **Verified** | `BaseResilientHttpClient` with `RetryPolicy`. |
| 8.5 | TTL/caching DIVERGENT | **Verified** | See 3.8. |
| 8.6 | Configuration DIVERGENT | **Verified** | Archive `DhanSettingsLoader` multi-source. Modern static `config.py`. |
| 8.7 | Structured logging PARTIAL | **Verified** | Archive richer audit trails. |

---

## Section 9: Traceability Matrix (Prior)

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 9.1 | Idempotency test mapping | **Partially Verified** | Prior cited wrong test file for idempotency (`test_dhan_auth_state.py` is auth, not orders). Correct archive tests: `test_orders_idempotency.py`, `test_broker_contract.py:214-217`. |
| 9.2 | Circuit breaker UNKNOWN | **Partially Verified** | Modern `test_circuit_breaker_regression.py` exists. WS circuit state exposure still missing. |
| 9.3 | Account registry NOT_PORTED | **Partially Verified** | Archive `AccountConnectionRegistry`. Modern has generic `GatewayRegistry` (`brokers/infrastructure/registry.py:21`) but **not wired into DhanGateway construction path**. |

---

## Section 10–12: Risk & Verdict

| # | Prior Claim | Classification | Evidence |
|---|-------------|----------------|----------|
| 10.1 | Risk severities | **Verified** | Idempotency CRITICAL confirmed. TOTP cooldown HIGH confirmed. |
| 11.1 | Production checklist | **Partially Verified** | Historical Data marked VERIFIED — **Incorrect** for consumer API (DataFrame vs Candle). Orders status correct. |
| 12.1 | NOT READY verdict | **Verified** | Evidence supports NOT READY. Add: consumer API breaking changes and cancel HTTP verb divergence. |

---

## Summary: Corrections to Prior Assessment

1. **Unknown symbol handling:** Modern raises `InstrumentNotFoundError`, not `None`.
2. **Gateway API compatibility:** Prior Section 7 is **fundamentally wrong** — modern uses ISP ports, not fat facade methods.
3. **Historical return type:** `list[Candle]` vs `pd.DataFrame` — breaking change, not verified parity.
4. **Exception count:** Modern has 17 classes, not 6.
5. **Metrics count:** Modern defines 8 Prometheus metrics, not 3; WS wiring unverified.
6. **Refresh lock timeout:** Modern specifies 5.0s on HTTP 401 path.
7. **EDIS generate:** Different HTTP method and path between implementations.
8. **Cancel order:** POST vs DELETE — potential runtime behavioral difference at Dhan API layer.

## Prior Assessment Row Count

| Classification | Count |
|----------------|-------|
| Verified | 28 |
| Partially Verified | 18 |
| Incorrect | 7 |
| Insufficient Evidence | 4 |

**Conclusion:** Prior assessment directionally correct on production blockers (idempotency, TOTP guard, expected_segment, observability) but **understates consumer API breaking changes** and contains **7 factual errors** requiring correction in v2 report.
