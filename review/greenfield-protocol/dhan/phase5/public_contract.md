# Phase 5: Order Management — Public Contract Documentation

## 1. Orders API Contract

### 1.1 OrdersAdapter (Archive)

#### place_order()

```python
def place_order(self, request: BrokerOrderPayload) -> OrderResponse:
    """
    Place an order via the Dhan API.
    
    Parameters:
        request: BrokerOrderPayload with fields:
            - symbol: str
            - exchange: str
            - transaction_type: Side (BUY/SELL)
            - quantity: int
            - order_type: OrderType
            - product_type: ProductType
            - price: Decimal (optional)
            - trigger_price: Decimal (optional)
            - validity: Validity
            - correlation_id: str (optional)
    
    Returns:
        OrderResponse:
            - order_id: str
            - success: bool
            - message: str
            - status: OrderStatus
            - error_code: str (optional)
            - raw_payload: Order (optional)
    
    Raises:
        OrderError: If live orders disabled
        DhanError: If API call fails
    
    Side Effects:
        - Validates order (lot size, tick alignment, product/segment)
        - Checks idempotency cache
        - Performs risk check
        - Publishes ORDER_PLACED event
        - Caches response in idempotency cache
    """
```

#### modify_order()

```python
def modify_order(self, order_id: str, **changes: Any) -> Order:
    """
    Modify an existing order.
    
    Parameters:
        order_id: str - Order ID to modify
        **changes: dict - Fields to modify:
            - quantity: int
            - price: Decimal
            - order_type: OrderType
            - validity: Validity
            - trigger_price: Decimal
    
    Returns:
        Order: Updated order object
    
    Raises:
        OrderError: If live orders disabled or API fails
    
    Side Effects:
        - Logs modification
        - Parses response into Order
    """
```

#### cancel_order()

```python
def cancel_order(self, order_id: str) -> OrderResponse:
    """
    Cancel an order.
    
    Parameters:
        order_id: str - Order ID to cancel
    
    Returns:
        OrderResponse:
            - order_id: str
            - success: bool
            - message: str
            - status: OrderStatus.CANCELLED (on success)
            - error_code: str (on failure)
            - raw_payload: dict (optional)
    
    Raises:
        OrderError: If live orders disabled
    
    Side Effects:
        - Checks post-cancel race condition
        - Logs cancellation
    """
```

#### get_order()

```python
def get_order(self, order_id: str) -> Order:
    """
    Get order details by ID.
    
    Parameters:
        order_id: str - Order ID to fetch
    
    Returns:
        Order: Order object with all fields
    
    Raises:
        DhanError: If API call fails
    
    Side Effects:
        - None (read-only)
    """
```

#### get_orderbook()

```python
def get_orderbook(self) -> list[Order]:
    """
    Get all orders.
    
    Returns:
        list[Order]: List of all orders
    
    Raises:
        DhanError: If API call fails
    
    Side Effects:
        - Logs orderbook fetch
    """
```

#### Additional Methods

```python
def get_trade_book(self) -> list[Trade]:
    """Get all trades for the day."""

def get_order_status(self, order_id: str) -> OrderStatus:
    """Get status of a specific order."""

def cancel_all_orders(self) -> list[tuple[str, bool]]:
    """Cancel all open orders."""

def kill_switch(self, enable: bool) -> bool:
    """Activate/deactivate kill switch."""

def place_slice_order(self, symbol: str, exchange: str, **kwargs) -> Order:
    """Place a slice order (auto-splits large orders)."""

def get_trade_history(self, from_date: str, to_date: str, page: int = 0) -> list[Trade]:
    """Get trade history for a date range."""
```

### 1.2 DhanOrders (Greenfield)

#### place_order()

