# Phase 4 Source Audit — Dhan Market Data

## Executive Summary

Phase 4 (Market Data) implements real-time market data streaming and REST market data retrieval for the Dhan broker. The archive implementation provides a comprehensive WebSocket-based streaming system with three distinct feed types (market feed, depth-20, depth-200) plus REST endpoints for on-demand market data. The greenfield implementation establishes the foundation with basic streaming and market data adapters but lacks the depth feed infrastructure and advanced connection management present in the archive.

**Archive Scope:** 7 files, ~3,239 lines
**Greenfield Scope:** 5 files, ~515 lines
**Coverage Gap:** ~84% of archive functionality not yet ported

---

## Archive Files

| File | Lines | Purpose |
|------|-------|---------|
| `depth_feed_base.py` | 735 | Base class for binary WebSocket depth feeds with reconnection, subscription management, and packet parsing |
| `websocket/market_feed.py` | 1032 | Main market feed WebSocket manager using Dhan SDK with quote/depth streaming, reconnection backoff, and admission control |
| `subscription_engine.py` | 281 | Central subscription orchestration with instrument ref-counting and callback management |
| `connection.py` | 511 | Master connection orchestrator wiring all adapters, managing lifecycle, and providing factory methods |
| `market_data.py` | 187 | REST API adapter for LTP, quote, depth, OHLC, and batch operations |
| `depth_20.py` | 89 | Thin subclass implementing 20-level depth feed (50 instruments per connection) |
| `depth_200.py` | 320 | Thin subclass implementing 200-level depth feed (1 instrument per connection) with connection pooling |

**Total Archive Lines:** 3,239

---

## Greenfield Files

| File | Lines | Purpose |
|------|-------|---------|
| `market_data.py` | 90 | REST API adapter for LTP, quote, and depth (no OHLC or batch operations) |
| `streaming.py` | 117 | Basic WebSocket streaming adapter for market feed using websocket-client library |
| `depth20.py` | 112 | Depth-20 WebSocket adapter with binary packet parsing (placeholder implementation) |
| `depth200.py` | 107 | Depth-200 WebSocket adapter with binary packet parsing (placeholder implementation) |
| `order_stream.py` | 102 | Order update WebSocket stream with JSON parsing |

**Total Greenfield Lines:** 515

---

## Archived Test Files

| File | Lines | Coverage |
|------|-------|----------|
| `websocket/tests/test_connection_manager.py` | 241 | WebSocket connection manager singleton enforcement, thread safety, token propagation, lifecycle management |

**Test Coverage Areas:**
- Singleton pattern for market feed and order stream
- Thread-safe connection creation
- Access token propagation
- Connection statistics tracking
- Start/stop lifecycle
- Instrument subscription

---

## Key Symbols and Classes

### Archive

#### `depth_feed_base.py`
- **`BinaryDepthFeed`** — Base class for depth WebSocket feeds
  - Inherits: `ReconnectingServiceMixin`, `ManagedService`
  - Key methods:
    - `start()` / `stop()` — Lifecycle management
    - `subscribe(instruments)` / `unsubscribe(instruments)` — Subscription management
    - `on_depth(callback)` — Callback registration
    - `register_symbol(security_id, symbol)` — Symbol mapping
    - `_websocket_loop()` — Main reconnection loop
    - `_connect_and_run()` — WebSocket connection establishment
    - `_build_ws_url()` — URL construction with auth
    - `_websocket_handler()` — Async message processing
    - `_send_subscription(instruments)` — JSON subscription payload
    - `_process_binary_message(data)` — Binary packet routing
    - `_parse_depth_packet(data, response_code, header_value)` — Depth level extraction
    - `_dispatch_depth(depth_data)` — Cache update and callback invocation
    - `update_token(new_token)` — Token refresh hook
    - `health()` — Health status reporting
  - Key attributes:
    - `total_slots` — Depth levels per side (20 or 200)
    - `subs_per_connection` — Instrument limit (50 or 1)
    - `ENDPOINT`, `REQUEST_CODE`, `DEPTH_TYPE` — Wire format identifiers
    - `header_carries_security_id` — Header layout flag
    - `_depth_cache` — Per-security_id bid/ask cache
    - `_published_depths`, `_dropped_depths` — Telemetry counters

