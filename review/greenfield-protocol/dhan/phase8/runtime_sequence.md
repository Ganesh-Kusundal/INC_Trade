# Phase 8 — Cross-Cutting Concerns: Runtime Sequences

**Broker:** Dhan  
**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 8 — Cross-Cutting Concerns  
**Date:** 2026-07-03

---

## 1. Broker Bootstrap / Initialization Flow

### Archive Flow

The archive bootstrap is orchestrated by `BrokerFactory.create()`, which follows
a strict 7-step wiring sequence with account-level singleton enforcement.

```
Caller                    BrokerFactory              DhanSettingsLoader
  |                            |                            |
  |-- create(env_path) ------->|                            |
  |                            |-- from_env(env_path) ----->|
  |                            |<-- DhanConnectionSettings -|
  |                            |                            |
  |                            |  AccountConnectionRegistry
  |                            |-- get_or_create(DHAN, cid)|
  |                            |  .get_or_create()         |
  |                            |                            |
  |                            |  _build_gateway()          |
  |                            |-- _create_auth() ---------+
  |                            |   |  TOTP generation       |
  |                            |   |  JsonTokenStateStore   |
  |                            |   |  AuthManager.acquire() |
  |                            |   +-- (auth, token) -------+
  |                            |                            |
  |                            |-- _create_http_client() --+
  |                            |   |  DhanConfigLoader     |
  |                            |   |  CircuitBreakers x4   |
  |                            |   |  RateLimiter          |
  |                            |   +-- DhanHttpClient -----+
  |                            |                            |
  |                            |-- _create_connection_and_gateway()
  |                            |   |  DhanConnection(...)  |
  |                            |   |  register_status_mappings()
  |                            |   +-- BrokerGateway ------+
  |                            |                            |
  |                            |-- load_instruments()       |
  |                            |   (CSV download + parse)   |
  |                            |                            |
  |                            |-- _wire_websocket_services()
  |                            |   |  create_market_feed()  |
  |                            |   +-- create_order_stream()|
  |                            |                            |
  |                            |-- _setup_token_refresh_scheduler()
  |                            |   |  TokenRefreshScheduler |
  |                            |   |  lifecycle.register()  |
  |                            |   +-- on_refresh callback -+
  |                            |                            |
  |                            |-- register_broker_health_check()
  |<-- MarketDataGateway ------|                            |
```

**Key steps:**
1. **Settings loading** — `DhanSettingsLoader.from_env()` reads `.env` + env vars → frozen dataclass
2. **Singleton enforcement** — `AccountConnectionRegistry.get_or_create()` ensures one gateway per (broker, account)
3. **Auth creation** — TOTP generation via pyotp, `AuthManager` with `JsonTokenStateStore`
4. **HTTP client** — resilience config from `DhanConfigLoader`, circuit breakers (orders/market_data/portfolio/admin), rate limiter
5. **Connection + Gateway** — `DhanConnection` wraps all adapters; `BrokerGateway` is the sync facade
6. **WebSocket wiring** — market_feed + order_stream auto-created with token refresh callback
7. **Token scheduler** — periodic refresh with `refresh_lock` shared between scheduler and HTTP 401 handler

### Greenfield Flow

The greenfield collapses the factory into `DhanGateway.__init__()`, inlining all wiring.

```
Caller                    DhanGateway.__init__
  |                            |
  |-- DhanGateway(...) ------->|
  |                            |-- DhanAuth(access_token, pin, totp_secret, token_store)
  |                            |   |  TOTP generation if needed
  |                            |   +-- token acquired
  |                            |
  |                            |-- TokenBroadcast()
  |                            |-- DhanHttpClient(access_token, token_refresh_fn)
  |                            |-- DhanInstrumentResolver()
  |                            |
  |                            |-- Create all 20+ adapters:
  |                            |   DhanOrders, DhanMarketData, DhanPortfolio,
  |                            |   DhanInstruments, DhanHistorical, DhanOptions,
  |                            |   DhanFutures, DhanSuperOrders, DhanForeverOrders,
  |                            |   DhanMargin, DhanMTF, DhanConditionalTriggers,
  |                            |   DhanExitAll, DhanEDIS, DhanLedger, DhanAlerts,
  |                            |   DhanIpManagement, DhanUserProfile,
  |                            |   DhanReconciliation, DhanSymbolValidator
  |                            |
  |                            |-- DhanStreaming, DhanOrderStream,
  |                            |   DhanDepth20Stream, DhanDepth200Stream
  |                            |
  |                            |-- broadcast.register_receiver() x5
  |                            |   (client, streaming, order_stream, depth20, depth200)
  |                            |
  |                            |-- TokenRefreshScheduler (if auto_refresh + credentials)
  |                            |-- _persist_initial_token()
  |<-- DhanGateway instance ---|
```

