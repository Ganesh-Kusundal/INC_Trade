# Phase 7 Portfolio — Public Contract

## Overview

Phase 7 exposes portfolio query functionality through three layers:
1. **Port Interface** — Broker-agnostic Protocol
2. **Adapter Implementation** — Dhan-specific adapter
3. **Service Layer** — Application-level convenience methods

## Port Interface: PortfolioPort

### Location
`brokers/ports/portfolio.py`

### Interface Definition
```python
class PortfolioPort(Protocol):
    def positions(self) -> list[Position]: ...
    def holdings(self) -> list[Holding]: ...
    def funds(self) -> Balance: ...
    def trades(self) -> list[Trade]: ...
```

### Method Contracts

#### positions()
```python
def positions(self) -> list[Position]:
    """Fetch current open positions.
    
    Returns:
        list[Position]: List of open positions
        
    Raises:
        HTTPError: If API request fails
        AuthenticationError: If token is invalid/expired
        RateLimitError: If rate limit exceeded
        
    Example:
        >>> positions = portfolio.positions()
        >>> for pos in positions:
        ...     print(f"{pos.symbol}: {pos.quantity} @ {pos.average_price}")
    """
```

**Return Type:**
```python
@dataclass(frozen=True)
class Position:
    symbol: str                    # Trading symbol (e.g., "RELiance")
    exchange: str                  # Exchange (e.g., "NSE", "NFO")
    quantity: int                  # Net quantity (positive=long, negative=short)
    product_type: ProductType      # INTRADAY, DELIVERY, or MARGIN
    average_price: Decimal         # Average buy/sell price
    realized_pnl: Decimal          # Realized profit/loss
    unrealized_pnl: Decimal        # Unrealized profit/loss
```

**Guarantees:**
- Returns empty list `[]` if no positions exist
- Never returns `None`
- All Decimal values default to `Decimal("0")` if missing
- Exchange is normalized (e.g., "NSE_EQ" → "NSE")

---

#### holdings()
```python
def holdings(self) -> list[Holding]:
    """Fetch long-term holdings.
    
    Returns:
        list[Holding]: List of holdings
        
    Raises:
        HTTPError: If API request fails
        AuthenticationError: If token is invalid/expired
        RateLimitError: If rate limit exceeded
        
    Example:
        >>> holdings = portfolio.holdings()
        >>> for h in holdings:
        ...     print(f"{h.symbol}: {h.quantity} shares")
    """
```

**Return Type:**
```python
@dataclass(frozen=True)
class Holding:
    symbol: str                    # Trading symbol
    exchange: str                  # Exchange
    quantity: int                  # Total quantity
    average_price: Decimal         # Average buy price (cost basis)
    isin: str                      # ISIN code (empty if not available)
    t1_quantity: int               # T1 quantity (pending settlement)
```

**Guarantees:**
- Returns empty list `[]` if no holdings exist
- Never returns `None`
- All numeric fields default to 0 if missing
- ISIN defaults to empty string `""`

---

#### funds()
```python
def funds(self) -> Balance:
    """Fetch account balance and margin utilization.
    
    Returns:
        Balance: Account balance information
        
    Raises:
        HTTPError: If API request fails
        AuthenticationError: If token is invalid/expired
        RateLimitError: If rate limit exceeded
        
    Example:
        >>> balance = portfolio.funds()
        >>> print(f"Available: {balance.available_cash}")
    """
```

**Return Type:**
```python
@dataclass(frozen=True)
class Balance:
    available_cash: Decimal        # Available cash for trading
    utilized_margin: Decimal       # Margin currently in use
    total_margin: Decimal          # Total margin (available + utilized)
```

**Guarantees:**
- Never returns `None`
- Returns `Balance(available_cash=Decimal("0"))` on error
- All fields default to `Decimal("0")` if missing

**Notes:**
- Dhan API has typo: `availabelBalance` (not `availableBalance`)
- Mapper handles both flat and nested response structures

---