#### `websocket/market_feed.py`
- **`DhanMarketFeed`** — SDK-based market feed wrapper
  - Inherits: `ReconnectingServiceMixin`, `ManagedService`
  - Key methods:
    - `start()` / `stop()` — Lifecycle
    - `subscribe(instruments)` / `unsubscribe(instruments)` — Subscription
    - `on_quote(callback)` / `on_depth(callback)` — Callback registration
    - `off_quote(callback)` / `off_depth(callback)` — Callback removal
    - `update_token(access_token)` — Token refresh
    - `_run()` — Main reconnection loop with admission control
    - `_build_sdk_feed_locked()` — SDK feed factory
    - `_on_connect(feed)` — Connection handler with subscription replay
    - `_on_message(feed, data)` — Message dispatcher (quote/depth/full)
    - `_transform_quote(data)` — Quote normalization
    - `_transform_depth(data)` — Depth normalization
    - `_publish_tick(quote)` — Strict-mode tick publishing
    - `_publish_depth(depth)` — Strict-mode depth publishing
    - `_backfill_gap(disconnect_time)` — Reconnect backfill
    - `health()` — Health status with staleness detection
  - Key attributes:
    - `MAX_INSTRUMENTS = 1000` — SDK limit
    - `_admission` — Host-wide connection gate
    - `_backfill_callback` — Gap-fill hook
    - `_last_tick_time` — Per-symbol tick tracking
    - `_published_ticks`, `_dropped_ticks` — Telemetry

#### `subscription_engine.py`
- **`SubscriptionEngine`** — Central subscription orchestrator
  - Key methods:
    - `subscribe_market(symbol, exchange, mode, on_tick)` — Market subscription with ref-counting
    - `unsubscribe_market(symbol, exchange, on_tick)` — Market unsubscription
    - `subscribe_instruments(instrument_keys, modes, on_tick)` — Batch subscription
    - `unsubscribe_instruments(instrument_keys, on_tick)` — Batch unsubscription
    - `subscribe_order(on_order)` — Order stream subscription
    - `unsubscribe_order(on_order)` — Order stream unsubscription
    - `subscription_count()` / `callback_count()` — Observability
    - `instrument_snapshot()` — Instrument ref snapshot
  - Key attributes:
    - `_instrument_refs` — Per-instrument reference count
    - `_instrument_modes` — Per-instrument subscription mode
    - `_market_callbacks` — Per-instrument callback registry
    - `_order_callbacks` — Order stream callback registry

#### `connection.py`
- **`DhanConnection`** — Master connection orchestrator
  - Key methods:
    - `load_instruments(source, use_cache)` — Instrument loading
    - `create_market_feed(access_token, instruments, access_token_fn)` — Market feed factory
    - `create_order_stream(access_token, access_token_fn)` — Order stream factory
    - `create_depth_20_feed(access_token, instrument)` — Depth-20 factory
    - `create_depth_200_feed(access_token, instrument)` — Depth-200 factory
    - `create_polling_feed(instruments, interval_seconds)` — Polling feed factory
    - `register_token_receiver(receiver)` — Token refresh registration
    - `broadcast_token(new_token)` — Token broadcast
    - `close()` — Lifecycle shutdown
  - Key properties:
    - `market_feed`, `order_stream`, `depth_20_feed`, `depth_200_feed`, `polling_feed` — Feed accessors
    - `market_data`, `historical`, `orders`, `portfolio`, etc. — REST adapter accessors
    - `subscription_engine` — Subscription orchestrator
    - `identity` — Symbol resolver wrapper

#### `market_data.py`
- **`MarketDataAdapter`** — REST market data adapter
  - Key methods:
    - `get_ltp(symbol, exchange)` — Last traded price
    - `get_quote(symbol, exchange)` — Full quote
    - `get_depth(symbol, exchange)` — 5-level depth
    - `get_ohlc(symbol, exchange)` — OHLC data
    - `get_batch_ltp(symbols, exchange)` — Batch LTP
    - `get_batch_quote(symbols, exchange)` — Batch quote
  - Key attributes:
    - `_client` — HTTP client
    - `_identity` — Symbol resolver

