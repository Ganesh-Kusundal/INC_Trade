# Phase 7 Portfolio — Source Audit

## Executive Summary

Phase 7 (Portfolio) implements read-only portfolio queries for the Dhan broker:
- **Positions**: Current open positions with P&L tracking
- **Holdings**: Long-term holdings with cost basis
- **Funds**: Account balance and margin utilization
- **Trades**: Trade execution history
- **Margin Calculation**: Pre-order margin estimation (archive only)

The greenfield implementation successfully extracts portfolio functionality into a clean port-adapter-service architecture, removing broker-specific dependencies from the domain layer.

## Archive Files

| File | Lines | Purpose |
|------|-------|---------|
| `archive/brokers/dhan/portfolio.py` | 103 | Portfolio adapter (positions, holdings, balance) |
| `archive/brokers/dhan/margin.py` | 116 | Margin calculation adapter |

### Archive Key Symbols

**portfolio.py:**
- `PortfolioAdapter` class — main adapter
- `get_positions()` → `list[Position]`
- `get_holdings()` → `list[Holding]`
- `get_balance()` → `Balance`
- `_parse_product()` — helper for ProductType parsing

**margin.py:**
- `MarginAdapter` class — margin calculator
- `calculate(MarginRequest)` → `MarginResponse`
- `_validate_request()` — input validation

### Archive Dependencies
- `brokers.dhan.http_client.DhanHttpClient`
- `brokers.dhan.identity.DhanIdentityProvider`
- `brokers.dhan.segments.segment_to_exchange`
- `brokers.dhan.domain.MarginRequest`, `MarginResponse`
- `brokers.dhan.invariants.assert_dhan_payload`
- `domain.utils.price.to_wire_float`
- Domain entities: `Balance`, `Holding`, `Position`, `ProductType`

## Greenfield Files

| File | Lines | Purpose |
|------|-------|---------|
| `brokers/adapters/dhan/portfolio.py` | 55 | Dhan portfolio adapter implementation |
| `brokers/ports/portfolio.py` | 19 | Portfolio port interface (Protocol) |
| `brokers/services/portfolio_service.py` | 51 | Application-level portfolio service |
| `brokers/domain/entities.py` | 169 | Domain entities (Position, Holding, Balance, Trade) |
| `brokers/domain/enums.py` | 92 | Domain enumerations |

### Greenfield Key Symbols

**adapters/dhan/portfolio.py:**
- `DhanPortfolio` class — adapter implementation
- `positions()` → `list[Position]`
- `holdings()` → `list[Holding]`
- `funds()` → `Balance`
- `trades()` → `list[Trade]`

**ports/portfolio.py:**
- `PortfolioPort` Protocol — interface definition
- Methods: `positions()`, `holdings()`, `funds()`, `trades()`

**services/portfolio_service.py:**
- `PortfolioService` class — application service
- Delegates to `PortfolioPort`
- Adds: `total_unrealized_pnl()`, `total_realized_pnl()`, `net_exposure()`

**domain/entities.py:**
- `Position` — frozen dataclass (symbol, exchange, quantity, product_type, average_price, realized_pnl, unrealized_pnl)
- `Holding` — frozen dataclass (symbol, exchange, quantity, average_price, isin, t1_quantity)
- `Balance` — frozen dataclass (available_cash, utilized_margin, total_margin)
- `Trade` — frozen dataclass (trade_id, order_id, symbol, exchange, side, quantity, price, timestamp)

**domain/enums.py:**
- `ProductType` — INTRADAY, DELIVERY, MARGIN
- `Side` — BUY, SELL
- `OrderStatus`, `OrderType`, `Validity`

## REST API Endpoints

### Portfolio Endpoints (Greenfield)
| Endpoint | URL | Method | Purpose |
|----------|-----|--------|---------|
| positions | `https://api.dhan.co/v2/positions` | GET | Fetch open positions |
| holdings | `https://api.dhan.co/v2/holdings` | GET | Fetch long-term holdings |
| fund_limit | `https://api.dhan.co/v2/fundlimit` | GET | Fetch account balance |
| tradebook | `https://api.dhan.co/v2/tradebook` | GET | Fetch trade history |

### Margin Endpoint (Archive Only)
| Endpoint | URL | Method | Purpose |
|----------|-----|--------|---------|
| margincalculator | `https://api.dhan.co/v2/margincalculator` | POST | Calculate order margin |

## Data Models

### Position (Greenfield)
```python
@dataclass(frozen=True)
class Position:
    symbol: str
    exchange: str
    quantity: int
    product_type: ProductType = ProductType.INTRADAY
    average_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
```

### Position (Archive)
```python
Position(
    symbol=str,
    exchange=str,
    quantity=int,
    avg_price=Decimal,
    ltp=Decimal,
    unrealized_pnl=Decimal,
    realized_pnl=Decimal,
    product_type=ProductType,
)
```

**Delta:** Archive includes `ltp` field; greenfield omits it.

### Holding (Greenfield)
```python
@dataclass(frozen=True)
class Holding:
    symbol: str
    exchange: str
    quantity: int
    average_price: Decimal = Decimal("0")
    isin: str = ""
    t1_quantity: int = 0
```

### Holding (Archive)
```python
Holding(
    symbol=str,
    exchange=str,
    quantity=int,
    available_quantity=int,
    avg_price=Decimal,
    ltp=Decimal,
    pnl=Decimal,
)
```

**Delta:** Archive includes `available_quantity`, `ltp`, `pnl`; greenfield includes `isin`, `t1_quantity`.

### Balance (Greenfield)
```python
@dataclass(frozen=True)
class Balance:
    available_cash: Decimal
    utilized_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
```

### Balance (Archive)
```python
Balance(
    available_balance=Decimal,
    sod_limit=Decimal,
    collateral_amount=Decimal,
    utilized_amount=Decimal,
    withdrawable_balance=Decimal,
)
```

**Delta:** Archive has 5 fields; greenfield has 3 fields (simplified).

### MarginRequest (Archive Only)
```python
class MarginRequest:
    symbol: str
    exchange: str
    quantity: int
    order_type: str
    product_type: str
    price: Decimal | None
    trigger_price: Decimal | None
```

### MarginResponse (Archive Only)
```python
class MarginResponse:
    total_margin: Decimal
    order_margin: Decimal
    exposure_margin: Decimal
    available_margin: Decimal | None
    span_margin: Decimal | None
```

## API Methods Summary

### Portfolio API (Archive)
- `get_positions()` → `list[Position]`
- `get_holdings()` → `list[Holding]`
- `get_balance()` → `Balance`

### Portfolio API (Greenfield)
- `positions()` → `list[Position]`
- `holdings()` → `list[Holding]`
- `funds()` → `Balance`
- `trades()` → `list[Trade]` (new in greenfield)

### Margin API (Archive Only)
- `calculate(MarginRequest)` → `MarginResponse`
- Validates request (quantity > 0, price for LIMIT/STOP_LOSS)
- Resolves instrument via identity provider
- Calls `/margincalculator` endpoint
- Returns margin breakdown

### Service Layer (Greenfield Only)
- `PortfolioService(positions: PortfolioPort)`
- `positions()` → `list[Position]`
- `holdings()` → `list[Holding]`
- `funds()` → `Balance`
- `trades()` → `list[Trade]`
- `total_unrealized_pnl()` → `Decimal`
- `total_realized_pnl()` → `Decimal`
- `net_exposure()` → `Decimal`
