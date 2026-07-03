# Phase 5: Order Management — Failure Analysis Documentation

## 1. Timeout Policies

### 1.1 Order Placement Timeouts

**Archive Implementation:**
```python
# No explicit timeout configuration
# Relies on http_client default timeouts
# Network errors caught and logged
```

**Greenfield Implementation:**
```python
# No explicit timeout configuration
# Relies on DhanHttpClient default timeouts
# Network errors caught and logged
```

**Gap Analysis:**
- ❌ No configurable timeout per operation type
- ❌ No distinction between placement vs modification timeouts
- ❌ No timeout for idempotency cache operations
- ❌ No circuit breaker integration

**Recommended Timeout Policy:**
```python
TIMEOUT_POLICY = {
    "place_order": {
        "connect_timeout": 5.0,
        "read_timeout": 10.0,
        "retry_attempts": 2,
        "retry_delay": 1.0,
    },
    "modify_order": {
        "connect_timeout": 3.0,
        "read_timeout": 5.0,
        "retry_attempts": 1,
        "retry_delay": 0.5,
    },
    "cancel_order": {
        "connect_timeout": 3.0,
        "read_timeout": 5.0,
        "retry_attempts": 2,
        "retry_delay": 0.5,
    },
    "get_order": {
        "connect_timeout": 2.0,
        "read_timeout": 3.0,
        "retry_attempts": 1,
        "retry_delay": 0.5,
    },
}
```

### 1.2 Timeout Scenarios

**Scenario 1: Network Timeout During Placement**
```
Client → place_order() → [TIMEOUT] → ???

Recovery:
1. Check idempotency cache
2. Query order book for correlation_id
3. If order exists → return order_id
4. If order not found → retry with same correlation_id
5. If retry fails → return failure
```

**Scenario 2: Partial Response**
```
Client → place_order() → [PARTIAL_RESPONSE] → ???

Recovery:
1. Parse partial response
2. Extract order_id if present
3. Query order status
4. If status is OPEN/PENDING → return order_id
5. If status is REJECTED → return failure
6. If status unknown → retry
```

## 2. Exception Hierarchy

### 2.1 Archive Exception Hierarchy

```
TradeXV2Error (root)
├── ConfigError
├── DataError
├── ValidationError
└── BrokerError
    ├── RetryableError
    │   └── NetworkError
    ├── NonRetryableError
    ├── BrokerServerError
    ├── OrderRejectedError
    ├── RateLimitError
    ├── CircuitOpenError
    ├── AuthenticationError
    ├── TokenRateLimitError
    ├── InstrumentNotFoundError
    ├── NotSupportedError
    └── BrokerDegradedError

Dhan-Specific:
├── DhanError
│   ├── OrderError
│   ├── SuperOrderError
│   ├── ForeverOrderError
│   ├── ConditionalTriggerError
│   ├── ExitAllError
│   └── DhanIdentityError
```

### 2.2 Greenfield Exception Hierarchy

```
TradeXV2Error (root)
├── ConfigError
├── DataError
├── ValidationError
└── BrokerError
    ├── RetryableError
    │   └── NetworkError
    ├── NonRetryableError
    ├── BrokerServerError
    ├── OrderRejectedError
    ├── RateLimitError
    ├── CircuitOpenError
    ├── AuthenticationError
    ├── TokenRateLimitError
    ├── InstrumentNotFoundError
    ├── NotSupportedError
    └── BrokerDegradedError

OrderStateError (from order_lifecycle.py)
```

### 2.3 Exception Mapping

| Archive Exception | Greenfield Equivalent | Gap |
|-------------------|----------------------|-----|
| DhanError | Not defined | ❌ Missing |
| OrderError | Not defined | ❌ Missing |
| SuperOrderError | Not defined | ❌ Missing |
| ForeverOrderError | Not defined | ❌ Missing |
| ConditionalTriggerError | Not defined | ❌ Missing |
| ExitAllError | Not defined | ❌ Missing |
| DhanIdentityError | Not defined | ❌ Missing |