#### `depth_20.py`
- **`DhanDepth20Feed`** — 20-level depth feed
  - Inherits: `BinaryDepthFeed`
  - Key methods:
    - `latest_depth(security_id)` — Cached depth lookup
  - Key attributes:
    - `MAX_INSTRUMENTS = 50`
    - `TOTAL_DEPTH_PACKETS = 20`
    - `ENDPOINT = "wss://depth-api-feed.dhan.co/twentydepth"`

#### `depth_200.py`
- **`DhanDepth200Feed`** — 200-level depth feed
  - Inherits: `BinaryDepthFeed`
  - Key methods:
    - `subscribe(instrument)` — Single-instrument subscription (overrides base)
    - `latest_depth()` — Cached depth lookup (no security_id arg)
  - Key attributes:
    - `MAX_INSTRUMENTS = 1`
    - `TOTAL_DEPTH_PACKETS = 200`
    - `ENDPOINT = "wss://full-depth-api.dhan.co/twohundreddepth"`

- **`Depth200ConnectionPool`** — Connection pool for multiple depth-200 feeds
  - Key methods:
    - `get_feed(instrument)` — Feed factory with rate limiting
    - `has_feed(instrument)` — Feed existence check
    - `remove_feed(instrument)` — Feed removal
    - `get_all_feeds()` — Feed snapshot
    - `close_all()` — Pool shutdown

### Greenfield

#### `market_data.py`
- **`DhanMarketData`** — REST market data adapter
  - Key methods:
    - `ltp(symbol, exchange)` — Last traded price
    - `quote(symbol, exchange)` — Full quote
    - `depth(symbol, exchange)` — 5-level depth
  - Missing:
    - `get_ohlc()` — OHLC data
    - `get_batch_ltp()` — Batch LTP
    - `get_batch_quote()` — Batch quote

#### `streaming.py`
- **`DhanStreaming`** — Market feed WebSocket adapter
  - Inherits: `BaseWebSocketStreaming`
  - Key methods:
    - `subscribe(symbol, exchange)` / `unsubscribe(symbol, exchange)` — Subscription
    - `update_token(new_token)` — Token refresh
    - `_get_access_token()` — Token resolution (static or callable)
    - `_get_ws_headers()` — Auth headers
    - `_build_subscribe_message(keys)` / `_build_unsubscribe_message(keys)` — JSON payloads
    - `_parse_tick(data)` — Tick normalization
  - Key attributes:
    - `WS_URL = "wss://api.dhan.co/v2/ws/feed"`
  - Missing:
    - SDK integration
    - Admission control
    - Reconnection backoff
    - Staleness detection
    - Backfill on reconnect
    - Strict-mode publishing

#### `depth20.py`
- **`DhanDepth20Stream`** — Depth-20 WebSocket adapter
  - Inherits: `BaseWebSocketStreaming`
  - Key methods:
    - `subscribe(symbol, exchange)` / `unsubscribe(symbol, exchange)` — Subscription
    - `update_token(new_token)` — Token refresh
    - `_build_subscribe_message(keys)` / `_build_unsubscribe_message(keys)` — JSON payloads
    - `_on_message(ws, message)` — Binary/JSON message handler (placeholder parsing)
  - Key attributes:
    - `WS_URL = "wss://depth-api-feed.dhan.co/twentydepth"`
    - `on_depth_update` — Callback hook
  - Missing:
    - Full binary packet parsing
    - Depth cache
    - Symbol registration
    - Subscription limit enforcement
    - Reconnection logic
    - Health reporting

#### `depth200.py`
- **`DhanDepth200Stream`** — Depth-200 WebSocket adapter
  - Inherits: `BaseWebSocketStreaming`
  - Key methods:
    - `subscribe(symbol, exchange)` / `unsubscribe(symbol, exchange)` — Subscription
    - `update_token(new_token)` — Token refresh
    - `_build_subscribe_message(keys)` / `_build_unsubscribe_message(keys)` — JSON payloads
    - `_on_message(ws, message)` — Binary/JSON message handler (placeholder parsing)
  - Key attributes:
    - `WS_URL = "wss://full-depth-api.dhan.co/twohundreddepth"`
    - `on_depth_update` — Callback hook
  - Missing:
    - Full binary packet parsing
    - Depth cache
    - Single-instrument enforcement
    - Connection pooling
    - Reconnection logic
    - Health reporting

