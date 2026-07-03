# Phase 4 Runtime Sequences — Dhan Market Data

## Overview

This document details the runtime execution flows for market data operations in both the archive and greenfield implementations. Each flow is presented with sequence diagrams, step-by-step explanations, and a comparative analysis highlighting gaps in the greenfield implementation.

---

## 1. WebSocket Connection Establishment Flow

### Archive: DhanMarketFeed (SDK-based)

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│   Caller    │  │DhanMarketFeed│  │  Admission   │  │ Dhan SDK   │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘
       │                │                 │                 │
       │ start()        │                 │                 │
       ├───────────────>│                 │                 │
       │                │                 │                 │
       │                │ try_acquire()   │                 │
       │                ├────────────────>│                 │
       │                │                 │                 │
       │                │    lock_held?   │                 │
       │                │<────────────────┤                 │
       │                │                 │                 │
       │                │ _build_sdk_feed_locked()          │
       │                ├──────────────────────────────────>│
       │                │                 │                 │
       │                │    feed object  │                 │
       │                │<──────────────────────────────────┤
       │                │                 │                 │
       │                │ Spawn daemon thread (_run)        │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │                 │   feed.run()    │
       │                │                 │   (blocking)    │
       │                │                 │────────────────>│
       │                │                 │                 │
       │                │                 │   WebSocket     │
       │                │                 │   handshake     │
       │                │                 │────────────────>│
       │                │                 │                 │
       │                │                 │   _on_connect() │
       │                │<──────────────────────────────────┤
       │                │                 │                 │
       │                │ _is_connected = True              │
       │                │ _connected_at = now()             │
       │                │ _reconnect_count = 0              │
       │                │                 │                 │
       │                │ Replay subscriptions              │
       │                │ feed.subscribe_symbols()          │
       │                │──────────────────────────────────>│
       │                │                 │                 │
```

**Sequence Steps:**

1. **Caller invokes `start()`** — Idempotent; no-op if thread already alive
2. **Admission control** — `try_acquire()` obtains host-wide connection lock (file-based)
3. **Build SDK feed** — `_build_sdk_feed_locked()` creates fresh SDK feed instance with callbacks
4. **Spawn daemon thread** — Thread runs `_run()` method with reconnection loop
5. **SDK feed.run()** — Blocking call that drives WebSocket event loop
6. **WebSocket handshake** — SDK connects to `wss://api.dhan.co/v2/ws/feed` with auth
7. **`_on_connect()` callback** — SDK invokes on successful connection
8. **Update state** — Set `_is_connected = True`, record connection time, reset reconnect count
9. **Replay subscriptions** — Call `feed.subscribe_symbols()` with `_subscribed_instruments` set
10. **Admission cooldown check** — Clear 429 cooldown on successful connection

### Archive: BinaryDepthFeed (Custom WebSocket)

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│   Caller    │  │BinaryDepth   │  │  Admission   │  │ websockets │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘
       │                │                 │                 │
       │ start()        │                 │                 │
       ├───────────────>│                 │                 │
       │                │                 │                 │
       │                │ Spawn daemon thread               │
       │                │ (_websocket_loop)                 │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │ _connect_and_run()                │
       │                │                 │                 │
       │                │ seconds_until_connect_allowed()   │
       │                ├────────────────>│                 │
       │                │                 │                 │
       │                │    cooldown?    │                 │
       │                │<────────────────┤                 │
       │                │                 │                 │
       │                │ _build_ws_url() │                 │
       │                │                 │                 │
       │                │ websockets.connect(url)           │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │    WebSocket    │                 │
       │                │    handshake    │                 │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │ _websocket_handler()              │
       │                │                 │                 │
       │                │ _is_connected = True              │
       │                │ _reconnect_count = 0              │
       │                │                 │                 │
       │                │ clear_cooldown()│                 │
       │                ├────────────────>│                 │
       │                │                 │                 │
       │                │ If subscriptions exist:           │
       │                │ _send_subscription()              │
       │                │──────────────────────────────────>│
       │                │                 │                 │
```

**Sequence Steps:**

1. **Caller invokes `start()`** — Idempotent; no-op if thread alive
2. **Spawn daemon thread** — Thread runs `_websocket_loop()` with auto-reconnect
3. **`_connect_and_run()`** — Create new asyncio event loop for this thread
4. **Admission cooldown check** — `seconds_until_connect_allowed()` checks 429 cooldown
5. **Build WebSocket URL** — `_build_ws_url()` appends `?token=...&clientId=...&authType=2`
6. **Connect via websockets library** — Async `websockets.connect(url)` performs handshake
7. **`_websocket_handler()`** — Async message processing loop
8. **Update state** — Set `_is_connected = True`, reset reconnect count
9. **Clear cooldown** — `clear_cooldown()` resets 429 tracking
10. **Replay subscriptions** — If `_subscriptions` non-empty, send JSON subscription message

### Greenfield: DhanStreaming (websocket-client)

```
┌─────────────┐  ┌──────────────┐  ┌────────────┐
│   Caller    │  │DhanStreaming │  │ websocket  │
└──────┬──────┘  └──────┬───────┘  └─────┬──────┘
       │                │                │
       │ start()        │                │
       ├───────────────>│                │
       │                │                │
       │                │ Spawn daemon thread (_run)
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ _run() loop    │               │
       │                │                │               │
       │                │ WebSocketApp(  │               │
       │                │   url,         │               │
       │                │   headers,     │               │
       │                │   on_open,     │               │
       │                │   on_message,  │               │
       │                │   on_error,    │               │
       │                │   on_close     │               │
       │                │ )              │               │
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ ws.run_forever()│              │
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ WebSocket      │               │
       │                │ handshake      │               │
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ _on_open(ws)   │               │
       │                │<───────────────────────────────┤
       │                │                │               │
       │                │ Send subscriptions             │
       │                │ _send_subscribe(subs)          │
       │                │───────────────────────────────>│
       │                │                │               │
