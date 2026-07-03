# Phase 8 — Cross-Cutting Concerns: Dependency Graph

**Broker:** Dhan  
**Protocol:** Greenfield Broker Replication Protocol  
**Phase:** 8 — Cross-Cutting Concerns  
**Date:** 2026-07-03

---

## 1. Internal Dependencies (Archive)

### Module Import Matrix

The table below shows which archive modules import which other archive modules.
Rows are importers; columns are imported. `●` = direct import, `○` = conditional/lazy import.

| Module | gateway | factory | identity | config_loader | domain | extended | config | loader | settings | options | futures | symbol_val | recon | segments | alerts | common_ext | capabilities | ip_mgmt | edis | exceptions | inst_adapter | totp | session | account_reg | ledger | profile | metrics | token_mgr | constants | secret_utils | __init__ |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| gateway | — | | ● | | ○ | ○ | ● | | | | | | | ● | | | ● | | | ● | | | | | | | | | | |
| factory | | — | | ● | | | ● | | ● | | | | | | | | | | | | | | | ● | | | | ● | |
| identity | | | — | | ● | | | | | | | | | ● | | | | | | ● | | | | | | | | | | |
| config_loader | | | | — | | | ● | | | | | | | | | | | | | | | | | | | | | | | |
| domain | | | | | — | | | | | | | | | | | | | | | | | | | | | | | | | |
| extended | | | | | | — | | | | ○ | ○ | | | ● | | | | ○ | ○ | | | | | | | | | | |
| config | | | | | | | — | | | | | | | | | | | | | | | | | | | | | | | |
| loader | | | | | | | | — | | | | | | | | | | | | | | | | | | | | | | |
| settings | | | | | | | ● | | — | | | | | | | | | | | | | | | | | | | | | |
| options | | | | | | | | | | — | | | | | | | | | | ● | | | | | | | | | |
| futures | | | | | | | | | | | — | | | ● | | | | | | | | | | | | | | | |
| symbol_validator | | | | | ● | | | ● | | | | — | | | | | | | | | | | | | | | | | |
| reconciliation | | | | | | | | | | | | | — | | | | | | | | | | | | | | | | |
| segments | | | | | ● | | | | | | | | | — | | | | | | | | | | | | | | | | |
| alerts | | | | | ● | | | | | | | | | | — | | | | | ● | | | | | | | | | |
| common_extensions | | | | | | | | | | | | | | | | — | | | | | | | | | | | | | | |
| capabilities | | | | | | | | | | | | | | | | | — | | | | | | | | | | | | | |
| ip_management | | | | | | | | | | | | | | | | | | — | | ● | | | | | | | | | |
| edis | | | | | | | | | | | | | | | | | | | — | ● | | | | | | | | | |
| exceptions | | | | | | | | | | | | | | | | | | | | — | | | | | | | | | | |
| instrument_adapter | | | | | | | | | | | | | | | | | | | | — | | | | | | | | | |
| totp_client | | | | | | | | | | | | | | | | | | | | | — | | | | | | | | |
| session_manager | | | | | | | | | | | | | | | | | | | | | | — | | | | | | | |
| account_registry | | | | | | | | | | | | | | | | | | | | | | | — | | | | | | |
| ledger | | | | | | | | | | | | | | | | | | | | ● | | | | | — | | | | | |
| user_profile | | | | | | | | | | | | | | | | | | | | ● | | | | | | — | | | | |
| metrics | | | | | | | | | | | | | | | | | | | | | | | | | | — | | | |
| token_manager | | | | | | | | | | | | | | | | | | | | | | | | | | | — | | ● | |
| constants | | | | | | | | | | | | | | | | | | | | | | | | | | | | — | | |
| secret_utils | | | | | | | | | | | | | | | | | | | | | | | | | | | | | — | |
| __init__ | ● | ● | ● | | ● | | ● | | | | | | | | | | ● | | | ● | | | | | | | | | ● |

---

## 2. Internal Dependencies (Greenfield)

### Module Import Matrix

