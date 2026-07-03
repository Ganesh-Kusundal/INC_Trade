# Phase 6 Runtime Sequences — Historical Data & Market Data

## Overview

This document traces the runtime execution flow for historical data retrieval and market data operations in both the archive and greenfield implementations. Each sequence includes ASCII diagrams showing component interactions, data transformations, and error handling paths.

---

## 1. Historical Data Retrieval Flow

### Archive Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_historical(symbol, exchange, from_date, to_date, timeframe)
      ▼
┌─────────────────────────┐
│  HistoricalAdapter      │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    identity.      │  │
│  │    resolve_ref()  │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Get instrument │  │
│  │    resolver.      │  │
│  │    get_by_sec_id()│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Map timeframe  │  │
│  │    _TIMEFRAME_MAP │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. Get instrument │  │
│  │    type           │  │
│  │    _get_instrument│  │
│  │    _type()        │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Build payload  │  │
│  │    - securityId   │  │
│  │    - segment      │  │
│  │    - instrument   │  │
│  │    - dates        │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. Assert payload │  │
│  │    assert_dhan_   │  │
│  │    payload()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. POST request   │  │
│  │    client.post()  │  │
│  │    /charts/       │  │
│  │    historical     │  │
│  │    or /intraday   │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 8. Parse response │  │
│  │    _parse()       │  │
│  │    → DataFrame    │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ pd.DataFrame
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Key Steps**:
1. **Resolve instrument**: `identity.resolve_ref(symbol, exchange)` → `DhanInstrumentRef`
2. **Fetch instrument**: `resolver.get_by_security_id()` → `Instrument` (for type detection)
3. **Map timeframe**: Convert string ("1D", "5m") to API interval (1, 5, 60, "1D")
4. **Determine instrument type**: EQUITY, OPTIDX, FUTCOM, etc.
5. **Build payload**: Daily vs intraday branching (session times for intraday)
6. **Assert invariant**: `assert_dhan_payload()` validates payload structure
7. **HTTP POST**: `/charts/historical` or `/charts/intraday`
8. **Parse response**: Convert JSON → pandas DataFrame with columns: timestamp, OHLCV, oi, symbol, exchange, timeframe

**Session Time Handling** (Intraday Only):
- MCX: 09:00:00 → 23:30:00
- Default (NSE/BSE): 09:15:00 → 15:30:00

### Greenfield Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_historical_candles(symbol, exchange, start_time, end_time, resolution)
      ▼
┌─────────────────────────┐
│    DhanHistorical       │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    resolver.      │  │
│  │    resolve()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Map resolution │  │
│  │    _TIMEFRAME_MAP │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Format dates   │  │
│  │    start_time.    │  │
│  │    strftime()     │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. Build payload  │  │
│  │    - securityId   │  │
│  │    - segment      │  │
│  │    - instrument   │  │
│  │    - dates        │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Assert payload │  │
│  │    assert_valid_  │  │
│  │    dhan_payload() │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. POST request   │  │
│  │    client.post()  │  │
│  │    ENDPOINTS[     │  │
│  │    "historical"]  │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. Parse response │  │
│  │    _parse()       │  │
│  │    → list[Candle] │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ list[Candle]
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Key Steps**:
1. **Resolve instrument**: `resolver.resolve(symbol, exchange)` → `DhanInstrumentRef`
2. **Map resolution**: Convert string to API interval
3. **Format dates**: `datetime.strftime("%Y-%m-%d")` (no session times)
4. **Build payload**: Same structure as archive
5. **Assert invariant**: `assert_valid_dhan_payload()`
6. **HTTP POST**: `ENDPOINTS["historical"]` → `/charts/historical`
7. **Parse response**: JSON → `list[Candle]` (handles row and columnar formats)

