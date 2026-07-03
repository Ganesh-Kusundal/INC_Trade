# Phase 4 Dependency Graph — Dhan Market Data

## Overview

This document maps the dependency relationships for Phase 4 (Market Data) components, including internal module dependencies, external library dependencies, cross-phase dependencies, and identifies gaps in the greenfield implementation.

---

## 1. Internal Dependencies (Module-to-Module)

### Archive Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│                         connection.py                            │
│                    (DhanConnection orchestrator)                 │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ market_data  │    │ subscription     │    │   websocket/    │
│   .py        │    │  _engine.py      │    │  market_feed.py │
│(MarketData   │    │(Subscription     │    │ (DhanMarketFeed)│
│  Adapter)    │    │  Engine)         │    │                 │
└──────────────┘    └──────────────────┘    └─────────────────┘
                              │                     │
                              │                     ▼
                              │            ┌──────────────────┐
                              │            │  websocket/      │
                              │            │  _helpers.py     │
                              │            └──────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  depth_20.py │    │ depth_feed_base  │    │  depth_200.py   │
│(DhanDepth20  │    │    .py           │    │(DhanDepth200    │
│   Feed)      │    │(BinaryDepthFeed) │    │   Feed)         │
└──────────────┘    └──────────────────┘    └─────────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  connection      │
                    │  _admission.py   │
                    │(MarketFeed       │
                    │ Connection       │
                    │ Admission)       │
                    └──────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ reconnecting     │
                    │  _service.py     │
                    │(Reconnecting     │
                    │ ServiceMixin)    │
                    └──────────────────┘