```

**Sequence Steps:**

1. **Caller invokes `start()`** — Sets `_running = True`, spawns daemon thread
2. **`_run()` loop** — Reconnection loop with exponential backoff
3. **Create WebSocketApp** — Synchronous websocket-client library with callbacks
4. **`ws.run_forever()`** — Blocking call that drives WebSocket event loop
5. **WebSocket handshake** — Connect to `wss://api.dhan.co/v2/ws/feed` with headers
6. **`_on_open(ws)` callback** — Invoked on successful connection
7. **Send subscriptions** — `_send_subscribe()` sends JSON subscription message for all tracked subscriptions

### Comparison: Connection Establishment

| Aspect | Archive (MarketFeed) | Archive (DepthFeed) | Greenfield |
|--------|---------------------|---------------------|------------|
| **Library** | Dhan SDK (asyncio) | websockets (asyncio) | websocket-client (sync) |
| **Threading** | Daemon thread per feed | Daemon thread per feed | Daemon thread per feed |
| **Event Loop** | SDK-managed | Thread-local asyncio | websocket-client managed |
| **Admission Control** | Host-wide file lock | 429 cooldown only | None |
| **URL Construction** | SDK handles auth | Manual `?token=...` | Headers `access-token`, `client-id` |
| **Reconnection** | Exponential backoff + jitter | Exponential backoff | Exponential backoff |
| **Staleness Detection** | Yes (configurable threshold) | No | No |
| **Max Reconnect Guard** | Yes (50 attempts, then cooldown) | No | No |
| **Subscription Replay** | Yes (on reconnect) | Yes (on reconnect) | Yes (on reconnect) |
| **Token Refresh** | Yes (close socket, reconnect) | Yes (close socket, reconnect) | Yes (update token, no reconnect) |

**Greenfield Gaps:**
- No admission control (host-wide lock or 429 cooldown)
- No staleness detection
- No max reconnect guard
- Token refresh doesn't trigger reconnection
- No backfill on reconnect

---

## 2. Subscription Flow (Subscribe/Unsubscribe)

### Archive: DhanMarketFeed

```
┌─────────────┐  ┌──────────────────┐  ┌─────────────┐  ┌────────────┐
│   Caller    │  │SubscriptionEngine│ │DhanMarketFeed│  │ Dhan SDK   │
└──────┬──────┘  └────────┬─────────┘  └──────┬──────┘  └─────┬──────┘
       │                  │                   │               │
       │ subscribe_market │                   │               │
       │ (symbol,exchange)│                   │               │
       ├─────────────────>│                   │               │
       │                  │                   │               │
       │                  │ resolve(symbol, exchange)         │
       │                  │──────────────────────────────────>│
       │                  │                   │               │
       │                  │ (segment, sid, mode)              │
       │                  │<──────────────────────────────────┤
       │                  │                   │               │
       │                  │ _ensure_market_feed()             │
       │                  │──────────────────>│               │
       │                  │                   │               │
       │                  │    feed instance  │               │
       │                  │<──────────────────┤               │
       │                  │                   │               │
       │                  │ feed.subscribe([(segment,sid,mode)])
       │                  │──────────────────>│               │
       │                  │                   │               │
       │                  │                   │ _to_sdk_instruments()
       │                  │                   │               │
       │                  │                   │ Dedup check   │
       │                  │                   │ (already subscribed?)
       │                  │                   │               │
       │                  │                   │ Limit check   │
       │                  │                   │ (total <= 1000?)
       │                  │                   │               │
       │                  │                   │ If connected: │
       │                  │                   │ feed.subscribe_symbols()
       │                  │                   │──────────────>│
       │                  │                   │               │
       │                  │                   │ Else:         │
       │                  │                   │ Queue for reconnect
       │                  │                   │               │
       │                  │ Increment ref count               │
       │                  │ Register callback │               │
       │                  │                   │               │
       │                  │ If not connected: │               │
       │                  │ feed.connect()    │               │
       │                  │──────────────────>│               │
       │                  │                   │               │
```

**Sequence Steps:**

1. **Caller invokes `subscribe_market(symbol, exchange, mode, on_tick)`** — Symbol-centric API
2. **Resolve symbol** — `SymbolResolver.resolve()` returns instrument ref with (exchange, security_id)
3. **Ensure market feed** — `_ensure_market_feed()` creates feed if not exists
4. **Subscribe to feed** — `feed.subscribe([(segment, sid, mode)])` with SDK tuple format
5. **Convert to SDK format** — `_to_sdk_instruments()` converts to SDK's expected tuple format
6. **Deduplication check** — Skip if already in `_subscribed_instruments` set
7. **Limit check** — Raise `ValueError` if total would exceed `MAX_INSTRUMENTS` (1000)
8. **Send subscription (if connected)** — `feed.subscribe_symbols()` sends JSON to WebSocket
9. **Queue for reconnect (if disconnected)** — Add to `_subscribed_instruments` set for replay
10. **Increment ref count** — Track how many callers want this instrument
11. **Register callback** — Wrap `on_tick` to convert dict → Quote, store in `_market_callbacks`
12. **Connect feed (if not connected)** — `feed.connect()` triggers connection establishment

### Archive: BinaryDepthFeed

```
┌─────────────┐  ┌──────────────┐  ┌────────────┐
│   Caller    │  │BinaryDepth   │  │ WebSocket  │
└──────┬──────┘  └──────┬───────┘  └─────┬──────┘
       │                │                │
       │ subscribe      │                │
       │ (instruments)  │                │
       ├───────────────>│                │
       │                │                │
       │                │ Dedup check    │
       │                │ (already subscribed?)
       │                │                │
       │                │ Limit check    │
       │                │ (total <= subs_per_connection?)
       │                │                │
       │                │ Extend _subscriptions list
       │                │                │
       │                │ If connected and ws exists:
       │                │ _send_subscription(new_instruments)
       │                │───────────────────────────────>│
       │                │                │               │
       │                │                │ JSON payload: │
       │                │                │ {RequestCode:23,
       │                │                │  InstrumentCount:N,
       │                │                │  InstrumentList:[...]}
       │                │                │               │
```

