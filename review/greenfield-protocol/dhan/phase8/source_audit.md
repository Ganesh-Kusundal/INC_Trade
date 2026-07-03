# Phase 8 — Cross-Cutting Concerns: Source Audit

**Broker:** Dhan  
**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 8 — Cross-Cutting Concerns  
**Date:** 2026-07-03

---

## Executive Summary

Phase 8 covers all cross-cutting concerns that span multiple adapter layers and are not addressed by Phases 0–7. This includes:

- **Gateway facade** — the unified API surface that composes all adapters
- **Factory/bootstrap** — wiring, dependency injection, and lifecycle management
- **Identity management** — symbol→security_id resolution with invariant enforcement
- **Configuration system** — resilience config, settings loading, environment overrides
- **Domain models** — Dhan-specific dataclasses (alerts, EDIS, forever orders, super orders)
- **Extended capabilities** — broker-specific features beyond the MarketDataGateway ABC
- **Options/Futures trading** — derivative instrument handling
- **Symbol validation** — pre-trade symbol verification
- **Reconciliation** — OMS↔broker state drift detection
- **Alerts, EDIS, segments** — auxiliary trading features
- **Exception hierarchy** — error classification and propagation
- **Cross-cutting** — logging, metrics, IP management, secrets, token lifecycle

The archive contains **31 files** totaling ~7,400 lines. The greenfield replication contains **21 files** totaling ~2,500 lines. Key gaps exist in extended capabilities (super orders, forever orders, conditional triggers), configuration loader, and the full symbol validator.

---

## Archive Files Inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `gateway.py` | 959 | Main broker gateway facade; composes DhanConnection, exposes MarketDataGateway + ObservabilityProvider |
| 2 | `factory.py` | 595 | BrokerFactory; bootstraps auth, HTTP client, connection, gateway, WebSocket wiring, token scheduler |
| 3 | `identity.py` | 545 | DhanIdentityProvider + DhanInstrumentRef; single source of truth for symbol→security_id |
| 4 | `config_loader.py` | 408 | DhanConfigLoader; env var, JSON, .env file loading for DhanResilienceConfig |
| 5 | `domain.py` | 359 | Dhan-specific domain models: Exchange, InstrumentType, Alert, SuperOrder, ForeverOrder, LedgerEntry, etc. |
| 6 | `extended.py` | 313 | DhanExtendedCapabilities; broker-specific features beyond MarketDataGateway ABC |
| 7 | `config.py` | 305 | DhanResilienceConfig dataclasses: rate limits, retry, circuit breaker, token config |
| 8 | `loader.py` | 305 | InstrumentLoader; CSV download + daily cache + MCX detailed supplement |
| 9 | `settings.py` | 283 | DhanConnectionSettings + DhanSettingsLoader; env var → frozen dataclass |
| 10 | `options.py` | 328 | OptionsAdapter; option chain, expiries, expired options historical data |
| 11 | `futures.py` | 86 | FuturesAdapter; contract discovery from instrument cache |
| 12 | `symbol_validator.py` | 437 | DhanSymbolValidator; F&O symbol parsing, instrument master validation |
| 13 | `reconciliation.py` | 185 | DhanReconciliationService; OMS↔broker drift detection + auto-repair |
| 14 | `segments.py` | 183 | Segment mappings: wire format, SDK codes, EXCHANGE_TO_SEGMENT, DERIVATIVE_SEGMENTS |
| 15 | `alerts.py` | 162 | AlertsAdapter; price alert CRUD with identity provider integration |
| 16 | `common_extensions.py` | 149 | Extension providers: SuperOrder, ForeverOrder, NativeSlice for ExtensionRegistry |
| 17 | `capabilities.py` | 133 | dhan_capabilities(); BrokerCapabilities descriptor with rate limits, historical windows |
| 18 | `ip_management.py` | 131 | IPManagementAdapter; static IP whitelisting (set/modify/get) |
| 19 | `edis.py` | 113 | EDISAdapter; TPIN generation, eDIS authorization, status check |
| 20 | `exceptions.py` | 144 | Exception hierarchy: DhanError → BrokerError, with feature-specific subclasses |
| 21 | `instrument_adapter.py` | 102 | to_instrument_id / from_instrument_id; canonical InstrumentId conversion |
| 22 | `totp_client.py` | 98 | DhanTotpClient; TOTP token generation with cooldown guard |
| 23 | `session_manager.py` | 74 | DhanSessionManager; auth + connection + subscription unified view |
| 24 | `account_registry.py` | 73 | AccountConnectionRegistry; process-wide singleton per (broker, account) |
| 25 | `ledger.py` | 73 | LedgerAdapter; account transaction ledger fetch |
| 26 | `user_profile.py` | 57 | UserProfileAdapter; user profile + configurations |
| 27 | `metrics.py` | 43 | Prometheus metrics: request counters, histograms, WS gauges |
| 28 | `token_manager.py` | 38 | generate_totp_token + read_secret utilities |
| 29 | `constants.py` | 35 | WS subscription limits, idempotency cache config |
| 30 | `secret_utils.py` | 32 | read_secret; env var → file fallback for secrets |
| 31 | `__init__.py` | 91 | Package init; re-exports key types, exceptions, factory |

