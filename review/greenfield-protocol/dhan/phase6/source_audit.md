# Phase 6 Source Audit — Historical Data & Market Data

## Executive Summary

Phase 6 of the Greenfield Broker Replication Protocol for Dhan focuses on **historical data retrieval** and **real-time market data access**. This phase migrates two critical adapter modules from the archive to the greenfield architecture:

1. **Historical Data Adapter** — Retrieves OHLCV candles for daily and intraday timeframes
2. **Market Data Adapter** — Provides LTP, quotes, market depth, and OHLC data

The migration transforms monolithic, pandas-dependent adapters into a clean, port-based architecture with frozen domain entities, dependency injection, and separation of concerns. Key improvements include elimination of pandas dependency, explicit timezone handling, and a service layer with TTL-based caching.

---

## Archive Files

| File | Lines | Purpose |
|------|-------|---------|
| `archive/brokers/dhan/historical.py` | 173 | Historical data retrieval (daily/intraday candles) |
| `archive/brokers/dhan/market_data.py` | 187 | Market data REST API (LTP, quote, depth, OHLC, batch operations) |
| `archive/datalake/gateway.py` | 13 | Data lake gateway stub (placeholder) |

### Archive Key Symbols

#### `archive/brokers/dhan/historical.py`
- **Class**: `HistoricalAdapter`
  - `__init__(client: DhanHttpClient, identity: DhanIdentityProvider)` — Constructor
  - `get_historical(symbol, exchange, from_date, to_date, timeframe)` — Main retrieval method
  - `_parse(data, symbol, exchange, timeframe)` — Response parser (returns `pd.DataFrame`)
  - `_get_instrument_type(inst)` — Instrument type resolver
- **Constants**:
  - `_TIMEFRAME_MAP` — Timeframe string to API interval mapping
  - `_SESSION_OPEN`, `_SESSION_CLOSE` — MCX session times
  - `_DEFAULT_OPEN`, `_DEFAULT_CLOSE` — Default session times (09:15:00, 15:30:00)

#### `archive/brokers/dhan/market_data.py`
- **Class**: `MarketDataAdapter`
  - `__init__(client: DhanHttpClient, identity: DhanIdentityProvider)` — Constructor
  - `_resolve_and_segment(symbol, exchange)` — Instrument resolution helper
  - `get_ltp(symbol, exchange)` — Last Traded Price retrieval
  - `get_quote(symbol, exchange)` — Full quote with OHLCV
  - `get_depth(symbol, exchange)` — Market depth (5-level bid/ask)
  - `get_ohlc(symbol, exchange)` — OHLC data only
  - `get_batch_ltp(symbols, exchange)` — Batch LTP for multiple symbols
  - `get_batch_quote(symbols, exchange)` — Batch quotes for multiple symbols

#### `archive/datalake/gateway.py`
- **Class**: `DataLakeGateway` — Stub implementation (no functionality)

---

## Greenfield Files

| File | Lines | Purpose |
|------|-------|---------|
| `brokers/adapters/dhan/historical.py` | 160 | Greenfield historical data adapter (returns `list[Candle]`) |
| `brokers/adapters/dhan/market_data.py` | 90 | Greenfield market data adapter (LTP, quote, depth) |
| `brokers/ports/historical.py` | 44 | Historical data port (Protocol definition) |
| `brokers/ports/market_data.py` | 19 | Market data port (Protocol definition) |
| `brokers/services/market_data_service.py` | 75 | Service layer with TTL caching |
| `brokers/domain/entities.py` | 169 | Domain entities (Candle, Quote, MarketDepth, etc.) |
| `brokers/adapters/dhan/config.py` | 116 | Endpoint configuration and rate limits |
| `brokers/adapters/dhan/mapper.py` | 202 | DTO → domain entity mappers |

### Greenfield Key Symbols

#### `brokers/adapters/dhan/historical.py`
- **Class**: `DhanHistorical`
  - `__init__(client: DhanHttpClient, resolver: DhanInstrumentResolver)` — Constructor
  - `get_historical_candles(symbol, exchange, start_time, end_time, resolution)` — Main method
  - `get_candles(...)` — Alias for protocol compatibility
  - `_parse(data, symbol)` — Response parser (returns `list[Candle]`)