**Sequence Steps:**

1. **Caller invokes `subscribe(instruments)`** — Accepts list of (exchange, security_id) tuples or single tuple
2. **Deduplication check** — Filter out instruments already in `_subscriptions`
3. **Limit check** — Raise `ValueError` if total would exceed `subs_per_connection` (50 or 1)
4. **Extend subscriptions list** — Add new instruments to `_subscriptions`
5. **Send subscription (if connected)** — `_send_subscription()` constructs and sends JSON payload
6. **JSON payload construction** — `{"RequestCode": 23, "InstrumentCount": N, "InstrumentList": [...]}`
7. **Thread-safe send** — Use `asyncio.run_coroutine_threadsafe()` to send from sync caller thread to async WebSocket loop
8. **Track send failures** — Register done callback to increment `_dropped_depths` on send failure

### Greenfield: DhanStreaming

```
┌─────────────┐  ┌──────────────┐  ┌────────────┐
│   Caller    │  │DhanStreaming │  │ WebSocket  │
└──────┬──────┘  └──────┬───────┘  └─────┬──────┘
       │                │                │
       │ subscribe      │                │
       │ (symbol,       │                │
       │  exchange)     │                │
       ├───────────────>│                │
       │                │                │
       │                │ EXCHANGE_MAP.get(exchange)
       │                │ segment = "NSE_EQ"
       │                │                │
       │                │ key = f"{segment}|{symbol}"
       │                │                │
       │                │ super().subscribe(key)
       │                │                │
       │                │ _subscriptions.add(key)
       │                │                │
       │                │ If ws and _running:
       │                │ _send_subscribe([key])
       │                │───────────────────────────────>│
       │                │                │               │
       │                │                │ JSON payload: │
       │                │                │ {type:"subscribe",
       │                │                │  instrumentKeys:[...]}
       │                │                │               │
```

**Sequence Steps:**

1. **Caller invokes `subscribe(symbol, exchange)`** — Symbol-centric API
2. **Map exchange to segment** — `EXCHANGE_MAP.get(exchange)` returns `"NSE_EQ"`, `"NSE_FNO"`, etc.
3. **Construct key** — Format as `"{segment}|{symbol}"` (e.g., `"NSE_EQ|RELIANCE"`)
4. **Delegate to base class** — `super().subscribe(key)` calls `BaseWebSocketStreaming.subscribe()`
5. **Add to subscriptions set** — `_subscriptions.add(key)` tracks subscribed instruments
6. **Send subscription (if connected)** — `_send_subscribe([key])` sends JSON to WebSocket
7. **JSON payload construction** — `{"type": "subscribe", "instrumentKeys": [...]}`

### Unsubscribe Flow

**Archive (DhanMarketFeed):**
```python
# Via SubscriptionEngine
engine.unsubscribe_market("RELIANCE", "NSE", on_tick=callback)
  → Decrement ref count
  → If ref count == 0:
      feed.unsubscribe([(segment, sid, mode)])
      feed.clear_symbol_tracking(symbol)
  → Remove callback from registry
```

**Archive (BinaryDepthFeed):**
```python
feed.unsubscribe([(exchange, security_id)])
  → Remove from _subscriptions list
  → Evict from _depth_cache
  → (No wire message sent; Dhan depth WS doesn't support unsubscribe)
```

**Greenfield (DhanStreaming):**
```python
streaming.unsubscribe("RELIANCE", "NSE")
  → Construct key = "NSE_EQ|RELIANCE"
  → super().unsubscribe(key)
      → _subscriptions.discard(key)
      → If ws and _running:
          _send_unsubscribe([key])
              → Send JSON: {"type": "unsubscribe", "instrumentKeys": [...]}
```

### Comparison: Subscription Flow

