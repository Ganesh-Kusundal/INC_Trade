# Phase 8 — Public Contract: Cross-Cutting Concerns

> **Greenfield Broker Replication Protocol — Dhan Adapter**
> Phase 8 documents every public API surface not owned by Phases 0–7:
> gateway, factory, identity, configuration, domain models, extended features,
> options, futures, symbol validator, reconciliation, alerts, EDIS, segments,
> capabilities, exceptions, and all other cross-cutting modules.

---

## Table of Contents

1. [Gateway API](#1-gateway-api)
2. [Factory API](#2-factory-api)
3. [Identity API](#3-identity-api)
4. [Configuration System API](#4-configuration-system-api)
5. [Domain Models API](#5-domain-models-api)
6. [Extended Capabilities API](#6-extended-capabilities-api)
7. [Options Trading API](#7-options-trading-api)
8. [Futures Trading API](#8-futures-trading-api)
9. [Symbol Validator API](#9-symbol-validator-api)
10. [Reconciliation API](#10-reconciliation-api)
11. [Alerts API](#11-alerts-api)
12. [EDIS API](#12-edis-api)
13. [Segments API](#13-segments-api)
14. [Capabilities API](#14-capabilities-api)
15. [Exception Hierarchy API](#15-exception-hierarchy-api)
16. [Session Manager API](#16-session-manager-api)
17. [Account Registry API](#17-account-registry-api)
18. [TOTP Client API](#18-totp-client-api)
19. [Secret Utilities API](#19-secret-utilities-api)
20. [Metrics API](#20-metrics-api)
21. [Ledger API](#21-ledger-api)
22. [IP Management API](#22-ip-management-api)
23. [User Profile API](#23-user-profile-api)
24. [Greenfield Equivalents Summary](#24-greenfield-equivalents-summary)

---

## 1. Gateway API

### Archive — `BrokerGateway`

| Method | Input | Output | Exceptions | Side Effects |
|--------|-------|--------|------------|--------------|
| `__init__(connection)` | `DhanConnection` | — | — | Stores connection ref, creates `_stream_lock`, `GatewayOptionsFacade` |
| `common_broker_gateway()` | — | `_DhanCommonBrokerGateway` | — | Lazy-creates cached async wrapper (thread-safe) |
| `extended` (property) | — | `DhanExtendedCapabilities` | — | Constructs new instance per access |
| `place_order(symbol, exchange, side, quantity, price, order_type, product_type, validity, trigger_price, correlation_id)` | See params | `OrderResponse` | `ValueError` (bad segment) | Resolves correlation_id, parses segment, delegates to `_conn.orders` |
| `cancel_order(order_id)` | `str` | `OrderResponse` | — | Post-cancel verification via `get_order()`; returns `ALREADY_EXECUTED` if filled |
| `modify_order(order_id, **changes)` | `str`, kwargs | `OrderResponse` | — | Delegates to `_conn.orders.modify_order` |
| `get_order(order_id)` | `str` | `Order \| None` | — | Direct lookup via `GET /orders/{id}`; swallows exceptions |
| `get_orderbook()` | — | `list[Order]` | — | Full orderbook fetch |
| `get_trade_book()` | — | `list[Trade]` | — | Full tradebook fetch |
| `load_instruments(source, use_cache)` | `str?`, `bool` | — | Loader errors | Delegates to `_conn.load_instruments()` |
| `close()` | — | — | — | Closes HTTP pool + all WS |
| `ltp(symbol, exchange)` | `str`, `str` | `Decimal` | — | REST LTP fetch |
| `quote(symbol, exchange)` | `str`, `str` | `Quote` | — | REST quote fetch |
| `depth(symbol, exchange)` | `str`, `str` | `MarketDepth` | — | 5-level REST depth |
| `depth_20(symbol, exchange, on_depth)` | `str`, `str`, `Callable?` | `MarketDepth` | `ValueError` (non-NSE) | WS 20-level depth with REST fallback |
| `depth_200(symbol, exchange, on_depth)` | `str`, `str`, `Callable?` | `MarketDepth` | `ValueError` (non-NSE, already subscribed) | WS 200-level; 1 instrument per connection |
| `history(symbol, exchange, timeframe, lookback_days, from_date, to_date)` | See params | `pd.DataFrame` | — | Batch dispatch for list input; single for string |
| `option_chain(underlying, exchange, expiry)` | `str`, `str`, `str?` | `OptionChain` | — | Delegates to `extended.get_option_chain` |
| `future_chain(underlying, exchange)` | `str`, `str` | `FutureChain` | — | Delegates to `build_future_chain` |
| `get_balance()` / `funds()` | — | `Balance` | — | `GET /fundlimit` |
| `positions()` | — | `list[Position]` | — | `GET /positions` |
| `holdings()` | — | `list[Holding]` | — | `GET /holdings` |
| `trades()` | — | `list[Trade]` | — | Alias for `get_trade_book` |
| `describe()` | — | `dict` | — | Static metadata dict |
| `capabilities()` | — | `BrokerCapabilities` | — | Returns `dhan_capabilities()` |
| `search(query)` | `str` | `list[dict]` | — | Linear scan of instrument master (max 20) |
| `stream(symbol, exchange, mode, on_tick)` | See params | Stream handle | — | Subscribes via `SubscriptionEngine` |
| `unstream(symbol, exchange, on_tick)` | See params | — | — | Unsubscribes |
| `stream_depth(symbol, exchange, depth_type, on_depth)` | See params | Stream handle | `ValueError` (unsupported depth_type) | Routes to `depth_20` or `depth_200` |
| `stream_order(on_order)` | `Callable?` | Stream handle | — | Order update subscription |
| `unstream_order(on_order)` | `Callable?` | — | — | Remove order callback |
| `ltp_batch(symbols, exchange)` | `list[str]`, `str` | `dict[str, Decimal]` | — | Native batch LTP (up to 1000) |
| `quote_batch(symbols, exchange)` | `list[str]`, `str` | `dict[str, Quote]` | — | Native batch quote (up to 1000) |
| `get_connection_status()` | — | `dict[str, bool]` | — | ObservabilityProvider: WS status |
| `get_connection_metadata()` | — | `dict[str, Any]` | — | Non-bool diagnostic values |
| `get_circuit_breaker_states()` | — | `dict[str, int]` | — | 0=CLOSED, 1=OPEN, 2=HALF_OPEN |
| `get_token_refresh_metrics()` | — | `dict[str, int]` | — | Token refresh counters |

### Greenfield — `DhanGateway`

| Method / Property | Input | Output | Greenfield Difference |
|-------------------|-------|--------|-----------------------|
| `__init__(access_token, client_id, pin, totp_secret, ...)` | 11 params | — | Inline bootstrap; no separate factory |
| `orders` (property) | — | `DhanOrders` | Direct adapter access |
| `market_data` (property) | — | `DhanMarketData` | Direct adapter access |
| `portfolio` (property) | — | `DhanPortfolio` | Direct adapter access |
| `instruments` (property) | — | `DhanInstruments` | Direct adapter access |
| `auth` (property) | — | `DhanAuth` | Implements `AuthPort` |
| `historical` (property) | — | `DhanHistorical` | Direct adapter access |
| `streaming` (property) | — | `StreamingPort` | Implements port protocol |
| `options` (property) | — | `DhanOptions` | Richer dataclass model |
| `futures` (property) | — | `DhanFutures` | CURRENT/NEXT/FAR selection |
| `super_orders` (property) | — | `DhanSuperOrders` | Direct adapter access |
| `forever_orders` (property) | — | `DhanForeverOrders` | Direct adapter access |
| `margin` (property) | — | `DhanMargin` | Direct adapter access |
| `mtf` (property) | — | `DhanMTF` | **New:** MTF support |
| `conditional_triggers` (property) | — | `DhanConditionalTriggers` | Direct adapter access |
| `exit_all` (property) | — | `DhanExitAll` | Direct adapter access |
| `edis` (property) | — | `DhanEDIS` | Direct adapter access |
| `ledger` (property) | — | `DhanLedger` | Direct adapter access |
| `alerts` (property) | — | `DhanAlerts` | Direct adapter access |
| `ip_management` (property) | — | `DhanIpManagement` | Direct adapter access |
| `user_profile` (property) | — | `DhanUserProfile` | Direct adapter access |
| `reconciliation` (property) | — | `DhanReconciliation` | Position-only |
| `symbol_validator` (property) | — | `DhanSymbolValidator` | Simplified |
| `broadcast` (property) | — | `TokenBroadcast` | **New:** explicit broadcast |
| `scheduler` (property) | — | `TokenRefreshScheduler?` | Nullable |
| `health()` | — | `dict` | Auth + scheduler + broadcast metrics |
| `close()` | — | — | Stops scheduler, 4 streams, HTTP client |

---

## 2. Factory API

### Archive — `BrokerFactory`

| Method | Input | Output | Exceptions | Side Effects |
|--------|-------|--------|------------|--------------|
| `create(env_path, load_instruments, event_bus, risk_manager, lifecycle, backfill_callback, reconciliation_service)` | 7 kwargs | `MarketDataGateway` | `ValueError`, `ConfigurationError` | Full multi-step bootstrap |
| `_build_gateway(settings, env_path, ...)` | Internal | `BrokerGateway` | Any bootstrap error | Auth → HTTP → Connection → WS → Scheduler |
| `_create_auth(settings, env_file)` | Settings, Path | `(AuthManager, str)` | `ConfigurationError` | TOTP generation, token persistence |
| `_create_http_client(settings, auth, cid, token, env_file, refresh_lock)` | Internal | `DhanHttpClient` | — | Circuit breakers, rate limiter |
| `_create_connection_and_gateway(client, auth, settings, ...)` | Internal | `BrokerGateway` | — | DhanConnection + BrokerGateway |
| `_wire_websocket_services(gateway, client, token, lifecycle, event_bus)` | Internal | — | — | Creates market_feed + order_stream |
| `_setup_token_refresh_scheduler(gateway, auth, client, settings, env_file, lifecycle, refresh_lock)` | Internal | — | — | Creates + registers scheduler |

**Module-level helpers:**
- `_generate_totp_token(settings)` → `str | None` — TOTP with rate-limit detection
- `_update_env_token(env_path, token)` — Atomic fcntl-based .env update
- `_refresh_via_auth(auth, env_file, refresh_lock)` — Lock-guarded refresh (5s timeout)
- `_next_token_expiry(now, lifetime_seconds)` — Trading-session-aligned expiry

### Greenfield

**No factory class.** `DhanGateway.__init__()` performs all bootstrap inline.
Token persistence, broadcast registration, and scheduler setup happen within the constructor.

---

## 3. Identity API

### Archive — `DhanIdentityProvider` + `DhanInstrumentRef`

**`DhanInstrumentRef`** (frozen dataclass):

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | User-facing trading symbol |
| `exchange` | `Exchange \| str` | Normalised to enum in `__post_init__` |
| `exchange_segment` | `str` | Dhan segment code (validated against `DHAN_SEGMENTS`) |
| `security_id` | `str` | Digit string (validated > 0) |
| `instrument_type` | `InstrumentType` | EQUITY/FUTURE/OPTION/COMMODITY |
| `lot_size` | `int` | Default 1 |
| `source` | `DhanIdentitySource` | CSV/MCX_JSON/HARDCODED_INDEX |
| `is_synthetic_index` | `bool` | From hardcoded index table |
| `underlying` | `str?` | Root symbol for F&O |
| `expiry` | `str?` | ISO date for derivatives |
| `strike_price` | `object?` | Decimal or None |
| `option_type` | `object?` | CALL/PUT or None |

Properties: `is_derivative`, `is_option`, `is_future`, `security_id_str()`

**`DhanIdentityProvider`:**

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `__init__(resolver)` | `SymbolResolver` | — | — |
| `resolver` (property) | — | `SymbolResolver` | — |
| `issue_count` (property) | — | `int` | — |
| `synthetic_index_count` (property) | — | `int` | — |
| `to_payload_security_id(ref)` | `DhanInstrumentRef` | `str` | `DhanIdentityError` (None ref) |
| `resolve_ref(symbol, exchange, *, expected_segment)` | `str, str, str?` | `DhanInstrumentRef` | `InstrumentNotFoundError`, `DhanIdentityError` |
| `resolve_ref_from_security_id(security_id, exchange)` | `str, str` | `DhanInstrumentRef?` | — |

**Module-level:**
- `DHAN_SEGMENTS: frozenset[str]` — 9 canonical segment codes
- `is_dhan_segment(segment) -> bool`
- `coerce_identity_provider(identity, allow_duck=False)` — Backward-compat wrapper

### Greenfield — `DhanInstrumentRef` + `DhanInstrumentResolver`

| Class/Method | Difference |
|-------------|------------|
| `DhanInstrumentRef` | Simplified frozen dataclass; same core fields |
| `DhanInstrumentResolver` | CSV loading with O(1) lookup, substring search |
| No `coerce_identity_provider` | Adapters take resolver directly |
| No `DhanIdentitySource` audit | No source tracking |
| No `expected_segment` constraint | Simpler resolution |

---

## 4. Configuration System API

### Archive — `DhanResilienceConfig` + `DhanConfigLoader`

**`DhanResilienceConfig`** (frozen dataclass):

| Sub-config | Fields |
|------------|--------|
| `DhanRateLimitConfig` | `limits: dict`, `read_prefixes: tuple`, `write_prefixes: tuple`, `bucket_map: dict` |
| `DhanRetryConfig` | `max_retries: int=3`, `base_delay_ms: int=500`, `max_delay_ms: int=5000` |
| `DhanCircuitBreakerConfig` | `orders_failure_threshold=3`, `default_failure_threshold=5`, `recovery_timeout_ms=30000`, `success_threshold=3` |
| `DhanTokenConfig` | `refresh_cooldown_seconds=60`, `rate_limit_backoff_seconds=130` |
| Root | `base_url: str` |

Methods: `from_dict(data)`, `to_dict()`, `get_endpoint_interval(endpoint)`, `calculate_backoff(attempt)`, `categorize_endpoint(endpoint)`

**`DhanConfigLoader`:**

| Method | Input | Output |
|--------|-------|--------|
| `load(env_path, env_prefix)` | Path?, str | `DhanResilienceConfig` |
| `load_from_file(file_path)` | Path | `DhanResilienceConfig` |
| `load_from_dict(data)` | dict | `DhanResilienceConfig` |
| `load_from_environment(prefix)` | str | `DhanResilienceConfig` |

**Module-level functions:** `load_from_environment()`, `load_from_file()`, `load_from_env_file()`

**Env var convention:** Prefix `DHAN_RESILIENCE_`, flat→nested via `ENV_KEY_MAPPING`.

### Greenfield — `config.py`

Static module-level constants. No runtime loading.

| Constant | Type | Description |
|----------|------|-------------|
| `REST_BASE` | `str` | `"https://api.dhan.co/v2"` |
| `ENDPOINTS` | `dict` | All API endpoint URLs |
| `RATE_LIMITS` | `dict` | Endpoint→interval mapping |
| `READ_PREFIXES` | `tuple` | Read circuit breaker endpoints |
| `WRITE_PREFIXES` | `tuple` | Write circuit breaker endpoints |
| `EXCHANGE_MAP` | `dict` | Exchange→wire segment |
| `SEGMENT_TO_EXCHANGE` | `dict` | Reverse of EXCHANGE_MAP |
| `CSV_EXCHANGE_TO_SEGMENT` | `dict` | CSV exchange→wire segment |
| `INSTRUMENT_TO_SEGMENT` | `dict` | Instrument type→segment |
| `DHAN_SEGMENTS` | `frozenset` | Valid segment codes |
| `DERIVATIVE_SEGMENTS` | `frozenset` | Derivative-only segments |
| `INSTRUMENT_TYPE_MAP` | `dict` | Instrument type normalisation |
| `SIDE_MAP` | `dict` | BUY→1, SELL→2 |
| `ORDER_TYPE_MAP` | `dict` | Order type→int |
| `PRODUCT_TYPE_MAP` | `dict` | Product type→wire string |
| `VALIDITY_MAP` | `dict` | Validity→wire string |

---

## 5. Domain Models API

### Archive — `brokers.dhan.domain`

| Model | Fields | Notes |
|-------|--------|-------|
| `Exchange` (enum) | NSE, BSE, NFO, BFO, MCX, CDS, INDEX | Short codes |
| `DhanInstrumentType` (enum) | EQUITY, FUTURE, OPTION, COMMODITY | — |
| `OptionType` (enum) | CALL, PUT | — |
| `MarginRequest` | symbol, exchange, quantity, product_type, order_type, price?, trigger_price? | Frozen |
| `MarginResponse` | total_margin, order_margin, exposure_margin, available_margin?, span_margin? | Frozen |
| `AlertRequest` | symbol, exchange, condition, trigger_price, valid_until? | Frozen |
| `Alert` | alert_id, symbol, exchange, condition, trigger_price, active, created_at? | Frozen |
| `Instrument` | domain_instrument, exchange, instrument_type, option_type?, sm_symbol_name? | Composition wrapper |
| `SuperOrderLeg` | leg_name, transaction_type, quantity, price, trigger_price?, order_status?, trailing_jump? | Frozen |
| `SuperOrder` | order_id, correlation_id, transaction_type, exchange_segment, product_type, ... | 14 fields |
| `ForeverOrderRequest` | symbol, exchange, order_flag, transaction_type, ... | SINGLE or OCO |
| `ForeverOrder` | order_id, order_status, order_flag, ... | 13 fields |
| `ConditionalTriggerRequest` | symbol, exchange, comparison_type, operator, comparing_value, ... | — |
| `ConditionalTrigger` | alert_id, alert_status, comparison_type, ... | 12 fields |
| `LedgerEntry` | narration, voucher_date, exchange, ... | 7 fields |
| `UserProfile` | token_valid, active_segments, ddpi_status, mtf_enabled, ... | — |
| `IPConfig` | ip_address, ip_type, status | — |
| `ExitAllResponse` | positions_closed, orders_cancelled, success, message | — |

**Canonical re-exports:** `__getattr__` delegates Order, Trade, Position, etc. to `domain` package.

### Greenfield

Domain entities are in `brokers/domain/entities.py` (shared across all brokers):
`Order`, `OrderResponse`, `Quote`, `DepthLevel`, `MarketDepth`, `Trade`, `Position`, `Holding`, `Balance`, `Candle` — all frozen dataclasses.

---

## 6. Extended Capabilities API

### Archive — `DhanExtendedCapabilities`

| Method | Input | Output | Delegates To |
|--------|-------|--------|--------------|
| `instruments` (prop) | — | resolver | `_conn.instruments` |
| `identity` (prop) | — | `DhanIdentityProvider` | `_conn.identity` |
| `orders` (prop) | — | orders adapter | `_conn.orders` |
| `get_positions()` | — | `list` | `_conn.portfolio` |
| `get_holdings()` | — | `list` | `_conn.portfolio` |
| `get_balance()` | — | `Balance` | `_conn.portfolio` |
| `get_expiries(underlying, exchange)` | `str, str` | `list[str]` | Options adapter |
| `place_super_order(**kwargs)` | kwargs | Any | Super orders adapter |
| `modify_super_order(order_id, **kwargs)` | `str`, kwargs | Any | Super orders adapter |
| `cancel_super_order_leg(order_id, leg_name)` | `str, str` | `OrderResponse` | Super orders adapter |
| `get_super_orders()` | — | `list` | Super orders adapter |
| `place_forever_order(request)` | `ForeverOrderRequest` | Any | Forever orders adapter |
| `modify_forever_order(order_id, request)` | `str`, request | Any | Forever orders adapter |
| `cancel_forever_order(order_id)` | `str` | `OrderResponse` | Forever orders adapter |
| `get_all_forever_orders()` | — | `list` | Forever orders adapter |
| `place_conditional_trigger(request)` | request | Any | Conditional triggers |
| `modify_conditional_trigger(alert_id, request)` | `str`, request | Any | Conditional triggers |
| `delete_conditional_trigger(alert_id)` | `str` | `bool` | Conditional triggers |
| `get_conditional_trigger(alert_id)` | `str` | Any | Conditional triggers |
| `get_all_conditional_triggers()` | — | `list` | Conditional triggers |
| `get_ledger(from_date, to_date)` | `str, str` | `list` | Ledger adapter |
| `get_user_profile()` | — | Any | User profile adapter |
| `set_ip(ip_address, ip_type)` | `str, str` | `dict` | IP management |
| `modify_ip(ip_address, ip_type)` | `str, str` | `dict` | IP management |
| `get_ip()` | — | `list[IPConfig]` | IP management |
| `generate_tpin()` | — | `dict` | EDIS adapter |
| `authorize_edis(isin, quantity, exchange)` | `str, int, str` | `dict` | EDIS adapter |
| `check_edis_status(isin)` | `str` | `dict` | EDIS adapter |
| `exit_all()` | — | Any | Exit all adapter |
| `get_option_expiries(underlying, exchange)` | `str, str` | `list[str]` | Options adapter |
| `get_expired_options_data(...)` | 9 params | `dict` | Options adapter |
| `get_option_chain(underlying, exchange, expiry)` | `str, str, str?` | `dict` | MCX-aware logic |
| `get_futures_contracts(underlying, exchange)` | `str, str` | `list[dict]` | Futures adapter |
| `get_futures_expiries(underlying, exchange)` | `str, str` | `list[str]` | Futures adapter |
| `is_commodity(symbol)` | `str` | `bool` | Futures adapter |
| `validate_order(**kwargs)` | kwargs | `list[str]` | Orders adapter |
| `get_alerts()` | — | `list` | Alerts adapter |

### Greenfield

No `DhanExtendedCapabilities` class. All capabilities are exposed as direct
properties on `DhanGateway` (see Section 1 greenfield table).

---

## 7. Options Trading API

### Archive — `OptionsAdapter`

| Method | Input | Output | Exceptions | Notes |
|--------|-------|--------|------------|-------|
| `__init__(client, identity)` | `DhanHttpClient`, provider | — | — | Calls `coerce_identity_provider` |
| `get_option_chain(underlying, exchange, expiry, *, security_id)` | `str, str, str, int?` | `OptionChainResult` | `InstrumentNotFoundError` | `assert_dhan_identity` invariant; MCX path via `security_id` |
| `get_expiries(underlying, exchange)` | `str, str` | `list[str]` | — | `assert_dhan_identity` invariant |
| `get_expired_options_data(security_id, expiry_flag, expiry_code, strike, option_type, from_date, to_date, required_data, interval)` | 9 params | `ExpiredOptionsResult` | — | Rolling option API; NSE_FNO segment forced |

**TypedDicts:** `OptionLegData`, `OptionStrikeRow`, `OptionChainResult`, `ExpiredOptionsSeries`, `ExpiredOptionsResult`

### Greenfield — `DhanOptions`

| Method | Difference |
|--------|------------|
| `get_option_chain(underlying, exchange, expiry)` | Richer `_resolve_underlying()` with 4-stage fallback chain |
| `get_expiries(underlying, exchange)` | Same flow, no invariant assertion |
| `get_expired_options_data(...)` | Same API shape |
| Return types | Frozen dataclasses (`OptionLeg`, `OptionStrike`, `OptionChain`) instead of TypedDicts |

---

## 8. Futures Trading API

### Archive — `FuturesAdapter`

| Method | Input | Output | Notes |
|--------|-------|--------|-------|
| `__init__(client, identity)` | HttpClient, provider | — | Read-side only |
| `get_contracts(underlying, exchange)` | `str, str` | `list[dict]` | Resolves derivatives exchange |
| `get_nearest(underlying, exchange)` | `str, str` | `dict?` | First contract or None |
| `get_expiries(underlying, exchange)` | `str, str` | `list[str]` | Via resolver |
| `is_commodity(symbol)` | `str` | `bool` | Static set lookup |

### Greenfield — `DhanFutures`

| Method | Difference |
|--------|------------|
| `get_contract(underlying, exchange, expiry_type)` | **New:** CURRENT/NEXT/FAR selection |
| `get_futures_chain(underlying, exchange)` | Full chain with expiry parsing from symbol strings |
| `get_expiries(underlying, exchange)` | Same |
| No `is_commodity` | Dropped |

---

## 9. Symbol Validator API

### Archive — `DhanSymbolValidator`

| Method | Input | Output | Notes |
|--------|-------|--------|-------|
| `__init__(resolver?)` | `SymbolResolver?` | — | Auto-loads if None |
| `validate(symbol, exchange?, segment?)` | `str, str?, str?` | `dict` | Returns `{status, message, candidates, ...}` |

**Status values:** `VALID`, `INVALID`, `AMBIGUOUS`, `EXPIRED`, `INVALID_EXPIY_FORMAT`

**Module-level:** `parse_fo_symbol(symbol) -> dict?` — Regex-based F&O symbol parsing (4 patterns)

### Greenfield — `DhanSymbolValidator`

| Method | Difference |
|--------|------------|
| `validate(symbol, exchange?)` | Simplified: delegates to resolver, no regex parsing |
| No `parse_fo_symbol` | Dropped |

---

## 10. Reconciliation API

### Archive — `DhanReconciliationService`

| Method | Input | Output | Notes |
|--------|-------|--------|-------|
| `__init__(orders, portfolio, oms?, *, auto_repair)` | Adapters + OMS | — | — |
| `reconcile(local_orders?, local_positions?)` | Lists? | `ReconciliationReport` | Fetches broker state, delegates to `ReconciliationEngine`, optional auto-repair |
| `_repair_local_oms(broker_orders, broker_positions, drift)` | Internal | — | Upserts missing orders/positions |

**Factory:** `create_reconciliation_service(orders, portfolio, oms, auto_repair)`

### Greenfield — `DhanReconciliation`

| Method | Difference |
|--------|------------|
| `reconcile_positions()` | Position-only; no order reconciliation |
| No auto-repair | Dropped |
| No `ReconciliationEngine` delegation | Inline comparison |

---

## 11. Alerts API

### Archive — `AlertsAdapter`

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `__init__(client, identity)` | HttpClient, provider | — | — |
| `place(request)` | `AlertRequest` | `Alert` | `ValueError` (validation), `DhanError` |
| `get(alert_id)` | `str` | `Alert` | — |
| `list_all()` | — | `list[Alert]` | — |
| `delete(alert_id)` | `str` | `bool` | — |

Validation: `trigger_price > 0`, `condition ∈ {LTP_CROSSES_ABOVE, LTP_CROSSES_BELOW}`
Invariant: `assert_dhan_payload(payload)`

### Greenfield — `DhanAlerts`

| Method | Difference |
|--------|------------|
| `create_alert(payload)` | No validation, no identity resolution |
| `get_alerts()` | Same |
| `delete_alert(id)` | Same |
| `update_alert(id, payload)` | **New:** update support |

---

## 12. EDIS API

### Archive — `EDISAdapter`

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `generate_tpin()` | — | `dict` | `EDISError` |
| `authorize_edis(isin, quantity, exchange)` | `str, int, str` | `dict` | `ValueError` (bad ISIN), `EDISError` |
| `check_status(isin)` | `str` | `dict` | `EDISError` |

ISIN validation: `^[A-Z]{2}[A-Z0-9]{9}[A-Z0-9]{1}$`

### Greenfield — `DhanEDIS`

| Method | Difference |
|--------|------------|
| `get_tpin_status()` | Equivalent of `check_status` |
| `generate_tpin()` | Same |
| `get_edis_form()` | **New:** form retrieval |

---

## 13. Segments API

### Archive — `brokers.dhan.segments`

| Symbol | Type | Description |
|--------|------|-------------|
| `EXCHANGE_TO_SEGMENT` | `dict[str, str]` | Short code → wire segment |
| `SEGMENT_TO_EXCHANGE` | `dict[str, str]` | Wire segment → short code |
| `NUMERIC_TO_SEGMENT` | `dict[int, str]` | WS binary code → wire segment |
| `SEGMENT_TO_NUMERIC` | `dict[str, int]` | Reverse |
| `DERIVATIVE_SEGMENTS` | `frozenset[str]` | 6 derivative segments |
| `EQUITY_ONLY_PRODUCTS` | `frozenset[str]` | `{CNC, MTF}` |
| `parse_segment(value)` | Function | Canonical `ExchangeSegment` |
| `to_dhan_wire(segment)` | Function | Segment → wire string |
| `to_sdk_int(segment)` | Function | Segment → SDK integer |
| `from_sdk_int(code)` | Function | SDK integer → segment |
| `segment_to_exchange(segment, default)` | Function | Segment → `Exchange` enum |
| `DhanSegmentMapper` | Class | `SegmentMapper` ABC impl |

### Greenfield — `config.py`

| Symbol | Difference |
|--------|------------|
| `EXCHANGE_MAP` | Equivalent but uses `"NSE_CD"` vs `"NSE_CURRENCY"` |
| `SEGMENT_TO_EXCHANGE` | Auto-generated reverse |
| `CSV_EXCHANGE_TO_SEGMENT` | **New:** CSV-specific mapping |
| `INSTRUMENT_TO_SEGMENT` | **New:** instrument type→segment |
| `DHAN_SEGMENTS` | 7 vs 9 (missing `NSE_CURRENCY`, `BSE_CURRENCY`) |
| No `NUMERIC_TO_SEGMENT` | Dropped |
| No `DhanSegmentMapper` | Dropped |

---

## 14. Capabilities API

### Archive — `dhan_capabilities()`

Returns `BrokerCapabilities` with:
- 16 boolean feature flags
- 6 `RateLimitProfile` entries (orders, quotes, historical, option_chain, funds, positions)
- 6 `HistoricalWindowConstraint` entries (1m–1D)
- `StreamLimitProfile` (1 connection, 1000 instruments, 200 depth)
- `latency_class="low"`, `reliability_class="tier1"`
- `product_types={INTRADAY, MARGIN, CNC, MTF}`
- `max_batch_size=1000`

### Greenfield — `DhanCapabilities`

Simple dataclass with boolean feature flags only. No rate limit profiles,
historical windows, or stream limits.

---

## 15. Exception Hierarchy API

### Archive

```
BrokerError (common.resilience.errors)
└── DhanError
    ├── InstrumentNotFoundError (+ _CommonInstrumentNotFoundError)
    ├── MarketDataError
    ├── OrderError (+ _CommonOrderError)
    ├── AuthenticationError (+ _CommonAuthenticationError)
    ├── ConfigurationError
    ├── DhanIdentityError
    ├── SuperOrderError
    ├── ForeverOrderError
    ├── ConditionalTriggerError
    ├── LedgerError
    ├── UserProfileError
    ├── IPManagementError
    ├── ExitAllError (+ _CommonExitAllError)
    └── EDISError
RateLimitError (re-exported from common)
```

Multiple inheritance ensures `isinstance` checks in global handler match.

### Greenfield

```
TradeXV2Error (domain.exceptions)
└── BrokerError
    ├── DhanError
    │   └── (no sub-classes defined)
    ├── DhanAuthenticationError (→ AuthenticationError)
    ├── DhanRateLimitError (→ RateLimitError)
    ├── DhanOrderRejectedError (→ OrderRejectedError)
    ├── DhanConnectionError (→ NetworkError → RetryableError)
    └── DhanServerError (→ BrokerServerError)
```

**Gap:** Greenfield has 5 exception types vs archive's 14. Missing:
`InstrumentNotFoundError`, `ConfigurationError`, `DhanIdentityError`,
`SuperOrderError`, `ForeverOrderError`, `ConditionalTriggerError`,
`LedgerError`, `UserProfileError`, `IPManagementError`, `ExitAllError`, `EDISError`.

---

## 16. Session Manager API

### Archive — `DhanSessionManager`

| Method | Input | Output |
|--------|-------|--------|
| `__init__(connection, auth?)` | `DhanConnection`, `AuthManager?` | — |
| `auth` (property) | — | `AuthManager?` |
| `token_valid()` | — | `bool` |
| `connection_state()` | — | `dict[str, bool]` |
| `subscription_snapshot()` | — | `dict[str, Any]` |
| `lifecycle_state()` | — | `str` (AUTH_REQUIRED/DISCONNECTED/DEGRADED/HEALTHY) |
| `is_ready_for_trading()` | — | `bool` |
| `health_summary()` | — | `dict[str, Any]` |

### Greenfield

No session manager. `DhanGateway.health()` provides equivalent data points.

---

## 17. Account Registry API

### Archive — `AccountConnectionRegistry`

| Method | Input | Output | Notes |
|--------|-------|--------|-------|
| `get_or_create(broker_id, account_id, factory_fn)` | `str, str, Callable` | gateway | Thread-safe singleton |
| `get(broker_id, account_id)` | `str, str` | gateway? | Lookup only |
| `release(broker_id, account_id)` | `str, str` | — | Closes + removes |
| `release_all()` | — | — | Closes all |
| `active_count()` | — | `int` | Current count |

Class-level `_lock` + `_gateways` dict. Process-wide singleton.

### Greenfield

No account registry. Caller manages gateway lifecycle.

---

## 18. TOTP Client API

### Archive — `DhanTotpClient`

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `__init__(settings?, cooldown?)` | Settings?, `TotpCooldownGuard?` | — | — |
| `generate()` | — | `str?` | `TotpRateLimitError` |

Uses `TotpCooldownGuard.for_broker("dhan")` for rate-limit protection.

### Greenfield

TOTP logic embedded in `DhanAuth.generate_token()`. No separate client class.

---

## 19. Secret Utilities API

### Archive — `secret_utils.py`

| Function | Input | Output |
|----------|-------|--------|
| `read_secret(env_key, file_key)` | `str, str` | `str?` |

Env var → file fallback pattern.

### Greenfield

Secret reading handled by infrastructure layer (`token_persistence` module).

---

## 20. Metrics API

### Archive — `metrics.py`

| Metric | Type | Labels |
|--------|------|--------|
| `dhan_request_total` | Counter | — |
| `dhan_request_duration_seconds` | Histogram | — |
| `dhan_errors_total` | Counter | — |
| `dhan_rate_limit_retries_total` | Counter | — |
| `dhan_ws_subscriptions` | Gauge | — |
| `dhan_ws_callbacks` | Gauge | — |
| `dhan_ws_reconnect_total` | Counter | — |
| `dhan_ws_ticks_total` | Counter | — |
| `dhan_ws_dropped_ticks_total` | Counter | — |

### Greenfield — `metrics.py`

| Metric | Type | Labels |
|--------|------|--------|
| `dhan_requests_total` | Counter | method, path, status |
| `dhan_request_errors_total` | Counter | method, path, error_type |
| `dhan_request_duration_seconds` | Histogram | method, path |

Plus decorators: `observe_metrics(func)`, `with_metrics(name, tracker)`, `with_rate_limit(rate_limiter)`

---

## 21. Ledger API

### Archive — `LedgerAdapter`

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `get_ledger(from_date, to_date)` | `str, str` (YYYY-MM-DD) | `list[LedgerEntry]` | `ValueError` (bad date), `LedgerError` |

### Greenfield — `DhanLedger`

| Method | Difference |
|--------|------------|
| `get_entries(from_date, to_date)` | Same flow, uses `observe_metrics` decorator |

---

## 22. IP Management API

### Archive — `IPManagementAdapter`

| Method | Input | Output | Exceptions |
|--------|-------|--------|------------|
| `set_ip(ip_address, ip_type)` | `str, str` | `dict` | `ValueError` (bad IP/type), `IPManagementError` |
| `modify_ip(ip_address, ip_type)` | `str, str` | `dict` | `ValueError`, `IPManagementError` |
| `get_ip()` | — | `list[IPConfig]` | `IPManagementError` |

IPv4 validation: standard dotted-quad regex.

### Greenfield — `DhanIpManagement`

| Method | Difference |
|--------|------------|
| `whitelist_ip(ip)` | Equivalent of `set_ip` |
| `get_ips()` | Same |
| `remove_ip(ip)` | **New:** removal support |

---

## 23. User Profile API

### Archive — `UserProfileAdapter`

| Method | Input | Output |
|--------|-------|--------|
| `get_profile()` | — | `UserProfile` |

### Greenfield — `DhanUserProfile`

| Method | Difference |
|--------|------------|
| `get()` | Returns dict |
| `update(data)` | **New:** update support |

---

## 24. Greenfield Equivalents Summary

| Archive Module | Greenfield Equivalent | Gap Severity |
|----------------|----------------------|--------------|
| `BrokerGateway` (959 lines) | `DhanGateway` (364 lines) | Low — port-based decomposition |
| `BrokerFactory` (595 lines) | Inlined in `DhanGateway.__init__` | Medium — no registry singleton |
| `DhanIdentityProvider` (545 lines) | `DhanInstrumentResolver` (226 lines) | Medium — no audit, no expected_segment |
| `DhanConfigLoader` (408 lines) | Static `config.py` (116 lines) | High — no runtime config |
| `DhanResilienceConfig` (305 lines) | Hardcoded constants | High — no resilience tuning |
| `DhanExtendedCapabilities` (313 lines) | Direct gateway properties | Low — same surface, different shape |
| `OptionsAdapter` (328 lines) | `DhanOptions` (367 lines) | Low — richer model |
| `FuturesAdapter` (86 lines) | `DhanFutures` (183 lines) | Low — richer model |
| `DhanSymbolValidator` (437 lines) | `DhanSymbolValidator` (26 lines) | High — no regex parsing |
| `DhanReconciliationService` (185 lines) | `DhanReconciliation` (67 lines) | High — no order recon, no repair |
| `AlertsAdapter` (162 lines) | `DhanAlerts` (51 lines) | Medium — no validation |
| `EDISAdapter` (113 lines) | `DhanEDIS` (58 lines) | Low |
| `segments.py` (183 lines) | `config.py` constants | Medium — no SDK int mapping |
| `capabilities.py` (133 lines) | `DhanCapabilities` (19 lines) | High — no rate profiles |
| `exceptions.py` (144 lines) | `exceptions.py` (35 lines) | High — 5 vs 14 types |
| `DhanSessionManager` (74 lines) | No equivalent | Medium |
| `AccountConnectionRegistry` (73 lines) | No equivalent | Medium |
| `DhanTotpClient` (98 lines) | Inlined in `DhanAuth` | Low |
| `secret_utils.py` (32 lines) | Infrastructure layer | Low |
| `metrics.py` (43 lines) | `metrics.py` (101 lines) | Low — richer labels |
| `LedgerAdapter` (73 lines) | `DhanLedger` (53 lines) | Low |
| `IPManagementAdapter` (131 lines) | `DhanIpManagement` (33 lines) | Low |
| `UserProfileAdapter` (57 lines) | `DhanUserProfile` (27 lines) | Low |