- **Constants**:
  - `_TIMEFRAME_MAP` — Timeframe mapping (same as archive)

#### `brokers/adapters/dhan/market_data.py`
- **Class**: `DhanMarketData`
  - `__init__(client: DhanHttpClient, resolver: DhanInstrumentResolver)` — Constructor
  - `ltp(symbol, exchange)` — Last Traded Price
  - `quote(symbol, exchange)` — Full quote
  - `depth(symbol, exchange)` — Market depth

#### `brokers/ports/historical.py`
- **Protocol**: `HistoricalPort`
  - `get_historical_candles(symbol, exchange, start_time, end_time, resolution) -> list[Candle]`

#### `brokers/ports/market_data.py`
- **Protocol**: `MarketDataPort`
  - `ltp(symbol, exchange) -> Decimal`
  - `quote(symbol, exchange) -> Quote`
  - `depth(symbol, exchange) -> MarketDepth`

#### `brokers/services/market_data_service.py`
- **Class**: `MarketDataService`
  - `__init__(provider: MarketDataPort, cache_ttl_seconds: float = 1.0)` — Constructor
  - `ltp(symbol, exchange)` — Cached LTP (delegates to quote)
  - `quote(symbol, exchange)` — Cached quote
  - `depth(symbol, exchange)` — Cached depth
  - `invalidate(symbol, exchange)` — Cache invalidation
  - `_get_cached(key)`, `_set_cached(key, value)` — Internal cache methods

#### `brokers/domain/entities.py`
- **Dataclass**: `Candle` (frozen)
  - Fields: `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`
- **Dataclass**: `Quote` (frozen)
  - Fields: `symbol`, `ltp`, `exchange`, `open`, `high`, `low`, `close`, `volume`, `timestamp`
- **Dataclass**: `MarketDepth` (frozen)
  - Fields: `symbol`, `bids`, `asks`, `exchange`, `timestamp`
- **Dataclass**: `DepthLevel` (frozen)
  - Fields: `price`, `quantity`, `orders`

---

## Historical Data API Methods

### Archive Implementation

#### `get_historical(symbol, exchange, from_date, to_date, timeframe)`
- **Endpoint**: `/charts/historical` (daily) or `/charts/intraday` (intraday)
- **Method**: POST
- **Parameters**:
  - `symbol`: Instrument symbol (string)
  - `exchange`: Exchange code (NSE, BSE, NFO, etc.)
  - `from_date`: Start date (string, format: YYYY-MM-DD)
  - `to_date`: End date (string, format: YYYY-MM-DD)
  - `timeframe`: Time resolution (default: "1D")
- **Returns**: `pd.DataFrame` with columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `oi`, `symbol`, `exchange`, `timeframe`
- **Payload Construction**:
  - Daily: `securityId`, `exchangeSegment`, `instrument`, `expiryCode=0`, `oi=True`, `fromDate`, `toDate`
  - Intraday: Same + `interval` (numeric), session times appended to dates

### Greenfield Implementation

#### `get_historical_candles(symbol, exchange, start_time, end_time, resolution)`
- **Endpoint**: `ENDPOINTS["historical"]` → `/charts/historical`
- **Method**: POST
- **Parameters**:
  - `symbol`: Instrument symbol (string)
  - `exchange`: Exchange code (string)
  - `start_time`: Start datetime (datetime object)
  - `end_time`: End datetime (datetime object)
  - `resolution`: Time resolution (string, default: "1D")
- **Returns**: `list[Candle]` (frozen domain entities)
- **Payload Construction**: Same as archive, but uses `datetime.strftime()` for date formatting
- **Parsing**: Handles both row-oriented and columnar response formats

#### `get_candles(...)`
- Alias for `get_historical_candles()` (protocol compatibility)

---

## Market Data API Methods

### LTP (Last Traded Price)

#### Archive: `get_ltp(symbol, exchange="NSE")`
- **Endpoint**: `/marketfeed/ltp`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `Decimal` (last_price)
- **Response Path**: `data[segment][security_id]["last_price"]`

#### Greenfield: `ltp(symbol, exchange="NSE")`
- **Endpoint**: `ENDPOINTS["ltp"]` → `/marketfeed/ltp`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `Decimal` (last_price)
- **Response Path**: Multiple fallback paths (segment→sid, sid, segment:sid, symbol)