| Module | gateway | options | auth | identity | mapper | futures | token_broadcast | config | reconciliation | mtf | metrics | edis | alerts | invariants | instruments | ledger | exceptions | ip_mgmt | profile | symbol_val | capabilities |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| gateway | — | ● | ● | ● | | ● | ● | | ● | | | ● | ● | | ● | ● | | ● | ● | ● | |
| options | | — | | ● | | | | ● | | | | | | ● | | | | | | | |
| auth | | | — | | | | | ● | | | | | | | | | ● | | | | |
| identity | | | | — | | | | ● | | | | | | | | | | | | | |
| mapper | | | | | — | | | | | | | | | | | | | | | | |
| futures | | | | ● | | — | | ● | | | | | | ● | | | | | | | |
| token_broadcast | | | | | | | — | | | | | | | | | | | | | | |
| config | | | | | | | | — | | | | | | | | | | | | | |
| reconciliation | | | | | | | | | — | | | | | | | | | | | | |
| mtf | | | | ● | | | | ● | | — | | | | ● | | | | | | | |
| metrics | | | | | | | | | | | — | | | | | | | | | | |
| edis | | | | ● | | | | ● | | | | — | | ● | | | | | | | |
| alerts | | | | | | | | ● | | | | | — | | | | | | | | |
| invariants | | | | | | | | ● | | | | | | — | | | | | | | |
| instruments | | | | ● | | | | | | | | | | | — | | | | | | |
| ledger | | | | | | | | ● | | | | | | | | — | | | | | |
| exceptions | | | | | | | | | | | | | | | | | — | | | | |
| ip_mgmt | | | | | | | | ● | | | | | | | | | | — | | | |
| profile | | | | | | | | ● | | | | | | | | | | | — | | |
| symbol_validator | | | | ● | | | | | | | | | | | | | | | | — | |
| capabilities | | | | | | | | | | | | | | | | | | | | | — |

---

## 3. Cross-Phase Dependencies (Phases 0–7)

### Domain Layer Dependencies

```
brokers.domain.entities          ← Phase 1 (Order, Quote, Position, etc.)
brokers.domain.enums             ← Phase 1 (Side, OrderType, ProductType, etc.)
brokers.domain.exceptions        ← Phase 2 (BrokerError hierarchy)
brokers.domain.error_codes       ← Phase 2 (AUTH_ERROR, RATE_LIMITED, etc.)
brokers.domain.order_lifecycle   ← Phase 3 (OrderState enum)
```

### Port Layer Dependencies

```
brokers.ports.broker.BrokerGateway   ← Phase 4 (ISP composition)
brokers.ports.auth.AuthPort           ← Phase 1 (token management)
brokers.ports.instruments.InstrumentPort ← Phase 5 (instrument resolution)
brokers.ports.streaming.StreamingPort ← Phase 6 (WebSocket streaming)
brokers.ports.market_data.MarketDataPort ← Phase 4
brokers.ports.order_execution.OrderExecutionPort ← Phase 3
brokers.ports.portfolio.PortfolioPort ← Phase 4
brokers.ports.historical.HistoricalPort ← Phase 5
```

### Infrastructure Dependencies

```
brokers.infrastructure.token_persistence    ← Phase 1 (JsonTokenStateStore, update_env_token)
brokers.resilience.token_scheduler          ← Phase 2 (TokenRefreshScheduler)
```

### External Dependencies

```
Archive:
  brokers.common.resilience.errors          ← BrokerError, RateLimitError, etc.
  brokers.common.auth                       ← AuthManager, JsonTokenStateStore, TokenSource
  brokers.common.factory                    ← BrokerProviderFactory
  brokers.common.gateway                    ← MarketDataGateway, ObservabilityProvider
  brokers.common.batch_mixin                ← BatchFetchMixin
  brokers.common.broker_port               ← CommonBrokerGateway
  brokers.common.reconciliation.engine      ← ReconciliationEngine
  brokers.common.capabilities               ← BrokerCapabilities, RateLimitProfile
  brokers.common.segment_mapper             ← SegmentMapper ABC
  brokers.common.identity                   ← BrokerId
  brokers.dhan.connection                   ← DhanConnection (Phase 3-6 wiring)
  brokers.dhan.http_client                  ← DhanHttpClient (Phase 2)
  brokers.dhan.resilience                   ← create_circuit_breakers, create_rate_limiter
  brokers.dhan.token_scheduler              ← TokenRefreshScheduler
  brokers.dhan.secret_utils                 ← read_secret
  domain.entities.instrument                ← Canonical Instrument
  domain.exchange_segments                  ← parse_segment
  domain.symbols                            ← normalize_symbol
  config.endpoints.Dhan                     ← REST_BASE URL
  config.indices                            ← is_index, dhan_index_exchange

Greenfield:
  brokers.domain.entities                   ← Order, Quote, Position, etc.
  brokers.domain.enums                      ← Side, OrderType, etc.
  brokers.domain.exceptions                 ← BrokerError, InstrumentNotFoundError, etc.
  brokers.infrastructure.token_persistence  ← JsonTokenStateStore, update_env_token
  brokers.resilience.token_scheduler        ← TokenRefreshScheduler
  requests                                  ← HTTP client for CSV download
  pyotp                                     ← TOTP generation
  prometheus_client                         ← Metrics (Counter, Histogram)
```

