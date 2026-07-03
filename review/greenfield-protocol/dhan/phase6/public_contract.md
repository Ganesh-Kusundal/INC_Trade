# Phase 6 — Public Contract: Historical Data & Market Data APIs

> Greenfield Broker Replication Protocol — Dhan  
> Phase 6: Historical Data  
> Source: `archive/brokers/dhan/historical.py`, `archive/brokers/dhan/market_data.py`, `brokers/adapters/dhan/historical.py`, `brokers/adapters/dhan/market_data.py`, `brokers/ports/historical.py`, `brokers/ports/market_data.py`, `brokers/services/market_data_service.py`

---

## 1. Historical Data API — Full Contract

### 1.1 Archive Contract

**Class:** `HistoricalAdapter`  
**Module:** `archive/brokers/dhan/historical.py`

```python
class HistoricalAdapter:
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object)

    def get_historical(
        self,
        symbol: str,          # Instrument symbol (e.g., "RELIANCE", "NIFTY")
        exchange: str,        # Exchange code (e.g., "NSE", "NFO", "MCX")
        from_date: str,       # Start date as string (e.g., "2024-01-01")
        to_date: str,         # End date as string (e.g., "2024-01-31")
        timeframe: str = "1D" # Timeframe string (see §1.3)
    ) -> pd.DataFrame         # Returns DataFrame with OHLCV + metadata columns
```

**Return DataFrame columns:**
| Column | Type | Description |
|---|---|---|
| `timestamp` | `datetime64[ns]` | Candle timestamp (parsed from epoch or ISO) |
| `open` | float | Opening price |
| `high` | float | High price |
| `low` | float | Low price |
| `close` | float | Closing price |
| `volume` | int | Volume (0 if missing) |
| `oi` | int | Open interest (0 if missing) |
| `symbol` | str | Echo of input symbol |
| `exchange` | str | Echo of input exchange |
| `timeframe` | str | Echo of input timeframe |

**Dhan API endpoints called:**
| Condition | Endpoint | Method |
|---|---|---|
| `interval == "1D"` | `POST /charts/historical` | JSON payload |
| `interval != "1D"` | `POST /charts/intraday` | JSON payload |

**Daily payload (`/charts/historical`):**
```json
{
  "securityId": "2885",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "expiryCode": 0,
  "oi": true,
  "fromDate": "2024-01-01",
  "toDate": "2024-01-31"
}
```

**Intraday payload (`/charts/intraday`):**
```json
{
  "securityId": "2885",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "interval": "5",
  "oi": true,
  "fromDate": "2024-01-01 09:15:00",
  "toDate": "2024-01-01 15:30:00"
}
```

**Session time overrides (archive only):**
| Exchange | Open | Close |
|---|---|---|
| MCX / MCX_COMM | 09:00:00 | 23:30:00 |
| All others (default) | 09:15:00 | 15:30:00 |

---

### 1.2 Greenfield Contract

**Class:** `DhanHistorical`  
**Module:** `brokers/adapters/dhan/historical.py`

```python
class DhanHistorical:
    def __init__(self, client: DhanHttpClient, resolver: DhanInstrumentResolver)

    def get_historical_candles(
        self,
        symbol: str,              # Instrument symbol
        exchange: str,            # Exchange code
        start_time: datetime,     # Start time (timezone-aware recommended)
        end_time: datetime,       # End time (timezone-aware recommended)
        resolution: str,          # Timeframe string (see §1.3)
    ) -> list[Candle]             # Returns list of domain Candle entities

    def get_candles(              # Alias for get_historical_candles
        self, symbol, exchange, start_time, end_time, resolution
    ) -> list[Candle]
```

**Return entity — `Candle`:**
```python
@dataclass(frozen=True)
class Candle:
    symbol: str           # Instrument symbol
    timestamp: datetime   # Timezone-aware (Asia/Kolkata)
    open: Decimal         # Opening price
    high: Decimal         # High price
    low: Decimal          # Low price
    close: Decimal        # Closing price
    volume: int           # Volume (0 if missing)
```

**Dhan API endpoint called:**
| Condition | Endpoint key | URL |
|---|---|---|
| `interval == "1D"` | `ENDPOINTS["historical"]` | `https://api.dhan.co/v2/charts/historical` |
| `interval != "1D"` | `ENDPOINTS["historical"]` | `https://api.dhan.co/v2/charts/historical` |