### Quote

#### Archive: `get_quote(symbol, exchange="NSE")`
- **Endpoint**: `/marketfeed/quote`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `Quote` (domain entity)
- **Fields**: symbol, ltp, open, high, low, close, volume, change

#### Greenfield: `quote(symbol, exchange="NSE")`
- **Endpoint**: `ENDPOINTS["quote"]` → `/marketfeed/quote`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `Quote` (via `map_quote()` mapper)
- **Fields**: Same as archive

### Market Depth

#### Archive: `get_depth(symbol, exchange="NSE")`
- **Endpoint**: `/marketfeed/quote`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `MarketDepth` (5-level bid/ask)
- **Response Path**: `data[segment][security_id]["depth"]["buy"|"sell"]`

#### Greenfield: `depth(symbol, exchange="NSE")`
- **Endpoint**: `ENDPOINTS["quote"]` → `/marketfeed/quote`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `MarketDepth` (via `map_depth()` mapper)
- **Response Path**: Multiple fallback paths

### OHLC

#### Archive: `get_ohlc(symbol, exchange="NSE")`
- **Endpoint**: `/marketfeed/ohlc`
- **Method**: POST
- **Payload**: `{segment: [security_id]}`
- **Returns**: `dict` (open, high, low, close)

#### Greenfield: **NOT IMPLEMENTED**
- Endpoint defined in config but no method in `DhanMarketData`

### Batch Operations

#### Archive: `get_batch_ltp(symbols, exchange="NSE")`
- **Endpoint**: `/marketfeed/ltp`
- **Method**: POST
- **Payload**: `{segment: [sid1, sid2, ...]}` (grouped by segment)
- **Returns**: `dict[str, Decimal]` (symbol → ltp)

#### Archive: `get_batch_quote(symbols, exchange="NSE")`
- **Endpoint**: `/marketfeed/quote`
- **Method**: POST
- **Payload**: `{segment: [sid1, sid2, ...]}` (grouped by segment)
- **Returns**: `dict[str, Quote]` (symbol → Quote)

#### Greenfield: **NOT IMPLEMENTED**

---

## Timeframe Definitions

### Archive `_TIMEFRAME_MAP`
```python
{
    "1": 1, "1M": 1, "1m": 1,        # 1 minute
    "5": 5, "5M": 5, "5m": 5,        # 5 minutes
    "15": 15, "15M": 15, "15m": 15,  # 15 minutes
    "25": 25,                          # 25 minutes
    "60": 60, "60M": 60, "60m": 60,  # 1 hour
    "1D": "1D", "D": "1D", "DAY": "1D"  # Daily
}
```

### Greenfield `_TIMEFRAME_MAP`
```python
{
    "1m": 1, "1M": 1, "1": 1,        # 1 minute
    "5m": 5, "5M": 5, "5": 5,        # 5 minutes
    "15m": 15, "15M": 15, "15": 15,  # 15 minutes
    "25m": 25, "25": 25,              # 25 minutes
    "60m": 60, "60M": 60, "60": 60,  # 1 hour
    "1D": "1D", "D": "1D", "DAY": "1D"  # Daily
}
```

**Note**: Greenfield adds explicit "m" suffix variants (e.g., "25m") for consistency.

---

## Data Formats

### Candle Structure

#### Archive (pandas DataFrame)
```
Columns: timestamp, open, high, low, close, volume, oi, symbol, exchange, timeframe
Types:   datetime64, float,   float, float, float, int,    int, str,    str,      str
```

#### Greenfield (Candle dataclass)
```python
@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime  # timezone-aware (Asia/Kolkata)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
```

**Key Differences**:
- Archive uses pandas DataFrame (mutable, float precision)
- Greenfield uses frozen dataclass (immutable, Decimal precision)
- Greenfield includes explicit timezone (Asia/Kolkata)
- Archive includes `oi` (open interest), `exchange`, `timeframe` fields
- Greenfield omits `oi` (not in domain entity)

### Quote Structure

#### Archive (Quote from `domain`)
```python
Quote(
    symbol=str,
    ltp=Decimal,
    open=Decimal,
    high=Decimal,
    low=Decimal,
    close=Decimal,
    volume=int,
    change=Decimal,  # net_change
)
```