### Archive vs Greenfield Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Factory pattern | Separate `BrokerFactory` implementing `BrokerProviderFactory` | No factory; `DhanGateway.__init__` does all wiring |
| Account registry | `AccountConnectionRegistry` singleton per (broker, account) | Missing — no singleton enforcement |
| Settings | `DhanConnectionSettings` frozen dataclass via `DhanSettingsLoader` | Constructor parameters directly |
| Resilience config | `DhanConfigLoader` with env var, JSON, .env loading | Hardcoded in `config.py` constants |
| Instrument loading | Explicit `load_instruments()` call after gateway creation | Lazy — `DhanInstrumentResolver.load()` on first `resolve()` |
| WebSocket wiring | Separate `_wire_websocket_services()` method | Inline in `__init__` |
| Token scheduler | Separate `_setup_token_refresh_scheduler()` | Inline conditional in `__init__` |
| Health check | `register_broker_health_check()` with observability layer | `health()` method on gateway |

---

## 2. Gateway Request Routing Flow

### Archive — Order Placement

```
Caller              BrokerGateway          DhanConnection       OrdersAdapter       DhanHttpClient
  |                      |                      |                    |                    |
  |-- place_order(sym,   |                      |                    |                    |
  |   exchange, side) -->|                      |                    |                    |
  |                      |-- resolve_correlation_id()                |                    |
  |                      |-- parse_segment(exchange)                 |                    |
  |                      |-- _build_order_payload() → BrokerOrderPayload               |
  |                      |                      |                    |                    |
  |                      |-- _conn.orders.place_order(request) ----->|                    |
  |                      |                      |                    |-- identity.resolve_ref()
  |                      |                      |                    |-- assert_dhan_payload()
  |                      |                      |                    |-- POST /orders ----->|
  |                      |                      |                    |                    |-- rate_limit_check()
  |                      |                      |                    |                    |-- circuit_breaker_check()
  |                      |                      |                    |                    |-- HTTP POST
  |                      |                      |                    |<-- response ---------|
  |                      |                      |                    |-- map to OrderResponse
  |                      |<-- OrderResponse -----|                    |                    |
  |<-- OrderResponse ----|                      |                    |                    |
```

### Greenfield — Order Placement

```
Caller              DhanGateway            DhanOrders           DhanHttpClient
  |                      |                    |                    |
  |-- .orders            |                    |                    |
  |   .place_order(...)  |                    |                    |
  |                      |-- (property access) |                    |
  |                      |-------------------->|                    |
  |                      |                    |-- resolver.resolve(symbol, exchange)
  |                      |                    |-- assert_valid_dhan_payload()
  |                      |                    |-- POST /orders ----->|
  |                      |                    |                    |-- rate_limit + CB
  |                      |                    |<-- response ---------|
  |                      |                    |-- map to OrderResponse
  |<-- OrderResponse -------------------------|                    |
```

**Key difference:** Archive goes through `BrokerGateway → DhanConnection → OrdersAdapter`; greenfield goes through `DhanGateway.orders → DhanOrders` (one fewer layer).

---

## 3. Identity Resolution Flow

### Archive — DhanIdentityProvider

```
Adapter             DhanIdentityProvider     SymbolResolver       config.indices
  |                       |                       |                    |
  |-- resolve_ref(sym,    |                       |                    |
  |   exchange,           |                       |                    |
  |   expected_segment) ->|                       |                    |
  |                       |-- resolver.resolve(sym, exchange) ------->|
  |                       |                       |-- CSV lookup       |
  |                       |                       |-- index fallback ->|
  |                       |<-- Instrument ---------|                    |
  |                       |                       |                    |
  |                       |-- EXCHANGE_TO_SEGMENT.get(inst.exchange)   |
  |                       |-- check expected_segment constraint        |
  |                       |   if derivative_segment and result==IDX_I: |
  |                       |       raise DhanIdentityError              |
  |                       |                       |                    |
  |                       |-- DhanInstrumentRef(  |                    |
  |                       |     symbol, exchange,  |                    |
  |                       |     exchange_segment,  |                    |
  |                       |     security_id, ...)  |                    |
  |                       |-- __post_init__ validates segment + sid    |
  |                       |                       |                    |
  |                       |-- issue_count += 1    |                    |
  |                       |-- log security_id_issued (source=csv/index)|
  |                       |                       |                    |
  |<-- DhanInstrumentRef -|                       |                    |
```