#### trades()
```python
def trades(self) -> list[Trade]:
    """Fetch trade execution history.
    
    Returns:
        list[Trade]: List of executed trades
        
    Raises:
        HTTPError: If API request fails
        AuthenticationError: If token is invalid/expired
        RateLimitError: If rate limit exceeded
        
    Example:
        >>> trades = portfolio.trades()
        >>> for t in trades:
        ...     print(f"{t.side} {t.quantity} {t.symbol} @ {t.price}")
    """
```

**Return Type:**
```python
@dataclass(frozen=True)
class Trade:
    trade_id: str                  # Unique trade identifier
    order_id: str                  # Associated order ID
    symbol: str                    # Trading symbol
    exchange: str                  # Exchange
    side: Side                     # BUY or SELL
    quantity: int                  # Traded quantity
    price: Decimal                 # Trade price
    timestamp: datetime | None     # Trade timestamp (None if not available)
```

**Guarantees:**
- Returns empty list `[]` if no trades exist
- Never returns `None`
- Trade ID falls back to order ID if not available
- Timestamp may be `None` if not provided by API

---

## Adapter Implementation: DhanPortfolio

### Location
`brokers/adapters/dhan/portfolio.py`

### Class Definition
```python
class DhanPortfolio:
    def __init__(self, client: DhanHttpClient):
        """Initialize Dhan portfolio adapter.
        
        Args:
            client: Authenticated HTTP client
            
        Example:
            >>> client = DhanHttpClient(config)
            >>> portfolio = DhanPortfolio(client)
        """
```

### Implementation Details

#### positions()
```python
def positions(self) -> list[Position]:
    data = self._client.get(ENDPOINTS["positions"])
    items = data if isinstance(data, list) else data.get("data", [])
    if isinstance(items, list):
        return [map_position(p) for p in items]
    return []
```

**Endpoint:** `GET https://api.dhan.co/v2/positions`

**Response Structure:**
```json
{
  "data": [
    {
      "tradingSymbol": "RELiance",
      "exchangeSegment": "NSE_EQ",
      "netQty": 10,
      "productType": "INTRADAY",
      "avgBuyCost": 2500.50,
      "realizedProfit": 100.00,
      "unrealizedProfit": 50.00
    }
  ]
}
```

**Field Mapping:**
| Dhan Field | Domain Field | Notes |
|------------|--------------|-------|
| `tradingSymbol` | `symbol` | Direct mapping |
| `exchangeSegment` | `exchange` | Normalized via `_normalize_exchange()` |
| `netQty` | `quantity` | Direct mapping |
| `productType` | `product_type` | Mapped via `_PRODUCT_MAP` |
| `avgBuyCost` | `average_price` | Converted via `to_decimal()` |
| `realizedProfit` | `realized_pnl` | Converted via `to_decimal()` |
| `unrealizedProfit` | `unrealized_pnl` | Converted via `to_decimal()` |

---

#### holdings()
```python
def holdings(self) -> list[Holding]:
    data = self._client.get(ENDPOINTS["holdings"])
    items = data if isinstance(data, list) else data.get("data", [])
    if isinstance(items, list):
        return [map_holding(h) for h in items]
    return []
```

**Endpoint:** `GET https://api.dhan.co/v2/holdings`

**Response Structure:**
```json
{
  "data": [
    {
      "tradingSymbol": "TCS",
      "exchangeSegment": "NSE_EQ",
      "holdingQty": 50,
      "avgBuyPrice": 3500.00,
      "isin": "INE467B01029",
      "t1Qty": 0
    }
  ]
}
```

**Field Mapping:**
| Dhan Field | Domain Field | Notes |
|------------|--------------|-------|
| `tradingSymbol` | `symbol` | Direct mapping |
| `exchangeSegment` | `exchange` | Normalized |
| `holdingQty` or `quantity` | `quantity` | Fallback chain |
| `avgBuyPrice` or `costPrice` | `average_price` | Fallback chain |
| `isin` | `isin` | Direct mapping |
| `t1Qty` | `t1_quantity` | Direct mapping |

