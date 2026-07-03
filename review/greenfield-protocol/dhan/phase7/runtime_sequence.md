# Phase 7 Portfolio — Runtime Sequences

## Position Retrieval Flow

### Archive Flow
```
User Code
    │
    ├─> PortfolioAdapter.get_positions()
    │       │
    │       ├─> DhanHttpClient.get("/positions")
    │       │       │
    │       │       └─> HTTP GET https://api.dhan.co/v2/positions
    │       │               │
    │       │               └─> Response JSON
    │       │
    │       ├─> Parse response["data"] as list
    │       │
    │       ├─> For each item:
    │       │       │
    │       │       ├─> segment_to_exchange(item["exchangeSegment"])
    │       │       │
    │       │       ├─> _parse_product(item["productType"])
    │       │       │
    │       │       └─> Build Position(
    │       │               symbol=item["tradingSymbol"],
    │       │               exchange=...,
    │       │               quantity=item["netQuantity"],
    │       │               avg_price=item["buyAveragePrice"],
    │       │               ltp=item["lastPrice"],
    │       │               unrealized_pnl=item["unrealizedPnl"],
    │       │               realized_pnl=item["realizedPnl"],
    │       │               product_type=...
    │       │           )
    │       │
    │       └─> Return list[Position]
    │
    └─> User receives positions
```

### Greenfield Flow
```
User Code
    │
    ├─> PortfolioService.positions()
    │       │
    │       └─> PortfolioPort.positions()
    │               │
    │               └─> DhanPortfolio.positions()
    │                       │
    │                       ├─> DhanHttpClient.get(ENDPOINTS["positions"])
    │                       │       │
    │                       │       └─> HTTP GET https://api.dhan.co/v2/positions
    │                       │               │
    │                       │               └─> Response JSON
    │                       │
    │                       ├─> Parse response as list or response["data"]
    │                       │
    │                       ├─> For each item:
    │                       │       │
    │                       │       └─> map_position(item)
    │                       │               │
    │                       │               ├─> _normalize_exchange(item["exchangeSegment"])
    │                       │               │
    │                       │               └─> Build Position(
    │                       │                       symbol=item["tradingSymbol"],
    │                       │                       exchange=...,
    │                       │                       quantity=item["netQty"],
    │                       │                       product_type=_PRODUCT_MAP[...],
    │                       │                       average_price=item["avgBuyCost"],
    │                       │                       realized_pnl=item["realizedProfit"],
    │                       │                       unrealized_pnl=item["unrealizedProfit"]
    │                       │                   )
    │                       │
    │                       └─> Return list[Position]
    │
    └─> User receives positions
```

### Comparison
| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Entry point | `PortfolioAdapter.get_positions()` | `PortfolioService.positions()` |
| HTTP client | `DhanHttpClient` | `DhanHttpClient` (same) |
| Endpoint | `/positions` | `ENDPOINTS["positions"]` (same) |
| Field mapping | Inline in adapter | Delegated to `map_position()` |
| Exchange mapping | `segment_to_exchange()` | `_normalize_exchange()` |
| Product mapping | `_parse_product()` | `_PRODUCT_MAP` dict |
| Quantity field | `netQuantity` | `netQty` |
| Avg price field | `buyAveragePrice` | `avgBuyCost` |
| LTP field | `lastPrice` | Not mapped |
| P&L fields | `unrealizedPnl`, `realizedPnl` | `unrealizedProfit`, `realizedProfit` |

## Holdings Retrieval Flow

### Archive Flow
```
User Code
    │
    ├─> PortfolioAdapter.get_holdings()
    │       │
    │       ├─> DhanHttpClient.get("/holdings")
    │       │       │
    │       │       └─> HTTP GET https://api.dhan.co/v2/holdings
    │       │               │
    │       │               └─> Response JSON
    │       │
    │       ├─> Parse response["data"] as list
    │       │
    │       ├─> For each item:
    │       │       │
    │       │       ├─> Extract quantity: item["totalQty"] or item["quantity"]
    │       │       │
    │       │       ├─> Extract avg_price: item["avgCostPrice"] or item["costPrice"]
    │       │       │
    │       │       ├─> Extract ltp: item["lastTradedPrice"] or item["lastPrice"]
    │       │       │
    │       │       ├─> Calculate P&L:
    │       │       │       if item["pnlValue"] exists:
    │       │       │           pnl = item["pnlValue"]
    │       │       │       elif avg_price > 0 and ltp > 0:
    │       │       │           pnl = (ltp - avg_price) * quantity
    │       │       │       else:
    │       │       │           pnl = 0
    │       │       │
    │       │       └─> Build Holding(
    │       │               symbol=item["tradingSymbol"],
    │       │               exchange=segment_to_exchange(...),
    │       │               quantity=qty,
    │       │               available_quantity=item["availableQty"],
    │       │               avg_price=avg_px,
    │       │               ltp=ltp,
    │       │               pnl=pnl
    │       │           )
    │       │
    │       └─> Return list[Holding]
    │
    └─> User receives holdings
```

