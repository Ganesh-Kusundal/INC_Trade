# Greenfield Architectural Audit — `brokers/` Module

You requested a deep architectural audit of the newly implemented greenfield `brokers/` module to verify we are not introducing new smells or copying complexity from the archived code.

Here is the exhaustive analysis of the codebase built so far.

---

## PHASE 1 — Codebase Mapping

### 1. Modules and Responsibilities
- **`brokers/domain/`**: Pure data models (`entities.py`), constants (`enums.py`), and error types (`exceptions.py`). Contains absolutely no I/O or broker-specific logic.
- **`brokers/ports/`**: The interfaces (Protocols) that the system requires to operate (`BrokerGateway`, `OrderExecutionPort`, `HistoricalPort`, etc.). Defines the exact boundaries.
- **`brokers/resilience/`**: Domain-agnostic resilience primitives (`CircuitBreaker`, `RetryPolicy`, `TokenBucketRateLimiter`, `TokenManager`).
- **`brokers/services/`**: Application services (`OrderService`, `MarketDataService`) that enforce business rules and orchestrate calls to the ports.
- **`brokers/adapters/{broker}/`**: Concretions implementing the ports. They translate domain entities to broker-specific DTOs/JSON and vice versa.

### 2. Import/Dependency Graph
- `domain` ← `ports` ← `resilience` ← `services`
- `domain` ← `ports` ← `adapters/{broker}`
- **Constraint Verified**: No service imports an adapter. No adapter imports another adapter. Strict Dependency Inversion is successfully maintained.

