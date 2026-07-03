# Phase 7 Portfolio — State Machines

## Overview

Phase 7 (Portfolio) is primarily a **read-only** phase. Unlike order management which has complex state transitions, portfolio queries retrieve current state from the broker without managing local state machines.

However, we can document:
1. **Data flow states** — the transformation from API response to domain entity
2. **Error states** — failure paths and recovery
3. **Service layer states** — aggregation and calculation flows

## Position Data Flow State Machine

### State Diagram
```
┌─────────────────┐
│   API Response  │
│   (Raw JSON)    │
└────────┬────────┘
         │
         │ DhanPortfolio.positions()
         ▼
┌─────────────────┐
│   Parse List    │
│   (Extract      │
│    data array)  │
└────────┬────────┘
         │
         │ For each item
         ▼
┌─────────────────┐
│   Map Position  │
│   (map_position)│
└────────┬────────┘
         │
         │ Normalize exchange
         ▼
┌─────────────────┐
│   Map Product   │
│   (_PRODUCT_MAP)│
└────────┬────────┘
         │
         │ Convert prices
         ▼
┌─────────────────┐
│   Build Entity  │
│   (Position     │
│    dataclass)   │
└────────┬────────┘
         │
         │ Collect all
         ▼
┌─────────────────┐
│   Return List   │
│   (list[Position])
└─────────────────┘
```

### State Transitions

| From State | To State | Trigger | Action |
|------------|----------|---------|--------|
| API Response | Parse List | `positions()` called | Extract `data` array |
| Parse List | Map Position | For each item | Call `map_position(item)` |
| Map Position | Map Product | Exchange segment found | Lookup `_PRODUCT_MAP[productType]` |
| Map Product | Build Entity | Product mapped | Convert prices with `to_decimal()` |
| Build Entity | Return List | Entity created | Append to result list |

### Error States

```
┌─────────────────┐
│   API Response  │
└────────┬────────┘
         │
         ├─> HTTP Error (4xx, 5xx)
         │       │
         │       └─> Exception raised by DhanHttpClient
         │               │
         │               └─> State: ERROR_HTTP
         │
         ├─> Invalid JSON
         │       │
         │       └─> JSON decode error
         │               │
         │               └─> State: ERROR_PARSE
         │
         ├─> Missing "data" field
         │       │
         │       └─> Return empty list
         │               │
         │               └─> State: SUCCESS_EMPTY
         │
         └─> Invalid field values
                 │
                 └─> Default values used (0, "")
                         │
                         └─> State: SUCCESS_DEFAULT
```

### Error State Descriptions

| State | Condition | Recovery |
|-------|-----------|----------|
| ERROR_HTTP | Network error, timeout, auth failure | Propagate exception to caller |
| ERROR_PARSE | Malformed JSON response | Propagate exception to caller |
| SUCCESS_EMPTY | No positions (empty account) | Return `[]` |
| SUCCESS_DEFAULT | Missing fields in response | Use default values (0, "") |

## Holding Data Flow State Machine

### State Diagram
```
┌─────────────────┐
│   API Response  │
│   (Raw JSON)    │
└────────┬────────┘
         │
         │ DhanPortfolio.holdings()
         ▼
┌─────────────────┐
│   Parse List    │
│   (Extract      │
│    data array)  │
└────────┬────────┘
         │
         │ For each item
         ▼
┌─────────────────┐
│   Map Holding   │
│   (map_holding) │
└────────┬────────┘
         │
         │ Normalize exchange
         ▼
┌─────────────────┐
│   Extract Qty   │
│   (holdingQty   │
│    or quantity) │
└────────┬────────┘
         │
         │ Extract avg price
         ▼
┌─────────────────┐
│   Extract Price │
│   (avgBuyPrice  │
│    or costPrice)│
└────────┬────────┘
         │
         │ Build entity
         ▼
┌─────────────────┐
│   Build Entity  │
│   (Holding      │
│    dataclass)   │
└────────┬────────┘
         │
         │ Collect all
         ▼
┌─────────────────┐
│   Return List   │
│   (list[Holding])
└─────────────────┘
```

### Archive vs Greenfield Differences

**Archive adds P&L calculation state:**
```
┌─────────────────┐
│   Extract P&L   │
│   (pnlValue     │
│    or calculate)│
└────────┬────────┘
         │
         ├─> If pnlValue exists: use it
         │
         ├─> If avg_price > 0 and ltp > 0:
         │       calculate: (ltp - avg_price) * qty
         │
         └─> Else: use 0
```

**Greenfield omits P&L calculation** — simpler state machine.

## Funds/Balance Data Flow State Machine

