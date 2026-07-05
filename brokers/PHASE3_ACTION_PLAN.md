# Phase 3 — Unified Capability Model: Action Plan

## Status: 🔴 All dependency analysis complete. Ready to execute.

---

## Codebase Verification Results

| File | Status | Uses Old Protocol | Uses New Dataclass |
|------|--------|------------------|--------------------|
| `domain/capabilities.py` | ✅ New dataclass | No | Yes |
| `ports/capabilities.py` | 🔴 Old Protocol defined | Yes | No |
| `ports/broker.py` | 🔴 Returns old type | Yes | No |
| `adapters/dhan/capabilities.py` | ✅ Already returns new | No | Yes |
| `adapters/dhan/new_capabilities.py` | 🔴 Old Protocol impl | Yes | No |
| `adapters/dhan/gateway.py` | 🔴 Calls old | Yes | No |
| `adapters/paper/capabilities.py` | 🔴 Old Protocol impl | Yes | No |
| `adapters/paper/gateway.py` | 🔴 Returns old (`PaperGateway.capabilities()`) | Yes | No |
| `adapters/upstox/capabilities.py` | ✅ Already returns new | No | Yes |
| `adapters/upstox/gateway.py` | ✅ Returns new | No | Yes |
| `services/capability_discovery.py` | 🔴 Uses `has_feature()` | Yes | No |
| `services/broker_router.py` | 🔴 Uses `has_feature()` | Yes | No |

---

## Execution Order (strictly dependency-driven)

### Step 1: Add missing fields to `BrokerCapabilities`

**What**: Add `supports_alerts`, `supports_edis`, `supports_exit_all`, `supports_ip_management`, `supports_basket_orders`, `supports_gtt`, `supports_mtf`, `supports_slice_order` to `domain/capabilities.py`.

**Why**: These features exist in `domain/constants/capabilities.py` as `FEATURE_*` constants but have no corresponding `supports_*` field in `BrokerCapabilities`. Without these, `supports("edis")` silently returns `False` for all brokers.

**File**: `domain/capabilities.py` — lines 48-76