#### Greenfield (Quote from `brokers.domain.entities`)
```python
@dataclass(frozen=True)
class Quote:
    symbol: str
    ltp: Decimal
    exchange: str = ""
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    timestamp: datetime | None = None
```

**Key Differences**:
- Archive includes `change` field (net_change)
- Greenfield includes `exchange` and `timestamp` fields
- Greenfield is frozen (immutable)

### Market Depth Structure

#### Archive
```python
MarketDepth(
    symbol=str,
    bids=list[DepthLevel],  # up to 5 levels
    asks=list[DepthLevel],  # up to 5 levels
    depth_type="DEPTH_5",
)
```

#### Greenfield
```python
@dataclass(frozen=True)
class MarketDepth:
    symbol: str
    bids: tuple[DepthLevel, ...]  # immutable tuple
    asks: tuple[DepthLevel, ...]  # immutable tuple
    exchange: str = ""
    timestamp: datetime | None = None
```

**Key Differences**:
- Archive uses `list` (mutable), Greenfield uses `tuple` (immutable)
- Archive includes `depth_type` field
- Greenfield includes `exchange` and `timestamp` fields

---

## Data Lake Gateway

### Archive
- **File**: `archive/datalake/gateway.py`
- **Class**: `DataLakeGateway`
- **Status**: Stub implementation (no functionality)
- **Purpose**: Placeholder for future data lake integration

### Greenfield
- **Status**: Not implemented
- **Note**: No equivalent in greenfield architecture

---

## REST API Endpoints

### Historical Data
| Endpoint | Method | Purpose | Rate Limit |
|----------|--------|---------|------------|
| `/charts/historical` | POST | Daily candles | 0.15s (≈6.7 req/s) |
| `/charts/intraday` | POST | Intraday candles | 0.15s (≈6.7 req/s) |

### Market Data
| Endpoint | Method | Purpose | Rate Limit |
|----------|--------|---------|------------|
| `/marketfeed/ltp` | POST | Last Traded Price | 0.15s (≈6.7 req/s) |
| `/marketfeed/quote` | POST | Full quote + depth | 1.0s (1 req/s) |
| `/marketfeed/ohlc` | POST | OHLC data | 0.15s (≈6.7 req/s) |

### Base URL
- **Archive**: Implicit (via `DhanHttpClient`)
- **Greenfield**: `https://api.dhan.co/v2` (defined in `ENDPOINTS`)

---

## Summary of Changes

### Architectural Improvements
1. **Port-based design**: Protocols define contracts, adapters implement them
2. **Dependency injection**: Constructors accept interfaces, not concrete classes
3. **Frozen entities**: Immutable domain objects (thread-safe)
4. **Service layer**: TTL caching reduces API calls
5. **Mapper separation**: DTO → entity conversion isolated in `mapper.py`
6. **Explicit timezones**: `ZoneInfo("Asia/Kolkata")` instead of naive datetimes
7. **Decimal precision**: All prices use `Decimal` (no float)

### Removed Features
1. **pandas dependency**: Replaced with native Python dataclass
2. **Open interest (oi)**: Not in greenfield `Candle` entity
3. **Batch operations**: `get_batch_ltp()`, `get_batch_quote()` not ported
4. **OHLC method**: `get_ohlc()` not ported to greenfield
5. **Data lake gateway**: Stub removed

### Added Features
1. **Columnar parsing**: Greenfield handles both row and columnar response formats
2. **Fallback paths**: Multiple response path attempts (robustness)
3. **Cache invalidation**: Explicit `invalidate()` method in service layer
4. **Alias method**: `get_candles()` for protocol compatibility

---

## Phase 6 Scope Summary

**In Scope**:
- Historical data retrieval (daily + intraday)
- LTP retrieval
- Quote retrieval
- Market depth retrieval
- Port definitions (HistoricalPort, MarketDataPort)
- Service layer with caching
- Domain entities (Candle, Quote, MarketDepth)

**Out of Scope**:
- Batch operations (LTP, quotes)
- OHLC-only endpoint
- Data lake integration
- Open interest tracking
- WebSocket streaming (Phase 7)