**Parsing Logic** (Dual Format Support):
```
IF response has "start_Time" or "timestamp" AND "open" as arrays:
    # Columnar format
    FOR each index i:
        timestamp = fromtimestamp(start_Time[i], tz=Asia/Kolkata)
        candle = Candle(symbol, timestamp, open[i], high[i], ...)
ELSE:
    # Row format
    FOR each item in response:
        timestamp = fromisoformat(item["timestamp"]) or fromtimestamp(item["timestamp"])
        candle = Candle(symbol, timestamp, item["open"], ...)
```

### Archive vs Greenfield Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| **Input dates** | String (YYYY-MM-DD) | `datetime` objects |
| **Output format** | `pd.DataFrame` | `list[Candle]` |
| **Timezone** | Naive (no tz) | `Asia/Kolkata` (aware) |
| **Session times** | MCX-specific (09:00-23:30) | Hardcoded (09:15-15:30) |
| **Instrument type** | Computed via `_get_instrument_type()` | Read from `ref.instrument_type` |
| **Response parsing** | Single format (row-oriented) | Dual format (row + columnar) |
| **Precision** | Float (pandas) | Decimal |
| **Mutability** | Mutable DataFrame | Immutable dataclass |
| **Open interest** | Included (`oi` column) | Not included |
| **Endpoint config** | Hardcoded string | `ENDPOINTS["historical"]` |

---

## 2. OHLC Data Retrieval Flow

### Archive Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_ohlc(symbol, exchange)
      ▼
┌─────────────────────────┐
│   MarketDataAdapter     │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    _resolve_and_  │  │
│  │    segment()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    int(ref.       │  │
│  │    security_id)   │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Assert identity│  │
│  │    assert_dhan_   │  │
│  │    identity()     │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. POST request   │  │
│  │    client.post()  │  │
│  │    /marketfeed/   │  │
│  │    ohlc           │  │
│  │    payload:       │  │
│  │    {segment:[sid]}│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Extract OHLC   │  │
│  │    data["data"]   │  │
│  │    [segment][sid] │  │
│  │    ["ohlc"]       │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ dict (open, high, low, close)
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Response Structure**:
```json
{
  "data": {
    "NSE_EQ": {
      "12345": {
        "ohlc": {
          "open": 100.5,
          "high": 105.2,
          "low": 99.8,
          "close": 103.1
        }
      }
    }
  }
}
```

### Greenfield Flow

**Status**: NOT IMPLEMENTED

**Note**: The endpoint is defined in `ENDPOINTS["ohlc"]` but no method exists in `DhanMarketData` class.

**Workaround**: Use `quote()` method and extract OHLC fields from the `Quote` entity.

---

## 3. LTP (Last Traded Price) Retrieval Flow

### Archive Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_ltp(symbol, exchange="NSE")
      ▼
┌─────────────────────────┐
│   MarketDataAdapter     │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    _resolve_and_  │  │
│  │    segment()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    int(ref.       │  │
│  │    security_id)   │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Assert identity│  │
│  │    assert_dhan_   │  │
│  │    identity()     │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. POST request   │  │
│  │    client.post()  │  │
│  │    /marketfeed/   │  │
│  │    ltp            │  │
│  │    payload:       │  │
│  │    {segment:[sid]}│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Extract LTP    │  │
│  │    data["data"]   │  │
│  │    [segment][sid] │  │
│  │    ["last_price"] │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. Convert to     │  │
│  │    Decimal        │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ Decimal
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Error Handling**:
- If `entry is None`: Log warning + raise `ValueError`
- Warning includes: symbol, security_id, segment, available_keys

### Greenfield Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ ltp(symbol, exchange="NSE")
      ▼