**Recommendation:**
- Add Dhan-specific exceptions to greenfield
- Map archive exceptions to greenfield hierarchy
- Ensure all exceptions have error codes

## 3. Race Conditions Inventory

### 3.1 Concurrent Modify/Cancel

**Scenario:**
```
Thread 1: modify_order(order_id="123", quantity=200)
Thread 2: cancel_order(order_id="123")

Timeline:
T1: modify request sent → [IN_FLIGHT]
T2: cancel request sent → [IN_FLIGHT]
T3: modify response received → order modified
T4: cancel response received → order cancelled

Result: Order modified then immediately cancelled
```

**Archive Mitigation:**
- No explicit mitigation
- Relies on broker-side ordering
- Last write wins

**Greenfield Mitigation:**
- No explicit mitigation
- Relies on broker-side ordering
- Post-cancel race check in `cancel_order()`

**Recommended Solution:**
```python
class OrderLockManager:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
    
    async def with_order_lock(self, order_id: str, operation: Callable):
        if order_id not in self._locks:
            self._locks[order_id] = asyncio.Lock()
        
        async with self._locks[order_id]:
            return await operation()

# Usage
async def modify_order(order_id, **changes):
    return await lock_manager.with_order_lock(
        order_id,
        lambda: executor.modify_order(order_id, **changes)
    )
```

### 3.2 Duplicate Order IDs

**Scenario:**
```
Client 1: place_order(correlation_id="abc-123")
Client 2: place_order(correlation_id="abc-123")

Timeline:
T1: Client 1 checks idempotency cache → MISS
T2: Client 2 checks idempotency cache → MISS
T3: Client 1 places order → order_id="456"
T4: Client 2 places order → order_id="789"
T5: Client 1 caches response
T6: Client 2 caches response (overwrites)

Result: Two orders placed with same correlation_id
```

**Archive Mitigation:**
```python
with self._idempotency.lock(correlation_id):
    cached = self._idempotency.get(correlation_id)
    if cached is not None:
        return cached
    # Place order
    response = self._client.post("/orders", json=payload)
    self._idempotency.put(correlation_id, response)
    return response
```

**Greenfield Mitigation:**
```python
if self._idempotency and correlation_id:
    if not self._idempotency.check_and_set(correlation_id):
        return OrderResponse.already_executed(correlation_id)
```

**Gap Analysis:**
- ✅ Archive has atomic lock
- ⚠️ Greenfield has check_and_set (may not be atomic)
- ❌ No distributed lock for multi-instance deployment

**Recommended Solution:**
```python
class DistributedIdempotencyCache:
    def __init__(self, redis_client):
        self._redis = redis_client
    
    async def check_and_set(self, correlation_id: str) -> bool:
        """Atomic check-and-set using Redis SETNX."""
        key = f"idempotency:{correlation_id}"
        result = await self._redis.set(key, "1", nx=True, ex=3600)
        return result is not None  # True if set, False if exists
```

### 3.3 Post-Cancel Race

**Scenario:**
```
T1: cancel_order(order_id="123") → request sent
T2: Exchange fills order → status=FILLED
T3: Cancel response received → success
T4: get_order(order_id="123") → status=FILLED

Result: Cancel appeared successful but order was filled
```

**Archive Mitigation:**
```python
def cancel_order(self, order_id: str) -> OrderResponse:
    data = self._client.delete(f"/orders/{order_id}")
    # Check broker response status
    broker_status = str(data.get("status", "")).lower()
    success = broker_status in {"success", "ok"}
    if success:
        return R.ok(order_id=order_id, status=OrderStatus.CANCELLED)
    return R.fail(...)
```