```

### Detailed Archive Dependencies

#### `connection.py` (DhanConnection)
**Imports:**
- `brokers.dhan.market_data.MarketDataAdapter`
- `brokers.dhan.subscription_engine.SubscriptionEngine`
- `brokers.dhan.websocket.DhanMarketFeed`
- `brokers.dhan.websocket.DhanOrderStream`
- `brokers.dhan.websocket.PollingMarketFeed`
- `brokers.dhan.depth_20.DhanDepth20Feed`
- `brokers.dhan.depth_200.DhanDepth200Feed`
- `brokers.dhan.depth_200.Depth200ConnectionPool`
- `brokers.dhan.http_client.DhanHttpClient`
- `brokers.dhan.resolver.SymbolResolver`
- `brokers.dhan.identity.DhanIdentityProvider`
- `brokers.dhan.connection_lifecycle.ConnectionLifecycle`
- `brokers.dhan.connection_token_manager.ConnectionTokenManager`
- `infrastructure.event_bus.EventBus`
- `infrastructure.lifecycle.LifecycleManager`

**Responsibilities:**
- Master orchestrator wiring all adapters
- Factory methods for WebSocket feeds
- Lifecycle management
- Token broadcast

#### `market_data.py` (MarketDataAdapter)
**Imports:**
- `brokers.dhan.http_client.DhanHttpClient`
- `brokers.dhan.identity.DhanIdentityProvider`
- `brokers.dhan.invariants.assert_dhan_identity`
- `domain.Quote`
- `domain.MarketDepth`
- `domain.DepthLevel`

**Responsibilities:**
- REST API for LTP, quote, depth, OHLC
- Symbol resolution
- Payload validation
- Response parsing

#### `subscription_engine.py` (SubscriptionEngine)
**Imports:**
- `brokers.dhan.segments.EXCHANGE_TO_SEGMENT`
- `brokers.dhan.segments.DEFAULT_SEGMENT`
- `domain.Quote`
- `domain.symbols.make_position_key`

**Responsibilities:**
- Instrument ref-counting
- Callback registration
- Feed lifecycle
- Order stream management

#### `websocket/market_feed.py` (DhanMarketFeed)
**Imports:**
- `brokers.dhan.websocket._helpers._DhanContext`
- `brokers.dhan.websocket._helpers._sdk_market_feed_class`
- `brokers.dhan.websocket._helpers._to_decimal`
- `brokers.dhan.websocket._helpers._to_sdk_instruments`
- `brokers.dhan.connection_admission.MarketFeedConnectionAdmission`
- `brokers.dhan.reconnecting_service.ReconnectingServiceMixin`
- `domain.Quote`
- `domain.MarketDepth`
- `domain.DepthLevel`
- `infrastructure.event_bus.DomainEvent`
- `infrastructure.event_bus.EventBus`
- `infrastructure.lifecycle.lifecycle.HealthState`
- `infrastructure.lifecycle.lifecycle.HealthStatus`
- `infrastructure.lifecycle.lifecycle.ManagedService`

**Responsibilities:**
- SDK-based market feed wrapper
- Quote/depth streaming
- Reconnection with backoff
- Admission control
- Staleness detection
- EventBus publishing

#### `depth_feed_base.py` (BinaryDepthFeed)
**Imports:**
- `brokers.dhan.connection_admission.MarketFeedConnectionAdmission`
- `brokers.dhan.reconnecting_service.ReconnectingServiceMixin`
- `domain.DepthLevel`
- `domain.MarketDepth`
- `domain.symbols.normalize_symbol`
- `infrastructure.event_bus.DomainEvent`
- `infrastructure.event_bus.EventBus`
- `infrastructure.lifecycle.lifecycle.HealthState`
- `infrastructure.lifecycle.lifecycle.HealthStatus`
- `infrastructure.lifecycle.lifecycle.ManagedService`

**Responsibilities:**
- Base class for depth WebSocket feeds
- Binary packet parsing
- Depth cache management
- Reconnection logic
- Callback dispatch

#### `depth_20.py` (DhanDepth20Feed)
**Imports:**
- `brokers.dhan.depth_feed_base.BinaryDepthFeed`
- `config.endpoints.Dhan`
- `domain.MarketDepth`
- `infrastructure.event_bus.EventBus`

**Responsibilities:**
- 20-level depth feed
- 50 instruments per connection
- Header carries security_id

#### `depth_200.py` (DhanDepth200Feed)
**Imports:**
- `brokers.dhan.depth_feed_base.BinaryDepthFeed`
- `config.endpoints.Dhan`
- `domain.MarketDepth`
- `infrastructure.event_bus.EventBus`

**Responsibilities:**
- 200-level depth feed
- 1 instrument per connection
- Header carries num_rows

#### `depth_200.py` (Depth200ConnectionPool)
**Imports:**
- `brokers.dhan.depth_200.DhanDepth200Feed`
- `brokers.dhan.resilience.websocket_rate_limiter_simple.get_dhan_ws_rate_limiter`

**Responsibilities:**
- Connection pooling for multiple depth-200 feeds
- Rate limiting
- Feed lifecycle

### Greenfield Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│                    (No master orchestrator yet)                  │
└─────────────────────────────────────────────────────────────────┘
                              
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ market_data  │    │  streaming.py    │    │  order_stream   │
│   .py        │    │ (DhanStreaming)  │    │    .py          │
│(DhanMarket   │    │                  │    │(DhanOrderStream)│
│  Data)       │    │                  │    │                 │
└──────────────┘    └──────────────────┘    └─────────────────┘
        │                     │                     │
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  depth20.py  │    │base_streaming.py │    │base_streaming.py│
│(DhanDepth20  │    │(BaseWebSocket    │    │(BaseWebSocket   │
│  Stream)     │    │ Streaming)       │    │ Streaming)      │
└──────────────┘    └──────────────────┘    └─────────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  config.py       │
                    │(ENDPOINTS,       │
                    │ EXCHANGE_MAP)    │
                    └──────────────────┘
```

### Detailed Greenfield Dependencies

#### `market_data.py` (DhanMarketData)
**Imports:**
- `brokers.adapters.dhan.config.ENDPOINTS`
- `brokers.adapters.dhan.config.SEGMENT_TO_EXCHANGE`
- `brokers.adapters.dhan.http.DhanHttpClient`
- `brokers.adapters.dhan.identity.DhanInstrumentResolver`
- `brokers.adapters.dhan.invariants.assert_valid_dhan_payload`
- `brokers.adapters.dhan.mapper.map_depth`
- `brokers.adapters.dhan.mapper.map_quote`
- `brokers.domain.MarketDepth`
- `brokers.domain.Quote`

**Responsibilities:**
- REST API for LTP, quote, depth
- Symbol resolution
- Payload validation
- Response parsing (flexible)