┌─────────────────────────┐
│    DhanMarketData       │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    resolver.      │  │
│  │    resolve()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    ref.security_  │  │
│  │    id_int()       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Get segment    │  │
│  │    ref.exchange_  │  │
│  │    segment        │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. Build payload  │  │
│  │    {segment:[sid]}│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Assert payload │  │
│  │    assert_valid_  │  │
│  │    dhan_payload() │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. POST request   │  │
│  │    client.post()  │  │
│  │    ENDPOINTS["ltp"]│ │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. Extract feed   │  │
│  │    data.get(      │  │
│  │    "data", {})    │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 8. Multi-path     │  │
│  │    lookup:        │  │
│  │    - segment→sid  │  │
│  │    - sid          │  │
│  │    - segment:sid  │  │
│  │    - symbol       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 9. Extract price  │  │
│  │    - last_price   │  │
│  │    - lastPrice    │  │
│  │    - raw value    │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 10. Convert to    │  │
│  │     Decimal       │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ Decimal
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Multi-Path Lookup** (Robustness):
```python
entry = (
    feed.get(segment, {}).get(str(sid))  # Standard path
    or feed.get(str(sid))                 # Flat mapping
    or feed.get(f"{segment}:{sid}")       # Composite key
    or feed.get(symbol)                   # Symbol key
    or {}
)
```

**Price Extraction** (Multiple Formats):
```python
price = entry.get("last_price") or entry.get("lastPrice")
if price is None:
    if isinstance(entry, (int, float, str, Decimal)):
        price = entry  # Direct value
    else:
        price = 0
```

### Archive vs Greenfield Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| **Response path** | Single path (segment→sid) | Multi-path fallback |
| **Error handling** | Raises `ValueError` if missing | Returns `Decimal(0)` if missing |
| **Field names** | `last_price` only | `last_price` or `lastPrice` |
| **Direct values** | Not supported | Supports raw numeric responses |
| **Logging** | Warning on missing LTP | No explicit error logging |
| **Precision** | Decimal | Decimal |

---

## 4. Quote Retrieval Flow

### Archive Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_quote(symbol, exchange="NSE")
      ▼
┌─────────────────────────┐
│   MarketDataAdapter     │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    _resolve_and_  │  │
│  │    segment()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    int(ref.       │  │
│  │    security_id)   │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Assert identity│  │
│  │    assert_dhan_   │  │
│  │    identity()     │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. POST request   │  │
│  │    client.post()  │  │
│  │    /marketfeed/   │  │
│  │    quote          │  │
│  │    payload:       │  │
│  │    {segment:[sid]}│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Extract raw    │  │
│  │    data["data"]   │  │
│  │    [segment][sid] │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. Extract OHLC   │  │
│  │    raw.get("ohlc")│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. Build Quote    │  │
│  │    Quote(         │  │
│  │      symbol=      │  │
│  │        ref.symbol,│  │
│  │      ltp=         │  │
│  │        last_price,│  │
│  │      open=ohlc,   │  │
│  │      high=ohlc,   │  │
│  │      low=ohlc,    │  │
│  │      close=ohlc,  │  │
│  │      volume,      │  │
│  │      change=      │  │
│  │        net_change)│  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ Quote
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Quote Fields**:
- `symbol`: From `ref.symbol`
- `ltp`: `raw["last_price"]`
- `open`: `raw["ohlc"]["open"]`
- `high`: `raw["ohlc"]["high"]`
- `low`: `raw["ohlc"]["low"]`
- `close`: `raw["ohlc"]["close"]`
- `volume`: `raw["volume"]`
- `change`: `raw["net_change"]`

### Greenfield Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ quote(symbol, exchange="NSE")
      ▼