**Total archive lines:** ~7,400

---

## Greenfield Files Inventory

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `gateway.py` | 364 | DhanGateway; composes all adapters, manages token lifecycle end-to-end |
| 2 | `options.py` | 367 | DhanOptions; option chain, expiries, expired options data |
| 3 | `auth.py` | 240 | DhanAuth; TOTP token generation, state tracking, refresh |
| 4 | `identity.py` | 226 | DhanInstrumentResolver + DhanInstrumentRef; CSV-based resolution |
| 5 | `mapper.py` | 202 | DTO→domain entity mapper; map_order, map_quote, map_depth, map_position, etc. |
| 6 | `futures.py` | 183 | DhanFutures; contract resolution by underlying + expiry |
| 7 | `token_broadcast.py` | 183 | TokenBroadcast; weak-ref pub/sub for token refresh notification |
| 8 | `config.py` | 116 | Endpoints, rate limits, segment maps, type maps |
| 9 | `reconciliation.py` | 67 | DhanReconciliation; position-only reconciliation |
| 10 | `mtf.py` | 67 | DhanMTF; Margin Trading Facility order placement |
| 11 | `metrics.py` | 66 | Prometheus metrics + observe_metrics decorator |
| 12 | `edis.py` | 58 | DhanEDIS; TPIN status, generate, EDIS form |
| 13 | `alerts.py` | 51 | DhanAlerts; alert CRUD (simplified) |
| 14 | `invariants.py` | 54 | assert_valid_dhan_payload; securityId + exchangeSegment checks |
| 15 | `instruments.py` | 44 | DhanInstruments; InstrumentPort backed by resolver |
| 16 | `ledger.py` | 53 | DhanLedger; ledger fetch (simplified) |
| 17 | `exceptions.py` | 35 | Dhan exception hierarchy mapping to domain exceptions |
| 18 | `ip_management.py` | 33 | DhanIpManagement; IP whitelisting (simplified) |
| 19 | `user_profile.py` | 27 | DhanUserProfile; profile fetch/update |
| 20 | `symbol_validator.py` | 26 | DhanSymbolValidator; simple resolve-based validation |
| 21 | `capabilities.py` | 19 | DhanCapabilities; feature flag dataclass |

**Total greenfield lines:** ~2,500

---

## Key Symbols & Classes

### Archive — Gateway API (Public Methods)