### State Diagram
```
┌─────────────────┐
│   API Response  │
│   (Raw JSON)    │
└────────┬────────┘
         │
         │ DhanPortfolio.funds()
         ▼
┌─────────────────┐
│   Validate Dict │
│   (isinstance   │
│    check)       │
└────────┬────────┘
         │
         ├─> Not a dict
         │       │
         │       └─> Return Balance(available_cash=0)
         │               │
         │               └─> State: DEFAULT_ZERO
         │
         ├─> Flat structure
         │       (contains "availabelBalance" or "sodLimit")
         │       │
         │       └─> map_balance(data)
         │               │
         │               └─> State: SUCCESS_FLAT
         │
         └─> Nested structure
                 (contains "data" array)
                 │
                 ├─> Empty array
                 │       │
                 │       └─> Return Balance(available_cash=0)
                 │               │
                 │               └─> State: DEFAULT_ZERO
                 │
                 └─> Non-empty array
                         │
                         └─> map_balance(data["data"][0])
                                 │
                                 └─> State: SUCCESS_NESTED
```

### State Descriptions

| State | Condition | Result |
|-------|-----------|--------|
| DEFAULT_ZERO | Invalid response or empty data | `Balance(available_cash=0)` |
| SUCCESS_FLAT | Direct balance object | Mapped from response dict |
| SUCCESS_NESTED | Balance in `data` array | Mapped from first element |

### Archive vs Greenfield Differences

**Archive:**
```
┌─────────────────┐
│   Validate Dict │
└────────┬────────┘
         │
         ├─> Not a dict
         │       │
         │       └─> Log warning
         │               │
         │               └─> Return Balance() (all zeros)
         │
         └─> Is dict
                 │
                 └─> Extract fields with fallbacks
                         │
                         └─> Build Balance with 5 fields
```

**Greenfield:**
```
┌─────────────────┐
│   Check Struct  │
└────────┬────────┘
         │
         ├─> Flat structure
         │       │
         │       └─> map_balance(data)
         │
         └─> Nested structure
                 │
                 └─> map_balance(data["data"][0])
```

**Key difference:** Greenfield handles both flat and nested structures; archive assumes flat structure.

## Trade Data Flow State Machine

### State Diagram
```
┌─────────────────┐
│   API Response  │
│   (Raw JSON)    │
└────────┬────────┘
         │
         │ DhanPortfolio.trades()
         ▼
┌─────────────────┐
│   Parse List    │
│   (Extract      │
│    data array)  │
└────────┬────────┘
         │
         │ For each item
         ▼
┌─────────────────┐
│   Map Trade     │
│   (map_trade)   │
└────────┬────────┘
         │
         │ Normalize exchange
         ▼
┌─────────────────┐
│   Map Side      │
│   (_SIDE_MAP)   │
└────────┬────────┘
         │
         │ Extract trade ID
         ▼
┌─────────────────┐
│   Extract IDs   │
│   (tradeId or   │
│    orderId)     │
└────────┬────────┘
         │
         │ Build entity
         ▼
┌─────────────────┐
│   Build Entity  │
│   (Trade        │
│    dataclass)   │
└────────┬────────┘
         │
         │ Collect all
         ▼
┌─────────────────┐
│   Return List   │
│   (list[Trade]) │
└─────────────────┘
```

## Service Layer State Machine

### P&L Aggregation Flow
```
┌─────────────────┐
│   User Calls    │
│   total_unreal- │
│   ized_pnl()    │
└────────┬────────┘
         │
         │ PortfolioService
         ▼
┌─────────────────┐
│   Fetch Positions│
│   (portfolio.   │
│    positions()) │
└────────┬────────┘
         │
         │ list[Position]
         ▼
┌─────────────────┐
│   Initialize    │
│   total = 0     │
└────────┬────────┘
         │
         │ For each position
         ▼
┌─────────────────┐
│   Accumulate    │
│   total +=      │
│   pos.unrealized│
│   _pnl          │
└────────┬────────┘
         │
         │ All positions processed
         ▼
┌─────────────────┐
│   Return Total  │
│   (Decimal)     │
└─────────────────┘
```

### Net Exposure Flow
```
┌─────────────────┐
│   User Calls    │
│   net_exposure()│
└────────┬────────┘
         │
         │ PortfolioService
         ▼
┌─────────────────┐
│   Fetch Positions│
└────────┬────────┘
         │
         │ list[Position]
         ▼
┌─────────────────┐
│   Initialize    │
│   total = 0     │
└────────┬────────┘
         │
         │ For each position
         ▼
┌─────────────────┐
│   Calculate     │
│   exposure =    │
│   avg_price *   │
│   abs(quantity) │
└────────┬────────┘
         │
         │ Accumulate
         ▼
┌─────────────────┐
│   total +=      │
│   exposure      │
└────────┬────────┘
         │
         │ All positions processed
         ▼
┌─────────────────┐
│   Return Total  │
│   (Decimal)     │
└─────────────────┘
```

## Failure Paths and Recovery

### HTTP Client Failures