┌─────────────────────────┐
│    DhanMarketData       │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    resolver.      │  │
│  │    resolve()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    ref.security_  │  │
│  │    id_int()       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Get segment    │  │
│  │    ref.exchange_  │  │
│  │    segment        │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. Build payload  │  │
│  │    {segment:[sid]}│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Assert payload │  │
│  │    assert_valid_  │  │
│  │    dhan_payload() │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. POST request   │  │
│  │    client.post()  │  │
│  │    ENDPOINTS[     │  │
│  │    "quote"]       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. Extract feed   │  │
│  │    data.get(      │  │
│  │    "data", {})    │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 8. Multi-path     │  │
│  │    lookup:        │  │
│  │    - sid          │  │
│  │    - symbol       │  │
│  │    - segment:sid  │  │
│  │    - exchange:    │  │
│  │      symbol       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 9. Map to Quote   │  │
│  │    map_quote(     │  │
│  │      symbol,      │  │
│  │      symbol_data) │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ Quote
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Mapper Logic** (`map_quote()`):
```python
# Handle nested last_price (dict or scalar)
last = data.get("last_price", data.get("lastPrice", {}))
if isinstance(last, dict):
    ltp = to_decimal(last.get("last_price", last.get("ltp", 0)))
else:
    ltp = to_decimal(last)

return Quote(
    symbol=symbol,
    ltp=ltp,
    open=to_decimal(data.get("ohlc", {}).get("open", 0)),
    high=to_decimal(data.get("ohlc", {}).get("high", 0)),
    low=to_decimal(data.get("ohlc", {}).get("low", 0)),
    close=to_decimal(data.get("ohlc", {}).get("close", 0)),
    volume=int(data.get("volume", 0)),
)
```

### Archive vs Greenfield Comparison

| Aspect | Archive | Greenfield |
|--------|---------|------------|
| **Response path** | Single path (segment→sid) | Multi-path fallback |
| **Mapper** | Inline construction | Delegated to `map_quote()` |
| **Field mapping** | Direct | Handles nested `last_price` dict |
| **Price conversion** | `Decimal(str(...))` | `to_decimal()` utility |
| **Change field** | Included (`net_change`) | Not included |
| **Exchange field** | Not included | Not included (but in entity) |
| **Timestamp field** | Not included | Not included (but in entity) |

---

## 5. Batch Quote Retrieval Flow

### Archive Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_batch_quote(symbols: list[str], exchange="NSE")
      ▼
┌─────────────────────────────────────────┐
│        MarketDataAdapter                │
│  ┌───────────────────────────────────┐  │
│  │ 1. Initialize maps                │  │
│  │    segment_map: {seg: [sids]}     │  │
│  │    symbol_map: {sid: symbol}      │  │
│  │    ref_map: {sid: ref}            │  │
│  └───────────┬───────────────────────┘  │
│              │                          │
│  ┌───────────▼───────────────────────┐  │
│  │ 2. FOR each symbol in symbols:    │  │
│  │    ┌─────────────────────────┐    │  │
│  │    │ 2a. Resolve ref        │    │  │
│  │    │     _resolve_and_      │    │  │
│  │    │     segment()          │    │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 2b. Extract sid        │    │  │
│  │    │     int(ref.security_id)│   │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 2c. Assert identity    │    │  │
│  │    │     assert_dhan_       │    │  │
│  │    │     identity()         │    │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 2d. Group by segment   │    │  │
│  │    │     segment_map[seg]   │    │  │
│  │    │       .append(sid)     │    │  │
│  │    │     symbol_map[sid]    │    │  │
│  │    │       = symbol         │    │  │
│  │    │     ref_map[sid]       │    │  │
│  │    │       = ref            │    │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 2e. On exception:      │    │  │
│  │    │     continue (skip)    │    │  │
│  │    └─────────────────────────┘    │  │
│  └───────────┬───────────────────────┘  │
│              │                          │
│  ┌───────────▼───────────────────────┐  │
│  │ 3. Check if segment_map empty    │  │
│  │    IF empty: return {}           │  │
│  └───────────┬───────────────────────┘  │
│              │                          │
│  ┌───────────▼───────────────────────┐  │
│  │ 4. POST request (single call)    │  │
│  │    client.post(/marketfeed/quote,│  │
│  │      json=segment_map)           │  │
│  └───────────┬───────────────────────┘  │
│              │                          │
│  ┌───────────▼───────────────────────┐  │
│  │ 5. FOR each segment in response: │  │
│  │    FOR each sid in segment:      │  │
│  │    ┌─────────────────────────┐    │  │
│  │    │ 5a. Check if sid in    │    │  │
│  │    │     symbol_map         │    │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 5b. Extract info       │    │  │
│  │    │     last_price, ohlc   │    │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 5c. Build Quote        │    │  │
│  │    │     Quote(symbol=      │    │  │
│  │    │       ref.symbol,      │    │  │
│  │    │       ltp, open,       │    │  │
│  │    │       high, low,       │    │  │
│  │    │       close, volume,   │    │  │
│  │    │       change)          │    │  │
│  │    └───────────┬─────────────┘    │  │
│  │                │                  │  │
│  │    ┌───────────▼─────────────┐    │  │
│  │    │ 5d. Add to result      │    │  │
│  │    │     result[symbol]     │    │  │
│  │    │       = Quote          │    │  │
│  │    └─────────────────────────┘    │  │
│  └───────────┬───────────────────────┘  │
│              │                          │
└──────────────┼──────────────────────────┘
               │ dict[str, Quote]
               ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Key Optimizations**:
1. **Single API call**: All symbols grouped by segment → one POST request
2. **Error tolerance**: Failed resolutions skipped (continue on exception)
3. **Efficient mapping**: Three maps (segment, symbol, ref) for O(1) lookups

**Payload Structure**:
```json
{
  "NSE_EQ": [12345, 67890],
  "BSE_EQ": [11111]
}
```

### Greenfield Flow

**Status**: NOT IMPLEMENTED

**Workaround**: Call `quote()` method in a loop (N API calls instead of 1).

**Performance Impact**:
- Archive: 1 API call for N symbols
- Greenfield: N API calls for N symbols
- Rate limit: 1 req/s for `/marketfeed/quote` → 10 symbols takes 10 seconds

---

## 6. Market Depth Retrieval Flow

### Archive Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_depth(symbol, exchange="NSE")
      ▼
┌─────────────────────────┐
│   MarketDataAdapter     │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    _resolve_and_  │  │
│  │    segment()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    int(ref.       │  │
│  │    security_id)   │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Assert identity│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. POST request   │  │
│  │    /marketfeed/   │  │
│  │    quote          │  │
│  │    (same as quote)│  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Extract raw    │  │
│  │    data["data"]   │  │
│  │    [segment][sid] │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. Parse bids     │  │
│  │    raw["depth"]   │  │
│  │    ["buy"][:5]    │  │
│  │    → DepthLevel[] │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. Parse asks     │  │
│  │    raw["depth"]   │  │
│  │    ["sell"][:5]   │  │
│  │    → DepthLevel[] │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 8. Build Market   │  │
│  │    Depth          │  │
│  │    MarketDepth(   │  │
│  │      symbol,      │  │
│  │      bids,        │  │
│  │      asks,        │  │
│  │      depth_type=  │  │
│  │        "DEPTH_5") │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ MarketDepth
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**DepthLevel Structure**:
```python
DepthLevel(
    price=Decimal(level["price"]),
    quantity=int(level["quantity"]),
    orders=int(level.get("orders", 0)),
)
```

### Greenfield Flow

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ depth(symbol, exchange="NSE")
      ▼
┌─────────────────────────┐
│    DhanMarketData       │
│  ┌───────────────────┐  │
│  │ 1. Resolve ref    │  │
│  │    resolver.      │  │
│  │    resolve()      │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 2. Extract sid    │  │
│  │    ref.security_  │  │
│  │    id_int()       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 3. Get segment    │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 4. Build payload  │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 5. Assert payload │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 6. POST request   │  │
│  │    ENDPOINTS[     │  │
│  │    "quote"]       │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 7. Extract feed   │  │
│  │    (multi-path)   │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ 8. Map to depth   │  │
│  │    map_depth(     │  │
│  │      symbol,      │  │
│  │      symbol_data) │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ MarketDepth
             ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Mapper Logic** (`map_depth()`):