### Greenfield — DhanInstrumentResolver

```
Adapter             DhanInstrumentResolver   CSV Master
  |                       |                    |
  |-- resolve(sym, exch)->|                    |
  |                       |-- if not loaded: load()
  |                       |   |-- GET images.dhan.co/api-scrip-master.csv
  |                       |   |-- parse rows → _by_symbol, _by_security_id
  |                       |   +-- loaded = True  |
  |                       |                    |
  |                       |-- EXCHANGE_MAP.get(exchange) → segment    |
  |                       |-- lookup (symbol_upper, segment)          |
  |                       |   if found: return ref                    |
  |                       |   broader scan: match symbol + prefix     |
  |                       |   if not found: raise InstrumentNotFoundError
  |                       |                    |
  |<-- DhanInstrumentRef -|                    |
```

### Key Differences

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Provider pattern | Separate `DhanIdentityProvider` wrapping `SymbolResolver` | `DhanInstrumentResolver` combines both roles |
| Invariant enforcement | `DhanInstrumentRef.__post_init__` checks `DHAN_SEGMENTS` + digit security_id | Same `__post_init__` checks |
| Expected segment | `expected_segment` param disambiguates index vs derivatives | Not supported |
| Audit logging | `security_id_issued` with source (csv/mcx_json/hardcoded_index) | Basic `dhan_instruments_loaded` count |
| Index fallback | Hardcoded `config.indices` table | Not present |
| Coercion helper | `coerce_identity_provider()` with duck-typing opt-in | Not needed |
| Reverse lookup | `resolve_ref_from_security_id()` | `get_by_security_id()` |

---

## 4. Configuration Loading Flow

### Archive

```
BrokerFactory._create_http_client()
  |
  |-- settings.resilience_config (from DhanSettingsLoader)
  |   if None:
  |       DhanConfigLoader.load_from_environment()
  |           |-- env vars: DHAN_RESILIENCE_RATE_LIMIT_*, DHAN_RESILIENCE_RETRY_*, etc.
  |           |-- deep merge over DEFAULT_CONFIG
  |           +-- DhanResilienceConfig
  |
  |-- if custom thresholds:
  |       CircuitBreaker(custom_config) x4
  |   else:
  |       create_circuit_breakers()  # defaults
  |
  |-- create_rate_limiter()
  |
  +-- DhanHttpClient(config=resilience_config, circuit_breakers=..., rate_limiter=...)
```

### Greenfield

```
DhanGateway.__init__()
  |
  |-- config.py constants (ENDPOINTS, RATE_LIMITS, EXCHANGE_MAP, etc.)
  |   No runtime config loading — all hardcoded at module level
  |
  +-- DhanHttpClient(access_token, client_id, token_refresh_fn, refresh_lock)
      No resilience config injection — uses internal defaults
```

**Gap:** Greenfield has no `DhanConfigLoader`, no env var override, no JSON file loading, no deep merge. All configuration is compile-time constants.

---

## 5. Options Trading Flow

### Archive

```
Caller          BrokerGateway         DhanExtendedCapabilities    OptionsAdapter       DhanHttpClient
  |                 |                         |                        |                    |
  |-- option_chain  |                         |                        |                    |
  |   (underlying,  |                         |                        |                    |
  |    exchange,    |                         |                        |                    |
  |    expiry) ---->|                         |                        |                    |
  |                 |-- .extended             |                        |                    |
  |                 |   .get_option_chain()-->|                        |                    |
  |                 |                         |-- MCX check:           |                    |
  |                 |                         |   if MCX underlying:   |                    |
  |                 |                         |     find nearest fut   |                    |
  |                 |                         |     sec_id = fut.security_id                |
  |                 |                         |     seg = MCX_COMM     |                    |
  |                 |                         |                        |                    |
  |                 |                         |-- if expiry is None:   |                    |
  |                 |                         |   get_expiries() ----->| POST /optionchain/ |
  |                 |                         |   <--- expiries -------| expirylist         |
  |                 |                         |   expiry = expiries[0] |                    |
  |                 |                         |                        |                    |
  |                 |                         |-- get_option_chain()-->| POST /optionchain  |
  |                 |                         |                        |-- identity.resolve_ref()
  |                 |                         |                        |-- assert_dhan_identity()
  |                 |                         |                        |-- parse OC response |
  |                 |                         |                        |-- resolve CE/PE symbols via security_id
  |                 |                         |<-- OptionChainResult --|                    |
  |                 |<-- OptionChain ---------|                        |                    |
  |<-- OptionChain --|                         |                        |                    |
```