**Risk**: None (adding frozen dataclass fields is backward-compatible — existing callers don't use these missing fields)

**Test to write**: `test_all_feature_constants_have_corresponding_field` in `test_capability_architecture.py`

---

### Step 2: Update `adapters/dhan/capabilities.py` with all feature fields

**What**: Populate the new fields in `dhan_capabilities()` function.

**Current state**: `dhan_capabilities()` in `adapters/dhan/capabilities.py` returns `BrokerCapabilities` (new dataclass), but it's **not called by the gateway**.

**File**: `adapters/dhan/capabilities.py`

---

### Step 3: Migrate Paper gateway to new dataclass

**What**: 
- Replace `PaperCapabilities` class (old Protocol) in `adapters/paper/capabilities.py`
- Create `paper_capabilities()` that returns `BrokerCapabilities`
- Update `PaperGateway.capabilities()` to return `BrokerCapabilities`
- Delete `adapters/paper/capabilities.py`

**Files affected**:
- `adapters/paper/capabilities.py` — **DELETE after migration**
- `adapters/paper/gateway.py` — Update `capabilities()` method + imports
- `adapters/paper/gateway.py` (MetaGateway) — Update its `capabilities()` if needed

**Current code in `paper/gateway.py:292-293`**:
```python
def capabilities(self) -> Capabilities:
    return paper_capabilities()
```

**Target**:
```python
def capabilities(self) -> BrokerCapabilities:
    return paper_capabilities()
```

---

### Step 4: Migrate Dhan gateway to new dataclass

**What**:
- Update `DhanGateway.capabilities()` to call `dhan_capabilities()` from `adapters/dhan/capabilities.py`
- Remove dead import: `from brokers.adapters.dhan.new_capabilities import dhan_capabilities as new_dhan_capabilities`
- Delete `adapters/dhan/new_capabilities.py`

**Files affected**:
- `adapters/dhan/gateway.py:15-17` — Remove dead import, update call
- `adapters/dhan/new_capabilities.py` — **DELETE**

**Current code in `dhan/gateway.py:74-76`**:
```python
def capabilities(self) -> Capabilities:
    """Return Dhan broker capability matrix."""
    return new_dhan_capabilities()
```

**Target**:
```python
def capabilities(self) -> BrokerCapabilities:
    """Return Dhan broker capability matrix."""
    return dhan_capabilities()
```

---

### Step 5: Update `ports/broker.py` return type

**What**: Change `BrokerGateway.capabilities()` return type from `Capabilities` to `BrokerCapabilities`.

**File**: `ports/broker.py:37`

**Current**:
```python
def capabilities(self) -> Capabilities:
```

**Target**:
```python
def capabilities(self) -> "BrokerCapabilities":
```

(Use string annotation to avoid circular import since `BrokerCapabilities` is in `domain/capabilities.py`)

---

### Step 6: Remove old `Capabilities` Protocol from `ports/capabilities.py`

**What**: Remove the `Capabilities` class (lines 17-46). Keep all extension providers (`MarginProvider`, `SuperOrderProvider`, etc.).

**Files affected**:
- `ports/capabilities.py` — Remove `Capabilities` class
- `ports/__init__.py` — Remove `Capabilities` from imports and `__all__`

---

### Step 7: Update services

**What**: Replace `has_feature()` calls with `supports()` in both services.

**File**: `services/capability_discovery.py:46`:
```python
# Current:
return gateway.capabilities().has_feature(feature)
# Target:
return gateway.capabilities().supports(feature)
```

**File**: `services/broker_router.py:67`:
```python
# Current:
if gateway.capabilities().has_feature(capability):
# Target:
if gateway.capabilities().supports(capability):
```

---

### Step 8: Update tests

**What**: Migrate all test files from `has_feature` to `supports`.

**Files affected**:
1. `tests/unit/test_capability_architecture.py`
   - `test_capabilities_work()` — lines 42-49: `caps.has_feature(FEATURE_ORDERS)` → `caps.supports("orders")`
   - `test_capability_discovery_works()` — lines 76-77: `discovery.has_feature("paper", FEATURE_ORDERS)` → update
   - Add new test: `test_unified_capability_model()`

2. `tests/unit/test_gateway_completeness.py`
   - Lines 24-26: `caps.has_feature("orders")` → `caps.supports("orders")`

3. `tests/unit/test_broker_router.py`
   - Line 18: Update mock to return `BrokerCapabilities` instead of old Protocol

4. `tests/contract/test_capability_contract.py`
   - Update to only test new `supports()` path
   - Test for all three adapters

---

### Step 9: Run test suite

```bash
# Architecture tests (must pass: 59)
python -m pytest tests/unit/test_architecture.py -m architecture -v

# Contract tests (must pass: 58)
python -m pytest tests/contract/ -v

# Unit tests (must pass: 1,363+)
python -m pytest tests/unit/ -v -q

# Full non-integration suite
python -m pytest -m "not integration" --ignore=tests/contract --ignore=tests/integration -q
```

---

### Step 10: Cleanup verification

```bash
# Verify no old Protocol usage remains
grep -r "has_feature" brokers/ --include="*.py" | grep -v __pycache__
grep -r "get_feature_metadata" brokers/ --include="*.py" | grep -v __pycache__
grep -r "class Capabilities" brokers/ --include="*.py" | grep -v __pycache__
grep -r "from brokers.ports.capabilities import Capabilities" brokers/ --include="*.py" | grep -v __pycache__

# Verify deleted files don't exist
test ! -f brokers/adapters/dhan/new_capabilities.py
test ! -f brokers/adapters/paper/capabilities.py
```

---

## Rollback Plan

If Phase 3 migration breaks anything:

1. **Revert `domain/capabilities.py`** if new fields cause issues
2. **Restore deleted files** from git: `git checkout -- brokers/adapters/dhan/new_capabilities.py brokers/adapters/paper/capabilities.py`
3. **Revert service changes**: `git checkout -- brokers/services/capability_discovery.py brokers/services/broker_router.py`
4. **Revert gateway changes**: `git checkout -- brokers/adapters/dhan/gateway.py brokers/adapters/paper/gateway.py`

The old `Capabilities` Protocol code path remains functional until Step 6 (actual removal), so Steps 1-5 are individually revertible.

---

## Acceptance Criteria for Phase 3

```
✅ No broker uses has_feature() or get_feature_metadata()
✅ All three adapters return BrokerCapabilities dataclass
✅ Capabilities Protocol class removed from ports/
✅ services/capability_discovery.py uses supports()
✅ services/broker_router.py uses supports()
✅ 1,363+ unit tests pass (no regressions)
✅ 59 architecture tests pass
✅ 58 contract tests pass
✅ adapters/dhan/new_capabilities.py deleted
✅ adapters/paper/capabilities.py deleted
✅ ports/broker.py returns BrokerCapabilities type
✅ No dead imports remain
```
