# Phase 4 Evidence Matrix — Dhan Market Data

## Verdict Legend

| Verdict | Meaning |
|---------|---------|
| **IDENTICAL** | Greenfield implements the exact same behavior with equivalent semantics |
| **PARTIAL** | Greenfield implements some but not all aspects of the archive behavior |
| **DIVERGENT** | Greenfield implements the behavior differently (may be better or worse) |
| **NOT_PORTED** | Archive behavior is completely missing from greenfield |
| **IMPROVED** | Greenfield implementation is demonstrably better than archive |

## Evidence Table

### 1. WebSocket Connection Establishment

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| SDK-based market feed WebSocket | `DhanMarketFeed` uses Dhan SDK `MarketFeed` class via `_sdk_market_feed_class()` | `DhanStreaming` uses `websocket-client` library directly via `BaseWebSocketStreaming` | **DIVERGENT** | Archive: `market_feed.py:181-197` (_build_sdk_feed_locked). Greenfield: `streaming.py:22-57` (uses websocket-client) |
| Raw WebSocket for depth-20 | `BinaryDepthFeed` uses `websockets` async library with manual event loop management | `DhanDepth20Stream` uses `websocket-client` sync library via base class | **DIVERGENT** | Archive: `depth_feed_base.py:353-374` (asyncio.new_event_loop). Greenfield: `depth20.py:18-38` (inherits BaseWebSocketStreaming) |
| Raw WebSocket for depth-200 | Same as depth-20 but with different endpoint and 1-instrument limit | `DhanDepth200Stream` uses same base class pattern | **DIVERGENT** | Archive: `depth_200.py:47-89`. Greenfield: `depth200.py:18-38` |
| Order stream WebSocket | `DhanOrderStream` uses Dhan SDK `OrderUpdate` class | `DhanOrderStream` uses `websocket-client` directly | **DIVERGENT** | Archive: `order_stream.py:61-116` (SDK). Greenfield: `order_stream.py:18-42` (websocket-client) |
| Authentication via URL params | Depth feeds use `?token=...&clientId=...&authType=2` URL params | Greenfield uses headers: `access-token` and `client-id` | **DIVERGENT** | Archive: `depth_feed_base.py:376-378` (_build_ws_url). Greenfield: `depth20.py:58-62` (_get_ws_headers) |
| Authentication via headers | Market feed uses SDK context with access_token | Uses `access-token` and `client-id` headers | **PARTIAL** | Archive: `market_feed.py:88-92` (_DhanContext). Greenfield: `streaming.py:83-87` (_get_ws_headers) |

### 2. Subscription/Unsubscription

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Market feed subscription | SDK-based `subscribe_symbols()` with instrument tuples (exchange_int, sid_str, mode_int) | JSON-based subscription with `instrumentKeys` array | **DIVERGENT** | Archive: `market_feed.py:509-557` (subscribe). Greenfield: `streaming.py:59-67` (subscribe with segment|symbol keys) |
| Depth-20 subscription | Binary JSON with `RequestCode: 23`, `InstrumentCount`, `InstrumentList` with ExchangeSegment/SecurityId | Same JSON structure with RequestCode 23 | **IDENTICAL** | Archive: `depth_feed_base.py:449-482` (_send_subscription). Greenfield: `depth20.py:64-79` (_build_subscribe_message) |
| Depth-200 subscription | Same as depth-20 but limited to 1 instrument | Same structure, explicitly limits to first instrument only | **IDENTICAL** | Archive: `depth_200.py:92-123` (subscribe override). Greenfield: `depth200.py:64-83` (limits to instrument_list[0]) |
| Unsubscription | SDK-based `unsubscribe_symbols()` for market feed; JSON for depth feeds | JSON-based unsubscribe with RequestCode 24 (assumed) | **PARTIAL** | Archive: `market_feed.py:559-576`. Greenfield: `depth20.py:81-89` (assumes RequestCode 24) |
| Subscription replay on reconnect | Full subscription set replayed from `_subscribed_instruments` on every reconnect | Subscriptions replayed from `_subscriptions` set in base class | **IDENTICAL** | Archive: `market_feed.py:614-641` (_on_connect). Greenfield: `base_streaming.py:133-140` (_on_open) |
| Instrument limit enforcement | Market feed: 1000 instruments; Depth-20: 50; Depth-200: 1 | No explicit limit enforcement in greenfield | **NOT_PORTED** | Archive: `market_feed.py:524-529` (MAX_INSTRUMENTS check). Greenfield: no limit checks |