### Greenfield

```
Caller          DhanGateway            DhanOptions            DhanHttpClient
  |                 |                       |                      |
  |-- .options      |                       |                      |
  |   .get_option_  |                       |                      |
  |    chain(...)   |                       |                      |
  |   ------------->|--- (property) ------->|                      |
  |                 |                       |-- _resolve_underlying(symbol, exchange)
  |                 |                       |   resolver.resolve()  |
  |                 |                       |-- POST /optionchain ->|
  |                 |                       |<-- response ----------|
  |                 |                       |-- parse to OptionChain dataclass
  |                 |                       |-- resolve CE/PE symbols
  |<-- OptionChain --|<-- OptionChain ------|                      |
```

**Key differences:**
- Archive handles MCX-specific expiry lookup via futures contract resolution
- Greenfield has dataclass returns (`OptionChain`, `OptionStrike`, `OptionLeg`) vs archive TypedDict
- Both use identity resolver for symbol→security_id

---

## 6. Futures Trading Flow

### Archive

```
Caller          BrokerGateway         DhanExtendedCapabilities    FuturesAdapter
  |                 |                         |                        |
  |-- future_chain  |                         |                        |
  |   (underlying,  |                         |                        |
  |    exchange) -->|                         |                        |
  |                 |-- .extended             |                        |
  |                 |   .get_futures_contracts()                     |
  |                 |   ------------------------------>|              |
  |                 |                         |                        |-- scan instruments
  |                 |                         |                        |-- filter by underlying
  |                 |                         |                        |-- _resolve_derivatives_exchange()
  |                 |                         |<-- list[dict] ---------|
  |                 |<-- FutureChain ---------|                        |
```

### Greenfield

```
Caller          DhanGateway            DhanFutures            DhanInstrumentResolver
  |                 |                       |                      |
  |-- .futures      |                       |                      |
  |   .get_futures_ |                       |                      |
  |    chain(...)   |                       |                      |
  |   ------------->|--- (property) ------->|                      |
  |                 |                       |-- resolver.resolve(underlying, exchange)
  |                 |                       |   <--- DhanInstrumentRef
  |                 |                       |-- scan resolver for matching contracts
  |                 |                       |-- _parse_expiry() for sorting
  |<-- list ---------|<-- list --------------|                      |
```

**Key difference:** Greenfield `DhanFutures` (183L) is significantly expanded vs archive `FuturesAdapter` (86L). It adds `get_contract()` with CURRENT/NEXT/FAR expiry resolution.

---

## 7. Symbol Validation Flow

### Archive — Full Validation

```
Caller          DhanSymbolValidator      SymbolResolver         parse_fo_symbol()
  |                  |                        |                       |
  |-- validate(sym,  |                        |                       |
  |   exchange) ---->|                        |                       |
  |                  |-- normalize_symbol()   |                       |
  |                  |-- parse_fo_symbol() -->|                       |
  |                  |                        |                       |-- 4 regex patterns:
  |                  |                        |                       |   1. Spaced option
  |                  |                        |                       |   2. Compact option
  |                  |                        |                       |   3. Futures with day
  |                  |                        |                       |   4. Futures no day
  |                  |<-- fo_info or None -----|----------------------|
  |                  |                        |                       |
  |                  |  if fo_info:           |                       |
  |                  |    _validate_fo()      |                       |
  |                  |      |-- scan all_instruments()                |
  |                  |      |-- match underlying, type, strike,       |
  |                  |      |   option_type, expiry month+day         |
  |                  |      |-- check expired → status=EXPIRED        |
  |                  |      +-- return {status: VALID/INVALID/AMBIGUOUS/EXPIRED}
  |                  |                        |                       |
  |                  |  else:                 |                       |
  |                  |    _validate_standard()|                       |
  |                  |      |-- try all exchanges                     |
  |                  |      |-- resolver.resolve(sym, exch) ---------->|
  |                  |      |-- collect candidates                    |
  |                  |      +-- return {status: VALID/AMBIGUOUS/INVALID}
  |                  |                        |                       |
  |<-- validation result                      |                       |
```