#### `streaming.py` (DhanStreaming)
**Imports:**
- `brokers.adapters.base_streaming.BaseWebSocketStreaming`
- `brokers.adapters.dhan.config.EXCHANGE_MAP`

**Responsibilities:**
- Market feed WebSocket adapter
- Subscription management
- Tick parsing

#### `depth20.py` (DhanDepth20Stream)
**Imports:**
- `brokers.adapters.base_streaming.BaseWebSocketStreaming`
- `brokers.adapters.dhan.config.EXCHANGE_MAP`

**Responsibilities:**
- Depth-20 WebSocket adapter
- Binary packet parsing (placeholder)
- Depth callback dispatch

#### `depth200.py` (DhanDepth200Stream)
**Imports:**
- `brokers.adapters.base_streaming.BaseWebSocketStreaming`
- `brokers.adapters.dhan.config.EXCHANGE_MAP`

**Responsibilities:**
- Depth-200 WebSocket adapter
- Binary packet parsing (placeholder)
- Depth callback dispatch

#### `order_stream.py` (DhanOrderStream)
**Imports:**
- `brokers.adapters.base_streaming.BaseWebSocketStreaming`
- `brokers.domain.entities.Order`
- `brokers.adapters.dhan.mapper.map_order` (lazy import)

**Responsibilities:**
- Order update WebSocket adapter
- JSON message parsing
- Order entity mapping

#### `base_streaming.py` (BaseWebSocketStreaming)
**Imports:**
- `websocket` (websocket-client library)
- `brokers.domain.entities.Quote`
- `brokers.ports.streaming.StreamingPort`

**Responsibilities:**
- Base class for WebSocket streaming
- Connection management
- Subscription tracking
- Reconnection logic

---

## 2. External Dependencies (Third-party Libraries)

### Archive External Dependencies

| Library | Version | Used By | Purpose |
|---------|---------|---------|---------|
| `websockets` | 11.0+ | `BinaryDepthFeed` | Async WebSocket client for depth feeds |
| `websocket-client` | 1.6+ | `DhanMarketFeed` (via SDK) | Sync WebSocket client (SDK uses internally) |
| `dhan-trading` SDK | Latest | `DhanMarketFeed` | Dhan SDK for market feed |
| `asyncio` | stdlib | `BinaryDepthFeed` | Async event loop for websockets |
| `threading` | stdlib | All WebSocket feeds | Daemon threads for WebSocket loops |
| `struct` | stdlib | `BinaryDepthFeed` | Binary packet parsing |
| `json` | stdlib | All feeds | JSON message construction/parsing |
| `fcntl` | stdlib (Unix) | `MarketFeedConnectionAdmission` | File-based locking for admission control |
| `decimal` | stdlib | All market data | Precision decimal arithmetic |
| `logging` | stdlib | All modules | Structured logging |
| `time` | stdlib | Reconnection logic | Sleep and backoff |
| `datetime` | stdlib | Timestamps | UTC timestamps |
| `collections.abc` | stdlib | Type hints | Callable type |
| `typing` | stdlib | Type hints | Any, Dict, Tuple, etc. |

### Greenfield External Dependencies

| Library | Version | Used By | Purpose |
|---------|---------|---------|---------|
| `websocket-client` | 1.6+ | `BaseWebSocketStreaming` | Sync WebSocket client |
| `threading` | stdlib | All WebSocket feeds | Daemon threads for WebSocket loops |
| `struct` | stdlib | `DhanDepth20Stream`, `DhanDepth200Stream` | Binary packet parsing (placeholder) |
| `json` | stdlib | All feeds | JSON message construction/parsing |
| `decimal` | stdlib | All market data | Precision decimal arithmetic |
| `logging` | stdlib | All modules | Structured logging |
| `time` | stdlib | Reconnection logic | Sleep and backoff |
| `typing` | stdlib | Type hints | Callable, Any, Dict, etc. |

### Comparison: External Dependencies

| Aspect | Archive | Greenfield | Gap? |
|--------|---------|------------|------|
| **Async WebSocket** | `websockets` (asyncio) | Not used | Yes (depth feeds) |
| **Sync WebSocket** | `websocket-client` (via SDK) | `websocket-client` | No |
| **Dhan SDK** | Yes | No | Yes (market feed) |
| **File Locking** | `fcntl` (admission control) | No | Yes |
| **Binary Parsing** | Full implementation | Placeholder | Yes |