| Aspect | Archive (MarketFeed) | Archive (DepthFeed) | Greenfield |
|--------|---------------------|---------------------|------------|
| **API Style** | Symbol-centric (via SubscriptionEngine) | Tuple-centric (exchange, security_id) | Symbol-centric |
| **Instrument Format** | SDK tuple `(segment, sid, mode)` | Tuple `(exchange, security_id)` | String key `"segment|symbol"` |
| **Deduplication** | Yes (set-based) | Yes (list filter) | Yes (set-based) |
| **Limit Enforcement** | Yes (1000 instruments) | Yes (50 or 1 instrument) | No |
| **Ref Counting** | Yes (via SubscriptionEngine) | No | No |
| **Subscription Replay** | Yes (on reconnect) | Yes (on reconnect) | Yes (on reconnect) |
| **Unsubscribe Wire Message** | Yes (SDK handles) | No (Dhan depth WS doesn't support) | Yes (JSON unsubscribe) |
| **Callback Management** | Yes (Quote wrapping) | Yes (MarketDepth callbacks) | Yes (tick callbacks) |
| **Symbol Resolution** | Yes (via SymbolResolver) | No (caller provides security_id) | No (caller provides symbol) |

**Greenfield Gaps:**
- No subscription limit enforcement
- No ref counting for shared subscriptions
- No symbol resolution (caller must provide correct symbol)
- No batch subscription API
- No callback wrapping (raw dict, not Quote entity)

---

## 3. Depth Feed Data Flow

### Archive: BinaryDepthFeed (Binary Packet Parsing)

```
┌────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐
│  WebSocket │  │_websocket    │  │_process      │  │_parse_depth  │  │_dispatch   │
│  (async)   │  │_handler()    │  │_binary       │  │_packet()     │  │_depth()    │
└─────┬──────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘
      │                │                 │                 │                │
      │ Binary message │                 │                 │                │
      │ (bytes)        │                 │                 │                │
      ├───────────────>│                 │                 │                │
      │                │                 │                 │                │
      │                │ _process_binary_message(data)     │                │
      │                │────────────────>│                 │                │
      │                │                 │                 │                │
      │                │                 │ Length check    │                │
      │                │                 │ (>= 12 bytes?)  │                │
      │                │                 │                 │                │
      │                │                 │ Extract response_code (offset 2)│
      │                │                 │                 │                │
      │                │                 │ Extract header_value            │
      │                │                 │ (depth-20: offset 4 = sec_id)   │
      │                │                 │ (depth-200: offset 8 = num_rows)│
      │                │                 │                 │                │
      │                │                 │ _note_message_received()        │
      │                │                 │                 │                │
      │                │                 │ If response_code in (41, 51):   │
      │                │                 │ _parse_depth_packet()           │
      │                │                 │────────────────>│                │
      │                │                 │                 │                │
      │                │                 │                 │ Iterate depth levels
      │                │                 │                 │ (20 or 200)   │
      │                │                 │                 │                │
      │                │                 │                 │ For each level:│
      │                │                 │                 │   offset = 12 + (i * 16)
      │                │                 │                 │   price = unpack("<d", offset)
      │                │                 │                 │   quantity = unpack("<I", offset+8)
      │                │                 │                 │   orders = unpack("<I", offset+12)
      │                │                 │                 │   if quantity > 0:
      │                │                 │                 │     append DepthLevel
      │                │                 │                 │                │
      │                │                 │                 │ Return {levels, side, header_value}
      │                │                 │<────────────────┤                │
      │                │                 │                 │                │
      │                │                 │ _dispatch_depth(depth_data)     │
      │                │                 │────────────────────────────────>│
      │                │                 │                 │                │
      │                │                 │                 │                │ Resolve security_id
      │                │                 │                 │                │ (depth-20: header_value)
      │                │                 │                 │                │ (depth-200: implicit from subscription)
      │                │                 │                 │                │
      │                │                 │                 │                │ Update _depth_cache
      │                │                 │                 │                │ (merge bid/ask sides)
      │                │                 │                 │                │
      │                │                 │                 │                │ Build MarketDepth entity
      │                │                 │                 │                │
      │                │                 │                 │                │ Invoke callbacks
      │                │                 │                 │                │ (snapshot-and-iterate)
      │                │                 │                 │                │
      │                │                 │                 │                │ Publish to EventBus
      │                │                 │                 │                │ (DEPTH_20 or DEPTH_200 event)
      │                │                 │                 │                │
```

**Sequence Steps:**

1. **WebSocket receives binary message** — Async `_websocket_handler()` receives bytes via `ws.recv()`
2. **Route to binary processor** — `_process_binary_message(data)` handles binary packets
3. **Length validation** — Reject packets < 12 bytes (header size)
4. **Extract response code** — `data[2]` indicates bid (41) or ask (51)
5. **Extract header value** — Depth-20: `security_id` at offset 4; Depth-200: `num_rows` at offset 8
6. **Track message receipt** — `_note_message_received()` updates last message timestamp
7. **Parse depth packet** — `_parse_depth_packet()` iterates depth levels
8. **Iterate depth levels** — Loop `total_slots` times (20 or 200)
9. **Extract level data** — For each level at `offset = 12 + (i * 16)`:
   - `price` — 8-byte double at offset
   - `quantity` — 4-byte uint32 at offset + 8
   - `orders` — 4-byte uint32 at offset + 12
10. **Filter zero-quantity levels** — Only append `DepthLevel` if `quantity > 0`
11. **Return parsed data** — `{levels: [...], side: "bids"|"asks", header_value: int}`
12. **Dispatch depth** — `_dispatch_depth(depth_data)` updates cache and notifies subscribers
13. **Resolve security_id** — Depth-20: use `header_value`; Depth-200: resolve from subscription
14. **Update depth cache** — Merge bid/ask into `_depth_cache[security_id]` (separate packets per side)
15. **Build MarketDepth entity** — Combine cached bids/asks into `MarketDepth` object
16. **Invoke callbacks** — Snapshot callback list, iterate, call each with `MarketDepth`
17. **Publish to EventBus** — Emit `DomainEvent` with event name `"DEPTH_20"` or `"DEPTH_200"`

### Greenfield: DhanDepth20Stream (Placeholder Implementation)

```
┌────────────┐  ┌──────────────┐  ┌──────────────┐
│  WebSocket │  │_on_message   │  │on_depth      │
│  (sync)    │  │()            │  │_update       │
└─────┬──────┘  └──────┬───────┘  └──────┬───────┘
      │                │                 │
      │ Binary message │                 │
      │ (bytes)        │                 │
      ├───────────────>│                 │
      │                │                 │
      │                │ isinstance(message, bytes)?
      │                │                 │
      │                │ struct.unpack("<HBBII", message[:12])
      │                │ header = (packet_type, response_code, reserved, security_id, num_rows)
      │                │                 │
      │                │ data = {"raw_header": header, "is_binary": True}
      │                │                 │
      │                │ on_depth_update(data)
      │                │────────────────>│
      │                │                 │
```

**Sequence Steps:**

1. **WebSocket receives binary message** — `_on_message(ws, message)` invoked by websocket-client
2. **Type check** — `isinstance(message, bytes)` determines binary vs JSON
3. **Parse header (placeholder)** — `struct.unpack("<HBBII", message[:12])` extracts first 12 bytes
4. **Build placeholder data** — `{"raw_header": header, "is_binary": True}` (no depth level parsing)
5. **Invoke callback** — `on_depth_update(data)` passes raw header to caller

### Comparison: Depth Data Flow

| Aspect | Archive (BinaryDepthFeed) | Greenfield |
|--------|---------------------------|------------|
| **Library** | websockets (asyncio) | websocket-client (sync) |
| **Message Handling** | Async `_websocket_handler()` | Sync `_on_message()` |
| **Binary Parsing** | Full depth level extraction (20 or 200 levels) | Header only (placeholder) |
| **Depth Level Parsing** | Yes (price, quantity, orders per level) | No |
| **Quantity Filter** | Yes (skip zero-quantity levels) | No |
| **Depth Cache** | Yes (per-security_id bid/ask merge) | No |
| **Symbol Resolution** | Yes (security_id → symbol mapping) | No |
| **Entity Construction** | Yes (MarketDepth with DepthLevel list) | No (raw header dict) |
| **Callback Type** | `Callable[[MarketDepth], None]` | `Callable[[dict], Any]` |
| **EventBus Publishing** | Yes (DEPTH_20 or DEPTH_200 events) | No |
| **Telemetry** | Yes (published/dropped counters) | No |

**Greenfield Gaps:**
- Binary packet parsing incomplete (header only, no depth levels)
- No depth cache or bid/ask merge logic
- No symbol resolution
- No MarketDepth entity construction
- No EventBus publishing
- No telemetry or health reporting
- No quantity filtering

---

## 4. Reconnection Flow

### Archive: DhanMarketFeed (with Staleness Detection)

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│   WebSocket │  │DhanMarketFeed│  │  Admission   │  │ Dhan SDK   │
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘
       │                │                 │                 │
       │ Connection     │                 │                 │
       │ closed         │                 │                 │
       ├───────────────>│                 │                 │
       │                │                 │                 │
       │                │ _on_close(feed) │                 │
       │                │<──────────────────────────────────┤
       │                │                 │                 │
       │                │ _is_connected = False             │
       │                │ _disconnect_time = now()          │
       │                │                 │                 │
       │                │ _run() loop continues             │
       │                │                 │                 │
       │                │ Admission check │                 │
       │                │ try_acquire()   │                 │
       │                ├────────────────>│                 │
       │                │                 │                 │
       │                │ 429 cooldown check                │
       │                │ seconds_until_connect_allowed()   │
       │                ├────────────────>│                 │
       │                │                 │                 │
       │                │ Max reconnect check               │
       │                │ (reconnect_count >= 50?)          │
       │                │                 │                 │
       │                │ Staleness check │                 │
       │                │ (last_message_age > 60s?)         │
       │                │                 │                 │
       │                │ If stale:       │                 │
       │                │   Close old feed│                 │
       │                │   feed.close_connection()         │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │   Backoff       │                 │
       │                │   delay = min(delay * 2, 30) + random(0, 1)
       │                │   sleep(delay)  │                 │
       │                │                 │                 │
       │                │ Rebuild SDK feed│                 │
       │                │ _build_sdk_feed_locked()          │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │    new feed     │                 │
       │                │<──────────────────────────────────┤
       │                │                 │                 │
       │                │ feed.run()      │                 │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │ _on_connect(feed)                 │
       │                │<──────────────────────────────────┤
       │                │                 │                 │
       │                │ Replay subscriptions              │
       │                │ feed.subscribe_symbols()          │
       │                │──────────────────────────────────>│
       │                │                 │                 │
       │                │ Backfill gap (if reconnect)       │
       │                │ _backfill_gap(_disconnect_time)   │
       │                │                 │                 │
```

**Sequence Steps:**

1. **WebSocket connection closed** — Server drops connection or network failure
2. **`_on_close(feed)` callback** — SDK invokes on connection close
3. **Update state** — Set `_is_connected = False`, record `_disconnect_time`
4. **`_run()` loop continues** — Reconnection loop doesn't exit on close
5. **Admission check** — `try_acquire()` re-checks host-wide connection lock
6. **429 cooldown check** — `seconds_until_connect_allowed()` checks rate-limit cooldown
7. **Max reconnect guard** — If `reconnect_count >= 50`, enter cooldown (300s default)
8. **Staleness check** — If `last_message_age > 60s`, force reconnect (stale connection)
9. **Close old feed** — `feed.close_connection()` cleans up poisoned transport
10. **Exponential backoff** — `delay = min(delay * 2, 30) + random(0, 1)` with jitter
11. **Rebuild SDK feed** — `_build_sdk_feed_locked()` creates fresh SDK feed instance
12. **`feed.run()`** — New connection attempt
13. **`_on_connect(feed)` callback** — Invoked on successful reconnection
14. **Replay subscriptions** — `feed.subscribe_symbols()` re-subscribes all instruments
15. **Backfill gap** — `_backfill_gap()` fetches missed bars via REST and publishes as TICK events

### Archive: BinaryDepthFeed (Simpler Reconnection)

```
┌─────────────┐  ┌──────────────┐  ┌────────────┐
│   WebSocket │  │BinaryDepth   │  │ websockets │
└──────┬──────┘  └──────┬───────┘  └─────┬──────┘
       │                │                │
       │ Connection     │                │
       │ closed         │                │
       ├───────────────>│                │
       │                │                │
       │                │ ConnectionClosed exception
       │                │                │
       │                │ _is_connected = False
       │                │ _reconnect_count += 1
       │                │                │
       │                │ Backoff       │
       │                │ delay = min(delay * 2, 30)
       │                │ sleep(delay)  │
       │                │                │
       │                │ 429 cooldown check
       │                │ seconds_until_connect_allowed()
       │                │                │
       │                │ _build_ws_url()
       │                │                │
       │                │ websockets.connect(url)
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ _websocket_handler()           │
       │                │                │               │
       │                │ _is_connected = True           │
       │                │ _reconnect_count = 0           │
       │                │                │               │
       │                │ Replay subscriptions           │
       │                │ _send_subscription(_subscriptions)
       │                │───────────────────────────────>│
       │                │                │               │
```

**Sequence Steps:**

1. **WebSocket connection closed** — `websockets.ConnectionClosed` exception raised
2. **Update state** — Set `_is_connected = False`, increment `_reconnect_count`
3. **Exponential backoff** — `delay = min(delay * 2, 30)` (no jitter)
4. **429 cooldown check** — `seconds_until_connect_allowed()` checks rate-limit cooldown
5. **Build WebSocket URL** — `_build_ws_url()` with fresh token
6. **Connect via websockets** — Async `websockets.connect(url)` performs handshake
7. **`_websocket_handler()`** — Async message processing loop
8. **Update state** — Set `_is_connected = True`, reset `_reconnect_count = 0`
9. **Replay subscriptions** — `_send_subscription(_subscriptions)` re-subscribes all instruments

### Greenfield: DhanStreaming (Basic Reconnection)

```
┌─────────────┐  ┌──────────────┐  ┌────────────┐
│   WebSocket │  │DhanStreaming │  │ websocket  │
└──────┬──────┘  └──────┬───────┘  └─────┬──────┘
       │                │                │
       │ Connection     │                │
       │ closed         │                │
       ├───────────────>│                │
       │                │                │
       │                │ _on_close(ws, close_status_code, close_msg)
       │                │<───────────────────────────────┤
       │                │                │               │
       │                │ _on_disconnect callback         │
       │                │                │               │
       │                │ _run() loop continues           │
       │                │                │               │
       │                │ Backoff       │                │
       │                │ delay = min(delay * 2, max_delay)
       │                │ sleep(delay)  │                │
       │                │                │               │
       │                │ WebSocketApp(...)              │
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ ws.run_forever()               │
       │                │───────────────────────────────>│
       │                │                │               │
       │                │ _on_open(ws)   │               │
       │                │<───────────────────────────────┤
       │                │                │               │
       │                │ Replay subscriptions           │
       │                │ _send_subscribe(_subscriptions)│
       │                │───────────────────────────────>│
       │                │                │               │
```

**Sequence Steps:**

1. **WebSocket connection closed** — `_on_close()` callback invoked
2. **`_on_disconnect` callback** — Notify caller of disconnection
3. **`_run()` loop continues** — Reconnection loop doesn't exit on close
4. **Exponential backoff** — `delay = min(delay * 2, max_delay)` (default max 60s)
5. **Create new WebSocketApp** — Fresh instance with callbacks
6. **`ws.run_forever()`** — Blocking call drives WebSocket event loop
7. **`_on_open(ws)` callback** — Invoked on successful reconnection
8. **Replay subscriptions** — `_send_subscribe(_subscriptions)` re-subscribes all instruments

### Comparison: Reconnection Flow

| Aspect | Archive (MarketFeed) | Archive (DepthFeed) | Greenfield |
|--------|---------------------|---------------------|------------|
| **Backoff Strategy** | Exponential + jitter | Exponential | Exponential |
| **Max Backoff** | 30s | 30s | 60s (configurable) |
| **Max Reconnect Guard** | Yes (50 attempts) | No | No |
| **Reconnect Cooldown** | Yes (300s after max) | No | No |
| **Staleness Detection** | Yes (60s threshold) | No | No |
| **Admission Control** | Yes (host-wide lock) | 429 cooldown only | No |
| **Token Refresh** | Yes (close socket, reconnect) | Yes (close socket, reconnect) | Yes (update token, no reconnect) |
| **Feed Rebuild** | Yes (fresh SDK feed) | No (reuse same feed) | No (reuse same WebSocketApp) |
| **Subscription Replay** | Yes (on reconnect) | Yes (on reconnect) | Yes (on reconnect) |
| **Backfill on Reconnect** | Yes (REST gap fill) | No | No |
| **Telemetry** | Yes (reconnect_count, staleness) | Yes (reconnect_count) | No |

**Greenfield Gaps:**
- No max reconnect guard or cooldown
- No staleness detection
- No admission control
- No feed rebuild (may reuse poisoned transport)
- No backfill on reconnect
- No telemetry

---

## 5. Connection Admission Control Flow

### Archive: DhanMarketFeed (Host-wide Lock)

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│DhanMarketFeed│ │  Admission   │  │  Lock File   │  │   Other    │
│              │  │   Gate       │  │  (fcntl)     │  │  Process   │
└──────┬───────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘
       │                 │                │                 │
       │ _run() loop     │                │                 │
       │                 │                │                 │
       │ try_acquire()   │                │                 │
       ├────────────────>│                │                 │
       │                 │                │                 │
       │                 │ fcntl.flock()  │                 │
       │                 ├───────────────>│                 │
       │                 │                │                 │
       │                 │    Success?    │                 │
       │                 │<───────────────┤                 │
       │                 │                │                 │
       │  lock_held = True               │                 │
       │<────────────────┤                │                 │
       │                 │                │                 │
       │ Continue with connection        │                 │
       │                 │                │                 │
       │ ... later ...   │                │                 │
       │                 │                │                 │
       │ Other process tries try_acquire()                 │
       │                 │                │<────────────────┤
       │                 │                │                 │
       │                 │ fcntl.flock()  │                 │
       │                 ├───────────────>│                 │
       │                 │                │                 │
       │                 │    Blocked     │                 │
       │                 │<───────────────┤                 │
       │                 │                │                 │
       │  lock_held = False              │                 │
       │<────────────────┤                │                 │
       │                 │                │                 │
       │ _admission_blocked = True       │                 │
       │ sleep(5s)       │                │                 │
       │ retry           │                │                 │
       │                 │                │                 │
       │ ... later ...   │                │                 │
       │                 │                │                 │
       │ 429 rate limit  │                │                 │
       │ from server     │                │                 │
       ├────────────────>│                │                 │
       │                 │                │                 │
       │ record_rate_limit_cooldown()    │                 │
       ├────────────────>│                │                 │
       │                 │                │                 │
       │                 │ cooldown_until = now() + 300s   │
       │                 │                │                 │
       │ ... later ...   │                │                 │
       │                 │                │                 │
       │ seconds_until_connect_allowed() │                 │
       ├────────────────>│                │                 │
       │                 │                │                 │
       │  cooldown_wait > 0              │                 │
       │<────────────────┤                │                 │
       │                 │                │                 │
       │ sleep(cooldown_wait)            │                 │
       │ retry           │                │                 │
       │                 │                │                 │
       │ ... on exit ... │                │                 │
       │                 │                │                 │
       │ release()       │                │                 │
       ├────────────────>│                │                 │
       │                 │                │                 │
       │                 │ fcntl.flock(UNLOCK)             │
       │                 ├───────────────>│                 │
       │                 │                │                 │
```

**Sequence Steps:**

1. **`_run()` loop starts** — Before connecting, check admission gate
2. **`try_acquire()`** — Attempt to obtain host-wide connection lock
3. **`fcntl.flock()`** — File-based lock on `/tmp/dhan_market_feed_<client_id>.lock`
4. **Lock acquired** — Set `lock_held = True`, proceed with connection
5. **Other process blocked** — Second process calling `try_acquire()` blocks on `fcntl.flock()`
6. **`_admission_blocked = True`** — Second process sets blocked flag
7. **Sleep and retry** — Second process sleeps 5s, retries `try_acquire()`
8. **429 rate limit from server** — WebSocket handshake rejected with 429 status
9. **`record_rate_limit_cooldown()`** — Set `cooldown_until = now() + 300s`
10. **`seconds_until_connect_allowed()`** — Check if cooldown period has elapsed
11. **Sleep cooldown** — If `cooldown_wait > 0`, sleep for that duration
12. **`release()` on exit** — Release lock file on `_run()` loop exit

### Greenfield: No Admission Control

```
┌─────────────┐  ┌──────────────┐
│DhanStreaming │  │   WebSocket  │
└──────┬──────┘  └──────┬───────┘
       │                │
       │ _run() loop    │
       │                │
       │ No admission check
       │                │
       │ WebSocketApp(...)
       │───────────────────────────────>│
       │                │               │
       │ ws.run_forever()              │
       │───────────────────────────────>│
       │                │               │
```

**Sequence Steps:**

1. **`_run()` loop starts** — No admission check
2. **Create WebSocketApp** — Connect immediately
3. **No rate-limit handling** — 429 errors not tracked

### Comparison: Admission Control

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| **Host-wide Lock** | Yes (fcntl file lock) | No |
| **Single Connection Enforcement** | Yes (per account) | No |
| **429 Rate-limit Tracking** | Yes (300s cooldown) | No |
| **Admission Blocked State** | Yes (health reporting) | No |
| **Lock File Path** | `/tmp/dhan_market_feed_<client_id>.lock` | N/A |
| **Cross-process Safety** | Yes | No |

**Greenfield Gaps:**
- No host-wide connection lock
- No 429 rate-limit tracking
- No admission blocked state
- Multiple processes can connect simultaneously (violates Dhan API limits)

---

## 6. Market Data REST API Flow

### Archive: MarketDataAdapter

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│   Caller    │  │MarketData    │  │  Symbol     │  │DhanHttpClient│
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘
       │                │                 │                 │
       │ get_ltp(symbol, exchange)        │                 │
       ├───────────────>│                 │                 │
       │                │                 │                 │
       │                │ _resolve_and_segment(symbol, exchange)
       │                │────────────────>│                 │
       │                │                 │                 │
       │                │    ref (security_id, segment)     │
       │                │<────────────────┤                 │
       │                │                 │                 │
       │                │ assert_dhan_identity(sid, segment)
       │                │                 │                 │
       │                │ POST /marketfeed/ltp              │
       │                │ {segment: [sid]}│                 │
       │                │─────────────────────────────────>│
       │                │                 │                 │
       │                │    response     │                 │
       │                │<─────────────────────────────────┤
       │                │                 │                 │
       │                │ Extract entry from response       │
       │                │ data["data"][segment][str(sid)]   │
       │                │                 │                 │
       │                │ Decimal(entry["last_price"])      │
       │                │                 │                 │
       │  Decimal       │                 │                 │
       │<───────────────┤                 │                 │
       │                │                 │                 │
```

**Sequence Steps:**

1. **Caller invokes `get_ltp(symbol, exchange)`** — Symbol-centric API
2. **Resolve symbol** — `_resolve_and_segment()` returns `(ref, segment)` via `DhanIdentityProvider`
3. **Extract security_id and segment** — `ref.security_id`, `ref.exchange_segment`
4. **Assert identity** — `assert_dhan_identity(sid, segment)` validates payload
5. **POST request** — `client.post("/marketfeed/ltp", json={segment: [sid]})`
6. **Extract response** — `data["data"][segment][str(sid)]`
7. **Parse last_price** — `Decimal(str(entry["last_price"]))`
8. **Return Decimal** — Last traded price

### Greenfield: DhanMarketData

```
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│   Caller    │  │DhanMarketData│  │DhanInstrument│  │DhanHttpClient│
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘
       │                │                 │                 │
       │ ltp(symbol, exchange)            │                 │
       ├───────────────>│                 │                 │
       │                │                 │                 │
       │                │ resolver.resolve(symbol, exchange)
       │                │────────────────>│                 │
       │                │                 │                 │
       │                │    ref (security_id, segment)     │
       │                │<────────────────┤                 │
       │                │                 │                 │
       │                │ sid = ref.security_id_int()       │
       │                │ segment = ref.exchange_segment    │
       │                │                 │                 │
       │                │ assert_valid_dhan_payload(payload)│
       │                │                 │                 │
       │                │ POST /marketfeed/ltp              │
       │                │ {segment: [sid]}│                 │
       │                │─────────────────────────────────>│
       │                │                 │                 │
       │                │    response     │                 │
       │                │<─────────────────────────────────┤
       │                │                 │                 │
       │                │ Flexible response parsing         │
       │                │ (handles multiple response formats)
       │                │                 │                 │
       │                │ Decimal(price)  │                 │
       │                │                 │                 │
       │  Decimal       │                 │                 │
       │<───────────────┤                 │                 │
       │                │                 │                 │
```

**Sequence Steps:**

1. **Caller invokes `ltp(symbol, exchange)`** — Symbol-centric API
2. **Resolve symbol** — `resolver.resolve()` returns instrument ref
3. **Extract security_id and segment** — `ref.security_id_int()`, `ref.exchange_segment`
4. **Assert payload validity** — `assert_valid_dhan_payload(payload)` validates request
5. **POST request** — `client.post(ENDPOINTS["ltp"], json={segment: [sid]})`
6. **Flexible response parsing** — Handles multiple response formats:
   - `feed[segment][str(sid)]`
   - `feed[str(sid)]`
   - `feed[f"{segment}:{sid}"]`
   - `feed[symbol]`
7. **Extract price** — `entry.get("last_price")` or `entry.get("lastPrice")`
8. **Return Decimal** — Last traded price

### Comparison: REST API Flow

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| **Symbol Resolution** | `DhanIdentityProvider` | `DhanInstrumentResolver` |
| **Payload Validation** | `assert_dhan_identity()` | `assert_valid_dhan_payload()` |
| **Response Parsing** | Strict (single format) | Flexible (multiple formats) |
| **Endpoint Paths** | Hard-coded strings | `ENDPOINTS` dict |
| **Methods** | `get_ltp`, `get_quote`, `get_depth`, `get_ohlc`, `get_batch_ltp`, `get_batch_quote` | `ltp`, `quote`, `depth` |
| **Batch Operations** | Yes | No |
| **OHLC** | Yes | No |
| **Entity Mapping** | Inline construction | `map_quote()`, `map_depth()` functions |

**Greenfield Gaps:**
- No `get_ohlc()` method
- No `get_batch_ltp()` method
- No `get_batch_quote()` method
- No historical data API (separate adapter in archive)

---

## 7. Summary of Runtime Sequence Gaps

### Critical Gaps

1. **Depth Feed Binary Parsing** — Greenfield has placeholder implementation (header only, no depth levels)
2. **Subscription Engine** — No orchestration layer for ref-counting and callback management
3. **Connection Admission Control** — No host-wide lock or 429 rate-limit tracking
4. **Staleness Detection** — No mechanism to detect and recover from stale connections
5. **Reconnect Backfill** — No gap-fill via REST on reconnection
6. **Strict-mode Publishing** — No validation of tick/depth data before publishing
7. **EventBus Integration** — No domain event publishing for ticks or depth
8. **Health Reporting** — No health status reporting or telemetry counters

### Moderate Gaps

1. **Connection Pooling** — No `Depth200ConnectionPool` for managing multiple depth-200 feeds
2. **Batch REST Operations** — No batch LTP or batch quote methods
3. **OHLC API** — No OHLC data retrieval
4. **Historical Data** — No historical candle API (separate adapter in archive)
5. **Token Refresh Reconnection** — Token update doesn't trigger socket close and reconnect
6. **Feed Rebuild** — No fresh feed creation on reconnect (may reuse poisoned transport)

### Minor Gaps

1. **Jitter in Backoff** — No random jitter in reconnection backoff
2. **Max Reconnect Guard** — No max reconnect attempt limit with cooldown
3. **Callback Wrapping** — No Quote entity wrapping in subscription callbacks
4. **Symbol Registration** — No security_id → symbol mapping for depth feeds

---

## 8. Recommended Implementation Priority

### Phase 4A: Core Depth Feed Functionality

1. Complete binary packet parsing for depth-20 and depth-200
2. Implement depth cache with bid/ask merge logic
3. Add symbol registration (security_id → symbol mapping)
4. Construct `MarketDepth` entities from parsed data
5. Add depth callback dispatch

### Phase 4B: Subscription Orchestration

1. Implement `SubscriptionEngine` with ref-counting
2. Add symbol resolution integration
3. Implement batch subscription API
4. Add callback wrapping (dict → Quote entity)

### Phase 4C: Connection Management

1. Add admission control (host-wide lock or 429 tracking)
2. Implement staleness detection
3. Add max reconnect guard with cooldown
4. Implement feed rebuild on reconnect
5. Add reconnect backfill via REST

### Phase 4D: EventBus and Telemetry

1. Integrate EventBus for tick and depth publishing
2. Add strict-mode validation before publishing
3. Implement health status reporting
4. Add telemetry counters (published/dropped ticks and depths)

### Phase 4E: REST API Completion

1. Add `get_ohlc()` method
2. Implement `get_batch_ltp()` and `get_batch_quote()`
3. Add historical data adapter (if in scope)

### Phase 4F: Advanced Features

1. Implement `Depth200ConnectionPool`
2. Add token refresh reconnection
3. Add jitter to reconnection backoff
4. Implement connection manager singleton (as in archive tests)

---

## 9. Conclusion

The greenfield implementation provides a solid foundation for basic market data streaming and REST operations but lacks the production-grade features present in the archive. The most critical gaps are in depth feed binary parsing, subscription orchestration, and connection management. A phased approach (4A through 4F) is recommended to systematically close these gaps while maintaining backward compatibility with the greenfield API surface.