```python
def place_order(
    self,
    symbol: str,
    exchange: str,
    side: Side,
    quantity: int,
    order_type: OrderType = OrderType.MARKET,
    price: Decimal = Decimal("0"),
    product_type: ProductType = ProductType.INTRADAY,
    validity: Validity = Validity.DAY,
    trigger_price: Decimal = Decimal("0"),
) -> OrderResponse:
    """
    Place an order via the Dhan API.
    
    Parameters:
        symbol: str - Trading symbol
        exchange: str - Exchange (NSE, BSE, NFO, etc.)
        side: Side - BUY or SELL
        quantity: int - Order quantity
        order_type: OrderType - MARKET, LIMIT, STOP_LOSS, etc.
        price: Decimal - Limit price (for LIMIT orders)
        product_type: ProductType - INTRADAY, DELIVERY, MARGIN
        validity: Validity - DAY, IOC, GTT
        trigger_price: Decimal - Trigger price (for STOP orders)
    
    Returns:
        OrderResponse:
            - order_id: str
            - success: bool
            - message: str
            - status: OrderStatus
            - error_code: str
    
    Raises:
        None (returns OrderResponse on error)
    
    Side Effects:
        - Validates live orders flag
        - Resolves instrument
        - Builds payload
        - Asserts payload invariants
        - Posts to API
        - Maps response
    """
```

#### modify_order()

```python
def modify_order(
    self,
    order_id: str,
    quantity: int | None = None,
    price: Decimal | None = None,
    order_type: OrderType | None = None,
    validity: Validity | None = None,
) -> OrderResponse:
    """
    Modify an existing order.
    
    Parameters:
        order_id: str - Order ID to modify
        quantity: int - New quantity (optional)
        price: Decimal - New price (optional)
        order_type: OrderType - New order type (optional)
        validity: Validity - New validity (optional)
    
    Returns:
        OrderResponse: Updated order response
    
    Raises:
        None (returns OrderResponse on error)
    
    Side Effects:
        - Validates live orders flag
        - Builds modification payload
        - Posts to API
    """
```

#### cancel_order()

```python
def cancel_order(self, order_id: str) -> OrderResponse:
    """
    Cancel an order.
    
    Parameters:
        order_id: str - Order ID to cancel
    
    Returns:
        OrderResponse:
            - order_id: str
            - success: bool
            - message: str
            - error_code: str (on failure)
    
    Raises:
        None (returns OrderResponse on error)
    
    Side Effects:
        - Validates live orders flag
        - Posts cancel request
        - Checks post-cancel race
    """
```

#### get_order()

```python
def get_order(self, order_id: str) -> Order | None:
    """
    Get order details by ID.
    
    Parameters:
        order_id: str - Order ID to fetch
    
    Returns:
        Order | None: Order object or None if not found
    
    Raises:
        None (returns None on error)
    
    Side Effects:
        - None (read-only)
    """
```

#### get_orderbook()

```python
def get_orderbook(self) -> list[Order]:
    """
    Get all orders.
    
    Returns:
        list[Order]: List of all orders
    
    Raises:
        None (returns empty list on error)
    
    Side Effects:
        - None (read-only)
    """
```

## 2. SuperOrders API Contract

### 2.1 SuperOrdersAdapter (Archive)

#### place_super_order()

```python
def place_super_order(
    self,
    symbol: str,
    exchange: str,
    transaction_type: str,
    quantity: int,
    price: Decimal,
    target_price: Decimal,
    stop_loss_price: Decimal,
    trailing_jump: Decimal,
    product_type: str = "INTRADAY",
    order_type: str = "LIMIT",
    correlation_id: str | None = None,
) -> SuperOrder:
    """
    Place a bracket order with Entry + Target + Stop Loss legs.
    
    Parameters:
        symbol: str - Trading symbol
        exchange: str - Exchange
        transaction_type: str - BUY or SELL
        quantity: int - Order quantity
        price: Decimal - Entry price
        target_price: Decimal - Target price
        stop_loss_price: Decimal - Stop loss price
        trailing_jump: Decimal - Trailing SL jump
        product_type: str - Product type
        order_type: str - Order type
        correlation_id: str - Optional correlation ID
    
    Returns:
        SuperOrder: Order with leg details
    
    Raises:
        ValueError: If validation fails
        SuperOrderError: If API call fails
    
    Validation:
        - BUY: target > entry > stop_loss
        - SELL: target < entry < stop_loss
        - All prices > 0
    """
```

#### modify_super_order()