### 3. Depth Feed Data Flow

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Binary packet parsing (depth-20) | Full binary parsing: 12-byte header, 16-byte levels, bid/ask separation, quantity filter | Placeholder binary parsing (header only, no level parsing) | **PARTIAL** | Archive: `depth_feed_base.py:527-591` (_process_binary_message, _parse_depth_packet). Greenfield: `depth20.py:91-111` (only parses header) |
| Binary packet parsing (depth-200) | Same as depth-20 but with implicit security_id (offset 8 = num_rows) | Placeholder binary parsing (header only) | **PARTIAL** | Archive: `depth_feed_base.py:562-591` (header_value handling). Greenfield: `depth200.py:90-106` (only parses header) |
| Depth cache management | Per-security_id cache with bid/ask merge, one-sided packet handling | No depth cache implemented | **NOT_PORTED** | Archive: `depth_feed_base.py:620-686` (_dispatch_depth with cache). Greenfield: no cache |
| DepthLevel domain entity | Converts binary data to `DepthLevel(price, quantity, orders)` entities | Returns raw header dict only | **NOT_PORTED** | Archive: `depth_feed_base.py:578-585` (DepthLevel creation). Greenfield: `depth20.py:103` (returns raw_header) |
| MarketDepth domain entity | Builds `MarketDepth(symbol, bids, asks, depth_type, timestamp)` from cache | Not implemented | **NOT_PORTED** | Archive: `depth_feed_base.py:649-655` (MarketDepth creation). Greenfield: no MarketDepth construction |
| Symbol registration | `register_symbol(security_id, symbol)` maps IDs to canonical symbols | Not implemented | **NOT_PORTED** | Archive: `depth_feed_base.py:187-189` (register_symbol). Greenfield: no symbol registration |

### 4. Reconnection with Backoff

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Exponential backoff | 1.0s → 30.0s with `min(backoff * 2, MAX_BACKOFF)` | 5.0s → 60.0s with `min(delay * 2, max_reconnect_delay)` | **DIVERGENT** | Archive: `reconnecting_service.py:208-233` (_backoff_sleep). Greenfield: `base_streaming.py:114-131` (_run reconnect loop) |
| Backoff reset on clean disconnect | Resets to INITIAL_BACKOFF after successful run return | No explicit reset logic | **NOT_PORTED** | Archive: `reconnecting_service.py:235-244` (_on_clean_disconnect). Greenfield: no reset |
| Jitter in backoff | `+ random.uniform(0, 1.0)` added to market feed backoff | No jitter | **NOT_PORTED** | Archive: `market_feed.py:279,338` (random jitter). Greenfield: no jitter |
| Interruptible sleep | `threading.Event.wait(timeout=backoff)` allows immediate stop | `time.sleep(delay)` blocks for full duration | **DIVERGENT** | Archive: `reconnecting_service.py:229-232` (Event.wait). Greenfield: `base_streaming.py:130` (time.sleep) |
| Max reconnect attempts | Configurable via `DHAN_MAX_RECONNECT_ATTEMPTS` (default 50), then cooldown | No max attempt limit | **NOT_PORTED** | Archive: `market_feed.py:238-255` (max reconnect guard). Greenfield: no limit |
| Reconnect cooldown | After max attempts, waits `DHAN_RECONNECT_COOLDOWN_SECONDS` (default 300s) | Not implemented | **NOT_PORTED** | Archive: `market_feed.py:248-254` (cooldown wait). Greenfield: no cooldown |

### 5. Connection Admission Control

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Host-wide lock (fcntl) | `MarketFeedConnectionAdmission` uses fcntl file locking for single-connection-per-account | Not implemented | **NOT_PORTED** | Archive: `connection_admission.py:92-141` (try_acquire with fcntl). Greenfield: no admission control |
| 429 rate-limit cooldown | Exponential cooldown after HTTP 429: base 60s → ceiling 900s, persisted to JSON file | Not implemented | **NOT_PORTED** | Archive: `connection_admission.py:224-268` (record_rate_limit_cooldown). Greenfield: no 429 handling |
| Cooldown persistence | Cooldown state persisted to `runtime/dhan-{type}-{client}.cooldown.json` survives restarts | Not implemented | **NOT_PORTED** | Archive: `connection_admission.py:254-256` (write_text). Greenfield: no persistence |
| Admission status reporting | `status()` returns lock state, cooldown remaining, rate-limit streak | Not implemented | **NOT_PORTED** | Archive: `connection_admission.py:276-288` (status method). Greenfield: no status |