### Greenfield Flow
```
User Code
    │
    ├─> PortfolioService.holdings()
    │       │
    │       └─> PortfolioPort.holdings()
    │               │
    │               └─> DhanPortfolio.holdings()
    │                       │
    │                       ├─> DhanHttpClient.get(ENDPOINTS["holdings"])
    │                       │       │
    │                       │       └─> HTTP GET https://api.dhan.co/v2/holdings
    │                       │               │
    │                       │               └─> Response JSON
    │                       │
    │                       ├─> Parse response as list or response["data"]
    │                       │
    │                       ├─> For each item:
    │                       │       │
    │                       │       └─> map_holding(item)
    │                       │               │
    │                       │               ├─> _normalize_exchange(item["exchangeSegment"])
    │                       │               │
    │                       │               └─> Build Holding(
    │                       │                       symbol=item["tradingSymbol"],
    │                       │                       exchange=...,
    │                       │                       quantity=item["holdingQty"] or item["quantity"],
    │                       │                       average_price=item["avgBuyPrice"] or item["costPrice"],
    │                       │                       isin=item["isin"],
    │                       │                       t1_quantity=item["t1Qty"]
    │                       │                   )
    │                       │
    │                       └─> Return list[Holding]
    │
    └─> User receives holdings
```

### Comparison
| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Entry point | `PortfolioAdapter.get_holdings()` | `PortfolioService.holdings()` |
| Field mapping | Inline with fallback logic | Delegated to `map_holding()` |
| Quantity field | `totalQty` or `quantity` | `holdingQty` or `quantity` |
| Avg price field | `avgCostPrice` or `costPrice` | `avgBuyPrice` or `costPrice` |
| LTP field | `lastTradedPrice` or `lastPrice` | Not mapped |
| P&L calculation | Yes (calculated if not provided) | Not calculated |
| Available qty | `availableQty` or `availableQuantity` | Not mapped |
| ISIN | Not mapped | `isin` |
| T1 quantity | Not mapped | `t1Qty` |

## Funds/Margin Retrieval Flow

### Archive Flow
```
User Code
    │
    ├─> PortfolioAdapter.get_balance()
    │       │
    │       ├─> DhanHttpClient.get("/fundlimit")
    │       │       │
    │       │       └─> HTTP GET https://api.dhan.co/v2/fundlimit
    │       │               │
    │       │               └─> Response JSON
    │       │
    │       ├─> Extract data: response["data"] or response
    │       │
    │       ├─> Validate: is dict?
    │       │       if not: log warning, return Balance()
    │       │
    │       └─> Build Balance(
    │               available_balance=raw["availabelBalance"] or raw["availableBalance"],
    │               sod_limit=raw["sodLimit"],
    │               collateral_amount=raw["collateralAmount"],
    │               utilized_amount=raw["utilizedAmount"],
    │               withdrawable_balance=raw["withdrawableBalance"]
    │           )
    │
    └─> User receives balance
```

### Greenfield Flow
```
User Code
    │
    ├─> PortfolioService.funds()
    │       │
    │       └─> PortfolioPort.funds()
    │               │
    │               └─> DhanPortfolio.funds()
    │                       │
    │                       ├─> DhanHttpClient.get(ENDPOINTS["fund_limit"])
    │                       │       │
    │                       │       └─> HTTP GET https://api.dhan.co/v2/fundlimit
    │                       │               │
    │                       │               └─> Response JSON
    │                       │
    │                       ├─> Validate: is dict?
    │                       │
    │                       ├─> Check structure:
    │                       │       if "availabelBalance" or "sodLimit" in data:
    │                       │           return map_balance(data)
    │                       │       else:
    │                       │           items = data["data"]
    │                       │           if items is list and not empty:
    │                       │               return map_balance(items[0])
    │                       │
    │                       └─> Default: return Balance(available_cash=0)
    │
    └─> User receives balance
```

### map_balance() Implementation
```python
def map_balance(data: dict) -> Balance:
    return Balance(
        available_cash=to_decimal(
            data.get("availabelBalance", data.get("availableMargin", 0))
        ),
        utilized_margin=to_decimal(data.get("utilizedMargin", 0)),
        total_margin=to_decimal(data.get("totalMargin", 0)),
    )
```

### Comparison
| Aspect | Archive | Greenfield |
|--------|---------|------------|
| Entry point | `PortfolioAdapter.get_balance()` | `PortfolioService.funds()` |
| Field mapping | Inline | Delegated to `map_balance()` |
| Available cash | `availabelBalance` or `availableBalance` | `availabelBalance` or `availableMargin` |
| SOD limit | `sodLimit` | Not mapped |
| Collateral | `collateralAmount` | Not mapped |
| Utilized | `utilizedAmount` | `utilizedMargin` |
| Withdrawable | `withdrawableBalance` | Not mapped |
| Total margin | Not mapped | `totalMargin` |
| Error handling | Returns empty Balance on failure | Returns Balance(available_cash=0) |
| Response structure | Flat or nested | Handles both flat and nested |