```python
def modify_super_order(
    self,
    order_id: str,
    leg_name: str,
    quantity: int | None = None,
    price: Decimal | None = None,
    trigger_price: Decimal | None = None,
) -> SuperOrder:
    """
    Modify a specific leg of a super order.
    
    Parameters:
        order_id: str - Super order ID
        leg_name: str - Leg to modify (ENTRY_LEG, TARGET_LEG, STOP_LOSS_LEG)
        quantity: int - New quantity
        price: Decimal - New price
        trigger_price: Decimal - New trigger price
    
    Returns:
        SuperOrder: Updated order
    
    Raises:
        SuperOrderError: If API call fails
    """
```

#### cancel_super_order_leg()

```python
def cancel_super_order_leg(self, order_id: str, leg_name: str) -> OrderResponse:
    """
    Cancel a specific leg of a super order.
    
    Parameters:
        order_id: str - Super order ID
        leg_name: str - Leg to cancel
    
    Returns:
        OrderResponse: Success/failure response
    
    Raises:
        SuperOrderError: On network/transport errors
    """
```

#### get_super_orders()

```python
def get_super_orders(self) -> list[SuperOrder]:
    """
    Get all super orders.
    
    Returns:
        list[SuperOrder]: List of super orders
    
    Raises:
        SuperOrderError: If API call fails
    """
```

### 2.2 Greenfield Equivalent

**Status:** ❌ NOT IMPLEMENTED

**Required Implementation:**
- DhanSuperOrders adapter class
- SuperOrder entity
- SuperOrderLeg entity
- Validation logic
- State machine for leg tracking

## 3. ForeverOrders API Contract

### 3.1 ForeverOrdersAdapter (Archive)

#### place_forever_order()

```python
def place_forever_order(self, request: ForeverOrderRequest) -> ForeverOrder:
    """
    Place a GTT order (SINGLE or OCO).
    
    Parameters:
        request: ForeverOrderRequest with fields:
            - symbol: str
            - exchange: str
            - order_flag: str (SINGLE or OCO)
            - transaction_type: str
            - quantity: int
            - price: Decimal
            - trigger_price: Decimal
            - product_type: str
            - order_type: str
            - validity: str
            - price1: Decimal (OCO only)
            - trigger_price1: Decimal (OCO only)
            - quantity1: int (OCO only)
            - correlation_id: str (optional)
    
    Returns:
        ForeverOrder: Created order
    
    Raises:
        ValueError: If validation fails
        ForeverOrderError: If API call fails
    
    Validation:
        - order_flag ∈ {SINGLE, OCO}
        - OCO requires price1, trigger_price1, quantity1
        - All prices > 0
        - quantity > 0
    """
```

#### modify_forever_order()

```python
def modify_forever_order(
    self,
    order_id: str,
    request: ForeverOrderRequest,
) -> ForeverOrder:
    """
    Modify an existing forever order.
    
    Parameters:
        order_id: str - Order ID to modify
        request: ForeverOrderRequest - Updated details
    
    Returns:
        ForeverOrder: Updated order
    
    Raises:
        ForeverOrderError: If API call fails
    """
```

#### cancel_forever_order()

```python
def cancel_forever_order(self, order_id: str) -> OrderResponse:
    """
    Cancel a forever order.
    
    Parameters:
        order_id: str - Order ID to cancel
    
    Returns:
        OrderResponse: Success/failure response
    
    Raises:
        ForeverOrderError: On network/transport errors
    """
```

#### get_all_forever_orders()

```python
def get_all_forever_orders(self) -> list[ForeverOrder]:
    """
    Get all forever orders.
    
    Returns:
        list[ForeverOrder]: List of forever orders
    
    Raises:
        ForeverOrderError: If API call fails
    """
```

### 3.2 Greenfield Equivalent

**Status:** ❌ NOT IMPLEMENTED

**Required Implementation:**
- DhanForeverOrders adapter class
- ForeverOrder entity
- ForeverOrderRequest entity
- SINGLE and OCO mode support
- Validation logic

## 4. ConditionalTriggers API Contract