---

## 3. Cross-Phase Dependencies

### Phase 0: Foundation (Config, Logging, Exceptions)

**Archive Dependencies:**
- `config.endpoints.Dhan` — WebSocket URLs, REST endpoints
- `infrastructure.logging_config` — Logging configuration
- `domain.exceptions` — Domain exceptions

**Greenfield Dependencies:**
- `brokers.adapters.dhan.config` — WebSocket URLs, REST endpoints, exchange maps
- `brokers.infrastructure.observability.logging` — Logging configuration
- `brokers.domain.exceptions` — Domain exceptions

**Status:** ✅ Both phases have config and logging

### Phase 1: Authentication (Token Refresh, Session Management)

**Archive Dependencies:**
- `brokers.dhan.connection_token_manager.ConnectionTokenManager` — Token broadcast
- `brokers.dhan.connection_lifecycle.ConnectionLifecycle` — Token refresh hooks
- `brokers.common.auth.AuthManager` — Auth orchestration

**Greenfield Dependencies:**
- None (token refresh not yet implemented)

**Status:** ❌ Greenfield missing token refresh integration

**Impact:**
- WebSocket feeds cannot update tokens without reconnection
- Token expiration will break long-running streams

### Phase 2: Instruments (Symbol Resolution, Instrument Loading)

**Archive Dependencies:**
- `brokers.dhan.resolver.SymbolResolver` — Symbol → security_id resolution
- `brokers.dhan.identity.DhanIdentityProvider` — Identity validation
- `brokers.dhan.loader.InstrumentLoader` — Instrument CSV loading
- `brokers.dhan.segments.EXCHANGE_TO_SEGMENT` — Exchange → segment mapping

**Greenfield Dependencies:**
- `brokers.adapters.dhan.identity.DhanInstrumentResolver` — Symbol → security_id resolution
- `brokers.adapters.dhan.config.EXCHANGE_MAP` — Exchange → segment mapping
- `brokers.adapters.dhan.config.CSV_EXCHANGE_TO_SEGMENT` — CSV exchange mapping

**Status:** ✅ Both phases have symbol resolution

**Difference:**
- Archive uses `DhanIdentityProvider` with assertion-based validation
- Greenfield uses `DhanInstrumentResolver` with simpler API

### Phase 3: HTTP Client (REST API, Rate Limiting, Circuit Breakers)

**Archive Dependencies:**
- `brokers.dhan.http_client.DhanHttpClient` — HTTP client with retries, rate limiting
- `brokers.common.resilience.circuit_breaker.CircuitBreaker` — Circuit breakers
- `brokers.dhan.metrics` — Prometheus metrics

**Greenfield Dependencies:**
- `brokers.adapters.dhan.http.DhanHttpClient` — HTTP client (simpler)
- `brokers.infrastructure.resilience.circuit_breaker.CircuitBreaker` — Circuit breakers

**Status:** ✅ Both phases have HTTP client

**Difference:**
- Archive HTTP client has more advanced rate limiting and metrics
- Greenfield HTTP client is simpler but functional

### Phase 4: Market Data (This Phase)

**Archive Dependencies:**
- All Phase 0-3 dependencies above
- `infrastructure.event_bus.EventBus` — Domain event publishing
- `infrastructure.lifecycle.LifecycleManager` — Service lifecycle

**Greenfield Dependencies:**
- Phase 0-3 dependencies above
- No EventBus integration
- No LifecycleManager integration

**Status:** ❌ Greenfield missing EventBus and LifecycleManager

---