```
class BrokerGateway(BatchFetchMixin, MarketDataGateway, ObservabilityProvider):
    __init__(connection: DhanConnection)
    common_broker_gateway() -> CommonBrokerGateway
    extended -> DhanExtendedCapabilities          # property
    place_order(symbol, exchange, side, ...) -> OrderResponse
    cancel_order(order_id) -> OrderResponse
    get_order(order_id) -> Order | None
    modify_order(order_id, **changes) -> OrderResponse
    get_orderbook() -> list[Order]
    get_trade_book() -> list[Trade]
    load_instruments(source, use_cache)
    close()
    ltp(symbol, exchange) -> Decimal
    quote(symbol, exchange) -> Quote
    depth(symbol, exchange) -> MarketDepth
    depth_20(symbol, exchange, on_depth) -> MarketDepth
    depth_200(symbol, exchange, on_depth) -> MarketDepth
    history(symbol, exchange, timeframe, ...) -> pd.DataFrame
    option_chain(underlying, exchange, expiry) -> OptionChain
    future_chain(underlying, exchange) -> FutureChain
    get_balance() -> Balance
    funds() -> Balance
    positions() -> list[Position]
    holdings() -> list[Holding]
    trades() -> list[Trade]
    describe() -> dict
    capabilities() -> BrokerCapabilities
    search(query) -> list[dict]
    stream(symbol, exchange, mode, on_tick) -> Any
    unstream(symbol, exchange, on_tick)
    stream_depth(symbol, exchange, depth_type, on_depth) -> Any
    stream_order(on_order) -> Any
    unstream_order(on_order)
    ltp_batch(symbols, exchange) -> dict
    quote_batch(symbols, exchange) -> dict
    get_connection_status() -> dict
    get_connection_metadata() -> dict
    get_circuit_breaker_states() -> dict
    get_token_refresh_metrics() -> dict
```

### Archive — Factory/Bootstrap API

```
class BrokerFactory(BrokerProviderFactory):
    create(env_path, load_instruments, event_bus, ...) -> MarketDataGateway
    _build_gateway(settings, env_path, ...) -> MarketDataGateway
    _create_auth(settings, env_file) -> (AuthManager, str)
    _create_http_client(settings, auth, cid, ...) -> DhanHttpClient
    _create_connection_and_gateway(client, auth, ...) -> BrokerGateway
    _wire_websocket_services(gateway, client, token, ...)
    _setup_token_refresh_scheduler(gateway, auth, client, ...)

# Module-level helpers:
_refresh_via_auth(auth, env_file, refresh_lock) -> str | None
_next_token_expiry(now, lifetime_seconds) -> datetime
_generate_totp_token(settings) -> str | None
_update_env_token(env_path, token)
```

### Archive — Identity Management API

```
class DhanInstrumentRef(dataclass, frozen):
    symbol, exchange, exchange_segment, security_id
    instrument_type, lot_size, source, is_synthetic_index
    underlying, expiry, strike_price, option_type
    is_derivative -> bool
    is_option -> bool
    is_future -> bool
    security_id_str() -> str

class DhanIdentityProvider:
    __init__(resolver: SymbolResolver)
    resolver -> SymbolResolver
    issue_count -> int
    synthetic_index_count -> int
    to_payload_security_id(ref) -> str  (static)
    resolve_ref(symbol, exchange, *, expected_segment) -> DhanInstrumentRef
    resolve_ref_from_security_id(security_id, exchange) -> DhanInstrumentRef | None

def coerce_identity_provider(identity, allow_duck=False) -> DhanIdentityProvider
DHAN_SEGMENTS: frozenset[str]
def is_dhan_segment(segment) -> bool
```

### Archive — Configuration System