### 4.1 ConditionalTriggersAdapter (Archive)

#### place_trigger()

```python
def place_trigger(self, request: ConditionalTriggerRequest) -> ConditionalTrigger:
    """
    Place a conditional trigger order.
    
    Parameters:
        request: ConditionalTriggerRequest with fields:
            - symbol: str
            - exchange: str
            - comparison_type: str (PRICE_WITH_VALUE)
            - operator: str (CROSSING_UP, CROSSING_DOWN, GREATER_THAN, LESS_THAN)
            - comparing_value: Decimal
            - exp_date: str
            - frequency: str (ONCE, DAILY, etc.)
            - orders: list (orders to place on trigger)
            - user_note: str (optional)
    
    Returns:
        ConditionalTrigger: Created trigger
    
    Raises:
        ValueError: If validation fails
        ConditionalTriggerError: If API call fails
    
    Validation:
        - operator ∈ {CROSSING_UP, CROSSING_DOWN, GREATER_THAN, LESS_THAN}
        - comparison_type == PRICE_WITH_VALUE
        - comparing_value > 0
    """
```

#### modify_trigger()

```python
def modify_trigger(
    self,
    alert_id: str,
    request: ConditionalTriggerRequest,
) -> ConditionalTrigger:
    """
    Modify an existing conditional trigger.
    
    Parameters:
        alert_id: str - Alert ID to modify
        request: ConditionalTriggerRequest - Updated details
    
    Returns:
        ConditionalTrigger: Updated trigger
    
    Raises:
        ConditionalTriggerError: If API call fails
    """
```

#### delete_trigger()

```python
def delete_trigger(self, alert_id: str) -> bool:
    """
    Delete a conditional trigger.
    
    Parameters:
        alert_id: str - Alert ID to delete
    
    Returns:
        bool: True if successful
    
    Raises:
        ConditionalTriggerError: If API call fails
    """
```

#### get_trigger()

```python
def get_trigger(self, alert_id: str) -> ConditionalTrigger:
    """
    Get a specific conditional trigger.
    
    Parameters:
        alert_id: str - Alert ID to fetch
    
    Returns:
        ConditionalTrigger: Trigger details
    
    Raises:
        ConditionalTriggerError: If API call fails
    """
```

#### get_all_triggers()

```python
def get_all_triggers(self) -> list[ConditionalTrigger]:
    """
    Get all conditional triggers.
    
    Returns:
        list[ConditionalTrigger]: List of triggers
    
    Raises:
        ConditionalTriggerError: If API call fails
    """
```

### 4.2 DhanConditionalTriggers (Greenfield)

#### place_conditional_order()

```python
def place_conditional_order(
    self,
    symbol: str,
    exchange: str,
    side: Side,
    quantity: int,
    order_type: OrderType = OrderType.LIMIT,
    price: Decimal = Decimal("0"),
    product_type: ProductType = ProductType.INTRADAY,
    validity: Validity = Validity.DAY,
    trigger_price: Decimal = Decimal("0"),
) -> dict:
    """
    Place a conditional (GTT) order.
    
    Parameters:
        symbol: str - Instrument symbol
        exchange: str - Exchange
        side: Side - BUY or SELL
        quantity: int - Quantity
        order_type: OrderType - Order type
        price: Decimal - Limit price
        product_type: ProductType - Product type
        validity: Validity - Validity
        trigger_price: Decimal - Trigger price
    
    Returns:
        dict: Broker response with trigger ID
    
    Raises:
        None (returns dict on error)
    
    Side Effects:
        - Resolves instrument
        - Builds payload
        - Posts to API
    """
```

#### cancel_conditional_order()

```python
def cancel_conditional_order(self, trigger_id: str) -> dict:
    """
    Cancel a pending conditional order.
    
    Parameters:
        trigger_id: str - Trigger ID to cancel
    
    Returns:
        dict: Broker response
    
    Raises:
        None
    """
```

#### get_conditional_orders()

```python
def get_conditional_orders(self) -> list[dict]:
    """
    Fetch all conditional orders.
    
    Returns:
        list[dict]: List of conditional orders
    
    Raises:
        None (returns empty list on error)
    """
```