**Greenfield Mitigation:**
```python
def cancel_order(self, order_id: str) -> OrderResponse:
    endpoint = ENDPOINTS["cancel_order"].format(order_id=order_id)
    self._client.post(endpoint)
    
    existing = self.get_order(order_id)
    if existing and existing.status == OrderStatus.FILLED:
        logger.warning(
            "Post-cancel race: order %s already FILLED before cancel took effect",
            order_id,
        )
        return OrderResponse(
            order_id=order_id,
            success=False,
            message="Order was already FILLED (post-cancel race)",
            error_code="ORDER_ALREADY_FILLED",
        )
    
    return OrderResponse(order_id=order_id, success=True)
```

**Gap Analysis:**
- ✅ Greenfield has explicit post-cancel race check
- ⚠️ Archive relies on broker response
- ❌ No event emitted for race condition

**Recommended Solution:**
```python
def cancel_order(self, order_id: str) -> OrderResponse:
    # Send cancel
    response = self._client.post(endpoint)
    
    # Verify status
    order = self.get_order(order_id)
    
    if order and order.status == OrderStatus.FILLED:
        # Emit race condition event
        event_bus.publish(DomainEvent(
            event_type="ORDER_CANCEL_RACE",
            data={"order_id": order_id, "actual_status": "FILLED"},
        ))
        return OrderResponse(
            success=False,
            message="Order was already FILLED",
            error_code="ORDER_ALREADY_FILLED",
        )
    
    return OrderResponse(success=True)
```

### 3.4 WebSocket vs REST Race

**Scenario:**
```
T1: WebSocket receives order update → status=FILLED
T2: REST API returns order → status=OPEN
T3: Local state inconsistent

Result: WebSocket and REST disagree on order status
```

**Mitigation:**
```python
class OrderStateResolver:
    def __init__(self):
        self._last_update_time: dict[str, datetime] = {}
    
    def resolve(self, order_id: str, ws_status: str, rest_status: str, ws_time: datetime, rest_time: datetime):
        """Use timestamp to determine which is newer."""
        if ws_time > rest_time:
            return ws_status
        return rest_status
```

## 4. Recovery Paths

### 4.1 Network Failure During Order Placement

**Failure:**
```
Client → POST /orders → [NETWORK_ERROR] → No response
```

**Recovery Path:**
```python
def place_order_with_recovery(request):
    try:
        response = client.post("/orders", json=payload)
        return response
    except NetworkError as e:
        # Check if order was placed
        order = find_order_by_correlation_id(request.correlation_id)
        if order:
            return OrderResponse(
                order_id=order.order_id,
                success=True,
                status=order.status,
            )
        
        # Retry with same correlation_id
        try:
            response = client.post("/orders", json=payload)
            return response
        except NetworkError:
            return OrderResponse(
                success=False,
                message="Network error after retry",
                error_code="NETWORK_ERROR",
            )
```

### 4.2 Partial Fill Handling

**Scenario:**
```
Order: BUY 100 @ 100
Fill 1: 30 @ 100 → status=PARTIALLY_FILLED
Fill 2: [NETWORK_ERROR] → Unknown if remaining 70 filled
```

**Recovery Path:**
```python
def handle_partial_fill(order_id):
    # Query order status
    order = get_order(order_id)
    
    if order.status == OrderStatus.PARTIALLY_FILLED:
        # Wait for more fills
        return {"status": "waiting", "filled_quantity": order.filled_quantity}
    
    elif order.status == OrderStatus.FILLED:
        # Order complete
        return {"status": "complete", "filled_quantity": order.filled_quantity}
    
    elif order.status == OrderStatus.OPEN:
        # Still waiting for fills
        return {"status": "waiting", "filled_quantity": order.filled_quantity}
    
    elif order.status in (OrderStatus.CANCELLED, OrderStatus.PARTIALLY_CANCELLED):
        # Order cancelled
        return {"status": "cancelled", "filled_quantity": order.filled_quantity}
```

### 4.3 Rejection Handling

**Scenario:**
```
Order placed → status=REJECTED → reason="Insufficient margin"
```