```python
# Parse up to 20 bid/ask levels
bids = []
asks = []
for i in range(20):
    bid = data.get(f"bid{i}") or data.get("bids", [])[i]
    ask = data.get(f"ask{i}") or data.get("asks", [])[i]
    if bid and isinstance(bid, dict):
        bids.append(DepthLevel(
            price=to_decimal(bid.get("price", 0)),
            quantity=int(bid.get("quantity") or bid.get("orders") or 0),
            orders=int(bid.get("orders") or 0),
        ))
    if ask and isinstance(ask, dict):
        asks.append(DepthLevel(...))

return MarketDepth(symbol=symbol, bids=bids, asks=asks)
```

**Key Differences**:
- Archive: Explicitly limits to 5 levels (`[:5]`)
- Greenfield: Parses up to 20 levels (no explicit limit)
- Archive: Includes `depth_type="DEPTH_5"`
- Greenfield: No `depth_type` field

---

## 7. Cached Market Data Flow (Greenfield Service Layer)

### Quote with TTL Cache

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ quote(symbol, exchange)
      ▼
┌─────────────────────────────────────┐
│     MarketDataService               │
│  ┌───────────────────────────────┐  │
│  │ 1. Build cache key            │  │
│  │    key = "quote:{exchange}:   │  │
│  │          {symbol}"            │  │
│  └───────────┬───────────────────┘  │
│              │                      │
│  ┌───────────▼───────────────────┐  │
│  │ 2. Check cache                │  │
│  │    _get_cached(key)           │  │
│  │    ┌─────────────────────┐    │  │
│  │    │ IF entry exists:    │    │  │
│  │    │   ts, value = entry │    │  │
│  │    │   IF now - ts > ttl:│    │  │
│  │    │     # Expired       │    │  │
│  │    │     remove from cache│   │  │
│  │    │     return None     │    │  │
│  │    │   ELSE:             │    │  │
│  │    │     return value    │    │  │
│  │    │ ELSE:               │    │  │
│  │    │   return None       │    │  │
│  │    └─────────────────────┘    │  │
│  └───────────┬───────────────────┘  │
│              │                      │
│  ┌───────────▼───────────────────┐  │
│  │ 3. IF cached is not None:     │  │
│  │      return cached Quote      │  │
│  └───────────┬───────────────────┘  │
│              │                      │
│  ┌───────────▼───────────────────┐  │
│  │ 4. ELSE: Call provider        │  │
│  │    result = provider.quote()  │  │
│  │    (DhanMarketData.quote())   │  │
│  └───────────┬───────────────────┘  │
│              │                      │
│  ┌───────────▼───────────────────┐  │
│  │ 5. Store in cache             │  │
│  │    _set_cached(key, result)   │  │
│  │    cache[key] = (now, result) │  │
│  └───────────┬───────────────────┘  │
│              │                      │
│  ┌───────────▼───────────────────┐  │
│  │ 6. Return result              │  │
│  └───────────┬───────────────────┘  │
│              │                      │
└──────────────┼──────────────────────┘
               │ Quote
               ▼
┌────────────┐
│   Caller   │
└────────────┘
```

**Cache Configuration**:
- Default TTL: 1.0 second
- Thread-safe: Uses `threading.Lock()`
- Cache key format: `quote:{exchange}:{symbol}`
- Eviction: Lazy (checked on access)

**LTP via Cache**:
```python
def ltp(symbol, exchange):
    q = self.quote(symbol, exchange)  # Reuse cached quote
    return q.ltp
```

**Cache Invalidation**:
```python
def invalidate(symbol="", exchange=""):
    if not symbol:
        cache.clear()  # Clear all
    else:
        cache.pop("quote:{exchange}:{symbol}")
        cache.pop("depth:{exchange}:{symbol}")