### Greenfield — Simplified Validation

```
Caller          DhanSymbolValidator      DhanInstrumentResolver
  |                  |                        |
  |-- validate_symbol|                        |
  |   (sym, exch) -->|                        |
  |                  |-- resolver.resolve(sym, exchange)
  |                  |   |-- CSV lookup       |
  |                  |   +-- DhanInstrumentRef|
  |                  |                        |
  |                  |-- return {status: VALID, security_id, exchange_segment}
  |                  |   (or InstrumentNotFoundError → INVALID)
  |                  |                        |
  |<-- result --------|-----------------------|
```

**Gap analysis:** Archive has 437 lines with F&O regex parsing (4 patterns), expired contract detection, candidate listing, segment code mapping. Greenfield has 26 lines — just a resolve check. **This is the largest single gap in Phase 8.**

---

## 8. Reconciliation Flow

### Archive

```
OMS/Caller        DhanReconciliationService    ReconciliationEngine    OrdersAdapter    PortfolioAdapter
  |                      |                            |                      |                    |
  |-- reconcile(         |                            |                      |                    |
  |   local_orders,      |                            |                      |                    |
  |   local_positions) ->|                            |                      |                    |
  |                      |-- orders.get_orderbook() ----------------------->| GET /orders        |
  |                      |<-- broker_orders --------------------------------|                    |
  |                      |-- portfolio.get_positions() ---------------------------------------->| GET /positions
  |                      |<-- broker_positions -------------------------------------------------|
  |                      |                            |                      |                    |
  |                      |-- engine.compare_orders(local_orders, broker_orders)
  |                      |   |<-- drift items ---------|                      |                    |
  |                      |-- engine.compare_positions(local_positions, broker_positions)
  |                      |   |<-- drift items ---------|                      |                    |
  |                      |                            |                      |                    |
  |                      |-- if auto_repair and oms:  |                      |                    |
  |                      |   _repair_local_oms()      |                      |                    |
  |                      |     |-- upsert missing orders                     |                    |
  |                      |     +-- upsert positions from broker               |                    |
  |                      |                            |                      |                    |
  |<-- ReconciliationReport                           |                      |                    |
```

### Greenfield

```
Caller          DhanReconciliation       DhanPortfolio
  |                  |                        |
  |-- reconcile_     |                        |
  |   positions() -->|                        |
  |                  |-- portfolio.get_positions()
  |                  |   |<-- positions -------|
  |                  |                        |
  |                  |-- compare with local positions
  |                  |-- return drift report  |
  |<-- report --------|                        |
```

**Gap:** Greenfield is position-only. No order reconciliation, no auto-repair, no shared engine.

---

## 9. Alert Management Flow

### Archive

```
Caller          AlertsAdapter          DhanIdentityProvider     DhanHttpClient
  |                  |                        |                      |
  |-- place(         |                        |                      |
  |   AlertRequest)  |                        |                      |
  |   -------------->|                        |                      |
  |                  |-- _validate_request()  |                      |
  |                  |-- identity.resolve_ref(symbol, exchange) ---->|
  |                  |<-- DhanInstrumentRef ---|                      |
  |                  |-- assert_dhan_payload(payload)                 |
  |                  |-- POST /alerts ------->|---------------------->|
  |                  |<-- Alert --------------|                      |
```

### Greenfield

```
Caller          DhanAlerts             DhanHttpClient
  |                  |                      |
  |-- create_alert   |                      |
  |   (payload) ---->|                      |
  |                  |-- POST /alerts ----->|
  |                  |<-- response ---------|
```

**Gap:** Greenfield has no identity provider integration, no domain models (AlertRequest/Alert), no request validation.

---

## 10. EDIS Flow

### Archive

```
Caller          EDISAdapter            DhanHttpClient
  |                  |                      |
  |-- generate_tpin()|                      |
  |   -------------->| POST /edis/tpin ---->|
  |                  |<-- response ---------|
  |                  |                      |
  |-- authorize_edis(isin, qty, exch)       |
  |   -------------->|                      |
  |                  |-- _is_valid_isin()   |
  |                  |   regex: ^[A-Z]{2}[A-Z0-9]{9}[A-Z0-9]{1}$
  |                  |-- POST /edis/authorize
  |                  |   {isin, quantity, exchange}
  |                  |<-- response ---------|
  |                  |                      |
  |-- check_status(isin)                    |
  |   -------------->| GET /edis/status/{isin}
  |                  |<-- response ---------|
```

