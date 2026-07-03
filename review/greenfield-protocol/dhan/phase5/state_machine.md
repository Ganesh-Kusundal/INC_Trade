# Phase 5: Order Management — State Machine Documentation

## 1. Order Lifecycle State Machine

### 1.1 Canonical Order States

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ORDER LIFECYCLE STATE MACHINE                     │
└─────────────────────────────────────────────────────────────────────┘

                         ┌──────────┐
                         │ PENDING  │
                         └────┬─────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │   OPEN   │    │ REJECTED │    │CANCELLED │
        └────┬─────┘    └──────────┘    └──────────┘
             │
     ┌───────┼───────┬───────────┐
     │       │       │           │
     ▼       ▼       ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ PARTIAL  │ │  FILLED  │ │CANCELLED │ │ EXPIRED  │
│  _FILLED │ └──────────┘ └──────────┘ └──────────┘
└────┬─────┘
     │
     ├───────────────┐
     │               │
     ▼               ▼
┌──────────┐    ┌──────────┐
│  FILLED  │    │CANCELLED │
└──────────┘    └──────────┘
```

### 1.2 State Transition Table

| From State | To State | Trigger | Description |
|------------|----------|---------|-------------|
| PENDING | OPEN | Order accepted by exchange | Order is now live in the market |
| PENDING | REJECTED | Validation/broker rejection | Order failed pre-trade checks |
| PENDING | CANCELLED | User cancellation | Order cancelled before reaching exchange |
| PENDING | EXPIRED | Validity period ended | DAY/IOC order not accepted in time |
| OPEN | PARTIALLY_FILLED | Partial execution | Some quantity filled |
| OPEN | FILLED | Full execution | Entire quantity filled |
| OPEN | CANCELLED | User cancellation | Active order cancelled |
| OPEN | PARTIALLY_CANCELLED | Partial fill + cancel | Some quantity filled, rest cancelled |
| OPEN | EXPIRED | Validity period ended | Order not executed within validity |
| OPEN | REJECTED | Late rejection | Exchange rejected after acceptance |
| PARTIALLY_FILLED | FILLED | Remaining quantity filled | Order fully executed |
| PARTIALLY_FILLED | CANCELLED | User cancellation | Remaining quantity cancelled |
| PARTIALLY_FILLED | PARTIALLY_CANCELLED | Partial cancel | Some filled, some cancelled |
| PARTIALLY_CANCELLED | CANCELLED | Final cancellation | All remaining quantity cancelled |

### 1.3 Terminal States

```python
TERMINAL_STATES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.PARTIALLY_CANCELLED,
    OrderStatus.EXPIRED,
    OrderStatus.REJECTED,
}
```

**Properties:**
- No outgoing transitions from terminal states
- Order is considered "closed" once in terminal state
- Immutable: cannot be modified or cancelled again

### 1.4 Active States

```python
ACTIVE_STATES = {
    OrderStatus.PENDING,
    OrderStatus.OPEN,
    OrderStatus.PARTIALLY_FILLED,
}
```

**Properties:**
- Order can be modified or cancelled
- Order is working in the market
- Quantity may be partially filled

## 2. Bracket Order State Machine (Super Orders)

### 2.1 Bracket Order Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                  BRACKET ORDER STATE MACHINE                         │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │   ENTRY_LEG      │
                    │  (Entry Order)   │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
        ┌──────────┐                  ┌──────────┐
        │ REJECTED │                  │  FILLED  │
        └──────────┘                  └────┬─────┘
                                           │
                    ┌──────────────────────┤
                    │                      │
                    ▼                      ▼
        ┌──────────────────┐    ┌──────────────────┐
        │   TARGET_LEG     │    │  STOP_LOSS_LEG   │
        │ (Target Order)   │    │  (SL Order)      │
        └────────┬─────────┘    └────────┬─────────┘
                 │                       │
                 ▼                       ▼
           ┌──────────┐            ┌──────────┐
           │  FILLED  │            │  FILLED  │
           └────┬─────┘            └────┬─────┘
                │                       │
                └───────────┬───────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │    CLOSED    │
                    │ (Both legs   │
                    │  executed)   │
                    └──────────────┘
```

### 2.2 Bracket Order States

| State | Description | Active Legs |
|-------|-------------|-------------|
| ENTRY | Entry order placed | Entry leg pending |
| LEG1 | Entry filled, Target/SL active | Target + SL legs |
| LEG2 | Target or SL triggered | One leg remaining |
| LEG3 | Both legs executed | None |
| CLOSED | All legs complete | None |

### 2.3 Bracket Order Transitions

```python
BRACKET_ORDER_TRANSITIONS = {
    "ENTRY": ["LEG1", "REJECTED"],
    "LEG1": ["LEG2", "LEG3", "CLOSED"],
    "LEG2": ["LEG3", "CLOSED"],
    "LEG3": ["CLOSED"],
    "CLOSED": [],  # Terminal
    "REJECTED": [],  # Terminal
}
```

### 2.4 Bracket Order Validation Rules