### 4.3 Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| Entity types | ConditionalTrigger, ConditionalTriggerRequest | dict | ❌ Greenfield lacks entities |
| Validation | Comprehensive | None | ❌ Missing |
| Modification | Supported | Not implemented | ❌ Missing |
| Get by ID | Supported | Not implemented | ❌ Missing |
| Operators | 4 operators | Not implemented | ❌ Missing |
| Comparison types | PRICE_WITH_VALUE | Not implemented | ❌ Missing |

## 5. ExitAll API Contract

### 5.1 ExitAllAdapter (Archive)

#### exit_all()

```python
def exit_all(self) -> ExitAllResponse:
    """
    Close all positions and cancel all orders.
    
    Returns:
        ExitAllResponse:
            - positions_closed: int
            - orders_cancelled: int
            - success: bool
            - message: str
    
    Raises:
        ExitAllError: If API call fails
    
    Side Effects:
        - Closes all positions
        - Cancels all orders
        - Logs operation
    """
```

### 5.2 DhanExitAll (Greenfield)

#### close_all_positions()

```python
def close_all_positions(self) -> dict:
    """
    Instantly square off all open positions concurrently.
    
    Returns:
        dict:
            - squared_off: int (count)
            - results: list (individual results)
    
    Raises:
        None (catches exceptions per position)
    
    Side Effects:
        - Fetches all positions
        - Calculates net quantity
        - Places market orders to square off
        - Uses ThreadPoolExecutor for concurrency
    """
```

#### cancel_all_orders()

```python
def cancel_all_orders(self) -> dict:
    """
    Instantly cancel all pending orders concurrently.
    
    Returns:
        dict:
            - cancelled: int (count)
            - results: list (individual results)
    
    Raises:
        None (catches exceptions per order)
    
    Side Effects:
        - Fetches orderbook
        - Filters active orders
        - Cancels each order
        - Uses ThreadPoolExecutor for concurrency
    """
```

### 5.3 Comparison

| Aspect | Archive | Greenfield | Gap |
|--------|---------|------------|-----|
| API | Single exit_all() | Two separate methods | ⚠️ Different design |
| Entity | ExitAllResponse | dict | ❌ Greenfield lacks entity |
| Concurrency | Single API call | ThreadPoolExecutor | ⚠️ Different approach |
| Error handling | Raise exception | Catch per-item | ⚠️ Different strategy |
| Position squaring | Broker-side | Client-side | ⚠️ Greenfield more complex |

## 6. StatusMapper Contract

### 6.1 Archive Implementation

```python
DHAN_STATUS_MAP: dict[str, OrderStatus] = {
    **COMMON_STATUS_MAP,
    "PLACED": OrderStatus.OPEN,
    "TRIGGERED": OrderStatus.OPEN,
    "PARTIALLY_CANCELLED": OrderStatus.PARTIALLY_CANCELLED,
}

def register_mappings() -> None:
    """Register Dhan status mappings with global registry."""
```

### 6.2 Greenfield Equivalent

**Status:** ❌ NOT IMPLEMENTED

**Required Implementation:**
- DhanStatusMapper class
- Status mapping dictionary
- Registration with global registry

## 7. Invariants Contract

### 7.1 Archive Implementation

```python
def assert_dhan_segment(segment: str, *, context: str = "") -> None:
    """Raise DhanIdentityError if segment is not Dhan-internal."""

def assert_dhan_identity(
    security_id_or_ref: Any,
    segment: Any = None,
    *,
    context: str = "",
) -> None:
    """Verify security_id and segment form a Dhan-internal pair."""

def assert_valid_security_id(security_id: Any, *, context: str = "") -> None:
    """Validate a single security_id against Dhan digit contract."""

def assert_dhan_payload(payload: dict[str, Any], *, context: str = "") -> None:
    """Verify securityId + exchangeSegment pair in payload dict."""
```

### 7.2 Greenfield Equivalent

**Status:** ✅ IMPLEMENTED (as `assert_valid_dhan_payload`)

**Location:** `brokers/adapters/dhan/invariants.py`