## 4. Dependency Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 0: Foundation                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   config/    │  │  logging/    │  │ exceptions/  │  │  entities/   │   │
│  │  endpoints   │  │  config      │  │  domain      │  │  Quote,      │   │
│  │  .py         │  │              │  │              │  │  MarketDepth │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 1: Authentication                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   auth/      │  │   token/     │  │  session/    │  │  identity/   │   │
│  │  manager     │  │  scheduler   │  │  manager     │  │  provider    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 2: Instruments                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  resolver/   │  │   loader/    │  │  segments/   │  │  identity/   │   │
│  │  Symbol      │  │  Instrument  │  │  EXCHANGE_   │  │  Dhan        │   │
│  │  Resolver    │  │  Loader      │  │  TO_SEGMENT  │  │  Identity    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE 3: HTTP Client                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   http/      │  │  circuit/    │  │  rate/       │  │  metrics/    │   │
│  │  client      │  │  breaker     │  │  limiter     │  │  Prometheus  │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PHASE 4: Market Data (Current)                          │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        ARCHITECTURE                                  │  │
│  │                                                                      │  │
│  │  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐ │  │
│  │  │   REST API   │         │  WebSocket   │         │    Depth     │ │  │
│  │  │              │         │   Market     │         │    Feeds     │ │  │
│  │  │ MarketData   │         │   Feed       │         │              │ │  │
│  │  │ Adapter      │         │ DhanMarket   │         │ Depth20      │ │  │
│  │  │              │         │ Feed         │         │ Depth200     │ │  │
│  │  └──────────────┘         └──────────────┘         └──────────────┘ │  │
│  │         │                           │                       │        │  │
│  │         │                           │                       │        │  │
│  │         └───────────────────────────┴───────────────────────┘        │  │
│  │                                     │                                │  │
│  │                                     ▼                                │  │
│  │                      ┌──────────────────────────┐                   │  │
│  │                      │  Subscription Engine     │                   │  │
│  │                      │  (orchestration)         │                   │  │
│  │                      └──────────────────────────┘                   │  │
│  │                                     │                                │  │
│  │                                     ▼                                │  │
│  │                      ┌──────────────────────────┐                   │  │
│  │                      │  Connection Lifecycle    │                   │  │
│  │                      │  (admission, reconnect)  │                   │  │
│  │                      └──────────────────────────┘                   │  │
│  │                                     │                                │  │
│  └─────────────────────────────────────┼────────────────────────────────┘  │
│                                        │                                   │
│                                        ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      INFRASTRUCTURE                                  │  │
│  │                                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │  │
│  │  │  EventBus    │  │  Lifecycle   │  │  Admission   │  │  Metrics │ │  │
│  │  │  (domain     │  │  Manager     │  │  Control     │  │          │ │  │
│  │  │   events)    │  │  (health)    │  │  (429, lock) │  │          │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │  │
│  │                                                                      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                        │                                   │
└────────────────────────────────────────┼───────────────────────────────────┘
                                         │
                                         ▼
                              ┌──────────────────┐
                              │  External APIs   │
                              │                  │
                              │  Dhan REST API   │
                              │  Dhan WebSocket  │
                              │  Dhan SDK        │
                              └──────────────────┘
```

---

## 5. Greenfield Gap Analysis

### Missing Dependencies

#### 1. EventBus Integration
**Archive:**
```python
from infrastructure.event_bus import EventBus, DomainEvent

class DhanMarketFeed:
    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus
    
    def _publish_tick(self, quote: dict):
        self._event_bus.publish(
            DomainEvent.now("TICK", {"quote": q}, symbol=q.symbol)
        )
```

**Greenfield:** No EventBus integration

**Impact:**
- No domain event publishing for ticks or depth
- Downstream subscribers cannot react to market data events
- No correlation tracking

**Required:**
- Add `EventBus` parameter to WebSocket feed constructors
- Implement `_publish_tick()` and `_publish_depth()` methods
- Emit `TICK`, `DEPTH_20`, `DEPTH_200` events

#### 2. LifecycleManager Integration
**Archive:**
```python
from infrastructure.lifecycle import LifecycleManager, ManagedService

class DhanMarketFeed(ManagedService):
    def start(self) -> None: ...
    def stop(self, timeout_seconds: float = 5.0) -> None: ...
    def health(self) -> HealthStatus: ...

class DhanConnection:
    def __init__(self, lifecycle: LifecycleManager | None = None):
        self._lifecycle = lifecycle
        # Register feeds with lifecycle
```

**Greenfield:** No LifecycleManager integration

**Impact:**
- No graceful shutdown of WebSocket threads
- No health status reporting
- No lifecycle orchestration

**Required:**
- Implement `ManagedService` interface in WebSocket feeds
- Add `start()`, `stop()`, `health()` methods
- Integrate with `LifecycleManager` (when available)

#### 3. Admission Control
**Archive:**
```python
from brokers.dhan.connection_admission import MarketFeedConnectionAdmission