## Margin Calculation Flow (Archive Only)

```
User Code
    │
    ├─> MarginAdapter.calculate(MarginRequest)
    │       │
    │       ├─> _validate_request(request)
    │       │       │
    │       │       ├─> Check: quantity > 0
    │       │       │
    │       │       ├─> Check: if LIMIT/STOP_LOSS, price > 0
    │       │       │
    │       │       └─> Return errors list
    │       │
    │       ├─> If errors: raise ValueError
    │       │
    │       ├─> Resolve instrument:
    │       │       ref = identity.resolve_ref(symbol, exchange)
    │       │       segment = ref.exchange_segment
    │       │
    │       ├─> Build payload:
    │       │       {
    │       │           "dhanClientId": client.client_id,
    │       │           "exchangeSegment": segment,
    │       │           "securityId": ref.security_id_str(),
    │       │           "transactionType": "BUY",
    │       │           "orderType": request.order_type,
    │       │           "productType": request.product_type,
    │       │           "quantity": request.quantity,
    │       │           "price": to_wire_float(request.price),
    │       │           "triggerPrice": to_wire_float(request.trigger_price)
    │       │       }
    │       │
    │       ├─> Assert payload: assert_dhan_payload(payload)
    │       │
    │       ├─> DhanHttpClient.post("/margincalculator", json=payload)
    │       │       │
    │       │       └─> HTTP POST https://api.dhan.co/v2/margincalculator
    │       │               │
    │       │               └─> Response JSON
    │       │
    │       └─> Build MarginResponse(
    │               total_margin=response["totalMargin"],
    │               order_margin=response["orderMargin"],
    │               exposure_margin=response["exposureMargin"],
    │               available_margin=response["availableMargin"],
    │               span_margin=response["spanMargin"]
    │           )
    │
    └─> User receives margin response
```

## Trade Retrieval Flow (Greenfield Only)

```
User Code
    │
    ├─> PortfolioService.trades()
    │       │
    │       └─> PortfolioPort.trades()
    │               │
    │               └─> DhanPortfolio.trades()
    │                       │
    │                       ├─> DhanHttpClient.get(ENDPOINTS["tradebook"])
    │                       │       │
    │                       │       └─> HTTP GET https://api.dhan.co/v2/tradebook
    │                       │               │
    │                       │               └─> Response JSON
    │                       │
    │                       ├─> Parse response["data"] as list
    │                       │
    │                       ├─> For each item:
    │                       │       │
    │                       │       └─> map_trade(item)
    │                       │               │
    │                       │               ├─> _normalize_exchange(item["exchangeSegment"])
    │                       │               │
    │                       │               └─> Build Trade(
    │                       │                       trade_id=item["tradeId"] or item["orderId"],
    │                       │                       order_id=item["orderId"],
    │                       │                       symbol=item["tradingSymbol"],
    │                       │                       exchange=...,
    │                       │                       side=_SIDE_MAP[item["transactionType"]],
    │                       │                       quantity=item["tradedQty"] or item["quantity"],
    │                       │                       price=item["tradedPrice"] or item["price"]
    │                       │                   )
    │                       │
    │                       └─> Return list[Trade]
    │
    └─> User receives trades
```

## Service Layer Aggregation (Greenfield Only)

```
User Code
    │
    ├─> PortfolioService.total_unrealized_pnl()
    │       │
    │       ├─> PortfolioPort.positions()
    │       │       │
    │       │       └─> [list of positions]
    │       │
    │       └─> Sum: sum(p.unrealized_pnl for p in positions)
    │
    └─> User receives Decimal
```

```
User Code
    │
    ├─> PortfolioService.net_exposure()
    │       │
    │       ├─> PortfolioPort.positions()
    │       │       │
    │       │       └─> [list of positions]
    │       │
    │       └─> Calculate: sum(p.average_price * abs(p.quantity) for p in positions)
    │
    └─> User receives Decimal
```

## Key Differences Summary

### Architecture
- **Archive**: Monolithic adapter with inline parsing logic
- **Greenfield**: Separated into port (interface), adapter (implementation), service (application logic), and mapper (DTO conversion)

### Field Mapping
- **Archive**: Inline with multiple fallbacks and complex logic
- **Greenfield**: Centralized in `mapper.py` with cleaner fallback chains

### Data Models
- **Archive**: Richer models (includes LTP, available_quantity, P&L calculations)
- **Greenfield**: Simpler models (focuses on essential fields)

### Error Handling
- **Archive**: Explicit error logging and graceful degradation
- **Greenfield**: Implicit error handling via default values

### New Features
- **Greenfield adds**: Trade retrieval, P&L aggregation, net exposure calculation
- **Greenfield removes**: Margin calculation (not in scope for Phase 7)