## 8. Service Layer APIs

### 8.1 OrderService

```python
class OrderService:
    def __init__(
        self,
        executor: OrderExecutionPort,
        idempotency_cache: Any = None,
        lot_size: int = 0,
        tick_size: Decimal = Decimal("0"),
    ):
        """
        Initialize order service.
        
        Parameters:
            executor: OrderExecutionPort - Broker adapter
            idempotency_cache: Any - Idempotency cache
            lot_size: int - Instrument lot size
            tick_size: Decimal - Instrument tick size
        """
    
    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
    ) -> OrderResponse:
        """
        Place an order with validation and idempotency.
        
        Validation:
            - Order fields (symbol, exchange, quantity, price)
            - Product/segment compatibility
            - Lot size multiple
            - Tick alignment
            - Notional warning
        
        Idempotency:
            - Check correlation_id in cache
            - Return IDEMPOTENCY_CONFLICT if duplicate
        
        Returns:
            OrderResponse: Order result
        """
    
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an order."""
    
    def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
    
    def get_orderbook(self) -> list[Order]:
        """Get all orders."""
```

### 8.2 OrderValidation

```python
def validate_order_fields(
    symbol: str,
    exchange: str,
    quantity: int,
    order_type: OrderType,
    price: Decimal,
    trigger_price: Decimal,
) -> None:
    """Validate basic order fields."""

def validate_lot_size(quantity: int, lot_size: int) -> None:
    """Validate quantity is multiple of lot size."""

def validate_tick_alignment(price: Decimal, tick_size: Decimal) -> None:
    """Validate price is aligned to tick size."""

def validate_product_segment(product_type: ProductType, exchange: str) -> None:
    """Validate product type is valid for exchange."""

def check_notional_warning(
    quantity: int,
    price: Decimal,
    threshold: Decimal = Decimal("50000"),
) -> None:
    """Log warning if notional exceeds threshold."""
```

### 8.3 ReconciliationEngine

```python
class ReconciliationEngine:
    def __init__(
        self,
        broker: BrokerGateway,
        sync_interval_seconds: int = 30,
    ):
        """
        Initialize reconciliation engine.
        
        Parameters:
            broker: BrokerGateway - Broker adapter
            sync_interval_seconds: int - Sync interval
        """
    
    def start(self):
        """Start background reconciliation loop."""
    
    async def stop(self):
        """Stop background loop."""
    
    async def _reconciliation_loop(self):
        """Periodically sync with broker."""
    
    async def _sync_orders(self):
        """
        Sync local OMS with broker ledger.
        
        Steps:
            1. Fetch broker state
            2. Compare against local_order_ledger
            3. Raise drift alerts
            4. Synthesize missing transitions
        """
```

## 9. Summary of Gaps

### 9.1 Missing in Greenfield

1. **Super Orders (Bracket Orders)**
   - No adapter implementation
   - No entity definitions
   - No state machine

2. **Forever Orders (GTT/OCO)**
   - No adapter implementation
   - No entity definitions
   - No state machine

3. **Conditional Triggers**
   - Partial implementation (basic place/cancel)
   - No entity definitions (uses dict)
   - No validation
   - No modification support

4. **Status Mapper**
   - No Dhan-specific status mapping
   - No registration with global registry

5. **Advanced Features**
   - No kill switch
   - No slice orders
   - No trade history

### 9.2 Greenfield Strengths

1. **Explicit State Machine**
   - `order_lifecycle.py` defines transitions
   - Transition validation
   - Terminal/active state properties

2. **Service Layer**
   - OrderService with validation
   - OrderValidation with comprehensive checks
   - ReconciliationEngine for drift detection

3. **Port-Based Architecture**
   - OrderExecutionPort protocol
   - Clean separation of concerns
   - Testable design

### 9.3 Recommendations

1. Implement Super Orders adapter with full state machine
2. Implement Forever Orders adapter with SINGLE/OCO support
3. Enhance Conditional Triggers with entities and validation
4. Add StatusMapper for Dhan-specific statuses
5. Add kill switch and slice order support
6. Implement trade history API
7. Add state transition events for audit trail