```
┌─────────────────┐
│   HTTP Request  │
└────────┬────────┘
         │
         ├─> Connection Error
         │       │
         │       └─> Raise: ConnectionError
         │               │
         │               └─> Recovery: Retry logic (Phase 2)
         │
         ├─> Timeout
         │       │
         │       └─> Raise: TimeoutError
         │               │
         │               └─> Recovery: Retry logic (Phase 2)
         │
         ├─> 401 Unauthorized
         │       │
         │       └─> Raise: AuthenticationError
         │               │
         │               └─> Recovery: Token refresh (Phase 3)
         │
         ├─> 403 Forbidden
         │       │
         │       └─> Raise: PermissionError
         │               │
         │               └─> Recovery: Check API key permissions
         │
         ├─> 404 Not Found
         │       │
         │       └─> Raise: EndpointNotFoundError
         │               │
         │               └─> Recovery: Verify endpoint URL
         │
         ├─> 429 Rate Limit
         │       │
         │       └─> Raise: RateLimitError
         │               │
         │               └─> Recovery: Backoff and retry (Phase 2)
         │
         └─> 500 Server Error
                 │
                 └─> Raise: ServerError
                         │
                         └─> Recovery: Retry with backoff
```

### Data Parsing Failures

```
┌─────────────────┐
│   Parse JSON    │
└────────┬────────┘
         │
         ├─> Invalid JSON
         │       │
         │       └─> Raise: JSONDecodeError
         │               │
         │               └─> Recovery: Log error, propagate exception
         │
         ├─> Missing field
         │       │
         │       └─> Use default value (0, "")
         │               │
         │               └─> Recovery: Graceful degradation
         │
         ├─> Invalid field type
         │       │
         │       └─> to_decimal() handles conversion
         │               │
         │               └─> Recovery: Return 0 on failure
         │
         └─> Unknown enum value
                 │
                 └─> Use default enum (ProductType.INTRADAY)
                         │
                         └─> Recovery: Graceful degradation
```

### Service Layer Failures

```
┌─────────────────┐
│   Service Call  │
└────────┬────────┘
         │
         ├─> Port raises exception
         │       │
         │       └─> Propagate to caller
         │               │
         │               └─> Recovery: Caller handles exception
         │
         ├─> Empty position list
         │       │
         │       └─> Return Decimal("0") for aggregations
         │               │
         │               └─> Recovery: Valid result (no positions)
         │
         └─> Partial data (some fields missing)
                 │
                 └─> Calculations use default values
                         │
                         └─> Recovery: May produce inaccurate results
```

## State Machine Comparison: Archive vs Greenfield

### Position Retrieval

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| States | 5 (parse, map, normalize, build, return) | 5 (same) |
| Error states | 2 (HTTP error, parse error) | 2 (same) |
| Recovery | Inline logging | Delegated to mapper |
| Complexity | Medium (inline parsing) | Low (delegated) |

### Holding Retrieval

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| States | 7 (includes P&L calculation) | 5 (no P&L) |
| Error states | 2 | 2 |
| Recovery | Calculate P&L if missing | Use defaults |
| Complexity | High (P&L logic) | Low (simple mapping) |

### Balance Retrieval

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| States | 4 (validate, extract, build, return) | 5 (check structure, branch, map, return) |
| Error states | 3 (invalid dict, missing fields, wrong type) | 2 (invalid dict, empty data) |
| Recovery | Log warning, return empty Balance | Return Balance(available_cash=0) |
| Complexity | Medium | Medium |

## Key Observations

### 1. No Local State Management
Phase 7 does not maintain local state. All data is fetched on-demand from the broker API.

### 2. Stateless Architecture
```
User Request → Fetch from API → Transform → Return → Discard
```

No caching, no persistence, no state tracking.

### 3. Error Propagation
Most errors propagate to the caller. The portfolio layer does not implement retry logic (delegated to Phase 2 HTTP client).

### 4. Graceful Degradation
Missing fields use default values rather than raising exceptions. This ensures partial data is returned rather than complete failure.

### 5. Archive Complexity
The archive implementation has more complex state machines due to:
- Inline P&L calculation for holdings
- Richer data models with more fields
- Direct parsing logic in adapter

### 6. Greenfield Simplicity
The greenfield implementation has simpler state machines due to:
- Delegated parsing to mapper functions
- Simpler data models
- Service layer separation

## Future State Machines (Out of Scope)

### Margin Calculation (Phase 7B)
```
┌─────────────────┐
│   Validate      │
│   Request       │
└────────┬────────┘
         │
         ├─> Validation failed
         │       │
         │       └─> Raise ValueError
         │
         └─> Validation passed
                 │
                 └─> Resolve instrument
                         │
                         └─> Build payload
                                 │
                                 └─> POST /margincalculator
                                         │
                                         └─> Parse response
                                                 │
                                                 └─> Return MarginResponse
```

### Cached Portfolio (Future Enhancement)
```
┌─────────────────┐
│   User Request  │
└────────┬────────┘
         │
         ├─> Cache hit (fresh)
         │       │
         │       └─> Return cached data
         │
         └─> Cache miss (stale)
                 │
                 └─> Fetch from API
                         │
                         └─> Update cache
                                 │
                                 └─> Return fresh data
```