```
# config.py
@dataclass DhanRateLimitConfig:   limits, read_prefixes, write_prefixes, bucket_map
@dataclass DhanRetryConfig:       max_retries, base_delay_ms, max_delay_ms
@dataclass DhanCircuitBreakerConfig: read/write_prefixes, thresholds, recovery
@dataclass DhanTokenConfig:       refresh_cooldown_seconds, rate_limit_backoff_seconds
@dataclass DhanResilienceConfig:  rate_limit, retry, circuit_breaker, token, base_url
    from_dict(data) -> DhanResilienceConfig
    to_dict() -> dict

# config_loader.py
class DhanConfigLoader:
    load(env_path, env_prefix) -> DhanResilienceConfig
    load_from_file(file_path) -> DhanResilienceConfig
    load_from_dict(data) -> DhanResilienceConfig
    load_from_environment(prefix) -> DhanResilienceConfig

# settings.py
@dataclass DhanConnectionSettings(BrokerSettings):
    environment, base_url, pin, totp_secret, token_lifetime_seconds
    scheduler_interval_seconds, refresh_buffer_seconds, allow_live_orders
    token_state_dir, resilience_config
    resolved_token_state_dir -> Path
    is_sandbox -> bool
    has_totp -> bool

class DhanSettingsLoader(SettingsLoaderBase):
    from_env(env_path, prefix) -> DhanConnectionSettings
    from_dict(values, prefix) -> DhanConnectionSettings
```

### Archive — Domain Models

```
Exchange(str, Enum):       NSE, BSE, NFO, BFO, MCX, CDS, INDEX
DhanInstrumentType(str, Enum): EQUITY, FUTURE, OPTION, COMMODITY
OptionType(str, Enum):     CALL, PUT

@dataclass MarginRequest / MarginResponse
@dataclass AlertRequest / Alert
@dataclass Instrument (wraps domain.entities.Instrument)
@dataclass SuperOrderLeg / SuperOrder
@dataclass ForeverOrderRequest / ForeverOrder
@dataclass ConditionalTriggerRequest / ConditionalTrigger
@dataclass LedgerEntry
@dataclass UserProfile
@dataclass IPConfig
@dataclass ExitAllResponse
```

### Archive — Extended Features

```
class DhanExtendedCapabilities:
    instruments -> Any
    identity -> Any
    orders -> Any
    get_positions() / get_holdings() / get_balance()
    get_expiries(underlying, exchange)
    place_super_order / modify_super_order / cancel_super_order_leg / get_super_orders
    place_forever_order / modify_forever_order / cancel_forever_order / get_all_forever_orders
    place_conditional_trigger / modify_conditional_trigger / delete_conditional_trigger
    get_ledger(from_date, to_date)
    get_user_profile()
    set_ip / modify_ip / get_ip
    generate_tpin / authorize_edis / check_edis_status
    exit_all()
    get_option_expiries / get_option_chain / get_expired_options_data
    get_futures_contracts / get_futures_expiries / is_commodity
    validate_order(**kwargs)
    get_alerts()
```

### Archive — Exception Hierarchy

```
BrokerError (brokers.common.resilience.errors)
  └── DhanError
        ├── InstrumentNotFoundError (also _CommonInstrumentNotFoundError)
        ├── MarketDataError
        ├── OrderError (also _CommonOrderError)
        ├── AuthenticationError (also _CommonAuthenticationError)
        ├── ConfigurationError
        ├── DhanIdentityError
        ├── SuperOrderError
        ├── ForeverOrderError
        ├── ConditionalTriggerError
        ├── LedgerError
        ├── UserProfileError
        ├── IPManagementError
        ├── ExitAllError (also _CommonExitAllError)
        └── EDISError

RateLimitError — aliased to canonical common version
```

### Greenfield — Gateway API (Public Properties & Methods)

```
class DhanGateway:
    __init__(access_token, client_id, pin, totp_secret, allow_live_orders, ...)
    orders -> DhanOrders                          # property
    super_orders -> DhanSuperOrders                # property
    forever_orders -> DhanForeverOrders            # property
    margin -> DhanMargin                           # property
    mtf -> DhanMTF                                 # property
    options -> DhanOptions                          # property
    futures -> DhanFutures                          # property
    order_stream -> DhanOrderStream                 # property
    conditional_triggers -> DhanConditionalTriggers # property
    exit_all -> DhanExitAll                         # property
    edis -> DhanEDIS                                # property
    depth20_stream -> DhanDepth20Stream             # property
    depth200_stream -> DhanDepth200Stream           # property
    ledger -> DhanLedger                            # property
    alerts -> DhanAlerts                            # property
    ip_management -> DhanIpManagement               # property
    user_profile -> DhanUserProfile                 # property
    reconciliation -> DhanReconciliation            # property
    symbol_validator -> DhanSymbolValidator         # property
    market_data -> DhanMarketData                   # property
    portfolio -> DhanPortfolio                      # property
    instruments -> DhanInstruments                  # property
    auth -> DhanAuth                                # property
    historical -> DhanHistorical                    # property
    streaming -> StreamingPort                      # property
    broadcast -> TokenBroadcast                     # property
    scheduler -> TokenRefreshScheduler | None       # property
    get_option_expiries(underlying, exchange) -> list[str]
    health() -> dict
    close()
```