> **Note:** Greenfield always uses the `/charts/historical` endpoint (via `ENDPOINTS["historical"]`). The archive distinguishes between `/charts/historical` and `/charts/intraday`. This is a **contract divergence** — Dhan's API may require `/charts/intraday` for sub-daily data.

**Greenfield daily payload:**
```json
{
  "securityId": "2885",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "expiryCode": 0,
  "oi": true,
  "fromDate": "2024-01-01",
  "toDate": "2024-01-31"
}
```

**Greenfield intraday payload:**
```json
{
  "securityId": "2885",
  "exchangeSegment": "NSE_EQ",
  "instrument": "EQUITY",
  "interval": "5",
  "oi": true,
  "fromDate": "2024-01-01 09:15:00",
  "toDate": "2024-01-01 15:30:00"
}
```

> **Note:** Greenfield hardcodes `09:15:00` / `15:30:00` for all exchanges. Archive overrides to `09:00:00` / `23:30:00` for MCX. This is a **gap** for MCX instruments.

---

### 1.3 Timeframe / Resolution Mapping

Both archive and greenfield support the same timeframe aliases:

| Input string | Mapped value | Type |
|---|---|---|
| `"1"`, `"1M"`, `"1m"` | `1` | Intraday (1 minute) |
| `"5"`, `"5M"`, `"5m"` | `5` | Intraday (5 minutes) |
| `"15"`, `"15M"`, `"15m"` | `15` | Intraday (15 minutes) |
| `"25"`, `"25M"`, `"25m"` | `25` | Intraday (25 minutes) |
| `"60"`, `"60M"`, `"60m"` | `60` | Intraday (60 minutes) |
| `"1D"`, `"D"`, `"DAY"` | `"1D"` | Daily |

**Unmapped values** pass through as-is (e.g., `"1W"` stays `"1W"`). No validation is performed.

---

## 2. Market Data API — Full Contract

### 2.1 Archive Contract

**Class:** `MarketDataAdapter`  
**Module:** `archive/brokers/dhan/market_data.py`

#### `get_ltp(symbol, exchange="NSE") -> Decimal`
- **Endpoint:** `POST /marketfeed/ltp`
- **Payload:** `{segment: [security_id]}`
- **Returns:** `Decimal` last traded price
- **Failure:** Raises `ValueError` if no data for the security ID

#### `get_quote(symbol, exchange="NSE") -> Quote`
- **Endpoint:** `POST /marketfeed/quote`
- **Payload:** `{segment: [security_id]}`
- **Returns:** `Quote` dataclass with ltp, ohlc, volume, change
- **Failure:** `KeyError` if response structure is unexpected (unhandled)

#### `get_depth(symbol, exchange="NSE") -> MarketDepth`
- **Endpoint:** `POST /marketfeed/quote` (same as quote)
- **Payload:** `{segment: [security_id]}`
- **Returns:** `MarketDepth` with up to 5 bid/ask levels
- **Failure:** `KeyError` if response structure is unexpected (unhandled)

#### `get_ohlc(symbol, exchange="NSE") -> dict`
- **Endpoint:** `POST /marketfeed/ohlc`
- **Payload:** `{segment: [security_id]}`
- **Returns:** Raw `dict` with OHLC values
- **Failure:** `KeyError` if response structure is unexpected (unhandled)

#### `get_batch_ltp(symbols: list[str], exchange="NSE") -> dict[str, Decimal]`
- **Endpoint:** `POST /marketfeed/ltp`
- **Payload:** `{segment: [sid1, sid2, ...]}` (grouped by segment)
- **Returns:** `{symbol: Decimal}` map
- **Failure:** Silently skips symbols that fail resolution

#### `get_batch_quote(symbols: list[str], exchange="NSE") -> dict[str, Quote]`
- **Endpoint:** `POST /marketfeed/quote`
- **Payload:** `{segment: [sid1, sid2, ...]}` (grouped by segment)
- **Returns:** `{symbol: Quote}` map
- **Failure:** Silently skips symbols that fail resolution

---

### 2.2 Greenfield Contract

**Class:** `DhanMarketData`  
**Module:** `brokers/adapters/dhan/market_data.py`