---

#### funds()
```python
def funds(self) -> Balance:
    data = self._client.get(ENDPOINTS["fund_limit"])
    if isinstance(data, dict):
        if "availabelBalance" in data or "sodLimit" in data:
            return map_balance(data)
        items = data.get("data", [])
        if isinstance(items, list) and items:
            return map_balance(items[0])
    return Balance(available_cash=Decimal("0"))
```

**Endpoint:** `GET https://api.dhan.co/v2/fundlimit`

**Response Structure (Flat):**
```json
{
  "availabelBalance": 50000.00,
  "utilizedMargin": 10000.00,
  "totalMargin": 60000.00
}
```

**Response Structure (Nested):**
```json
{
  "data": [
    {
      "availabelBalance": 50000.00,
      "utilizedMargin": 10000.00,
      "totalMargin": 60000.00
    }
  ]
}
```

**Field Mapping:**
| Dhan Field | Domain Field | Notes |
|------------|--------------|-------|
| `availabelBalance` or `availableMargin` | `available_cash` | Typo in Dhan API |
| `utilizedMargin` | `utilized_margin` | Direct mapping |
| `totalMargin` | `total_margin` | Direct mapping |

---

#### trades()
```python
def trades(self) -> list[Trade]:
    data = self._client.get(ENDPOINTS["tradebook"])
    items = data.get("data", [])
    if isinstance(items, list):
        return [map_trade(t) for t in items]
    return []
```

**Endpoint:** `GET https://api.dhan.co/v2/tradebook`

**Response Structure:**
```json
{
  "data": [
    {
      "tradeId": "123456",
      "orderId": "789012",
      "tradingSymbol": "INFY",
      "exchangeSegment": "NSE_EQ",
      "transactionType": 1,
      "tradedQty": 20,
      "tradedPrice": 1500.00
    }
  ]
}
```

**Field Mapping:**
| Dhan Field | Domain Field | Notes |
|------------|--------------|-------|
| `tradeId` or `orderId` | `trade_id` | Fallback chain |
| `orderId` | `order_id` | Direct mapping |
| `tradingSymbol` | `symbol` | Direct mapping |
| `exchangeSegment` | `exchange` | Normalized |
| `transactionType` | `side` | Mapped: 1=BUY, 2=SELL |
| `tradedQty` or `quantity` | `quantity` | Fallback chain |
| `tradedPrice` or `price` | `price` | Fallback chain |

---

## Service Layer: PortfolioService

### Location
`brokers/services/portfolio_service.py`

### Class Definition
```python
class PortfolioService:
    def __init__(self, portfolio: PortfolioPort):
        """Initialize portfolio service.
        
        Args:
            portfolio: Portfolio port implementation
            
        Example:
            >>> service = PortfolioService(dhan_portfolio)
        """
```

### Method Contracts

#### positions()
```python
def positions(self) -> list[Position]:
    """Fetch positions (delegates to port).
    
    Returns:
        list[Position]: Open positions
    """
    return self._portfolio.positions()
```

---

#### holdings()
```python
def holdings(self) -> list[Holding]:
    """Fetch holdings (delegates to port).
    
    Returns:
        list[Holding]: Long-term holdings
    """
    return self._portfolio.holdings()
```

---

#### funds()
```python
def funds(self) -> Balance:
    """Fetch balance (delegates to port).
    
    Returns:
        Balance: Account balance
    """
    return self._portfolio.funds()
```

---

#### trades()
```python
def trades(self) -> list[Trade]:
    """Fetch trades (delegates to port).
    
    Returns:
        list[Trade]: Trade history
    """
    return self._portfolio.trades()
```

---

#### total_unrealized_pnl()
```python
def total_unrealized_pnl(self) -> Decimal:
    """Calculate total unrealized P&L across all positions.
    
    Returns:
        Decimal: Sum of unrealized P&L
        
    Example:
        >>> pnl = service.total_unrealized_pnl()
        >>> print(f"Total unrealized P&L: {pnl}")
    """
    return sum(
        (p.unrealized_pnl for p in self._portfolio.positions()),
        Decimal("0"),
    )
```