### Greenfield — Auth API

```
class DhanAuth:
    __init__(access_token, client_id, pin, totp_secret, token_lifetime_seconds, token_store)
    state -> TokenState | None
    get_token() -> str
    is_valid() -> bool
    is_authenticated() -> bool
    generate_token() -> str           # TOTP-based, raises TokenRateLimitError
    refresh_token() -> str            # regenerate via TOTP
    acquire() -> TokenState | None
    force_refresh() -> TokenState | None
```

### Greenfield — Identity Resolver API

```
@dataclass(frozen=True)
class DhanInstrumentRef:
    symbol, security_id, exchange_segment, instrument_type, lot_size
    security_id_str() -> str
    security_id_int() -> int

class DhanInstrumentResolver:
    load()                              # fetch + parse master CSV
    resolve(symbol, exchange) -> DhanInstrumentRef
    get_by_security_id(security_id) -> DhanInstrumentRef | None
    search(query, limit) -> list[DhanInstrumentRef]
    load_from_csv_text(csv_text)        # testing helper
```

### Greenfield — Config Constants

```
ENDPOINTS: dict[str, str]               # REST API URLs
RATE_LIMITS: dict[str, float]           # endpoint → min interval
EXCHANGE_MAP: dict[str, str]            # user exchange → wire segment
CSV_EXCHANGE_TO_SEGMENT: dict[str, str] # CSV exchange → wire segment
INSTRUMENT_TO_SEGMENT: dict[str, str]   # CSV instrument name → segment
DHAN_SEGMENTS: frozenset[str]           # canonical segment set
DERIVATIVE_SEGMENTS: frozenset[str]     # derivative-only segments
SIDE_MAP, ORDER_TYPE_MAP, PRODUCT_TYPE_MAP, VALIDITY_MAP
```

### Greenfield — Exception Hierarchy

```
BrokerError (brokers.domain.exceptions)
  └── DhanError
        ├── DhanAuthenticationError (also AuthenticationError)
        ├── DhanRateLimitError (also RateLimitError)
        ├── DhanOrderRejectedError (also OrderRejectedError)
        ├── DhanConnectionError (also NetworkError)
        └── DhanServerError (also BrokerServerError)
```

---

## Greenfield vs Archive Comparison

### Coverage Matrix

