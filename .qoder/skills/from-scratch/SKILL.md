---
name: from-scratch
description: First-principles system design using Karpathy's "build from scratch" philosophy. Decomposes a domain into essential concepts (5-7), builds a minimal viable model with zero framework dependencies, identifies seams where the model touches the outside world, defines port interfaces, and validates testability. Use when designing new subsystems, evaluating architecture proposals, or when asked "how would you build this from scratch?" Invokes the from-scratch-architect agent.
mode: agent
agent: from-scratch-architect
---

# From Scratch — First-Principles System Design

Design systems from essential concepts outward, not from frameworks inward.

## Philosophy (Karpathy)

> **"You don't really understand something until you can build it from scratch."** — Andrej Karpathy

Your first implementation should be the minimal thing that could work. Not the most flexible, not the most scalable, not the most production-ready. Just the most *essential*. Frameworks, databases, and APIs come later — they are details, not decisions.

## When to Use

| Scenario | Why From-Scratch? |
|----------|-------------------|
| Designing a new subsystem | Avoid choosing a framework before understanding the problem |
| Evaluating an existing design | Validate that the core domain is framework-independent |
| Adding a new broker adapter | Understand the essential order/trade lifecycle before wiring |
| Reviewing architecture proposals | Check if seam placement is correct |
| Onboarding to a new domain | Build mental model from first principles |
| Debugging a complex issue | Strip away abstractions to find the root concept |

## Process

### Step 1: List ALL Concepts

Brain dump every concept in the domain. Don't filter yet.

```
Examples for an order management system:
Order, Trade, Position, Portfolio, OrderBook, Fill, Cancel, Reject,
PartialFill, MarketOrder, LimitOrder, StopLoss, BracketOrder, GTT,
OrderStatus, Side, ProductType, Validity, Broker, Exchange, Segment,
Margin, Holding, Balance, PnL, Commission, Slippage, ...
```

### Step 2: Identify the Core 5-7

For each concept, ask: *"If this didn't exist, would the system still work?"*

```
ESSENTIAL (system doesn't work without):
- Order: represents intent to trade
- Trade: represents executed fill
- Position: aggregated exposure
- Side: buy or sell direction
- Status: lifecycle of an order

SUPPORTING (makes the system better but isn't required):
- BracketOrder: convenient wrapper for multiple orders
- GTT: scheduled execution
- Margin: risk constraint
- Commission: cost tracking
- Slippage: execution quality metric
```

### Step 3: Build the Minimal Model

Write pure Python (no frameworks, no I/O, no imports beyond stdlib):

```python
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
from datetime import datetime

class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

@dataclass
class Order:
    order_id: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    status: OrderStatus
    created_at: datetime
    filled_quantity: int = 0
    avg_fill_price: Decimal = Decimal("0")

@dataclass
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    executed_at: datetime
```

### Step 4: Find the Seams

Where does the model touch the outside world?

```
Seam 1: Persistence — Orders must survive restarts
Seam 2: Market Data — Need prices to place orders
Seam 3: Execution — Need to send orders to an exchange
Seam 4: Notification — Need to know when orders fill
```

### Step 5: Define Interfaces at Seams

```python
from typing import Protocol

class OrderStore(Protocol):
    def save(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Order | None: ...

class PriceFeed(Protocol):
    def get_ltp(self, symbol: str) -> Decimal: ...

class OrderExecutor(Protocol):
    def submit(self, order: Order) -> Order: ...
    def cancel(self, order_id: str) -> bool: ...
```

### Step 6: Validate Testability

```
Can I test the entire order lifecycle without:
- A real database? ✅ (use InMemoryOrderStore)
- A real broker? ✅ (use MockPriceFeed + MockExecutor)
- A real event bus? ✅ (use callback collector)

Can I write:
- Unit test: create order, verify state? ✅
- Unit test: fill order, verify position? ✅
- Integration test: order → store → retrieve? ✅ (in-memory)
```

## Output Format

```markdown
## From-Scratch Design: [System Name]

### Core Concepts (Essential)
1. [Concept 1] — why it must exist
2. [Concept 2] — why it must exist
...

### Minimal Model
```python
[Pure Python — no frameworks, no I/O]
```

### Seams
| Seam | Interface | Production Adapter | Test Adapter |
|------|-----------|-------------------|--------------|
| [name] | Protocol | [real impl] | [test impl] |

### Testability
- Core model testable without infrastructure? ✅
- All seams have test double? ✅
```

## Constraints

- NO framework imports in the core model
- NO database, network, or filesystem in the core model
- NO external package dependencies in the core model
- MAX 5-7 core concepts — everything else is supporting
- Interfaces (Protocols) belong in the domain, not in infrastructure
- Production adapters come AFTER the model is validated
- The model must be testable without ANY infrastructure