### Greenfield

```
Caller          DhanEDIS               DhanInstrumentResolver    DhanHttpClient
  |                  |                        |                      |
  |-- get_tpin_status|                        |                      |
  |   -------------->| GET /edis/tpin ------->|---------------------->|
  |                  |<-- response -----------|                      |
  |                  |                        |                      |
  |-- generate_tpin()|                        |                      |
  |   -------------->| POST /edis/generateTpin
  |                  |<-- response ---------|                        |
  |                  |                        |                      |
  |-- get_edis_form()|                        |                      |
  |   -------------->| POST /edis/form ------|---------------------->|
  |                  |<-- response -----------|                      |
```

**Gap:** Greenfield has no ISIN validation, different API surface.

---

## 11. Token Lifecycle Flow

### Archive

```
TokenRefreshScheduler       AuthManager         _refresh_via_auth()       _update_env_token()
  |                            |                       |                        |
  |-- [periodic tick]          |                       |                        |
  |-- check token validity     |                       |                        |
  |-- if expiring within buffer:                        |                        |
  |   |-- refresh_lock.acquire()                        |                        |
  |   |-- auth.force_refresh() -->|                     |                        |
  |   |                       |-- TOTP generation       |                        |
  |   |                       |-- POST auth.dhan.co     |                        |
  |   |<-- TokenState ---------|                       |                        |
  |   |-- on_refresh(new_token)-->|                     |                        |
  |   |                       |-- client.update_token() |                        |
  |   |                       |-- _update_env_token()-->|                        |
  |   |                       |                       |-- fcntl.flock(EXCLUSIVE) |
  |   |                       |                       |-- read env file          |
  |   |                       |                       |-- replace DHAN_ACCESS_TOKEN
  |   |                       |                       |-- write tmp + fsync      |
  |   |                       |                       |-- os.replace(tmp, env)   |
  |   |                       |                       |-- broadcast_token()      |
  |   +-- refresh_lock.release()                        |                        |
```

### Greenfield

```
TokenRefreshScheduler       DhanAuth            TokenBroadcast           _persist_token()
  |                            |                       |                        |
  |-- [periodic tick]          |                       |                        |
  |-- check token validity     |                       |                        |
  |-- if expiring within buffer:                        |                        |
  |   |-- refresh_lock.acquire()                        |                        |
  |   |-- auth.generate_token()-->|                     |                        |
  |   |                       |-- TOTP + POST           |                        |
  |   |<-- new_token ----------|                       |                        |
  |   |-- on_refresh(new_token)-->|                     |                        |
  |   |                       |-- broadcast.broadcast()-->|                      |
  |   |                       |                       |-- weak-ref callbacks:    |
  |   |                       |                       |   client.update_token()  |
  |   |                       |                       |   streaming.update_token()
  |   |                       |                       |   order_stream.update_token()
  |   |                       |                       |   depth20.update_token() |
  |   |                       |                       |   depth200.update_token()|
  |   |                       |-- _persist_token()--->|                        |
  |   |                       |                       |-- JsonTokenStateStore.save()
  |   |                       |                       |-- update_env_token()     |
  |   +-- refresh_lock.release()                        |                        |
```

**Key improvement:** Greenfield `TokenBroadcast` uses weak references to avoid preventing garbage collection of receivers. Archive uses direct `broadcast_token()` on connection.

---

## 12. Summary of Runtime Flow Differences

| Flow | Archive Complexity | Greenfield Complexity | Status |
|------|:---:|:---:|------|
| Bootstrap | 7-step factory with singleton | Inline __init__ | Simplified |
| Order routing | 3-layer delegation | 2-layer direct | Simplified |
| Identity resolution | Provider + resolver + audit | Combined resolver | Reduced |
| Config loading | Multi-source (env/JSON/file) | Hardcoded constants | **GAP** |
| Options trading | MCX special handling + TypedDict | Dataclass returns | Replicated |
| Futures trading | Basic contract listing | Expanded with expiry resolution | Enhanced |
| Symbol validation | 4 regex patterns + expiry detection | Simple resolve check | **MASSIVE GAP** |
| Reconciliation | Orders + positions + auto-repair | Position-only | **GAP** |
| Alerts | Identity integration + validation | Simple CRUD | **GAP** |
| EDIS | ISIN validation | No validation | Partial |
| Token lifecycle | fcntl atomic env update | Weak-ref broadcast | Improved |