| Concern | Archive | Greenfield | Gap |
|---------|---------|------------|-----|
| Gateway facade | BrokerGateway (959L) | DhanGateway (364L) | Greenfield drops CommonBrokerGateway adapter, ObservabilityProvider, depth_20/200 merging, batch methods |
| Factory | BrokerFactory (595L) | Inline in DhanGateway.__init__ | No separate factory; no BrokerProviderFactory interface |
| Identity | DhanIdentityProvider (545L) | DhanInstrumentResolver (226L) | No DhanInstrumentRef invariant on exchange enum coercion; no expected_segment disambiguation; no audit logging |
| Config loader | DhanConfigLoader (408L) | config.py (116L) | No env var loading, no JSON file loading, no deep merge — hardcoded constants only |
| Settings | DhanConnectionSettings (283L) | Inline in DhanGateway.__init__ params | No frozen dataclass, no sandbox support, no resilience config |
| Domain models | domain.py (359L) | Entities in brokers.domain | No Dhan-specific models (Alert, SuperOrder, ForeverOrder, etc.) in greenfield |
| Extended | DhanExtendedCapabilities (313L) | Individual adapters | No unified extended facade; super orders/forever orders/conditional triggers exist as separate adapters |
| Options | OptionsAdapter (328L) | DhanOptions (367L) | Fully replicated with dataclass returns instead of TypedDict |
| Futures | FuturesAdapter (86L) | DhanFutures (183L) | Expanded: adds get_contract with expiry resolution, get_futures_chain |
| Symbol validator | DhanSymbolValidator (437L) | DhanSymbolValidator (26L) | MASSIVE GAP: no F&O parsing, no expiry validation, no candidate listing |
| Reconciliation | DhanReconciliationService (185L) | DhanReconciliation (67L) | Position-only; no order reconciliation, no auto-repair, no shared engine |
| Segments | segments.py (183L) | config.py maps | No DhanSegmentMapper, no SDK int conversion, no DERIVATIVE_SEGMENTS constant |
| Alerts | AlertsAdapter (162L) | DhanAlerts (51L) | Simplified; no identity provider integration, no domain models |
| EDIS | EDISAdapter (113L) | DhanEDIS (58L) | Different API surface; no ISIN validation |
| Capabilities | dhan_capabilities() (133L) | DhanCapabilities (19L) | MASSIVE GAP: no rate limit profiles, no historical windows, no stream limits |
| IP management | IPManagementAdapter (131L) | DhanIpManagement (33L) | Simplified; no IP validation, no PRIMARY/SECONDARY types |
| Exceptions | exceptions.py (144L) | exceptions.py (35L) | Fewer feature-specific exceptions; no SuperOrderError, ForeverOrderError, etc. |
| Metrics | metrics.py (43L) | metrics.py (66L) | Greenfield adds decorator pattern; archive uses shared registry |
| Invariants | invariants.py (via PR-B) | invariants.py (54L) | Fully replicated |
| Token broadcast | connection.broadcast_token | TokenBroadcast (183L) | Greenfield has dedicated class with weak-ref support |
| Mapper | (in connection/adapters) | mapper.py (202L) | New in greenfield: centralized DTO→domain mapping |
| Session manager | DhanSessionManager (74L) | — | MISSING in greenfield |
| Account registry | AccountConnectionRegistry (73L) | — | MISSING in greenfield |
| TOTP client | DhanTotpClient (98L) | DhanAuth (inline) | Merged into DhanAuth in greenfield |
| Constants | constants.py (35L) | — | MISSING in greenfield |
| Secret utils | secret_utils.py (32L) | — | MISSING in greenfield |
| Instrument adapter | instrument_adapter.py (102L) | — | MISSING in greenfield |
| Common extensions | common_extensions.py (149L) | — | MISSING in greenfield |
| Loader | InstrumentLoader (305L) | DhanInstrumentResolver._do_load | Simplified: no caching, no MCX supplement |

---

## Cross-Cutting Concerns Summary

### Logging
- **Archive:** Structured logging with `extra={}` dicts throughout; uses `logging.getLogger(__name__)`
- **Greenfield:** Same pattern; consistent structured logging

### Metrics
- **Archive:** Uses shared `infrastructure.metrics.registry` (9 metrics: request_total, duration, errors, WS gauges)
- **Greenfield:** Direct `prometheus_client` Counter/Histogram + `observe_metrics` decorator (3 metrics)

### IP Management
- **Archive:** Full IPv4 validation, PRIMARY/SECONDARY types, IPConfig domain model
- **Greenfield:** Simplified whitelist add/remove/list

### Secrets
- **Archive:** `read_secret(env_key, file_key)` with env→file fallback
- **Greenfield:** Secrets passed directly to DhanAuth constructor

### Token Lifecycle
- **Archive:** AuthManager + TokenRefreshScheduler + _refresh_via_auth + _update_env_token (atomic fcntl)
- **Greenfield:** DhanAuth + TokenRefreshScheduler + TokenBroadcast (weak-ref) + JsonTokenStateStore

