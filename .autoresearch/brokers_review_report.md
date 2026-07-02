# Quantitative Broker Adapter Compliance Audit Report

## Executive Summary

Scanned broker adapters (`brokers/dhan`, `brokers/upstox`, `brokers/common`). Found **3** compliance issues.

- 🔴 Critical: **0**
- 🟠 High: **3**
- 🟡 Medium: **0**
- 🟢 Low: **0**

## 1. Audit Findings

### 1. 🟠 High — UNNORMALIZED ADAPTER EXCEPTION
- **Location**: `brokers/dhan/gateway.py (match: except Exception)`
- **Affected Adapter(s)**: Dhan Gateway
- **Diagnosis**: Dhan adapter exposes raw exception Exception directly to the domain layer instead of normalizing it.
- **Risk**: Contract divergence / unclassified exception leakage
- **Prescription**:
Catch provider-specific errors and raise a unified `AdapterException`.

```python
# Before:
try:
    res = self._conn.orders.place_order(request)
except Exception as e:
    raise e

# After:
try:
    res = self._conn.orders.place_order(request)
except DhanSDKError as e:
    raise AdapterException(code='EXECUTION_FAILED', message=str(e))
```

---
### 2. 🟠 High — UNNORMALIZED ADAPTER EXCEPTION
- **Location**: `brokers/dhan/gateway.py (match: except Exception)`
- **Affected Adapter(s)**: Dhan Gateway
- **Diagnosis**: Dhan adapter exposes raw exception Exception directly to the domain layer instead of normalizing it.
- **Risk**: Contract divergence / unclassified exception leakage
- **Prescription**:
Catch provider-specific errors and raise a unified `AdapterException`.

```python
# Before:
try:
    res = self._conn.orders.place_order(request)
except Exception as e:
    raise e

# After:
try:
    res = self._conn.orders.place_order(request)
except DhanSDKError as e:
    raise AdapterException(code='EXECUTION_FAILED', message=str(e))
```

---
### 3. 🟠 High — UNNORMALIZED ADAPTER EXCEPTION
- **Location**: `brokers/dhan/gateway.py (match: except InstrumentNotFoundError)`
- **Affected Adapter(s)**: Dhan Gateway
- **Diagnosis**: Dhan adapter exposes raw exception InstrumentNotFoundError directly to the domain layer instead of normalizing it.
- **Risk**: Contract divergence / unclassified exception leakage
- **Prescription**:
Catch provider-specific errors and raise a unified `AdapterException`.

```python
# Before:
try:
    res = self._conn.orders.place_order(request)
except Exception as e:
    raise e

# After:
try:
    res = self._conn.orders.place_order(request)
except DhanSDKError as e:
    raise AdapterException(code='EXECUTION_FAILED', message=str(e))
```

---

## 2. Adapter Consistency Matrix

| Protocol Method | Dhan Adapter Status | Upstox Adapter Status | Notes |
| :--- | :--- | :--- | :--- |
| `cancel_order` | ✅ Implemented | ✅ Implemented | |
| `close` | ✅ Implemented | ✅ Implemented | |
| `disconnect` | ❌ Missing | ✅ Implemented | |
| `get_depth_snapshot` | ❌ Missing | ❌ Missing | |
| `get_historical_bars` | ❌ Missing | ❌ Missing | |
| `get_margins` | ⚠️ Mapped via Adapter | ❌ Missing | |
| `get_orders` | ⚠️ Mapped via Adapter | ❌ Missing | |
| `get_positions` | ⚠️ Mapped via Adapter | ❌ Missing | |
| `get_quote_snapshot` | ❌ Missing | ❌ Missing | |
| `get_trades` | ⚠️ Mapped via Adapter | ❌ Missing | |
| `health` | ❌ Missing | ❌ Missing | |
| `modify_order` | ✅ Implemented | ✅ Implemented | |
| `open_market_stream` | ❌ Missing | ❌ Missing | |
| `open_order_stream` | ❌ Missing | ❌ Missing | |
| `place_order` | ✅ Implemented | ✅ Implemented | |

## 3. Reliability Risk Register

| Adapter | Risk | Trigger | Impact | Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| Dhan WS | Ghost connection | Missing ping/pong listener | Silent price feed drop | Implement heartbeat timeout |
| Dhan HTTP | 429 Rate Throttling | Excessive scanning requests | HTTP 429 exceptions returned | Introduce QuotaScheduler limits |

## 4. Remediation Roadmap

| Phase | Task | Effort | Dependencies |
| :--- | :--- | :--- | :--- |
| Phase A | Fix domain-adapter leaks | Small | None |
| Phase B | Implement standardized HTTP exception maps | Medium | None |
| Phase C | Add ping/heartbeat checks to WS connections | Medium | Phase B |