**Guarantees:**
- Returns `Decimal("0")` if no positions exist
- Never returns `None`
- Sums all positions (both long and short)

---

#### total_realized_pnl()
```python
def total_realized_pnl(self) -> Decimal:
    """Calculate total realized P&L across all positions.
    
    Returns:
        Decimal: Sum of realized P&L
        
    Example:
        >>> pnl = service.total_realized_pnl()
        >>> print(f"Total realized P&L: {pnl}")
    """
    return sum(
        (p.realized_pnl for p in self._portfolio.positions()),
        Decimal("0"),
    )
```

**Guarantees:**
- Returns `Decimal("0")` if no positions exist
- Never returns `None`

---

#### net_exposure()
```python
def net_exposure(self) -> Decimal:
    """Calculate net exposure (sum of position values).
    
    Returns:
        Decimal: Total exposure
        
    Formula:
        sum(average_price * abs(quantity)) for all positions
        
    Example:
        >>> exposure = service.net_exposure()
        >>> print(f"Net exposure: {exposure}")
    """
    total = Decimal("0")
    for pos in self._portfolio.positions():
        total += pos.average_price * abs(pos.quantity)
    return total
```

**Guarantees:**
- Returns `Decimal("0")` if no positions exist
- Uses absolute quantity (treats short positions same as long)
- Never returns `None`

---

## Archive vs Greenfield Comparison

### Portfolio API

| Method | Archive | Greenfield | Notes |
|--------|---------|------------|-------|
| `get_positions()` / `positions()` | ✅ | ✅ | Greenfield adds service layer |
| `get_holdings()` / `holdings()` | ✅ | ✅ | Greenfield simplifies data model |
| `get_balance()` / `funds()` | ✅ | ✅ | Different field names |
| `trades()` | ❌ | ✅ | New in greenfield |

### Margin API (Archive Only)

| Method | Archive | Greenfield | Notes |
|--------|---------|------------|-------|
| `calculate(MarginRequest)` | ✅ | ❌ | Not in Phase 7 scope |

### Service Layer (Greenfield Only)

| Method | Archive | Greenfield | Notes |
|--------|---------|------------|-------|
| `total_unrealized_pnl()` | ❌ | ✅ | Convenience method |
| `total_realized_pnl()` | ❌ | ✅ | Convenience method |
| `net_exposure()` | ❌ | ✅ | Convenience method |

---

## Data Model Comparison

### Position

| Field | Archive | Greenfield | Notes |
|-------|---------|------------|-------|
| `symbol` | ✅ | ✅ | Same |
| `exchange` | ✅ | ✅ | Same |
| `quantity` | ✅ | ✅ | Same |
| `product_type` | ✅ | ✅ | Same |
| `average_price` | ✅ (avg_price) | ✅ | Different name |
| `ltp` | ✅ | ❌ | Missing in greenfield |
| `realized_pnl` | ✅ | ✅ | Same |
| `unrealized_pnl` | ✅ | ✅ | Same |

### Holding

| Field | Archive | Greenfield | Notes |
|-------|---------|------------|-------|
| `symbol` | ✅ | ✅ | Same |
| `exchange` | ✅ | ✅ | Same |
| `quantity` | ✅ | ✅ | Same |
| `available_quantity` | ✅ | ❌ | Missing in greenfield |
| `average_price` | ✅ (avg_price) | ✅ | Different name |
| `ltp` | ✅ | ❌ | Missing in greenfield |
| `pnl` | ✅ | ❌ | Missing in greenfield |
| `isin` | ❌ | ✅ | New in greenfield |
| `t1_quantity` | ❌ | ✅ | New in greenfield |

### Balance