**Entry Validation:**
- For BUY: `target_price > entry_price > stop_loss_price`
- For SELL: `target_price < entry_price < stop_loss_price`
- All prices must be positive
- Trailing jump must be non-negative

**Leg Modification:**
- Can modify individual legs (ENTRY_LEG, TARGET_LEG, STOP_LOSS_LEG)
- Cannot modify after leg is FILLED
- Price/quantity changes must pass validation

## 3. GTT Order State Machine (Forever Orders)

### 3.1 GTT Order Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GTT ORDER STATE MACHINE                           │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │    CREATED       │
                    │  (GTT Placed)    │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
        ┌──────────┐                  ┌──────────┐
        │TRIGGERED │                  │ CANCELLED│
        └────┬─────┘                  └──────────┘
             │
     ┌───────┴───────┐
     │               │
     ▼               ▼
┌──────────┐    ┌──────────┐
│ EXECUTED │    │ EXPIRED  │
└──────────┘    └──────────┘
```

### 3.2 GTT Order States

| State | Description | Modifiable |
|-------|-------------|------------|
| CREATED | GTT order placed, waiting for trigger | Yes |
| TRIGGERED | Trigger condition met, order placed | No |
| EXECUTED | Triggered order fully executed | No |
| EXPIRED | GTT validity period ended | No |
| CANCELLED | User cancelled GTT | No |

### 3.3 GTT Order Types

**SINGLE Mode:**
- One trigger condition
- One order placed on trigger
- Fields: `price`, `trigger_price`, `quantity`

**OCO (One Cancels Other) Mode:**
- Two trigger conditions
- When one triggers, the other is cancelled
- Fields: `price`, `trigger_price`, `quantity` + `price1`, `trigger_price1`, `quantity1`

### 3.4 GTT Validation Rules

```python
def validate_gtt_order(request):
    errors = []
    
    # Order flag validation
    if request.order_flag not in ("SINGLE", "OCO"):
        errors.append(f"Invalid order_flag: {request.order_flag}")
    
    # OCO requires additional fields
    if request.order_flag == "OCO":
        if request.price1 is None:
            errors.append("OCO requires price1")
        if request.trigger_price1 is None:
            errors.append("OCO requires trigger_price1")
        if request.quantity1 is None:
            errors.append("OCO requires quantity1")
    
    # Price validation
    if request.price <= 0:
        errors.append("Price must be positive")
    if request.trigger_price <= 0:
        errors.append("Trigger price must be positive")
    if request.quantity <= 0:
        errors.append("Quantity must be positive")
    
    return errors
```

## 4. Order Modification State Machine

### 4.1 Modification Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                  ORDER MODIFICATION STATE MACHINE                    │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │  ACTIVE_ORDER    │
                    │ (OPEN/PARTIAL)   │
                    └────────┬─────────┘
                             │
                             │ modify_order()
                             ▼
                    ┌──────────────────┐
                    │  MODIFICATION    │
                    │   REQUESTED      │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
        ┌──────────┐                  ┌──────────┐
        │ MODIFIED │                  │ REJECTED │
        └────┬─────┘                  └──────────┘
             │
             ▼
    ┌──────────────────┐
    │ UPDATED_ORDER    │
    │ (new state)      │
    └──────────────────┘
```

### 4.2 Modifiable Fields

| Field | Modifiable | Constraints |
|-------|------------|-------------|
| quantity | Yes | Must be ≥ filled_quantity |
| price | Yes | Must be tick-aligned |
| order_type | Yes | MARKET ↔ LIMIT |
| validity | Yes | DAY ↔ IOC |
| trigger_price | Yes | For STOP orders only |

### 4.3 Modification Validation

```python
def validate_modification(order, changes):
    errors = []
    
    # Quantity check
    if "quantity" in changes:
        if changes["quantity"] < order.filled_quantity:
            errors.append("Cannot reduce quantity below filled quantity")
    
    # Price check
    if "price" in changes:
        if not is_tick_aligned(changes["price"], tick_size):
            errors.append("Price not tick-aligned")
    
    # Order type check
    if "order_type" in changes:
        if changes["order_type"] not in (OrderType.MARKET, OrderType.LIMIT):
            errors.append("Can only switch between MARKET and LIMIT")
    
    return errors
```

## 5. Order Cancellation State Machine

### 5.1 Cancellation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                  ORDER CANCELLATION STATE MACHINE                    │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │  ACTIVE_ORDER    │
                    │ (OPEN/PARTIAL)   │
                    └────────┬─────────┘
                             │
                             │ cancel_order()
                             ▼
                    ┌──────────────────┐
                    │ CANCELLATION     │
                    │   REQUESTED      │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
        ┌──────────┐                  ┌──────────┐
        │CANCELLED │                  │  FAILED  │
        └──────────┘                  └──────────┘