### 3. Shared Constants & Types
- Types: `Order`, `OrderResponse`, `Side`, `OrderType`, `Decimal`.
- Configs: `ENDPOINTS`, `SIDE_MAP` (isolated within each adapter's `config.py`).
- Utilities: `brokers/utils/price.py` (for wire serialization).

---

## PHASE 2 — Shotgun Surgery Detection

### [SMELL-1] Scattered constants / magic values
**Pattern Type**: A (Scattered Constants)
**Files**: 
- `brokers/adapters/dhan/config.py`
- `brokers/adapters/dhan/identity.py`
- `brokers/adapters/upstox/config.py`
- `brokers/adapters/upstox/http.py`
- `brokers/adapters/upstox/instruments.py`
**Symbol/Value**: Base URLs (`https://api.dhan.co/v2`, `https://api.upstox.com/v2`, `eqmaster.csv`)
**Blast Radius**: 2-3 files per broker. Changing an environment (e.g. from prod to paper/sandbox) requires editing multiple files.
**Impact**: HIGH

### [SMELL-2] Duplicated logic (Resilience Wiring)
**Pattern Type**: B (Duplicated Logic)
**Files**: 
- `brokers/adapters/dhan/http.py`
- `brokers/adapters/upstox/http.py`
**Symbol/Value**: The setup of `CircuitBreaker`, `RetryPolicy`, and `TokenBucketRateLimiter` instances in the `__init__` methods.
**Blast Radius**: 2+ files. Adding a new broker (e.g., Zerodha) requires manually copy-pasting the resilience setup.
**Impact**: HIGH

### [SMELL-3] Mirrored hierarchies / Duplicated boilerplates
**Pattern Type**: B & F (Mirrored Hierarchies)
**Files**: 
- `brokers/adapters/dhan/mapper.py`
- `brokers/adapters/upstox/mapper.py`
**Symbol/Value**: The `map_order`, `map_quote`, `map_depth`, `map_position` functions. They are 80% identical, extracting keys from dicts and casting to `Decimal`.
**Blast Radius**: 2 files. Changing a domain entity requires updating all mappers manually.
**Impact**: MEDIUM

### [SMELL-4] Bypassed abstraction layers (Price Serialization)
**Pattern Type**: H (Missing abstraction layers)
**Files**: 
- `brokers/adapters/dhan/orders.py` (Lines 52-53)
**Symbol/Value**: `float(price) if price > 0 else 0`.
**Blast Radius**: 1 file per adapter.
**Impact**: MEDIUM. *Domain Knowledge*: Passing raw floats to JSON risks IEEE 754 precision issues (e.g. `100.05000000001`) which brokers reject. The abstraction `to_wire_float` was bypassed.

---

## PHASE 3 — Root Cause Classification

1. **Missing shared vocabulary layer**: Base URLs are scattered rather than provided via a unified `BrokerEnvironment` config object.
2. **Missing service layer (Infrastructure)**: The resilience wiring is duplicated because there is no `ResilientHttpClientBuilder` factory. Adapters are acting as their own dependency injection containers.
4. **Absent or inconsistent coding standards**: Inline `float()` casting slipped into the adapter instead of enforcing the usage of `brokers.utils.price.to_wire_float`.

---

## PHASE 4 — Refactoring Plan

**Task ID**: REF-1
**Root Cause**: 4 (Absent coding standards)
**Action**: Enforce `to_wire_float` usage for all JSON payloads.
**From**: Inline `float(price)` in `brokers/adapters/*/orders.py`
**To**: `from brokers.utils.price import to_wire_float`
**Touches**: `dhan/orders.py`, `upstox/orders.py`
**Test Strategy**: Code review and unit test asserting exact payload precision.
**Sequencing Note**: Do immediately.

**Task ID**: REF-2
**Root Cause**: 2 (Missing Infrastructure Factory)
**Action**: Extract the resilience setup into a shared HTTP builder.
**From**: `brokers/adapters/*/http.py` `__init__`
**To**: `brokers/resilience/http_builder.py` -> `build_resilient_session(config)`
**Touches**: All `http.py` files.
**Test Strategy**: Existing `test_resilience.py` + integration tests.
**Sequencing Note**: Can be done independently.

**Task ID**: REF-3
**Root Cause**: 1 (Missing shared vocabulary)
**Action**: Consolidate Base URLs and environments.
**From**: `config.py`, `identity.py`, `instruments.py`
**To**: A centralized `BrokerEnvironment` dataclass passed to the Gateway.
**Touches**: All adapter config and HTTP layers.
**Test Strategy**: Sandbox initialization tests.
**Sequencing Note**: Can be done independently.

---

## PHASE 5 — Structural Recommendations

1. **Proposed Directory Structure**
   - The current structure is excellent and adheres to Hexagonal Architecture. No major folder moves are needed, but we should add `brokers/config.py` to hold environment definitions (Prod vs UAT).

2. **Boundary Rules**
   - **Adapters may not construct their own resilience layers**. They must use a shared factory to ensure global limits are respected.
   - **Adapters must use Domain Entities natively**. They should never pass raw dictionaries into the core domain.

3. **Coding Standards to Enforce**
   1. All price/quantity values crossing the network boundary MUST use `brokers.utils.price.to_wire_float()`.
   2. Absolute URLs MUST NOT appear in adapter logic files (like `identity.py` or `http.py`); they belong exclusively in `config.py` or a configuration registry.
   3. Mappers MUST handle `KeyError` gracefully using `.get()` with safe defaults (currently well adhered to).

4. **Guardrails to Prevent Recurrence**
   - Implement an **Abstract Base Class for Mappers** (`BaseBrokerMapper`) that provides shared `_to_decimal` and `_extract_depth` utilities so we don't copy-paste mapping loops for new brokers.

---

**Conclusion**: The core architecture is solid, and the Dependency Inversion is working flawlessly. However, we have some minor duplication in the HTTP client setups (Resilience layer) and mapper files, plus a precision risk with inline `float()` casting. 

We can tackle REF-1 and REF-2 immediately before building out the Dhan Extensions (Super Orders, etc.) cleanly.

## PHASE 6 — Deep Architectural Diagrams & Full Execution Plan

As requested, here is the leaf-level architectural deep dive using Mermaid diagrams to visualize the class structures, components, and execution flow of the cleanly implemented `brokers/` module.

### 1. Component & Leaf-Level Hierarchy Diagram
This diagram shows the physical folder layout down to the leaf files, demonstrating strict Hexagonal Architecture boundaries.

```mermaid
graph TD
    subgraph Domain ["brokers/domain/ (Core Entities)"]
        D_Ent["entities.py (Order, Quote, Trade)"]
        D_Enum["enums.py (OrderType, Side)"]
        D_Exc["exceptions.py (BrokerError)"]
    end

    subgraph Ports ["brokers/ports/ (Interfaces)"]
        P_Auth["auth.py (AuthPort)"]
        P_Exec["order_execution.py (OrderExecutionPort)"]
        P_Mkt["market_data.py (MarketDataPort)"]
        P_Stream["streaming.py (StreamingPort)"]
        P_Gateway["broker.py (BrokerGateway)"]
    end

    subgraph Resilience ["brokers/resilience/ (Infrastructure)"]
        R_CB["circuit_breaker.py"]
        R_RL["rate_limiter.py"]
        R_TM["token_manager.py"]
        R_Retry["retry.py"]
    end

    subgraph Services ["brokers/services/ (Use Cases)"]
        S_Ord["order_service.py"]
        S_Mkt["market_data_service.py"]
        S_Port["portfolio_service.py"]
    end

    subgraph Adapters ["brokers/adapters/ (Concretions)"]
        A_Dhan["dhan/"]
        A_Upstox["upstox/"]
        A_Paper["paper/gateway.py"]
        
        subgraph Dhan Leaf Files ["dhan/"]
            D_Gate["gateway.py (DhanGateway)"]
            D_Http["http.py (DhanHttpClient)"]
            D_Ord["orders.py (DhanOrders)"]
            D_Map["mapper.py"]
            D_Inv["invariants.py"]
        end
    end

    Services --> Ports
    Adapters -.->|Implements| Ports
    D_Gate --> D_Http
    D_Gate --> D_Ord
    D_Ord --> D_Map
    D_Ord --> D_Inv
    D_Http -.->|Uses| Resilience
    Ports --> Domain
```

### 2. Class Diagram: Contract Adherence
This class diagram illustrates how the `BrokerGateway` Protocol enforces the contract on the Dhan adapter, and how services interact with the Gateway.

```mermaid
classDiagram
    class BrokerGateway {
        <<Protocol>>
        +orders: OrderExecutionPort
        +market_data: MarketDataPort
        +auth: AuthPort
        +historical: HistoricalPort
        +streaming: StreamingPort
        +close()
    }
    
    class DhanGateway {
        -client: DhanHttpClient
        -resolver: DhanInstrumentResolver
        +orders: DhanOrders
        +market_data: DhanMarketData
        +historical: DhanHistorical
        +streaming: DhanStreaming
    }
    
    class OrderExecutionPort {
        <<Protocol>>
        +place_order(...) OrderResponse
        +cancel_order(order_id) OrderResponse
    }
    
    class DhanOrders {
        -client: DhanHttpClient
        -resolver: DhanInstrumentResolver
        +place_order(...) OrderResponse
        +cancel_order(order_id) OrderResponse
    }
    
    class OrderService {
        -executor: OrderExecutionPort
        +place_order(...) OrderResponse
    }

    BrokerGateway <|.. DhanGateway : Implements
    OrderExecutionPort <|.. DhanOrders : Implements
    DhanGateway o-- DhanOrders : Composes
    OrderService --> OrderExecutionPort : Depends on Interface
```

### 3. Execution Flow Diagram: Order Placement
This sequence diagram shows the strict flow of control from the Service layer, through the Resilience layer, down to the Broker API, ensuring exact domain isolation.

```mermaid
sequenceDiagram
    participant App as Trading Strategy
    participant OS as OrderService
    participant DO as DhanOrders
    participant Inv as invariants.py
    participant HTTP as DhanHttpClient
    participant Res as Resilience (CircuitBreaker)
    participant API as Dhan API

    App->>OS: place_order(symbol="RELIANCE", side=BUY, quantity=100)
    OS->>OS: Validate core domain rules (qty > 0)
    OS->>DO: place_order(symbol="RELIANCE", ...)
    
    DO->>DO: Resolve instrument token (securityId)
    DO->>DO: Build JSON dict with to_wire_float()
    DO->>Inv: assert_valid_dhan_payload(payload)
    Inv-->>DO: ok
    
    DO->>HTTP: post("/orders", payload)
    HTTP->>Res: execute_with_circuit_breaker()
    Res->>API: HTTP POST
    API-->>Res: 200 OK (JSON)
    Res-->>HTTP: JSON data
    HTTP-->>DO: JSON data
    
    DO->>DO: map_order_response(data)
    DO-->>OS: OrderResponse(success=True)
    OS-->>App: OrderResponse
```

---

## FULL EXECUTION PLAN: Phase 3 & Beyond

As the Principal Architect, here is the immediate, prioritized execution plan to complete the Greenfield Brokers module, ensuring zero complexity bleed from the archived codebase:

### Phase 3.1: Clean Infrastructure Extraction (In Progress)
- **Action**: Extract `ResilientHttpClientBuilder` to `brokers/resilience/` and `BrokerEnvironment` to `brokers/config.py`.
- **Why**: Eliminates SMELL-1 and SMELL-2. Ensures `dhan/http.py` and `upstox/http.py` are purely concerned with headers and auth, not configuring standard rate limiters.

### Phase 3.2: Dhan Advanced Extensions (Clean TDD)
- **Target**: `SuperOrders`, `ForeverOrders`, `Margin`, `Ledger`, `Alerts`.
- **Plan**: 
  1. Define immutable domain requests/responses in `brokers/adapters/dhan/extensions/models.py`.
  2. Write `test_super_orders.py` using `_FakeHttpClient` to assert exact payload generation.
  3. Implement `SuperOrdersAdapter` ensuring it relies strictly on `assert_valid_dhan_payload` and `to_wire_float`.
  4. Expose as `@property` on `DhanGateway`.

### Phase 4: Upstox Adapter Parity
- **Target**: Upstox `historical.py`, `instruments.py`, `portfolio.py`, and `streaming.py`.
- **Plan**: 
  1. Migrate the protobuf parsing for Upstox WebSockets into an isolated parser class to prevent `streaming.py` from bloating.
  2. Implement standard `OrderExecutionPort` methods.
  
### Phase 5: Chaos Testing & Stress Validation
- **Target**: Validate the `CircuitBreaker` and `TokenBucketRateLimiter` under concurrent load.
- **Plan**: Run a locust/pytest-asyncio stress test simulating 500 concurrent order placements against the `DhanGateway` (using a mock HTTP client that randomly raises 429s and 500s) to prove the resilience layer guarantees stability without crashing the main thread.