#### `order_stream.py`
- **`DhanOrderStream`** — Order update WebSocket adapter
  - Inherits: `BaseWebSocketStreaming`
  - Key methods:
    - `update_token(new_token)` — Token refresh
    - `_build_subscribe_message(keys)` — Auth payload
    - `_build_unsubscribe_message(keys)` — Unsubscribe payload
    - `_on_message(ws, message)` — JSON message handler
    - `_parse_order_update(data)` — Order normalization
  - Key attributes:
    - `WS_ORDER_URL = "wss://api-order-update.dhan.co"`
    - `on_order_update` — Callback hook

---

## WebSocket Protocol Details

### Market Feed (SDK-based)

**URL:** `wss://api.dhan.co/v2/ws/feed` (inferred from archive SDK usage)

**Authentication:**
- Access token passed via SDK context
- SDK handles auth handshake internally

**Subscription Payload:**
```json
{
  "type": "subscribe",
  "instrumentKeys": ["NSE_EQ|RELIANCE", "NSE_FNO|NIFTY24JULFUT"]
}
```

**Unsubscription Payload:**
```json
{
  "type": "unsubscribe",
  "instrumentKeys": ["NSE_EQ|RELIANCE"]
}
```

**Message Types:**
- `"Ticker Data"` — LTP only
- `"Quote Data"` — Full quote
- `"Market Depth"` — Depth snapshot
- `"Full Data"` — Quote + depth
- `"Previous Close"`, `"OI Data"`, `"Market Status"` — Informational (ignored)

**Quote Payload (incoming):**
```json
{
  "type": "Quote Data",
  "security_id": "466583",
  "last_price": 2450.50,
  "open": 2430.00,
  "high": 2460.00,
  "low": 2425.00,
  "close": 2435.00,
  "volume": 1234567,
  "net_change": 15.50
}
```

**Depth Payload (incoming):**
```json
{
  "type": "Market Depth",
  "security_id": "466583",
  "last_price": 2450.50,
  "depth": {
    "bids": [
      {"price": 2450.00, "quantity": 100, "orders": 5},
      {"price": 2449.50, "quantity": 200, "orders": 8}
    ],
    "asks": [
      {"price": 2451.00, "quantity": 150, "orders": 6},
      {"price": 2451.50, "quantity": 250, "orders": 9}
    ]
  }
}
```

### Depth Feed (Binary)

**URLs:**
- Depth-20: `wss://depth-api-feed.dhan.co/twentydepth`
- Depth-200: `wss://full-depth-api.dhan.co/twohundreddepth`

**Authentication:**
```
wss://<endpoint>?token=<access_token>&clientId=<client_id>&authType=2
```

**Subscription Payload:**
```json
{
  "RequestCode": 23,
  "InstrumentCount": 1,
  "InstrumentList": [
    {
      "ExchangeSegment": "NSE_EQ",
      "SecurityId": "466583"
    }
  ]
}
```

**Binary Packet Structure:**

**Header (12 bytes):**
```
Offset  Size  Field              Notes
0       2     packet_type        Little-endian
2       1     response_code      41 = bid, 51 = ask
3       1     reserved
4       4     security_id        Depth-20 only
8       4     num_rows           Depth-200 only
```

**Depth Level (16 bytes each):**
```
Offset  Size  Field
0       8     price              Little-endian double
8       4     quantity           Little-endian uint32
12      4     orders             Little-endian uint32
```

**Packet Layout:**
```
[Header: 12 bytes][Level 0: 16 bytes][Level 1: 16 bytes]...[Level N: 16 bytes]
```

**Depth-20:**
- Max instruments: 50 per connection
- Depth levels: 20 per side
- Header carries `security_id` at offset 4
- Total packet size: 12 + (20 × 16) = 332 bytes

**Depth-200:**
- Max instruments: 1 per connection
- Depth levels: 200 per side
- Header carries `num_rows` at offset 8, `security_id` is implicit
- Total packet size: 12 + (200 × 16) = 3212 bytes

### Order Stream

**URL:** `wss://api-order-update.dhan.co`