### 6. Order Stream WebSocket

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| SDK-based order updates | Uses Dhan SDK `OrderUpdate` class with `on_update` callback | Uses websocket-client with manual JSON parsing | **DIVERGENT** | Archive: `order_stream.py:61-116` (SDK). Greenfield: `order_stream.py:18-87` (websocket-client) |
| Order transformation | `_transform_order()` maps SDK fields to canonical dict | `_parse_order_update()` uses mapper module | **DIVERGENT** | Archive: `order_stream.py:264-280` (_transform_order). Greenfield: `order_stream.py:89-101` (delegates to mapper) |
| Trade event publishing | Detects fills via cumulative filledQty delta, publishes TRADE event | Not implemented | **NOT_PORTED** | Archive: `order_stream.py:315-345` (TRADE event). Greenfield: no trade detection |
| TTLCache for filled qty | `TTLCache(maxsize=10000, ttl=3600)` tracks cumulative filled per order | Not implemented | **NOT_PORTED** | Archive: `order_stream.py:79` (TTLCache). Greenfield: no cache |
| Order callback registration | `on_order_update(callback)` with mixin-managed lock | `on_order_update` attribute (single callback) | **DIVERGENT** | Archive: `order_stream.py:227-229` (callback list). Greenfield: `order_stream.py:42` (single callback) |

### 7. Polling Feed Fallback

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| REST polling fallback | `PollingMarketFeed` polls `/marketfeed/ltp` at configurable interval | Not implemented | **NOT_PORTED** | Archive: `polling_feed.py:27-224` (full implementation). Greenfield: no polling feed |
| Batch LTP API | Groups instruments by segment, chunks into 1000-symbol batches | Not implemented | **NOT_PORTED** | Archive: `polling_feed.py:157-189` (_poll_batch). Greenfield: no batch polling |
| Same callback interface as WebSocket | `on_quote(callback)` matches DhanMarketFeed interface | Not implemented | **NOT_PORTED** | Archive: `polling_feed.py:132-134` (on_quote). Greenfield: no equivalent |

### 8. Instrument Resolver Integration

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Symbol resolution for ticks | `_resolver.get_by_security_id()` in `_transform_quote()` | `DhanInstrumentResolver.resolve()` in market_data REST calls | **PARTIAL** | Archive: `market_feed.py:788-799` (resolver in transform). Greenfield: `market_data.py:24` (resolver in REST only) |
| Symbol resolution for depth | `_sec_id_to_symbol` mapping via `register_symbol()` | Not implemented for streaming | **NOT_PORTED** | Archive: `depth_feed_base.py:187-189` (register_symbol). Greenfield: no symbol mapping in depth streams |
| Security ID to symbol mapping | Explicit mapping for depth feeds (security_id → canonical symbol) | Not implemented | **NOT_PORTED** | Archive: `depth_feed_base.py:159,641` (_sec_id_to_symbol). Greenfield: no mapping |

### 9. Resolver Periodic Refresh

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Background refresh service | `ResolverRefresher` periodically reloads instruments (default 24h) | Not implemented | **NOT_PORTED** | Archive: `resolver_refresher.py:56-265` (full implementation). Greenfield: no refresher |
| Atomic swap | New resolver built in memory, then atomic-swapped into connection | Not implemented | **NOT_PORTED** | Archive: `resolver.py:173-177` (atomic swap under lock). Greenfield: no atomic swap |
| Refresh metrics | `refresh_count`, `error_count`, `last_refresh_at` exposed via health() | Not implemented | **NOT_PORTED** | Archive: `resolver_refresher.py:158-167` (health metrics). Greenfield: no metrics |