**Recovery Path:**
```python
def handle_rejection(order_id):
    order = get_order(order_id)
    
    if order.status == OrderStatus.REJECTED:
        # Parse rejection reason
        reason = order.message
        
        if "margin" in reason.lower():
            # Notify user to add funds
            notify_user("Insufficient margin", order_id)
        
        elif "invalid" in reason.lower():
            # Log validation error
            logger.error(f"Order validation failed: {reason}")
        
        elif "risk" in reason.lower():
            # Notify risk manager
            notify_risk_manager(order_id, reason)
        
        # Emit rejection event
        event_bus.publish(DomainEvent(
            event_type="ORDER_REJECTED",
            data={"order_id": order_id, "reason": reason},
        ))
```

### 4.4 Broker Degradation

**Scenario:**
```
Broker API → [5xx_ERRORS] → Circuit breaker opens
```

**Recovery Path:**
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self._failure_count = 0
        self._state = "CLOSED"
        self._last_failure_time = None
    
    def call(self, func, *args, **kwargs):
        if self._state == "OPEN":
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = "HALF_OPEN"
            else:
                raise CircuitOpenError()
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        self._failure_count = 0
        self._state = "CLOSED"
    
    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
```

## 5. Idempotency Concerns

### 5.1 Order Placement Idempotency

**Problem:**
```
Client sends place_order() twice with same correlation_id
Expected: Only one order placed
```

**Archive Solution:**
```python
with self._idempotency.lock(correlation_id):
    cached = self._idempotency.get(correlation_id)
    if cached is not None:
        return cached
    # Place order
    response = self._client.post("/orders", json=payload)
    self._idempotency.put(correlation_id, response)
    return response
```

**Greenfield Solution:**
```python
if self._idempotency and correlation_id:
    if not self._idempotency.check_and_set(correlation_id):
        return OrderResponse.already_executed(correlation_id)
```

**Gap Analysis:**
- ✅ Archive has atomic lock
- ⚠️ Greenfield check_and_set may not be atomic
- ❌ No distributed lock for multi-instance deployment

**Recommended Solution:**
```python
class IdempotencyCache:
    def __init__(self, redis_client):
        self._redis = redis_client
    
    async def check_and_set(self, correlation_id: str) -> bool:
        """Atomic check-and-set using Redis SETNX."""
        key = f"idempotency:{correlation_id}"
        result = await self._redis.set(key, "1", nx=True, ex=3600)
        return result is not None
    
    async def get(self, correlation_id: str) -> OrderResponse | None:
        """Get cached response."""
        key = f"idempotency:{correlation_id}"
        data = await self._redis.get(key)
        if data:
            return OrderResponse.from_json(data)
        return None
    
    async def put(self, correlation_id: str, response: OrderResponse):
        """Cache response."""
        key = f"idempotency:{correlation_id}"
        await self._redis.set(key, response.to_json(), ex=3600)
```

### 5.2 Order Modification Idempotency

**Problem:**
```
Client sends modify_order() twice with same parameters
Expected: Order modified only once
```

**Current Solution:**
- No idempotency for modifications
- Broker handles duplicate modifications

**Recommended Solution:**
```python
def modify_order_with_idempotency(order_id, changes, idempotency_key):
    # Check if modification already applied
    cached = idempotency_cache.get(idempotency_key)
    if cached:
        return cached
    
    # Apply modification
    response = executor.modify_order(order_id, **changes)
    
    # Cache result
    idempotency_cache.put(idempotency_key, response)
    return response
```

### 5.3 Order Cancellation Idempotency

**Problem:**
```
Client sends cancel_order() twice
Expected: Order cancelled only once, second call returns success
```

**Current Solution:**
- Broker handles duplicate cancellations
- Returns success if already cancelled

**Recommended Solution:**
```python
def cancel_order_with_idempotency(order_id):
    # Check current status
    order = get_order(order_id)
    
    if order.status in (OrderStatus.CANCELLED, OrderStatus.PARTIALLY_CANCELLED):
        # Already cancelled
        return OrderResponse(success=True, message="Already cancelled")
    
    if order.status == OrderStatus.FILLED:
        # Cannot cancel filled order
        return OrderResponse(
            success=False,
            message="Order already FILLED",
            error_code="ORDER_ALREADY_FILLED",
        )
    
    # Send cancel
    return executor.cancel_order(order_id)
