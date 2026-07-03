# Phase 7 Portfolio — Dependency Graph

## Internal Dependencies

### Greenfield Architecture Layers
```
┌─────────────────────────────────────────────────────────┐
│                    User Code / Application               │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│              Service Layer (PortfolioService)            │
│  - Aggregates P&L                                       │
│  - Calculates net exposure                              │
│  - Provides convenience methods                         │
└────────────────┬────────────────────────────────────────┘
                 │
                 │ depends on
                 ▼
┌─────────────────────────────────────────────────────────┐
│              Port Layer (PortfolioPort)                  │
│  - Protocol interface                                   │
│  - Defines contract: positions(), holdings(),           │
│    funds(), trades()                                    │
└────────────────┬────────────────────────────────────────┘
                 │
                 │ implemented by
                 ▼
┌─────────────────────────────────────────────────────────┐
│           Adapter Layer (DhanPortfolio)                  │
│  - Implements PortfolioPort                             │
│  - Calls DhanHttpClient                                 │
│  - Delegates to mapper functions                        │
└────────────────┬────────────────────────────────────────┘
                 │
                 │ uses
                 ▼
┌─────────────────────────────────────────────────────────┐
│              Mapper Layer (mapper.py)                    │
│  - map_position()                                       │
│  - map_holding()                                        │
│  - map_balance()                                        │
│  - map_trade()                                          │
│  - _normalize_exchange()                                │
└────────────────┬────────────────────────────────────────┘
                 │
                 │ produces
                 ▼
┌─────────────────────────────────────────────────────────┐
│           Domain Layer (entities.py, enums.py)           │
│  - Position, Holding, Balance, Trade                    │
│  - ProductType, Side, OrderStatus                       │
└─────────────────────────────────────────────────────────┘
```

## Component Dependency Matrix

### PortfolioService
```
PortfolioService
    ├─> PortfolioPort (interface)
    │       │
    │       └─> Implemented by: DhanPortfolio
    │
    └─> Domain Entities
            ├─> Position
            ├─> Holding
            ├─> Balance
            └─> Trade
```

### DhanPortfolio
```
DhanPortfolio
    ├─> DhanHttpClient (Phase 2)
    │       │
    │       └─> HTTP GET requests
    │
    ├─> ENDPOINTS config (Phase 2)
    │       │
    │       └─> Endpoint URLs
    │
    ├─> Mapper functions (Phase 7)
    │       ├─> map_position
    │       ├─> map_holding
    │       ├─> map_balance
    │       └─> map_trade
    │
    └─> Domain Entities (Phase 0)
            ├─> Position
            ├─> Holding
            ├─> Balance
            └─> Trade
```

### Mapper Functions
```
map_position, map_holding, map_balance, map_trade
    ├─> Domain Entities (Phase 0)
    │       ├─> Position
    │       ├─> Holding
    │       ├─> Balance
    │       └─> Trade
    │
    ├─> Domain Enums (Phase 0)
    │       ├─> ProductType
    │       └─> Side
    │
    └─> Price utilities (Phase 0)
            └─> to_decimal()
```

## Cross-Phase Dependencies

### Phase 0: Foundation
```
Phase 0 (Foundation)
    │
    ├─> Domain Entities
    │       ├─> Position
    │       ├─> Holding
    │       ├─> Balance
    │       └─> Trade
    │
    ├─> Domain Enums
    │       ├─> ProductType
    │       ├─> Side
    │       └─> OrderStatus
    │
    └─> Utilities
            └─> to_decimal()
```

### Phase 2: HTTP Client
```
Phase 2 (HTTP Client)
    │
    ├─> DhanHttpClient
    │       │
    │       └─> Used by DhanPortfolio
    │
    └─> ENDPOINTS configuration
            │
            └─> Used by DhanPortfolio
```

### Phase 3: Authentication
```
Phase 3 (Authentication)
    │
    └─> Token management
            │
            └─> Used by DhanHttpClient (indirect)
```

### Phase 4: Order Management
```
Phase 4 (Order Management)
    │
    └─> Mapper functions
            │
            └─> map_order(), map_order_response()
                    │
                    └─> Shared with Phase 7 mapper
```