---

## 4. Full Dependency Diagram (ASCII)

### Archive Dependency Graph

```
                        ┌─────────────────────────────────────────────┐
                        │            EXTERNAL LAYER                    │
                        │  domain.*  config.*  brokers.common.*        │
                        └──────────────────┬──────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
              ┌─────▼─────┐       ┌───────▼───────┐      ┌──────▼──────┐
              │ exceptions │       │   segments    │      │   domain    │
              │  (144L)    │       │   (183L)      │      │  (359L)     │
              └─────┬──────┘       └───────┬───────┘      └──────┬──────┘
                    │                      │                      │
         ┌──────────┼──────────┐          │                      │
         │          │          │          │                      │
    ┌────▼───┐ ┌────▼────┐ ┌──▼──────┐  │                      │
    │config  │ │identity │ │loader   │  │                      │
    │(305L)  │ │(545L)   │ │(305L)   │  │                      │
    └────┬───┘ └────┬────┘ └────┬────┘  │                      │
         │          │           │        │                      │
    ┌────▼────┐     │      ┌────▼────┐  │                      │
    │config_  │     │      │symbol_  │  │                      │
    │loader   │     │      │validat. │  │                      │
    │(408L)   │     │      │(437L)   │  │                      │
    └─────────┘     │      └─────────┘  │                      │
                    │                    │                      │
    ┌───────────────┼────────────────────┼──────────────────────┤
    │               │                    │                      │
    │    ┌──────────▼──────────┐  ┌──────▼──────┐  ┌──────────▼──────────┐
    │    │    options (328L)   │  │futures(86L) │  │alerts (162L)        │
    │    └──────────┬──────────┘  └──────┬──────┘  └──────────┬──────────┘
    │               │                    │                      │
    │    ┌──────────▼──────────┐  ┌──────▼──────┐  ┌──────────▼──────────┐
    │    │    extended (313L)  │  │edis (113L)  │  │ip_mgmt (131L)       │
    │    └──────────┬──────────┘  └──────┬──────┘  └──────────┬──────────┘
    │               │                    │                      │
    │    ┌──────────▼────────────────────▼──────────────────────▼──────┐
    │    │                  DhanConnection (Phase 3-6)                  │
    │    └──────────────────────────┬──────────────────────────────────┘
    │                               │
    │    ┌──────────────────────────▼──────────────────────────────────┐
    │    │                  BrokerGateway (959L)                        │
    │    │  MarketDataGateway + ObservabilityProvider + BatchFetchMixin │
    │    └──────────────────────────┬──────────────────────────────────┘
    │                               │
    │    ┌──────────────────────────▼──────────────────────────────────┐
    └───►│                  BrokerFactory (595L)                        │
         │  Settings → Auth → HTTP → Connection → Gateway → WS → Sched │
         └─────────────────────────────────────────────────────────────┘
```

### Greenfield Dependency Graph