#### `ltp(symbol, exchange="NSE") -> Decimal`
- **Endpoint:** `POST ENDPOINTS["ltp"]` → `https://api.dhan.co/v2/marketfeed/ltp`
- **Payload:** `{segment: [security_id]}`
- **Returns:** `Decimal` last traded price
- **Failure:** Returns `Decimal("0")` if data is missing (no exception)
- **Defensive lookup:** Tries multiple key formats:
  1. `feed[segment][str(sid)]`
  2. `feed[str(sid)]`
  3. `feed[f"{segment}:{sid}"]`
  4. `feed[symbol]`
  5. Falls back to `Decimal("0")`

#### `quote(symbol, exchange="NSE") -> Quote`
- **Endpoint:** `POST ENDPOINTS["quote"]` → `https://api.dhan.co/v2/marketfeed/quote`
- **Payload:** `{segment: [security_id]}`
- **Returns:** `Quote` (domain entity)
- **Mapping:** Delegates to `map_quote(symbol, symbol_data)`
- **Defensive lookup:** Same multi-key fallback as `ltp()`

#### `depth(symbol, exchange="NSE") -> MarketDepth`
- **Endpoint:** `POST ENDPOINTS["quote"]` → `https://api.dhan.co/v2/marketfeed/quote`
- **Payload:** `{segment: [security_id]}`
- **Returns:** `MarketDepth` (domain entity)
- **Mapping:** Delegates to `map_depth(symbol, symbol_data)`
- **Defensive lookup:** Same multi-key fallback as `ltp()`

**Methods NOT present in greenfield adapter:**
- `get_ohlc()` — not implemented
- `get_batch_ltp()` — not implemented
- `get_batch_quote()` — not implemented

---

## 3. Port Interfaces

### 3.1 HistoricalPort

**Module:** `brokers/ports/historical.py`

```python
@runtime_checkable
class HistoricalPort(Protocol):
    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical OHLCV candles."""
        ...
```

**Contract notes:**
- `@runtime_checkable` — supports `isinstance()` checks.
- Single method: `get_historical_candles`.
- Parameters use `datetime` objects (not strings).
- Returns domain `Candle` entities (not DataFrames).
- No async variant exists.
- No cancellation token or timeout parameter.

### 3.2 MarketDataPort

**Module:** `brokers/ports/market_data.py`

```python
class MarketDataPort(Protocol):
    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal: ...
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote: ...
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth: ...
```

**Contract notes:**
- Narrow interface (ISP-compliant) — only 3 methods.
- No `ohlc()`, no batch methods.
- No `get_historical_candles()` — historical is on a separate port.
- Default exchange is `"NSE"`.
- Not `@runtime_checkable` (unlike HistoricalPort).

---

## 4. Service Layer APIs

### 4.1 MarketDataService

**Module:** `brokers/services/market_data_service.py`

```python
class MarketDataService:
    def __init__(
        self,
        provider: MarketDataPort,
        cache_ttl_seconds: float = 1.0,
    )

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal
    def quote(self, symbol: str, exchange: str = "NSE") -> Quote
    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth
    def invalidate(self, symbol: str = "", exchange: str = "") -> None
```

**Behavior:**
- Wraps a `MarketDataPort` provider with TTL-based caching.
- `ltp()` delegates to `quote()` and extracts `.ltp` (shares the cache entry).
- Cache key: `"{type}:{exchange}:{symbol}"`.
- Default TTL: 1.0 second.
- Thread-safe via `threading.Lock`.
- `invalidate()` with no args clears entire cache; with args clears specific keys.

**Cache entry format:** `tuple[float, Quote | MarketDepth]` where `float` is `time.monotonic()` timestamp.

---

## 5. Data Models

### 5.1 Candle (Greenfield domain entity)

```python
@dataclass(frozen=True)
class Candle:
    symbol: str           # Instrument symbol
    timestamp: datetime   # Timezone-aware datetime
    open: Decimal         # Opening price
    high: Decimal         # High price
    low: Decimal          # Low price
    close: Decimal        # Closing price
    volume: int           # Trade volume
```

**Archive equivalent:** DataFrame row with columns `[timestamp, open, high, low, close, volume, oi, symbol, exchange, timeframe]`.