### Phase 5: Market Data
```
Phase 5 (Market Data)
    │
    └─> Mapper functions
            │
            └─> map_quote(), map_depth()
                    │
                    └─> Shared with Phase 7 mapper
```

## Dependency Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                         User Code                             │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│              PortfolioService (Phase 7)                       │
│  - total_unrealized_pnl()                                     │
│  - total_realized_pnl()                                       │
│  - net_exposure()                                             │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ depends on
                     ▼
┌──────────────────────────────────────────────────────────────┐
│              PortfolioPort (Phase 7)                          │
│  - positions() → list[Position]                               │
│  - holdings() → list[Holding]                                 │
│  - funds() → Balance                                          │
│  - trades() → list[Trade]                                     │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ implemented by
                     ▼
┌──────────────────────────────────────────────────────────────┐
│              DhanPortfolio (Phase 7)                          │
│  - Uses DhanHttpClient                                        │
│  - Uses ENDPOINTS config                                      │
│  - Delegates to mapper                                        │
└────────┬───────────────┬────────────────┬────────────────────┘
         │               │                │
         │               │                │
         ▼               ▼                ▼
┌─────────────────┐  ┌──────────┐  ┌──────────────────────────┐
│ DhanHttpClient  │  │ ENDPOINTS│  │ mapper.py (Phase 7)      │
│ (Phase 2)       │  │ (Phase 2)│  │ - map_position           │
└────────┬────────┘  └──────────┘  │ - map_holding            │
         │                         │ - map_balance            │
         │                         │ - map_trade              │
         │                         └────────┬─────────────────┘
         │                                  │
         │                                  │ produces
         │                                  ▼
         │                         ┌──────────────────────────┐
         │                         │ Domain Entities (Phase 0)│
         │                         │ - Position               │
         │                         │ - Holding                │
         │                         │ - Balance                │
         │                         │ - Trade                  │
         │                         └──────────────────────────┘
         │
         │ uses
         ▼
┌──────────────────────────────────────────────────────────────┐
│              Token Manager (Phase 3)                          │
│  - Provides auth headers                                      │
└──────────────────────────────────────────────────────────────┘
```

## Archive Dependencies

### PortfolioAdapter (Archive)
```
PortfolioAdapter (Archive)
    ├─> DhanHttpClient (archive)
    │       │
    │       └─> HTTP GET requests
    │
    ├─> DhanIdentityProvider (archive)
    │       │
    │       ├─> coerce_identity_provider()
    │       └─> resolver
    │               │
    │               └─> segment_to_exchange()
    │
    ├─> Domain entities (archive)
    │       ├─> Balance
    │       ├─> Holding
    │       ├─> Position
    │       └─> ProductType
    │
    └─> Inline parsing logic
            └─> _parse_product()
```

### MarginAdapter (Archive)
```
MarginAdapter (Archive)
    ├─> DhanHttpClient (archive)
    │       │
    │       └─> HTTP POST requests
    │
    ├─> DhanIdentityProvider (archive)
    │       │
    │       ├─> coerce_identity_provider()
    │       └─> resolve_ref()
    │               │
    │               └─> security_id_str()
    │
    ├─> Domain models (archive)
    │       ├─> MarginRequest
    │       └─> MarginResponse
    │
    ├─> Invariants (archive)
    │       │
    │       └─> assert_dhan_payload()
    │
    └─> Price utilities (archive)
            └─> to_wire_float()
```

## Greenfield Gap Analysis

### Missing in Greenfield

#### 1. Margin Calculation
```
Archive:
    ├─> MarginAdapter
    ├─> MarginRequest
    ├─> MarginResponse
    └─> /margincalculator endpoint

Greenfield:
    └─> NOT IMPLEMENTED
```

**Impact**: Cannot pre-calculate order margins before submission.

**Recommendation**: Implement as separate port:
```python
class MarginPort(Protocol):
    def calculate(self, request: MarginRequest) -> MarginResponse: ...
```

#### 2. Rich Position Data
```
Archive Position:
    ├─> ltp (last traded price)
    └─> All P&L fields