```
                     ┌──────────────────────────────────────────┐
                     │           DOMAIN LAYER                    │
                     │  brokers.domain.{entities,enums,except.} │
                     └──────────────────┬───────────────────────┘
                                        │
              ┌─────────────────────────┼──────────────────────┐
              │                         │                      │
        ┌─────▼──────┐          ┌──────▼───────┐      ┌──────▼──────┐
        │ exceptions  │          │    config     │      │  invariants │
        │  (35L)      │          │   (116L)      │      │   (54L)     │
        └─────┬───────┘          └──────┬───────┘      └──────┬──────┘
              │                         │                      │
              │              ┌──────────┼──────────┐          │
              │              │          │          │          │
         ┌────▼────┐   ┌────▼────┐ ┌───▼────┐ ┌───▼────┐    │
         │  auth   │   │identity │ │metrics │ │ledger  │    │
         │ (240L)  │   │(226L)   │ │(101L)  │ │(53L)   │    │
         └────┬────┘   └────┬────┘ └────────┘ └────────┘    │
              │              │                                │
         ┌────▼────┐   ┌────▼────────────────────────────┐   │
         │  token_ │   │  options(367L)  futures(183L)   │   │
         │broadcast│   │  mtf(67L)  edis(58L)  alerts(51L)│  │
         │ (183L)  │   │  instruments(44L)  symbol_val   │   │
         └────┬────┘   │  (26L)                           │   │
              │        └────────────┬─────────────────────┘   │
              │                     │                          │
    ┌─────────▼─────────────────────▼──────────────────────────▼───┐
    │                     DhanGateway (364L)                          │
    │  Composes 20+ adapters, manages token lifecycle end-to-end     │
    │  TokenBroadcast ← DhanAuth ← DhanHttpClient                   │
    └───────────────────────────────────────────────────────────────┘
```

---

## 5. Domain Model Dependencies

### Archive Domain Models (domain.py)

```
domain.py
  ├── Exchange (enum) ← segments.py, identity.py, symbol_validator.py
  ├── DhanInstrumentType (enum) ← identity.py, symbol_validator.py
  ├── OptionType (enum) ← options.py, symbol_validator.py
  ├── MarginRequest / MarginResponse ← extended.py
  ├── AlertRequest / Alert ← alerts.py, extended.py
  ├── Instrument (wraps domain.entities.Instrument) ← identity.py, resolver
  ├── SuperOrderLeg / SuperOrder ← common_extensions.py
  ├── ForeverOrderRequest / ForeverOrder ← common_extensions.py
  ├── ConditionalTriggerRequest / ConditionalTrigger ← extended.py
  ├── LedgerEntry ← ledger.py
  ├── UserProfile ← user_profile.py
  ├── IPConfig ← ip_management.py
  └── ExitAllResponse ← extended.py
```

### Greenfield Domain Models

Greenfield uses `brokers.domain.entities` directly (Order, Quote, Position, etc.)
and defines adapter-specific dataclasses in individual modules:

```
options.py    → OptionChain, OptionStrike, OptionLeg (dataclasses)
identity.py   → DhanInstrumentRef (frozen dataclass)
auth.py       → uses TokenState from brokers.infrastructure
```

**Gap:** No Dhan-specific domain models (Alert, SuperOrder, ForeverOrder, etc.) in greenfield.

---

## 6. Port/Adapter Dependencies

### Greenfield Port Implementations

| Port | Implementation | Key Dependencies |
|------|---------------|-----------------|
| `BrokerGateway` | `DhanGateway` | All 20+ adapters |
| `AuthPort` | `DhanAuth` | `config.ENDPOINTS`, `pyotp`, `requests` |
| `OrderExecutionPort` | `DhanOrders` | `DhanHttpClient`, `DhanInstrumentResolver` |
| `MarketDataPort` | `DhanMarketData` | `DhanHttpClient`, `DhanInstrumentResolver` |
| `PortfolioPort` | `DhanPortfolio` | `DhanHttpClient` |
| `InstrumentPort` | `DhanInstruments` | `DhanInstrumentResolver` |
| `HistoricalPort` | `DhanHistorical` | `DhanHttpClient`, `DhanInstrumentResolver` |
| `StreamingPort` | `DhanStreaming` | `DhanInstrumentResolver`, token callback |

### Archive Port Implementations

| Port | Implementation | Key Dependencies |
|------|---------------|-----------------|
| `MarketDataGateway` | `BrokerGateway` | `DhanConnection` (facade) |
| `ObservabilityProvider` | `BrokerGateway` | Connection status, CB states, token metrics |
| `CommonBrokerGateway` | `_DhanCommonBrokerGateway` | Async wrapper around sync `BrokerGateway` |
| `BrokerProviderFactory` | `BrokerFactory` | Settings, Auth, HTTP, Connection, Gateway |

---

## 7. Greenfield Gap Analysis

### Missing Modules (Not Replicated)