class DhanMarketFeed:
    def __init__(self, admission: MarketFeedConnectionAdmission | None = None):
        self._admission = admission or MarketFeedConnectionAdmission(client_id)
    
    def _run(self):
        if not self._admission.try_acquire():
            # Wait for lock
            pass
```

**Greenfield:** No admission control

**Impact:**
- Multiple processes can connect simultaneously (violates Dhan API limits)
- No 429 rate-limit tracking
- Connection storms possible

**Required:**
- Implement `MarketFeedConnectionAdmission` (file-based lock)
- Add 429 cooldown tracking
- Integrate admission check in WebSocket connection loop

#### 4. Token Refresh Integration
**Archive:**
```python
from brokers.dhan.connection_token_manager import ConnectionTokenManager

class DhanConnection:
    def register_token_receiver(self, receiver: Callable[[str], None]):
        return self._token_manager.register_receiver(receiver)
    
    def broadcast_token(self, new_token: str):
        return self._token_manager.broadcast(new_token)

class DhanMarketFeed:
    def update_token(self, access_token: str):
        # Close socket, reconnect with new token
        self._context.update_token(access_token)
        ws.close()  # Triggers reconnect
```

**Greenfield:** No token refresh integration

**Impact:**
- Token expiration breaks long-running streams
- No automatic reconnection on token refresh

**Required:**
- Implement `ConnectionTokenManager` (or equivalent)
- Add `update_token()` method to WebSocket feeds
- Close socket on token update to trigger reconnect

#### 5. Subscription Engine
**Archive:**
```python
from brokers.dhan.subscription_engine import SubscriptionEngine

class DhanConnection:
    def __init__(self):
        self.subscription_engine = SubscriptionEngine(self)

class SubscriptionEngine:
    def subscribe_market(self, symbol, exchange, mode, on_tick):
        # Ref-counting, callback management
        pass
```

**Greenfield:** No subscription engine

**Impact:**
- No ref-counting for shared subscriptions
- No callback orchestration
- No symbol resolution integration

**Required:**
- Implement `SubscriptionEngine` with ref-counting
- Add symbol resolution integration
- Implement batch subscription API

#### 6. Depth Feed Binary Parsing
**Archive:**
```python
class BinaryDepthFeed:
    def _parse_depth_packet(self, data, response_code, header_value):
        for i in range(self.total_slots):
            offset = 12 + (i * 16)
            price = struct.unpack_from("<d", data, offset)[0]
            quantity = struct.unpack_from("<I", data, offset + 8)[0]
            orders = struct.unpack_from("<I", data, offset + 12)[0]
            # Build DepthLevel
```

**Greenfield:** Placeholder implementation (header only)

**Impact:**
- Depth feeds non-functional
- No depth level extraction
- No depth cache

**Required:**
- Complete binary packet parsing (20 or 200 levels)
- Implement depth cache with bid/ask merge
- Add symbol registration (security_id → symbol)
- Construct `MarketDepth` entities

#### 7. Connection Pooling (Depth-200)
**Archive:**
```python
from brokers.dhan.depth_200 import Depth200ConnectionPool

pool = Depth200ConnectionPool(client_id, access_token)
feed1 = pool.get_feed(("NSE", "12345"))
feed2 = pool.get_feed(("NSE", "67890"))
```

**Greenfield:** No connection pooling

**Impact:**
- Cannot manage multiple depth-200 feeds efficiently
- No rate limiting for depth-200 connections

**Required:**
- Implement `Depth200ConnectionPool`
- Add rate limiting integration
- Implement feed lifecycle management

#### 8. Staleness Detection
**Archive:**
```python
class DhanMarketFeed:
    def __init__(self, staleness_threshold: float = 60.0):
        self._staleness_threshold = staleness_threshold
    
    def _run(self):
        if self._last_activity_age_seconds_locked() > staleness_threshold:
            # Force reconnect
            pass