**Differences:**
- Greenfield has no `oi` (open interest) field on `Candle`.
- Greenfield has no `exchange` or `timeframe` fields on `Candle`.
- Greenfield uses `Decimal` for prices; archive uses `float` (via pandas).
- Greenfield timestamps are timezone-aware; archive timestamps are naive `datetime64[ns]`.

### 5.2 Quote (Greenfield domain entity)

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

**Archive equivalent:** `domain.Quote` with fields `[symbol, ltp, open, high, low, close, volume, change]`.

**Differences:**
- Greenfield has `exchange` and `timestamp` fields; archive does not.
- Archive has `change` (net change); greenfield does not.
- Both use `Decimal` for prices.

### 5.3 MarketDepth (Greenfield domain entity)

```python
@dataclass(frozen=True)
class MarketDepth:
    symbol: str
    bids: tuple[DepthLevel, ...] = ()
    asks: tuple[DepthLevel, ...] = ()
    exchange: str = ""
    timestamp: datetime | None = None
```

```python
@dataclass(frozen=True)
class DepthLevel:
    price: Decimal
    quantity: int
    orders: int = 0
```

**Archive equivalent:** `domain.MarketDepth` with `depth_type="DEPTH_5"` and list-based bids/asks.

**Differences:**
- Greenfield uses `tuple` (immutable); archive uses `list`.
- Greenfield has no `depth_type` field.
- Greenfield `MarketDepth.__init__` coerces lists to tuples for frozen safety.

### 5.4 Timeframe / Resolution

No formal `Timeframe` enum exists in either codebase. Timeframes are raw strings mapped via `_TIMEFRAME_MAP` dicts. Valid values are documented in §1.3.

---

## 6. Parameter Validation Rules

### 6.1 Archive Validation

| Parameter | Validation | Failure mode |
|---|---|---|
| `symbol` | None — passed through to resolver | `InstrumentNotFoundError` from resolver |
| `exchange` | None — passed through to resolver | `InstrumentNotFoundError` from resolver |
| `from_date` | `str()` coercion | Silent garbage if invalid format |
| `to_date` | `str()` coercion | Silent garbage if invalid format |
| `timeframe` | `_TIMEFRAME_MAP.get()` with passthrough | Invalid timeframe sent to API; API error |

### 6.2 Greenfield Validation

| Parameter | Validation | Failure mode |
|---|---|---|
| `symbol` | None — passed through to resolver | `InstrumentNotFoundError` from resolver |
| `exchange` | None — passed through to resolver | `InstrumentNotFoundError` from resolver |
| `start_time` | `.strftime("%Y-%m-%d")` | `AttributeError` if not a datetime |
| `end_time` | `.strftime("%Y-%m-%d")` | `AttributeError` if not a datetime |
| `resolution` | `_TIMEFRAME_MAP.get()` with passthrough | Invalid resolution sent to API |

### 6.3 Invariant Assertions

Both implementations call invariant assertions before HTTP requests:
- **Archive:** `assert_dhan_payload(payload, context=...)` and `assert_dhan_identity(sid, segment, context=...)`
- **Greenfield:** `assert_valid_dhan_payload(payload, context=...)`

These are defence-in-depth checks that validate payload structure before sending. They raise `AssertionError` on violation (programming bug, not runtime error).

---

## 7. Contract Divergence Summary

| Aspect | Archive | Greenfield | Severity |
|---|---|---|---|
| Historical endpoint for intraday | `/charts/intraday` | `/charts/historical` | **HIGH** — may fail for sub-daily data |
| MCX session times | `09:00–23:30` override | Hardcoded `09:15–15:30` | **MEDIUM** — wrong data window for MCX |
| Return type (historical) | `pd.DataFrame` | `list[Candle]` | Design improvement |
| LTP missing behavior | `ValueError` raised | `Decimal("0")` returned | **MEDIUM** — silent zero masks errors |
| Batch operations | 6 methods | 3 methods (no batch, no ohlc) | **Gap** — batch not in port |
| `change` field on Quote | Present | Absent | Low — derivable from close - prev_close |
| `oi` field on Candle | Present (DataFrame col) | Absent | **MEDIUM** — OI data lost |
| Cache layer | None | `MarketDataService` with TTL | New capability |
| `get_candles` alias | Not present | Present (protocol compat) | Convenience only |