### Error Handling
- **Archive:** 16 exception classes with multiple inheritance from common resilience errors
- **Greenfield:** 6 exception classes inheriting from domain exceptions directly

---

## Archive — Detailed Module Analysis

### Segments Module (`segments.py`, 183 lines)

The segments module provides the canonical mapping between user-facing exchange names,
Dhan wire-format segment codes, and SDK binary protocol numeric codes.

**Key mappings:**

| Layer | Example | Code |
|-------|---------|------|
| User exchange | NSE, NFO, MCX | Short codes |
| Wire segment | NSE_EQ, NSE_FNO, MCX_COMM | HTTP API payloads |
| SDK numeric | 1, 2, 5 | WebSocket binary protocol |
| Compact | (NSE, E)→NSE_EQ, (NSE, D)→NSE_FNO | Legacy format |

**Constants:**
- `EXCHANGE_TO_SEGMENT` — user exchange → wire segment (8 entries)
- `SEGMENT_TO_EXCHANGE` — wire segment → user exchange (reverse map)
- `NUMERIC_TO_SEGMENT` — SDK int → wire segment (8 entries)
- `DERIVATIVE_SEGMENTS` — frozenset of derivative-only segments
- `EQUITY_ONLY_PRODUCTS` — frozenset {CNC, MTF}

**DhanSegmentMapper** implements `SegmentMapper` ABC for polymorphic segment conversion.

### Loader Module (`loader.py`, 305 lines)

InstrumentLoader handles daily cache (6hr TTL) of the Dhan master CSV with MCX detailed supplement.

**Key methods:**
- `load_cached()` — returns cached rows, re-downloads if stale
- `_download_master()` — fetches CSV from `images.dhan.co`
- `_supplement_mcx()` — adds MCX commodity detail from JSON endpoint
- `_parse_compact_csv()` — memory-efficient compact CSV parsing

### Settings Module (`settings.py`, 283 lines)

DhanConnectionSettings extends BrokerSettings with Dhan-specific fields.

**Key fields:**
- `environment` (sandbox/live), `base_url`, `pin`, `totp_secret`
- `token_lifetime_seconds`, `scheduler_interval_seconds`, `refresh_buffer_seconds`
- `allow_live_orders`, `token_state_dir`, `resilience_config`

**DhanSettingsLoader** provides `from_env()` and `from_dict()` factory methods.

### TOTP Client (`totp_client.py`, 98 lines)

DhanTotpClient wraps pyotp with TotpCooldownGuard to prevent rate-limit hits.

### Session Manager (`session_manager.py`, 74 lines)

DhanSessionManager provides unified view of auth + connection + subscription state.

**Key methods:**
- `token_valid() -> bool`
- `connection_state() -> dict`
- `subscription_snapshot() -> dict`
- `lifecycle_state() -> dict`
- `health_summary() -> dict`

### Account Registry (`account_registry.py`, 73 lines)

AccountConnectionRegistry provides process-wide singleton per (broker, account) pair.
Thread-safe via class-level lock.

**Key methods:**
- `get_or_create(broker_id, account_id, factory) -> MarketDataGateway`
- `get(broker_id, account_id) -> MarketDataGateway | None`
- `release(broker_id, account_id)`
- `release_all()`

### Common Extensions (`common_extensions.py`, 149 lines)

Registers Dhan-specific extension providers with the ExtensionRegistry:
- `DhanSuperOrderExtension` — bracket order support
- `DhanForeverOrderExtension` — GTT order support
- `DhanNativeSliceOrderExtension` — native slice order support
- `register_dhan_extensions()` — factory function

### Instrument Adapter (`instrument_adapter.py`, 102 lines)

Conversion functions between Dhan instrument representation and canonical InstrumentId:
- `to_instrument_id(ref: DhanInstrumentRef) -> InstrumentId`
- `from_instrument_id(inst_id: InstrumentId) -> DhanInstrumentRef`