### 10. Market Data REST API

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| LTP REST endpoint | `get_ltp(symbol, exchange)` → POST `/marketfeed/ltp` | `ltp(symbol, exchange)` → POST `/marketfeed/ltp` | **IDENTICAL** | Archive: `market_data.py:32-58`. Greenfield: `market_data.py:23-53` |
| Quote REST endpoint | `get_quote(symbol, exchange)` → POST `/marketfeed/quote` | `quote(symbol, exchange)` → POST `/marketfeed/quote` | **IDENTICAL** | Archive: `market_data.py:60-82`. Greenfield: `market_data.py:55-71` |
| Depth REST endpoint | `get_depth(symbol, exchange)` → POST `/marketfeed/quote` (5-level) | `depth(symbol, exchange)` → POST `/marketfeed/quote` | **IDENTICAL** | Archive: `market_data.py:84-113`. Greenfield: `market_data.py:73-89` |
| OHLC REST endpoint | `get_ohlc(symbol, exchange)` → POST `/marketfeed/ohlc` | Not implemented | **NOT_PORTED** | Archive: `market_data.py:115-122`. Greenfield: no OHLC method |
| Batch LTP | `get_batch_ltp(symbols, exchange)` → single POST for multiple symbols | Not implemented | **NOT_PORTED** | Archive: `market_data.py:124-146`. Greenfield: no batch method |
| Batch quote | `get_batch_quote(symbols, exchange)` → single POST for multiple quotes | Not implemented | **NOT_PORTED** | Archive: `market_data.py:148-186`. Greenfield: no batch method |
| Identity assertion | `assert_dhan_identity(sid, segment, context)` on every REST call | `assert_valid_dhan_payload(payload, context)` on every REST call | **IDENTICAL** | Archive: `market_data.py:39,63,87,118`. Greenfield: `market_data.py:28,60,78` |

### 11. Connection Pool Management

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Depth-200 connection pool | `Depth200ConnectionPool` manages multiple 1-instrument connections | Not implemented | **NOT_PORTED** | Archive: `depth_200.py:150-320` (full pool implementation). Greenfield: no pool |
| Singleton enforcement | `WebSocketConnectionManager` ensures one market feed / order stream per broker | Not implemented (relies on base class singleton pattern) | **NOT_PORTED** | Archive: `connection_manager.py:27-256` (full manager). Greenfield: no connection manager |
| Lifecycle management | `ConnectionLifecycle` creates, caches, and tears down all WebSocket services | Not implemented | **NOT_PORTED** | Archive: `connection_lifecycle.py:48-383` (full lifecycle). Greenfield: no lifecycle |
| Token receiver registry | `register_token_receiver(receiver)` broadcasts token updates to all services | `update_token(new_token)` method on each adapter (manual broadcast) | **PARTIAL** | Archive: `connection.py:463-469` (registry). Greenfield: `streaming.py:69-75`, `depth20.py:50-51`, `order_stream.py:44-46` (individual update_token) |

### 12. Message Parsing and Dispatch

| Behavior | Archive | Greenfield | Verdict | Evidence |
|----------|---------|------------|---------|----------|
| Market feed message dispatch | `_on_message()` dispatches by `data["type"]`: "Ticker Data", "Quote Data", "Market Depth", "Full Data" | `_parse_tick()` extracts symbol/ltp/volume from generic dict | **DIVERGENT** | Archive: `market_feed.py:685-739` (type-based dispatch). Greenfield: `streaming.py:105-116` (generic parsing) |
| Strict-mode tick validation | Drops ticks with missing/zero LTP or missing symbol, increments `_dropped_ticks` | No validation | **NOT_PORTED** | Archive: `market_feed.py:867-943` (_publish_tick strict mode). Greenfield: no validation |
| Strict-mode depth validation | Drops depth with empty both sides or zero top-of-book price | No validation | **NOT_PORTED** | Archive: `market_feed.py:945-1017` (_publish_depth strict mode). Greenfield: no validation |
| Event bus publishing | Publishes TICK, DEPTH, ORDER_UPDATED, TRADE events to EventBus | Not implemented | **NOT_PORTED** | Archive: `market_feed.py:925-933` (TICK), `order_stream.py:306-314` (ORDER_UPDATED). Greenfield: no event bus |
| Callback fan-out | Multiple callbacks per event type with snapshot iteration | Single `on_tick` callback | **DIVERGENT** | Archive: `market_feed.py:700-706` (callback loop). Greenfield: `base_streaming.py:147-149` (single callback) |
| Correlation ID generation | Monotonic correlation IDs for event tracing (`dhan:ws:{uuid}`) | Not implemented | **NOT_PORTED** | Archive: `market_feed.py:742-751` (_gen_ws_correlation_id). Greenfield: no correlation |

## QA Validation Notes