```

## 6. Payload Invariant Violations

### 6.1 Invalid Security ID

**Violation:**
```python
payload = {
    "securityId": "INVALID_ID",  # Should be digit string
    "exchangeSegment": "NSE_EQ",
}
```

**Archive Detection:**
```python
def assert_valid_security_id(security_id: Any, *, context: str = "") -> None:
    if security_id is None or security_id == "":
        raise DhanIdentityError(f"{context}: Invalid security_id: empty")
    if isinstance(security_id, bool):
        raise DhanIdentityError(f"{context}: Invalid security_id: bool")
    if isinstance(security_id, int):
        if security_id <= 0:
            raise DhanIdentityError(f"{context}: Invalid security_id: non-positive")
    elif isinstance(security_id, str):
        stripped = security_id.strip()
        if not stripped.isdigit():
            raise DhanIdentityError(f"{context}: Invalid security_id: non-digit")
        if int(stripped) <= 0:
            raise DhanIdentityError(f"{context}: Invalid security_id: non-positive")
```

**Greenfield Detection:**
```python
def assert_valid_dhan_payload(payload: dict, *, context: str = "") -> None:
    # Similar checks in invariants.py
    pass
```

**Consequences:**
- Broker rejects order
- OrderError raised
- User sees rejection

**Prevention:**
- Validate at payload build time
- Use DhanInstrumentRef carrier
- Assert before sending

### 6.2 Invalid Exchange Segment

**Violation:**
```python
payload = {
    "securityId": "12345",
    "exchangeSegment": "INVALID_SEGMENT",  # Not a Dhan segment
}
```

**Archive Detection:**
```python
def assert_dhan_segment(segment: str, *, context: str = "") -> None:
    if not isinstance(segment, str) or not segment:
        raise DhanIdentityError(f"{context}: segment must be non-empty string")
    if not is_dhan_segment(segment):
        raise DhanIdentityError(f"{context}: segment {segment!r} is not a Dhan segment")
```

**Consequences:**
- Broker rejects order
- OrderError raised
- User sees rejection

**Prevention:**
- Validate segment at instrument resolution
- Use DhanInstrumentRef carrier
- Assert before sending

### 6.3 Missing Required Fields

**Violation:**
```python
payload = {
    "securityId": "12345",
    # Missing exchangeSegment
}
```

**Archive Detection:**
```python
def assert_dhan_payload(payload: dict, *, context: str = "") -> None:
    if "securityId" in payload and "exchangeSegment" in payload:
        assert_dhan_identity(payload["securityId"], payload["exchangeSegment"])
    elif "securityId" in payload:
        # Security ID present but no segment
        assert_dhan_identity(payload["securityId"], "", context=context)
```

**Consequences:**
- Broker rejects order
- OrderError raised

**Prevention:**
- Build payload with all required fields
- Use payload builder helper
- Assert before sending

## 7. Secret Exposure Risks

### 7.1 Access Token in Logs

**Risk:**
```python
logger.info(f"Placing order with token: {access_token}")
```

**Mitigation:**
```python
logger.info("Placing order")  # Never log token
```

**Current Status:**
- ✅ Archive does not log tokens
- ✅ Greenfield does not log tokens

### 7.2 Client ID in Error Messages

**Risk:**
```python
raise OrderError(f"Order failed for client {client_id}: {error}")
```

**Mitigation:**
```python
raise OrderError(f"Order failed: {error}")  # Don't expose client_id
```

**Current Status:**
- ⚠️ Archive includes client_id in payloads
- ⚠️ Greenfield includes client_id in payloads
- ✅ Not exposed in error messages

### 7.3 API Keys in Exception Traces

**Risk:**
```python
try:
    api_call()