**Authentication:**
```json
{
  "LoginReq": {
    "MsgCode": 42,
    "ClientId": "<client_id>",
    "Token": "<access_token>"
  },
  "UserType": "SELF"
}
```

**Order Payload (incoming):**
```json
{
  "orderId": "230703000000001",
  "dhanOrderId": "230703000000001",
  "orderStatus": "FILLED",
  "tradingSymbol": "RELIANCE",
  "exchange": "NSE",
  "transactionType": "BUY",
  "quantity": 10,
  "price": 2450.50,
  "orderType": "MARKET",
  "productType": "INTRADAY",
  "orderValidity": "DAY"
}
```

---

## Depth Feed Architecture

### Class Hierarchy

```
ReconnectingServiceMixin (mixin)
    ↓
ManagedService (interface)
    ↓
BinaryDepthFeed (base class)
    ├─ DhanDepth20Feed (20-level, 50 instruments)
    └─ DhanDepth200Feed (200-level, 1 instrument)
```

### BinaryDepthFeed Responsibilities

1. **WebSocket Lifecycle**
   - Thread-based async event loop
   - Auto-reconnection with exponential backoff
   - 429 rate-limit cooldown
   - Token refresh hook

2. **Subscription Management**
   - Instrument list tracking
   - Subscription limit enforcement
   - JSON subscription payload construction
   - Thread-safe subscription send via `asyncio.run_coroutine_threadsafe`

3. **Binary Packet Parsing**
   - Header extraction (response code, security_id/num_rows)
   - Depth level iteration (price, quantity, orders)
   - Quantity filter (> 0 only)
   - Side determination (bid/ask from response code)

4. **Depth Cache Management**
   - Per-security_id bid/ask cache
   - Merge bid/ask from separate packets
   - Thread-safe cache updates
   - Symbol resolution via `_sec_id_to_symbol` map

5. **Callback Dispatch**
   - Callback registration (`on_depth`)
   - Snapshot-and-iterate dispatch pattern
   - Exception isolation per callback
   - EventBus publishing with correlation IDs

6. **Health Reporting**
   - Thread alive status
   - Connection status
   - Reconnect count
   - Published/dropped depth counters
   - Last message age

### DhanDepth20Feed Specialization

- Endpoint: `wss://depth-api-feed.dhan.co/twentydepth`
- Max instruments: 50
- Depth levels: 20
- Header layout: `security_id` at offset 4
- `latest_depth(security_id)` — Direct cache lookup

### DhanDepth200Feed Specialization

- Endpoint: `wss://full-depth-api.dhan.co/twohundreddepth`
- Max instruments: 1
- Depth levels: 200
- Header layout: `num_rows` at offset 8, `security_id` implicit
- `subscribe(instrument)` — Overrides base to enforce single-instrument limit
- `latest_depth()` — Returns first cache entry (no security_id arg)
- `Depth200ConnectionPool` — Manages multiple feeds for multiple instruments

---

## Subscription Engine API

### Market Subscriptions

**`subscribe_market(symbol, exchange="NSE", mode="LTP", on_tick=None)`**
- Resolves symbol to (exchange, security_id)
- Creates/retrieves market feed
- Calls `feed.subscribe([(segment, sid, mode)])`
- Increments ref count for instrument
- Registers callback with Quote wrapping
- Connects feed if not connected
- Returns feed instance

**`unsubscribe_market(symbol, exchange="NSE", on_tick=None)`**
- Decrements ref count
- Removes callback
- If ref count reaches 0:
  - Calls `feed.unsubscribe([(segment, sid, mode)])`
  - Clears symbol tracking

**`subscribe_instruments(instrument_keys, modes, on_tick)`**
- Batch subscription for orchestrator paths
- Parses `"SYMBOL:EXCHANGE"` keys
- Delegates to `subscribe_market`

**`unsubscribe_instruments(instrument_keys, on_tick)`**
- Batch unsubscription
- Delegates to `unsubscribe_market`

### Order Stream Subscriptions

**`subscribe_order(on_order=None)`**
- Creates/retrieves order stream
- Registers callback
- Starts stream if not connected
- Returns stream instance

**`unsubscribe_order(on_order=None)`**
- Removes callback
- If no callbacks remain, clears registry

### Observability