### Test Coverage (Archive)
- `test_connection_manager.py` (241 lines) covers:
  - Singleton enforcement for market feed and order stream
  - Thread safety of connection creation
  - Access token propagation
  - Connection stats tracking
  - Start/stop/close lifecycle
  - Multiple manager instance independence

### Test Coverage (Greenfield)
- No dedicated tests found for greenfield market data adapters
- Base class `BaseWebSocketStreaming` provides common infrastructure but lacks unit tests

### Confidence Distribution

| Category | High Confidence | Medium Confidence | Low Confidence |
|----------|----------------|-------------------|----------------|
| WebSocket Connection | 6 | 0 | 0 |
| Subscription | 3 | 1 | 2 |
| Depth Feed | 0 | 2 | 4 |
| Reconnection | 1 | 1 | 4 |
| Admission Control | 0 | 0 | 4 |
| Order Stream | 1 | 2 | 2 |
| Polling Feed | 0 | 0 | 1 |
| Resolver Integration | 0 | 1 | 2 |
| REST API | 4 | 0 | 3 |
| Connection Pool | 0 | 0 | 4 |
| Message Parsing | 1 | 1 | 4 |

**Total:** 16 high, 8 medium, 30 low

### Gap Severity Summary

| Severity | Count | Examples |
|----------|-------|---------|
| **Critical** | 8 | Binary depth parsing incomplete, no depth cache, no event bus, no admission control |
| **High** | 12 | No polling fallback, no resolver refresh, no batch REST API, no trade detection |
| **Medium** | 15 | Divergent reconnection (no jitter, no interruptible sleep), no instrument limits, single callback vs multiple |
| **Low** | 9 | Different backoff defaults (5s vs 1s), different WS library choice, header-based vs URL-based auth |

### Open Questions

1. **WebSocket library choice**: Archive uses both Dhan SDK (wrapping websockets) and raw `websockets` async. Greenfield uses `websocket-client` sync. Is this intentional for simplicity, or should async be preserved?

2. **Binary depth parsing**: Greenfield depth adapters have placeholder binary parsing. Is this a known gap, or is there a different wire format expected?

3. **Event bus integration**: Archive publishes to EventBus extensively. Greenfield has no event bus. Is this architectural change intentional (callbacks only)?

4. **Admission control**: Archive has sophisticated fcntl-based host-wide locking and 429 cooldown. Is this over-engineering for single-instance deployments?

5. **Polling fallback**: Archive has full polling feed implementation. Is this a required feature or optional fallback?

6. **Resolver refresh**: Archive has background refresh service. Is this needed for long-running processes, or is startup-only loading sufficient?

## Phase 4 Exit Criteria Validation

| Exit Criterion | Status | Notes |
|----------------|--------|-------|
| Market data REST API (LTP, quote, depth) | ✅ **MET** | Greenfield implements all three core REST endpoints with identity assertions |
| WebSocket connection establishment | ⚠️ **PARTIAL** | Greenfield connects via websocket-client but uses different auth mechanism (headers vs URL params) |
| Subscription/unsubscription | ⚠️ **PARTIAL** | Greenfield implements basic subscribe/unsubscribe but lacks instrument limit enforcement |
| Depth feed data flow (20-level) | ❌ **NOT MET** | Binary parsing is placeholder only; no depth cache, no MarketDepth entities |
| Depth feed data flow (200-level) | ❌ **NOT MET** | Same as depth-20; also missing connection pool for multi-instrument |
| Reconnection with backoff | ⚠️ **PARTIAL** | Basic exponential backoff present but missing jitter, interruptible sleep, max attempts, cooldown |
| Order stream WebSocket | ⚠️ **PARTIAL** | Basic order stream present but missing trade detection, TTLCache, multiple callbacks |
| Event bus integration | ❌ **NOT MET** | No event bus publishing in greenfield |
| Connection admission control | ❌ **NOT MET** | No fcntl locking, no 429 cooldown |
| Polling feed fallback | ❌ **NOT MET** | Not implemented |
| Resolver periodic refresh | ❌ **NOT MET** | Not implemented |
| Instrument resolver integration (streaming) | ❌ **NOT MET** | Resolver used in REST but not in streaming tick/depth transformation |

**Overall Phase 4 Status:** ❌ **NOT COMPLETE** — Critical gaps in depth feed parsing, event bus integration, and connection admission control must be addressed before production readiness.