```

**Greenfield:** No staleness detection

**Impact:**
- Stale connections not detected
- Silent failures possible

**Required:**
- Add `_last_message_at` tracking
- Implement staleness check in reconnection loop
- Force reconnect on stale connection

#### 9. Reconnect Backfill
**Archive:**
```python
class DhanMarketFeed:
    def __init__(self, backfill_callback: Callable | None = None):
        self._backfill_callback = backfill_callback
    
    def _on_connect(self, feed):
        if not was_connected and disconnect_time is not None:
            self._backfill_gap(disconnect_time)
    
    def _backfill_gap(self, disconnect_time):
        bars = self._backfill_callback(symbol, disconnect_time, now)
        for bar in bars:
            self._publish_tick(bar)
```

**Greenfield:** No reconnect backfill

**Impact:**
- Gap in tick data on reconnection
- Downstream strategies see missing data

**Required:**
- Add `backfill_callback` parameter to market feed
- Implement `_backfill_gap()` method
- Fetch missed bars via REST on reconnect

#### 10. Strict-mode Publishing
**Archive:**
```python
class DhanMarketFeed:
    def _publish_tick(self, quote: dict):
        ltp = quote.get("ltp")
        if ltp is None or ltp == 0:
            self._dropped_ticks += 1
            return  # Drop zero-LTP ticks
        # Publish
```

**Greenfield:** No strict-mode publishing

**Impact:**
- Malformed packets published as valid data
- Zero-LTP ticks treated as real signals

**Required:**
- Add validation before publishing ticks/depth
- Drop malformed packets (zero LTP, empty depth)
- Track published/dropped counters

---

## 6. Dependency Priority Matrix

| Dependency | Criticality | Effort | Phase |
|------------|-------------|--------|-------|
| **Depth Feed Binary Parsing** | 🔴 Critical | Medium | 4A |
| **EventBus Integration** | 🔴 Critical | Low | 4A |
| **Subscription Engine** | 🟡 High | Medium | 4B |
| **Admission Control** | 🟡 High | Medium | 4C |
| **Token Refresh Integration** | 🟡 High | Low | 4C |
| **LifecycleManager Integration** | 🟡 High | Low | 4C |
| **Staleness Detection** | 🟠 Medium | Low | 4D |
| **Reconnect Backfill** | 🟠 Medium | Medium | 4D |
| **Strict-mode Publishing** | 🟠 Medium | Low | 4D |
| **Connection Pooling (Depth-200)** | 🟢 Low | Medium | 4E |

---

## 7. Implementation Roadmap

### Phase 4A: Core Depth Feed Functionality
1. Complete binary packet parsing for depth-20 and depth-200
2. Implement depth cache with bid/ask merge logic
3. Add symbol registration (security_id → symbol mapping)
4. Construct `MarketDepth` entities from parsed data
5. Integrate EventBus for depth event publishing
6. Add depth callback dispatch

### Phase 4B: Subscription Orchestration
1. Implement `SubscriptionEngine` with ref-counting
2. Add symbol resolution integration
3. Implement batch subscription API
4. Add callback wrapping (dict → Quote entity)

### Phase 4C: Connection Management
1. Add admission control (host-wide lock or 429 tracking)
2. Integrate token refresh with WebSocket reconnection
3. Implement `ManagedService` interface (start/stop/health)
4. Integrate with `LifecycleManager`

### Phase 4D: Reliability Features
1. Add staleness detection
2. Implement reconnect backfill via REST
3. Add strict-mode validation before publishing
4. Implement telemetry counters (published/dropped)

### Phase 4E: Advanced Features
1. Implement `Depth200ConnectionPool`
2. Add rate limiting for depth-200 connections
3. Implement connection manager singleton
4. Add max reconnect guard with cooldown

---

## 8. Conclusion

The greenfield implementation has a solid foundation for basic market data operations but lacks critical dependencies present in the archive. The most significant gaps are:

1. **EventBus integration** — No domain event publishing
2. **LifecycleManager integration** — No graceful shutdown or health reporting
3. **Admission control** — No host-wide connection lock or 429 tracking
4. **Token refresh integration** — No automatic reconnection on token update
5. **Subscription engine** — No orchestration or ref-counting
6. **Depth feed binary parsing** — Placeholder implementation only

A phased approach (4A through 4E) is recommended to systematically close these gaps while maintaining backward compatibility with the greenfield API surface. Critical dependencies (EventBus, binary parsing) should be addressed first, followed by orchestration (SubscriptionEngine), connection management (admission, token refresh), and finally advanced features (pooling, staleness detection).