**`subscription_count()`** — Number of unique instruments subscribed
**`callback_count()`** — Total number of registered callbacks
**`instrument_snapshot()`** — Dict of `"SYMBOL:EXCHANGE"` → ref count

---

## Connection Lifecycle States

### DhanMarketFeed States

1. **Initialized** — Instance created, not started
2. **Starting** — `start()` called, thread spawned
3. **Connecting** — WebSocket connection in progress
4. **Connected** — WebSocket connected, subscriptions active
5. **Stale** — Connected but no messages for `staleness_threshold` (default 60s)
6. **Disconnected** — WebSocket closed, reconnecting
7. **Admission Blocked** — Waiting for host-wide connection lock
8. **Cooldown** — Waiting for 429 rate-limit cooldown
9. **Stopped** — `stop()` called, thread joined

### BinaryDepthFeed States

1. **Initialized** — Instance created, not started
2. **Starting** — `start()` called, thread spawned
3. **Connecting** — WebSocket connection in progress
4. **Connected** — WebSocket connected, subscriptions active
5. **Disconnected** — WebSocket closed, reconnecting
6. **Cooldown** — Waiting for 429 rate-limit cooldown
7. **Stopped** — `stop()` called, thread joined

### Health States

- **HEALTHY** — Thread alive, connected, not stale
- **DEGRADED** — Thread alive but:
  - Not connected (reconnecting)
  - Admission blocked
  - Cooldown active
  - Stale (connected but no recent messages)
- **STOPPED** — Thread not alive

---

## Market Data REST API Methods

### Archive Implementation

**`get_ltp(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/ltp`
- Payload: `{segment: [security_id]}`
- Returns: `Decimal` (last traded price)

**`get_quote(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/quote`
- Payload: `{segment: [security_id]}`
- Returns: `Quote` (ltp, open, high, low, close, volume, change)

**`get_depth(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/quote`
- Payload: `{segment: [security_id]}`
- Returns: `MarketDepth` (5-level bids/asks)

**`get_ohlc(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/ohlc`
- Payload: `{segment: [security_id]}`
- Returns: `dict` (open, high, low, close)

**`get_batch_ltp(symbols, exchange="NSE")`**
- Endpoint: `POST /marketfeed/ltp`
- Payload: `{segment: [sid1, sid2, ...]}`
- Returns: `dict[str, Decimal]` (symbol → ltp)

**`get_batch_quote(symbols, exchange="NSE")`**
- Endpoint: `POST /marketfeed/quote`
- Payload: `{segment: [sid1, sid2, ...]}`
- Returns: `dict[str, Quote]` (symbol → quote)

### Greenfield Implementation

**`ltp(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/ltp`
- Payload: `{segment: [security_id]}`
- Returns: `Decimal` (last traded price)
- **Difference:** More flexible response parsing (handles multiple response formats)

**`quote(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/quote`
- Payload: `{segment: [security_id]}`
- Returns: `Quote` (via `map_quote`)
- **Difference:** Uses mapper function for normalization

**`depth(symbol, exchange="NSE")`**
- Endpoint: `POST /marketfeed/quote`
- Payload: `{segment: [security_id]}`
- Returns: `MarketDepth` (via `map_depth`)
- **Difference:** Uses mapper function for normalization

**Missing in Greenfield:**
- `get_ohlc()` — OHLC data
- `get_batch_ltp()` — Batch LTP
- `get_batch_quote()` — Batch quote

---

## Summary

Phase 4 archive provides a production-grade market data system with:
- Three WebSocket feed types (market, depth-20, depth-200)
- Advanced connection management (admission control, staleness detection, backfill)
- Binary packet parsing for depth feeds
- Subscription orchestration with ref-counting
- Comprehensive health reporting
- REST market data with batch operations

Greenfield implementation provides:
- Basic WebSocket streaming (market feed)
- Placeholder depth feed adapters (incomplete binary parsing)
- Basic REST market data (no batch operations)
- Order stream adapter

**Critical gaps:**
1. Depth feed binary packet parsing incomplete
2. No subscription engine for orchestration
3. No connection pooling for depth-200
4. No admission control or staleness detection
5. No reconnect backfill
6. No strict-mode publishing
7. No health reporting
8. Missing REST batch operations and OHLC