### Constants (`constants.py`, 35 lines)

WebSocket subscription limits and idempotency cache configuration:
- `WS_MAX_SUBSCRIPTIONS = 1000`
- `WS_DEPTH_LEVELS = (5, 20, 200)`
- `IDEMPOTENCY_CACHE_TTL = 300`

### Secret Utils (`secret_utils.py`, 32 lines)

`read_secret(env_key, file_key)` — reads secret from env var first, falls back to file path.

### Token Manager (`token_manager.py`, 38 lines)

Helper functions: `generate_totp_token(secret) -> str`, `read_secret(env_key, file_key) -> str`.

### Package Init (`__init__.py`, 91 lines)

Re-exports key types: BrokerFactory, BrokerGateway, DhanInstrumentRef, DhanIdentityProvider,
all exceptions, DhanResilienceConfig, DEFAULT_CONFIG.

---

## Greenfield — Detailed Module Analysis

### Token Broadcast (`token_broadcast.py`, 183 lines)

TokenBroadcast implements weak-ref pub/sub for token refresh notification.

**Key classes:**
- `TokenReceiverRef` — weak reference to a callback, with alive check
- `TokenBroadcast` — manages receivers, broadcasts new tokens, cleans dead refs

**Key methods:**
- `register_receiver(callback)` — adds weak-ref to callback
- `broadcast(new_token)` — sends token to all live receivers
- `token_refresh_metrics -> dict` — delivery success count

### Mapper (`mapper.py`, 202 lines)

Centralized DTO→domain entity mapping functions:
- `map_order(dto) -> Order`
- `map_order_response(dto) -> OrderResponse`
- `map_quote(dto) -> Quote`
- `map_depth(dto) -> MarketDepth`
- `map_position(dto) -> Position`
- `map_holding(dto) -> Holding`
- `map_balance(dto) -> Balance`
- `map_trade(dto) -> Trade`

### Invariants (`invariants.py`, 54 lines)

`assert_valid_dhan_payload(payload, context)` — defence-in-depth check before every HTTP call:
- Validates securityId is a positive digit string
- Validates exchangeSegment is in DHAN_SEGMENTS
- Scans market data dict values for non-numeric security IDs

### MTF (`mtf.py`, 67 lines)

DhanMTF places Margin Trading Facility orders using standard order endpoint with productType="MTF".

### Metrics (`metrics.py`, 101 lines)

Prometheus metrics integration:
- `dhan_api_requests_total` (Counter) — by endpoint, method, status
- `dhan_api_duration_seconds` (Histogram) — by endpoint
- `observe_metrics` decorator — auto-instruments any method
- `MetricsRegistry` — centralized registry

---

## Phase 8 Coverage Summary

| Category | Archive Files | Archive Lines | Greenfield Files | Greenfield Lines | Coverage |
|----------|:---:|:---:|:---:|:---:|:---:|
| Gateway/Facade | 1 | 959 | 1 | 364 | 38% |
| Factory/Bootstrap | 1 | 595 | 0 (inline) | 0 | 0% |
| Identity | 1 | 545 | 1 | 226 | 41% |
| Config/Settings | 3 | 996 | 1 | 116 | 12% |
| Domain Models | 1 | 359 | 0 (use domain/) | 0 | 0% |
| Extended Features | 2 | 462 | 0 (split) | 0 | 0% |
| Options/Futures | 2 | 414 | 2 | 550 | 133% |
| Symbol Validation | 1 | 437 | 1 | 26 | 6% |
| Reconciliation | 1 | 185 | 1 | 67 | 36% |
| Alerts/EDIS/Segments | 3 | 458 | 3 | 142 | 31% |
| Capabilities | 1 | 133 | 1 | 19 | 14% |
| Exceptions | 1 | 144 | 1 | 35 | 24% |
| Cross-cutting | 10 | 1,029 | 5 | 365 | 35% |
| **Total** | **31** | **~7,400** | **21** | **~2,500** | **34%** |