```

---

## 8. Data Pagination Flow

**Status**: NOT IMPLEMENTED (Archive or Greenfield)

**Note**: Dhan API does not support pagination for historical data. All candles are returned in a single response. For large date ranges, the API may truncate results silently.

**Workaround** (if needed):
- Split date range into chunks (e.g., 30-day intervals)
- Call `get_historical_candles()` for each chunk
- Concatenate results

---

## 9. Error Handling Sequences

### Historical Data — API Failure

```
┌────────────┐
│   Caller   │
└─────┬──────┘
      │ get_historical_candles(...)
      ▼
┌─────────────────────────┐
│    DhanHistorical       │
│  ...                    │
│  ┌───────────────────┐  │
│  │ POST request      │  │
│  │ → API returns:    │  │
│  │   {"status":      │  │
│  │    "failure",     │  │
│  │    "remarks":     │  │
│  │    {...}}         │  │
│  └─────────┬─────────┘  │
│            │             │
│  ┌─────────▼─────────┐  │
│  │ _parse() checks:  │  │
│  │ IF data["status"] │  │
│  │    == "failure":  │  │
│  │   raise Exception │  │
│  └─────────┬─────────┘  │
│            │             │
└────────────┼─────────────┘
             │ raises Exception
             ▼
┌────────────┐
│   Caller   │ (must handle)
└────────────┘
```

**Archive**: Raises `MarketDataError` if `data["status"] == "failure"`
**Greenfield**: No explicit check (returns empty list or partial data)

### LTP — Missing Data

**Archive**:
```python
if entry is None:
    logger.warning("ltp_missing_for_security_id", ...)
    raise ValueError(f"No LTP data for {symbol} ...")
```

**Greenfield**:
```python
# No explicit check, returns Decimal(0)
price = entry.get("last_price") or 0
return Decimal(str(price))
```

---

## 10. Sequence Comparison Summary

| Flow | Archive | Greenfield | Gap |
|------|---------|------------|-----|
| Historical candles | ✅ DataFrame | ✅ list[Candle] | No OI field |
| OHLC | ✅ dict | ❌ Not implemented | Missing method |
| LTP | ✅ Decimal | ✅ Decimal | — |
| Quote | ✅ Quote | ✅ Quote | No change field |
| Batch LTP | ✅ dict[str, Decimal] | ❌ Not implemented | Performance gap |
| Batch quote | ✅ dict[str, Quote] | ❌ Not implemented | Performance gap |
| Market depth | ✅ MarketDepth | ✅ MarketDepth | — |
| Cached LTP | ❌ No cache | ✅ TTL cache | — |
| Cached quote | ❌ No cache | ✅ TTL cache | — |
| Cached depth | ❌ No cache | ✅ TTL cache | — |

---

## 11. Performance Characteristics

### API Call Efficiency

| Operation | Archive | Greenfield | Impact |
|-----------|---------|------------|--------|
| 10x LTP (batch) | 1 call | 10 calls | 10x slower |
| 10x Quote (batch) | 1 call | 10 calls | 10x slower |
| LTP (repeated) | N calls | ~1 call (cache) | 10x faster |
| Quote (repeated) | N calls | ~1 call (cache) | 10x faster |

### Rate Limit Compliance

**Quote endpoint**: 1 req/s
- Batch: 1 call for N symbols (compliant)
- Loop: N calls for N symbols (violates rate limit if N > 1)

**LTP endpoint**: ~6.7 req/s
- Batch: 1 call for N symbols (compliant)
- Loop: N calls for N symbols (may violate if N > 6)

---

## 12. Migration Recommendations

1. **Implement batch operations** in greenfield (critical for performance)
2. **Implement OHLC method** in greenfield (or document workaround)
3. **Add open interest** to `Candle` entity (if needed for derivatives)
4. **Standardize error handling** (archive raises, greenfield returns defaults)
5. **Add pagination support** (if Dhan API adds it in future)
6. **Document rate limits** in service layer (prevent violations)