except Exception as e:
    logger.error(f"API call failed: {e}", exc_info=True)
    # Exception trace may contain API keys in request headers
```

**Mitigation:**
```python
try:
    api_call()
except Exception as e:
    # Sanitize exception before logging
    sanitized_error = sanitize_exception(e)
    logger.error(f"API call failed: {sanitized_error}")
```

**Current Status:**
- ⚠️ Archive logs exceptions with exc_info
- ⚠️ Greenfield logs exceptions with exc_info
- ❌ No sanitization

**Recommended Solution:**
```python
def sanitize_exception(exc: Exception) -> str:
    """Remove sensitive data from exception message."""
    message = str(exc)
    # Remove API keys, tokens, etc.
    message = re.sub(r'api[_-]?key[=:]\s*\S+', 'api_key=***', message, flags=re.IGNORECASE)
    message = re.sub(r'token[=:]\s*\S+', 'token=***', message, flags=re.IGNORECASE)
    return message
```

### 7.4 Order Payload in Logs

**Risk:**
```python
logger.info(f"Order payload: {payload}")
# Payload may contain client_id, security_id, etc.
```

**Mitigation:**
```python
logger.info("Order payload built")  # Don't log full payload
logger.debug(f"Payload: {payload}")  # Only in debug mode
```

**Current Status:**
- ⚠️ Archive logs some payload fields
- ⚠️ Greenfield logs some payload fields
- ✅ Sensitive fields not logged

## 8. Greenfield Gaps Summary

### 8.1 Critical Gaps

1. **No Super Orders (Bracket Orders)**
   - Missing adapter
   - Missing entities
   - Missing state machine

2. **No Forever Orders (GTT/OCO)**
   - Missing adapter
   - Missing entities
   - Missing state machine

3. **Incomplete Conditional Triggers**
   - No entities (uses dict)
   - No validation
   - No modification support

4. **No Dhan-Specific Exceptions**
   - Missing DhanError hierarchy
   - No error code mapping

5. **No Status Mapper**
   - Missing Dhan-specific status mapping
   - No registration with global registry

### 8.2 Moderate Gaps

1. **No Configurable Timeouts**
   - No per-operation timeout
   - No retry policy

2. **No Distributed Idempotency**
   - No Redis-based cache
   - No multi-instance support

3. **No Circuit Breaker**
   - No degradation handling
   - No health checks

4. **No Order Lock Manager**
   - No concurrent modify/cancel protection
   - Race conditions possible

5. **No Exception Sanitization**
   - Sensitive data may leak in logs

### 8.3 Minor Gaps

1. **No Kill Switch**
   - Missing emergency stop

2. **No Slice Orders**
   - Missing large order splitting

3. **No Trade History**
   - Missing historical trade queries

4. **No State Transition Events**
   - No audit trail for state changes

### 8.4 Recommendations

**Priority 1 (Critical):**
1. Implement Super Orders adapter
2. Implement Forever Orders adapter
3. Enhance Conditional Triggers
4. Add Dhan exception hierarchy
5. Add Status Mapper

**Priority 2 (Moderate):**
1. Add configurable timeouts
2. Implement distributed idempotency cache
3. Add circuit breaker
4. Implement order lock manager
5. Add exception sanitization

**Priority 3 (Minor):**
1. Add kill switch
2. Add slice orders
3. Add trade history
4. Add state transition events

## 9. Conclusion

The greenfield implementation has a solid foundation with:
- ✅ Explicit state machine
- ✅ Service layer with validation
- ✅ Port-based architecture
- ✅ Basic order management

However, it lacks several critical features:
- ❌ Advanced order types (Super, Forever)
- ❌ Dhan-specific exceptions
- ❌ Status mapping
- ❌ Timeout/retry policies
- ❌ Distributed idempotency
- ❌ Circuit breaker

**Next Steps:**
1. Implement missing order types
2. Add exception hierarchy
3. Add status mapper
4. Implement timeout/retry policies
5. Add distributed idempotency cache
6. Add circuit breaker for degradation handling