| Field | Archive | Greenfield | Notes |
|-------|---------|------------|-------|
| `available_balance` / `available_cash` | ✅ | ✅ | Different name |
| `sod_limit` | ✅ | ❌ | Missing in greenfield |
| `collateral_amount` | ✅ | ❌ | Missing in greenfield |
| `utilized_amount` / `utilized_margin` | ✅ | ✅ | Different name |
| `withdrawable_balance` | ✅ | ❌ | Missing in greenfield |
| `total_margin` | ❌ | ✅ | New in greenfield |

---

## Exception Hierarchy

### Base Exceptions
```python
# All exceptions inherit from standard Python exceptions
HTTPError              # requests.exceptions.HTTPError
AuthenticationError    # 401 Unauthorized
PermissionError        # 403 Forbidden
RateLimitError         # 429 Too Many Requests
ConnectionError        # Network errors
TimeoutError           # Request timeout
```

### Exception Handling Pattern
```python
try:
    positions = portfolio.positions()
except AuthenticationError:
    # Token expired, refresh and retry
    token_manager.refresh()
    positions = portfolio.positions()
except RateLimitError:
    # Backoff and retry
    time.sleep(backoff_seconds)
    positions = portfolio.positions()
except HTTPError as e:
    # Log and handle error
    logger.error(f"HTTP error: {e}")
    raise
```

---

## Usage Examples

### Basic Usage
```python
from brokers.adapters.dhan.portfolio import DhanPortfolio
from brokers.services.portfolio_service import PortfolioService

# Initialize
client = DhanHttpClient(config)
portfolio = DhanPortfolio(client)
service = PortfolioService(portfolio)

# Fetch positions
positions = service.positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.quantity} @ {pos.average_price}")

# Fetch holdings
holdings = service.holdings()
for h in holdings:
    print(f"{h.symbol}: {h.quantity} shares")

# Fetch balance
balance = service.funds()
print(f"Available: {balance.available_cash}")

# Calculate P&L
unrealized = service.total_unrealized_pnl()
realized = service.total_realized_pnl()
print(f"Unrealized: {unrealized}, Realized: {realized}")

# Calculate exposure
exposure = service.net_exposure()
print(f"Net exposure: {exposure}")
```

### Error Handling
```python
from requests.exceptions import HTTPError

try:
    positions = service.positions()
except HTTPError as e:
    if e.response.status_code == 401:
        # Token expired
        token_manager.refresh()
        positions = service.positions()
    elif e.response.status_code == 429:
        # Rate limited
        time.sleep(1)
        positions = service.positions()
    else:
        raise
```

---

## Contract Guarantees

### Return Types
- `positions()` always returns `list[Position]` (never `None`)
- `holdings()` always returns `list[Holding]` (never `None`)
- `funds()` always returns `Balance` (never `None`)
- `trades()` always returns `list[Trade]` (never `None`)

### Empty Results
- Empty positions → `[]`
- Empty holdings → `[]`
- Empty trades → `[]`
- Balance error → `Balance(available_cash=Decimal("0"))`

### Default Values
- Missing numeric fields → `0` or `Decimal("0")`
- Missing string fields → `""`
- Missing enum fields → Default enum value (e.g., `ProductType.INTRADAY`)

### Immutability
- All domain entities are frozen dataclasses
- Cannot modify fields after creation
- Thread-safe by design

---

## Future Extensions (Out of Scope)

### MarginPort
```python
class MarginPort(Protocol):
    def calculate(self, request: MarginRequest) -> MarginResponse: ...
```

### Enhanced Position
```python
@dataclass(frozen=True)
class Position:
    # ... existing fields ...
    ltp: Decimal = Decimal("0")  # Add last traded price
```

### Enhanced Holding
```python
@dataclass(frozen=True)
class Holding:
    # ... existing fields ...
    available_quantity: int = 0  # Add available qty
    ltp: Decimal = Decimal("0")  # Add last traded price
    pnl: Decimal = Decimal("0")  # Add P&L
```

### Enhanced Balance
```python
@dataclass(frozen=True)
class Balance:
    # ... existing fields ...
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")
```