| Archive Module | Lines | Purpose | Priority |
|---------------|:---:|---------|:---:|
| `session_manager.py` | 74 | Unified auth+connection+subscription health view | Medium |
| `account_registry.py` | 73 | Process-wide singleton per (broker, account) | Medium |
| `config_loader.py` | 408 | Multi-source config loading (env/JSON/file) | High |
| `common_extensions.py` | 149 | Extension registry integration | Low |
| `instrument_adapter.py` | 102 | Canonical InstrumentId conversion | Low |
| `constants.py` | 35 | WS subscription limits, idempotency config | Low |
| `secret_utils.py` | 32 | Env→file secret fallback | Low |
| `token_manager.py` | 38 | TOTP generation helpers | Low (merged into DhanAuth) |

### Severely Reduced Modules

| Module | Archive | Greenfield | Reduction | Gap Description |
|--------|:---:|:---:|:---:|------|
| `symbol_validator.py` | 437L | 26L | 94% | No F&O regex parsing, no expiry detection, no candidates |
| `capabilities.py` | 133L | 19L | 86% | No rate limit profiles, historical windows, stream limits |
| `identity.py` | 545L | 226L | 58% | No expected_segment, no audit logging, no index fallback |
| `reconciliation.py` | 185L | 67L | 64% | No order reconciliation, no auto-repair |
| `alerts.py` | 162L | 51L | 68% | No identity integration, no domain models |
| `edis.py` | 113L | 58L | 49% | No ISIN validation |
| `ip_management.py` | 131L | 33L | 75% | No IP validation, no PRIMARY/SECONDARY types |
| `exceptions.py` | 144L | 35L | 76% | No feature-specific exceptions |
| `gateway.py` | 959L | 364L | 62% | No CommonBrokerGateway, no ObservabilityProvider, no batch |

### Enhanced Modules (Greenfield > Archive)

| Module | Archive | Greenfield | Enhancement |
|--------|:---:|:---:|------|
| `futures.py` | 86L | 183L | Added get_contract with expiry resolution |
| `options.py` | 328L | 367L | Dataclass returns instead of TypedDict |
| `metrics.py` | 43L | 101L | Decorator pattern, centralized registry |
| `token_broadcast.py` | N/A | 183L | New: weak-ref pub/sub (archive used connection.broadcast_token) |
| `mapper.py` | N/A | 202L | New: centralized DTO→domain mapping |

---

## 8. Circular Dependency Check

### Archive — No Circular Dependencies Detected

The archive dependency graph is a DAG (directed acyclic graph). The dependency
flow is strictly:

```
exceptions → domain → segments → identity → [adapters] → extended → gateway → factory
```

No module imports a module that transitively imports it back. The only potential
cycle (`gateway ↔ extended`) is broken by a lazy import: `gateway.extended` uses
`from brokers.dhan.extended import DhanExtendedCapabilities` inside the property
method, not at module level.

### Greenfield — No Circular Dependencies Detected

Same DAG structure. The `gateway.py` imports all adapters at module level, but
no adapter imports gateway. The dependency flow is:

```
exceptions → config → invariants → identity → [adapters] → gateway
```

The `token_broadcast.py` has no imports from other adapter modules, breaking any
potential cycle with gateway.

### Potential Future Risks

1. **If `DhanOptions` imports `DhanFutures`** (for MCX expiry resolution) and
   `DhanFutures` imports `DhanOptions`, a cycle would form. Currently avoided:
   both use the shared resolver independently.

2. **If `DhanGateway` adds a `register_adapter()` method** that adapters call
   during init, a circular dependency would form. The current design avoids this
   by having the gateway create all adapters in `__init__`.

---

## 9. Dependency Direction Summary

```
LAYER 0 (Domain)     brokers.domain.{entities, enums, exceptions, error_codes}
        ↑
LAYER 1 (Ports)      brokers.ports.{broker, auth, instruments, streaming, ...}
        ↑
LAYER 2 (Config)     adapters.dhan.config, invariants
        ↑
LAYER 3 (Identity)   adapters.dhan.identity, exceptions
        ↑
LAYER 4 (Adapters)   adapters.dhan.{orders, market_data, portfolio, options, ...}
        ↑
LAYER 5 (Gateway)    adapters.dhan.gateway (DhanGateway)
        ↑
LAYER 6 (Infra)      brokers.infrastructure.token_persistence, resilience.token_scheduler
```

All dependencies point upward (inner layers depend on nothing in outer layers).
The gateway (Layer 5) composes adapters (Layer 4) which depend on identity (Layer 3)
and config (Layer 2), all grounded in domain types (Layer 0).