Greenfield Position:
    └─> No ltp field
```

**Impact**: Cannot display real-time P&L without separate market data subscription.

**Recommendation**: Add `ltp` field to Position entity.

#### 3. Rich Holding Data
```
Archive Holding:
    ├─> available_quantity
    ├─> ltp
    └─> pnl (calculated)

Greenfield Holding:
    ├─> isin (new)
    └─> t1_quantity (new)
```

**Impact**: Cannot determine available quantity for trading; no P&L calculation.

**Recommendation**: Add `available_quantity` and `ltp` fields to Holding entity.

#### 4. Rich Balance Data
```
Archive Balance:
    ├─> available_balance
    ├─> sod_limit
    ├─> collateral_amount
    ├─> utilized_amount
    └─> withdrawable_balance

Greenfield Balance:
    ├─> available_cash
    ├─> utilized_margin
    └─> total_margin
```

**Impact**: Missing SOD limit, collateral, and withdrawable balance information.

**Recommendation**: Expand Balance entity with additional fields.

#### 5. Identity Provider Integration
```
Archive:
    └─> DhanIdentityProvider
            ├─> Instrument resolution
            └─> Segment mapping

Greenfield:
    └─> No identity provider in portfolio adapter
```

**Impact**: Portfolio adapter cannot resolve instrument details (security_id, etc.).

**Recommendation**: Not needed for read-only portfolio queries, but required for margin calculation.

### Improvements in Greenfield

#### 1. Separation of Concerns
```
Archive:
    └─> PortfolioAdapter
            ├─> HTTP calls
            ├─> Parsing logic
            └─> Business logic

Greenfield:
    ├─> PortfolioPort (interface)
    ├─> DhanPortfolio (adapter)
    ├─> PortfolioService (service)
    └─> mapper.py (parsing)
```

**Benefit**: Each layer has single responsibility; easier to test and maintain.

#### 2. Port-Adapter Pattern
```
Greenfield:
    ├─> PortfolioPort (Protocol)
    │       └─> Broker-agnostic interface
    │
    └─> DhanPortfolio
            └─> Dhan-specific implementation
```

**Benefit**: Can implement adapters for other brokers (Upstox, Paper) without changing service layer.

#### 3. Centralized Mapper
```
Archive:
    ├─> Inline parsing in PortfolioAdapter
    └─> Inline parsing in MarginAdapter

Greenfield:
    └─> mapper.py
            ├─> map_position()
            ├─> map_holding()
            ├─> map_balance()
            ├─> map_trade()
            ├─> map_order() (Phase 4)
            └─> map_quote() (Phase 5)
```

**Benefit**: Single source of truth for DTO → domain mapping; reduces duplication.

#### 4. Service Layer Aggregation
```
Greenfield PortfolioService:
    ├─> total_unrealized_pnl()
    ├─> total_realized_pnl()
    └─> net_exposure()
```

**Benefit**: Common calculations provided out-of-the-box; archive requires user code to implement.

#### 5. Trade Retrieval
```
Archive:
    └─> No trade retrieval in PortfolioAdapter

Greenfield:
    └─> DhanPortfolio.trades()
```

**Benefit**: Complete portfolio view includes trade history.

## Dependency Risk Assessment

### Low Risk
- Domain entities (Phase 0) — stable foundation
- HTTP client (Phase 2) — well-tested
- Mapper functions — pure functions, easy to test

### Medium Risk
- Endpoint configuration — changes if Dhan API version changes
- Field mapping — Dhan API field names may change

### High Risk
- Margin calculation (missing) — critical for pre-order validation
- Rich position/holding data — affects UI/UX

## Migration Path

### Phase 7A: Portfolio Queries (Current)
- Positions, holdings, funds, trades
- Service layer aggregation

### Phase 7B: Margin Calculation (Future)
- MarginPort interface
- DhanMargin adapter
- MarginRequest/MarginResponse entities

### Phase 7C: Enhanced Data Models (Future)
- Add ltp to Position and Holding
- Add available_quantity to Holding
- Expand Balance with additional fields