```

### 5.2 Cancellation Rules

**Cancellable States:**
- PENDING (before reaching exchange)
- OPEN (active in market)
- PARTIALLY_FILLED (remaining quantity)

**Non-Cancellable States:**
- FILLED (already executed)
- CANCELLED (already cancelled)
- REJECTED (already rejected)
- EXPIRED (already expired)

### 5.3 Post-Cancel Race Condition

```python
def cancel_order(order_id):
    # Send cancel request
    response = client.delete(f"/orders/{order_id}")
    
    # Check if order was already filled
    existing = get_order(order_id)
    if existing and existing.status == OrderStatus.FILLED:
        return OrderResponse(
            success=False,
            message="Order was already FILLED (post-cancel race)",
            error_code="ORDER_ALREADY_FILLED"
        )
    
    return OrderResponse(success=True)
```

## 6. Failure Paths and Transitions

### 6.1 Network Failures

```
┌─────────────────────────────────────────────────────────────────────┐
│                      NETWORK FAILURE PATHS                           │
└─────────────────────────────────────────────────────────────────────┘

place_order()
    │
    ├─► NetworkError ──► Retry (idempotent)
    │
    ├─► Timeout ──► Check order book
    │               │
    │               ├─► Order exists ──► Return order_id
    │               │
    │               └─► Order not found ──► Retry or fail
    │
    └─► ConnectionReset ──► Retry with backoff

cancel_order()
    │
    ├─► NetworkError ──► Verify order status
    │                    │
    │                    ├─► Already cancelled ──► Success
    │                    │
    │                    └─► Still active ──► Retry
    │
    └─► Timeout ──► Assume success, verify later

modify_order()
    │
    ├─► NetworkError ──► Verify order state
    │                    │
    │                    ├─► Already modified ──► Success
    │                    │
    │                    └─► Not modified ──► Retry
    │
    └─► Timeout ──► Verify and retry
```

### 6.2 Validation Failures

```
┌─────────────────────────────────────────────────────────────────────┐
│                     VALIDATION FAILURE PATHS                         │
└─────────────────────────────────────────────────────────────────────┘

Pre-Trade Validation:
    │
    ├─► Invalid symbol ──► OrderRejectedError
    │
    ├─► Invalid quantity ──► OrderRejectedError
    │
    ├─► Invalid price ──► OrderRejectedError
    │
    ├─► Lot size violation ──► OrderRejectedError
    │
    ├─► Tick size violation ──► OrderRejectedError
    │
    └─► Product/segment mismatch ──► OrderRejectedError

Broker Validation:
    │
    ├─► Insufficient margin ──► OrderStatus.REJECTED
    │
    ├─► Invalid order type ──► OrderStatus.REJECTED
    │
    └─► Risk check failed ──► OrderStatus.REJECTED
```

### 6.3 Partial Fill Handling

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PARTIAL FILL HANDLING                             │
└─────────────────────────────────────────────────────────────────────┘

Order: BUY 100 @ 100
    │
    ├─► Fill 30 @ 100 ──► Status: PARTIALLY_FILLED
    │                     │
    │                     ├─► User cancels ──► Status: PARTIALLY_CANCELLED
    │                     │                    (30 filled, 70 cancelled)
    │                     │
    │                     └─► Fill remaining 70 @ 100 ──► Status: FILLED
    │
    └─► Fill 100 @ 100 ──► Status: FILLED
```

## 7. Greenfield vs Archive State Machine Comparison

### 7.1 Order Lifecycle

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| State machine definition | Implicit in code | Explicit `order_lifecycle.py` | ✅ Greenfield better |
| Transition validation | None | `validate_transition()` | ✅ Greenfield better |
| Terminal state detection | Manual checks | `is_terminal` property | ✅ Greenfield better |
| Active state detection | Manual checks | `is_active` property | ✅ Greenfield better |

### 7.2 Bracket Orders (Super Orders)

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| State machine | Not defined | Not implemented | ❌ Missing |
| Leg tracking | Basic parsing | Not implemented | ❌ Missing |
| Validation | Comprehensive | Not implemented | ❌ Missing |

**Status:** Greenfield lacks Super Orders entirely

### 7.3 GTT Orders (Forever Orders)

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| State machine | Not defined | Not implemented | ❌ Missing |
| SINGLE mode | Supported | Not implemented | ❌ Missing |
| OCO mode | Supported | Not implemented | ❌ Missing |
| Validation | Comprehensive | Not implemented | ❌ Missing |

**Status:** Greenfield lacks Forever Orders entirely

### 7.4 Order Modification

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| State tracking | None | None | ⚠️ Both lack |
| Validation | Basic | Basic | ⚠️ Similar |
| Post-modification verification | Fallback parsing | Direct mapping | ✅ Greenfield better |

### 7.5 Order Cancellation

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| Post-cancel race check | Yes | Yes | ✅ Both have |
| Error handling | Comprehensive | Basic | ⚠️ Archive better |
| Status verification | Yes | Yes | ✅ Both have |

### 7.6 Summary

**Greenfield Strengths:**
- Explicit state machine definition
- Transition validation
- Terminal/active state properties

**Greenfield Gaps:**
- No Super Orders (bracket orders)
- No Forever Orders (GTT/OCO)
- No conditional triggers
- Missing advanced order types

**Recommendations:**
1. Implement Super Orders adapter with state machine
2. Implement Forever Orders adapter with state machine
3. Add state machine enforcement at adapter level
4. Add state transition events for audit trail
