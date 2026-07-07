# Platform Architecture Adoption Plan

**Date:** July 6, 2026  
**Status:** Design Complete — Ready for Multi-Agent Implementation  
**Source:** Broker Abstraction Principle vision + Codebase Audit

---

## Executive Summary

The INC_Trade Broker SDK is **already ~90% aligned** with the Broker Abstraction Principle. Every infrastructure concern (auth, tokens, rate limiting, REST/WS clients, retry/reconnect, security ID mapping, capability discovery, request pipeline) is already internal and hidden from the consumer.

Three gaps remain to reach 100%:
1. **No `connect("dhan")` auto-login** — users still provide `client_id` + `access_token` manually
2. **`Broker` class naming** — should be `Platform` as the composition root
3. **Symbol format** — no convenience overload for `"NSE:RELIANCE"` colon-format

The infrastructure for auto-login already exists in full: `CredentialResolver`, `AuthManager`, `DhanTotpClient`, `TokenScheduler`, `TotpCooldownGuard`, `JsonTokenStateStore`. We just need to wire them together inside `Platform.connect()`.

**Implementation effort:** ~1 new file, ~7 modified files, 0 deleted files. **Zero breaking changes.**

---

## 1. Current State Audit: What's Already Hidden

| Concern | Status | Implementation |
|---------|--------|----------------|
| OAuth / login flows | ✅ Hidden | `CredentialResolver` + `AuthManager` |
| Token generation | ✅ Hidden | `TotpGenerator` (RFC 6238) |
| Token refresh | ✅ Hidden | `TokenScheduler` (daemon thread) |
| Token expiry | ✅ Hidden | `TokenState.expires_at` / `refresh_recommended()` |
| Session lifecycle | ✅ Hidden | `AuthManager.acquire()/refresh()/revoke()` |
| Credential storage | ✅ Hidden | `JsonTokenStateStore` (0o600 permissions) |
| TOTP generation | ✅ Hidden | `TotpGenerator.code_now()` |
| API auth headers | ✅ Hidden | `DhanHttpClient._session.headers` |
| Reconnect logic | ✅ Hidden | `StreamOrchestrator` |
| Heartbeat management | ✅ Hidden | `StreamHealth` / ping-pong |
| WebSocket lifecycle | ✅ Hidden | `DhanMarketFeed.start()/stop()` |
| Rate limiting | ✅ Hidden | `BaseHttpClient` endpoint throttling |
| Retry policies | ✅ Hidden | HTTP retry in client |
| Circuit breakers | ✅ Hidden | Exponential backoff |
| Broker-specific endpoints | ✅ Hidden | `DhanHttpClient` / `UpstoxHttpClient` |
| REST clients | ✅ Hidden | Provider protocol hides all HTTP |
| WebSocket clients | ✅ Hidden | Provider protocol hides all WS |
| JSON parsing | ✅ Hidden | Mapper classes per broker |
| Request throttling | ✅ Hidden | `RateConfig` / `BaseHttpClient` |
| Caching | ✅ Hidden | `MemoryIdempotencyCache` |
| Connection pooling | ✅ Hidden | `httpx.AsyncClient` in provider |
| Security ID mapping | ✅ Hidden | `instrument_resolver` + `mapper.py` |
| Instrument token mapping | ✅ Hidden | `resolve_security_id()` |
| Exchange mapping | ✅ Hidden | `_EXCHANGE_TO_SEGMENT` dicts |
| Broker-specific symbols | ✅ Hidden | `trading_symbol` on `InstrumentIdentity` |
| Order state mapping | ✅ Hidden | `DhanMapper.map_order()` |
| Error code mapping | ✅ Hidden | `OrderResponse.fail(error_code=...)` |
| Broker capability discovery | ✅ Hidden | `ProviderCapabilities` + `Capability` enum |
| Extension loading | ✅ Hidden | `ExtensionAccess` typed protocols |

**Result:** Every item on the "must remain internal" checklist is already internal. The SDK is not a thin wrapper — it IS a Broker Platform.

---

## 2. The Three Gaps (What Needs to Change)

### Gap 1: No `Platform.connect("dhan")` auto-login

**Current:**
```python
broker = Broker.dhan(client_id="123", access_token="tok")  # Manual token
```

**Target:**
```python
platform = await Platform.connect("dhan")  # Auto-login from .env.dhan
```

**Infrastructure already exists:**
- `CredentialResolver.for_dhan()` — loads `DHAN_CLIENT_ID`, `DHAN_TOTP_SECRET`, `DHAN_PIN` from `.env.dhan`
- `DhanTotpClient.login(totp_secret, pin, client_id)` — POST to Dhan token endpoint, returns `TokenState`
- `AuthManager(on_acquire=..., on_refresh=..., store=...)` — full lifecycle with cache
- `JsonTokenStateStore("~/.config/inc_trade/.dhan_token.json")` — persistent token cache
- `DhanTokenScheduler(auth_manager)` — daemon thread, proactive refresh, exponential backoff
- `TotpCooldownGuard(persist_path="runtime/dhan-totp-cooldown.json")` — prevents rate-limiting

**What's missing:** A single `async def connect()` function that wires them all together (~50 lines).

### Gap 2: `Broker` vs `Platform` naming

**Current:** `Broker` is the composition root class (factory + DI).  
**Target:** `Platform` as the named composition root. `Broker` kept as deprecated alias.

**Why:** The term "Broker" implies a thin API wrapper. "Platform" communicates that this is a complete financial operating system with orchestration, lifecycle management, and hidden infrastructure.

**Impact:** Zero breaking changes. `Broker` becomes `Broker = Platform` in `__init__.py` with a deprecation warning.

### Gap 3: Symbol format convenience

**Current:**
```python
broker.instrument("RELIANCE", Exchange.NSE)
```

**Target (both work):**
```python
platform.instrument("NSE:RELIANCE")           # Colon format
platform.instrument("RELIANCE", Exchange.NSE) # Original format
```

**What's needed:** A `"EXCHANGE:SYMBOL"` parsing overload in `Platform.instrument()` (~10 lines).

---

## 3. Platform Class Design

### 3.1 Class Structure

```python
class Platform:
    """Composition root and orchestration entry point.

    Replaces Broker as the SDK's primary entry point. Wires authentication,
    provider creation, and domain object injection.

    Usage::

        # Auto-login (recommended)
        platform = await Platform.connect("dhan")

        # Manual token (for advanced users)
        platform = Platform.dhan(client_id="123", access_token="tok")

        # Paper trading
        platform = Platform.paper()

        # Multi-broker
        platform = Platform.compose(
            primary=await Platform.connect("dhan"),
            secondary=Platform.upstox(access_token="tok"),
        )
    """

    __slots__ = ("_account", "_event_bus", "_provider",
                 "_risk_policy", "_token_scheduler")

    def __init__(
        self,
        provider: Provider,
        *,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        token_scheduler: Any | None = None,
    ) -> None:
        self._provider = provider
        self._risk_policy = risk_policy
        self._event_bus = event_bus
        self._account: Account | None = None
        self._token_scheduler = token_scheduler  # NEW: for cleanup

    @staticmethod
    async def connect(provider_name: str, **kwargs: Any) -> Platform:
        """Auto-login and connect to a broker.

        Args:
            provider_name: "dhan" or "upstox"
        """
        if provider_name == "dhan":
            return await Platform._connect_dhan(**kwargs)
        elif provider_name == "upstox":
            return await Platform._connect_upstox(**kwargs)
        else:
            raise ValueError(f"Unknown provider: {provider_name}. "
                             f"Use 'dhan', 'upstox', or 'paper'.")

    # ... factory methods (dhan, upstox, paper, compose) ported from Broker ...

    def instrument(
        self,
        symbol_or_key: str,
        exchange: Exchange | None = None,
        **kwargs: Any,
    ) -> Instrument:
        """Smart instrument factory.

        Both formats work::

            platform.instrument("NSE:RELIANCE")
            platform.instrument("RELIANCE", Exchange.NSE)
        """
        if exchange is None:
            if ":" not in symbol_or_key:
                raise ValueError(
                    "Must provide exchange or use 'EXCHANGE:SYMBOL' format"
                )
            exchange_str, symbol = symbol_or_key.split(":", 1)
            exchange = Exchange(exchange_str)
        else:
            symbol = symbol_or_key
        return Instrument(symbol, exchange, provider=self._provider, **kwargs)

    async def disconnect(self) -> None:
        """Disconnect: stop scheduler, then provider."""
        if self._token_scheduler is not None:
            self._token_scheduler.stop()
        await self._provider.disconnect()

    # ... account(), properties, lifecycle ported from Broker ...
```

### 3.2 `Platform.connect("dhan")` Auto-Login Flow

```
User: platform = await Platform.connect("dhan")
        │
        ▼
Platform._connect_dhan()
        │
        ├─► CredentialResolver.for_dhan()
        │       Reads .env.dhan → DHAN_CLIENT_ID, DHAN_TOTP_SECRET, DHAN_PIN
        │       Validates: must have (TOTP_SECRET + PIN) or ACCESS_TOKEN
        │
        ├─► JsonTokenStateStore("~/.config/inc_trade/.dhan_token.json")
        │       Persistent token cache (0o600 permissions)
        │
        ├─► DhanTotpClient()
        │       TOTP login: POST https://api.dhan.co/v2/auth/token
        │       Cooldown guard: 120s between attempts
        │
        ├─► AuthManager(
        │       on_acquire=lambda: client.login(secret, pin, client_id),
        │       on_refresh=lambda old: client.refresh(secret, pin, client_id),
        │       store=JsonTokenStateStore(...),
        │       refresh_buffer_seconds=300,
        │   )
        │
        ├─► auth_manager.ensure_valid()
        │       │
        │       ├─► Store has valid token? → RETURN (cache hit)
        │       ├─► Store has expired token? → refresh() → TOTP login → RETURN
        │       └─► No stored token? → acquire() → TOTP login → RETURN
        │
        ├─► DhanTokenScheduler(auth_manager).start()
        │       Daemon thread: checks every 60s, refreshes at 5min before expiry
        │       Exponential backoff on rate-limit: 120s → 240s → 480s → 600s
        │
        ├─► DhanProvider(
        │       client_id=creds.client_id,
        │       access_token=auth_manager.access_token,
        │   )
        │
        ├─► auth_manager.register_token_receiver(
        │       lambda new_token: provider.update_token(new_token)
        │   )
        │       Keeps DhanHttpClient session headers in sync with scheduler
        │
        └─► return Platform(provider, token_scheduler=scheduler)
```

**Edge Cases:**
| Scenario | Behavior |
|----------|----------|
| No `.env.dhan` file | `ValueError("DHAN_CLIENT_ID is required")` |
| TOTP cooldown active | `TotpRateLimitError("Wait 87s before retrying")` |
| Network error during login | `DhanTotpError("Dhan token request failed: ...")` |
| Token expired in cache | Auto-refreshes via `on_refresh` callback |
| Process restart | Loads cached token from JSON, validates |
| Scheduler refresh fails | Exponential backoff, logged, doesn't crash |

### 3.3 `Platform.connect("upstox")` Auto-Login Flow

```python
@staticmethod
async def _connect_upstox(**kwargs: Any) -> Platform:
    """Auto-login to Upstox."""
    creds = CredentialResolver.for_upstox()

    if creds.has_totp:
        # Route 1: TOTP-based login (like Dhan)
        from brokers.upstox.totp_client import UpstoxTotpClient
        client = UpstoxTotpClient()
        store = JsonTokenStateStore("~/.config/inc_trade/.upstox_token.json")
        manager = AuthManager(
            on_acquire=lambda: client.login(
                creds.totp_secret, creds.pin, creds.mobile, creds.client_id
            ),
            on_refresh=lambda old: client.refresh(
                creds.totp_secret, creds.pin, creds.mobile, creds.client_id
            ),
            store=store,
        )
    elif creds.has_oauth:
        # Route 2: OAuth flow
        raise NotImplementedError("Upstox OAuth auto-login not yet implemented")
    else:
        raise ValueError("Upstox requires TOTP or OAuth credentials")

    manager.ensure_valid()

    provider = UpstoxProvider(
        client_id=creds.client_id,
        access_token=manager.access_token,
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        **kwargs,
    )
    return Platform(provider)
```

---

## 4. Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          User Code                               │
│  platform = await Platform.connect("dhan")                       │
│  reliance = platform.instrument("NSE:RELIANCE")                  │
│  quote = await reliance.quote()                                  │
└───────────────┬─────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Platform                                  │
│                    (Composition Root)                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ connect("dhan")  factory methods  instrument()  account() │  │
│  │     │                  │                │            │      │  │
│  │     │  wires auth      │  creates       │  creates   │      │  │
│  │     ▼                  ▼                ▼            ▼      │  │
│  │ AuthManager ──► DhanProvider ──► Instrument    Account     │  │
│  │     │                                              │       │  │
│  │     │ background daemon                      RiskPolicy    │  │
│  │     ▼                                              │       │  │
│  │ TokenScheduler ──► hot-swaps token           EventBus      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────┘
                               │ injects Provider
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │ Instrument  │    │   Account   │    │  Extension  │
    │  (Domain)   │    │  (Domain)   │    │   Access    │
    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
           │                  │                  │
           │ delegates IO     │ delegates IO     │ typed access
           ▼                  ▼                  ▼
    ┌─────────────────────────────────────────────────┐
    │              Provider (Protocol)                  │
    │  get_quote()  get_history()  place_order()  ...  │
    └─────────┬───────────────┬───────────────┬───────┘
              │               │               │
    ┌─────────▼───┐  ┌────────▼────┐  ┌───────▼──────┐
    │ DhanProvider│  │UpstoxProvider│ │PaperProvider │
    └──────┬──────┘  └──────┬──────┘  └──────────────┘
           │                │
    ┌──────▼──────┐  ┌──────▼──────┐
    │DhanHttpClient│ │UpstoxClient │  (Internal — never exposed)
    └──────┬──────┘  └─────────────┘
           │
    ┌──────▼──────┐  ┌──────────────┐  ┌────────────────┐
    │ DhanMapper  │  │ DhanMarketFeed│  │ DhanOrderFeed │
    └─────────────┘  └──────────────┘  └────────────────┘

    ┌──────────────────────────────────────────────────┐
    │              Auth Subsystem (Internal)             │
    │  ┌──────────────────┐  ┌───────────────────────┐  │
    │  │CredentialResolver│  │     AuthManager        │  │
    │  │ .env.dhan parser │  │ acquire/refresh/revoke │  │
    │  └──────────────────┘  └───────────┬───────────┘  │
    │                                    │               │
    │              ┌─────────────────────┼───────────┐   │
    │              ▼                     ▼           ▼   │
    │  ┌────────────────┐  ┌──────────────────────┐     │
    │  │ DhanTotpClient │  │JsonTokenStateStore   │     │
    │  │ POST /auth/token│  │ ~/.dhan_token.json   │     │
    │  └────────────────┘  └──────────────────────┘     │
    │  ┌──────────────────────┐                         │
    │  │ DhanTokenScheduler   │ (background daemon)     │
    │  │ check/refresh loop   │                         │
    │  └──────────────────────┘                         │
    └──────────────────────────────────────────────────┘
```

---

## 5. Data Flow Diagrams

### 5.1 Connection Flow

```
User calls: platform = await Platform.connect("dhan")

Step 1: Credential Resolution
  Platform._connect_dhan()
    → CredentialResolver.for_dhan()
      → Reads .env.dhan: DHAN_CLIENT_ID, DHAN_TOTP_SECRET, DHAN_PIN
      → Validates required fields present
      → Returns DhanCredentials(client_id, totp_secret, pin)

Step 2: Storage Setup
  → JsonTokenStateStore("~/.config/inc_trade/.dhan_token.json")
  → Creates store instance (may load existing token from disk)

Step 3: TOTP Client
  → DhanTotpClient(cooldown=TotpCooldownGuard(120s))
  → Client ready for login calls

Step 4: Auth Manager
  → AuthManager(
        on_acquire=lambda: client.login(secret, pin, client_id),
        on_refresh=lambda old: client.refresh(secret, pin, client_id),
        store=store,
        refresh_buffer_seconds=300,
    )
  → Manager loads cached token from store (if exists)

Step 5: Token Acquisition
  → manager.ensure_valid()
    ├─ Cache HIT: token valid → return cached token
    ├─ Cache EXPIRED: token expired → refresh() → TOTP login
    │   → TotpGenerator.code_now(secret) → "482917"
    │   → DhanTotpClient.login(secret, pin, client_id)
    │   → POST https://api.dhan.co/v2/auth/token
    │       Body: {"dhanClientId": "123", "pin": "****", "totp": "482917"}
    │   → Response: {"access_token": "eyJ...", "expires_in": 86400}
    │   → TokenState(access_token, expires_at=now+24h, source=TOTP)
    │   → store.save(token_state)  # Persist to disk
    │   → return token_state
    └─ Cache MISS: no token → acquire() → TOTP login (same as above)

Step 6: Background Scheduler
  → DhanTokenScheduler(auth_manager, check_interval=60, refresh_buffer=300)
  → scheduler.start()  # Daemon thread begins
  → Every 60s: check if refresh_recommended()
  → 5min before expiry: TOTP login for fresh token

Step 7: Provider Creation
  → DhanProvider(
        client_id=creds.client_id,
        access_token=manager.access_token,  # "eyJ..."
    )
  → DhanHttpClient created internally with auth headers

Step 8: Token Receiver Hook
  → manager.register_token_receiver(
        lambda new_token: provider._client.update_token(new_token)
    )
  → When scheduler refreshes, HTTP client headers are hot-swapped

Step 9: Return Platform
  → Platform(provider, token_scheduler=scheduler)
  → User has fully connected platform
```

### 5.2 Market Data Flow

```
User calls: quote = await platform.instrument("NSE:RELIANCE").quote()

Step 1: Symbol Parsing
  → Platform.instrument("NSE:RELIANCE")
  → Splits "NSE:RELIANCE" → Exchange.NSE, "RELIANCE"
  → Instrument("RELIANCE", Exchange.NSE, provider=DhanProvider)

Step 2: Quote Request
  → instrument.quote()
  → await self._provider.get_quote(self)

Step 3: Security ID Resolution
  → DhanProvider._resolve_security_id(instrument)
  → Checks instrument.security_id (empty for user-created instruments)
  → Checks self._instruments dict: {"RELIANCE:NSE": "1333"}
  → Falls back to InstrumentResolver if configured
  → Returns "1333"

Step 4: API Call
  → DhanHttpClient.get_quote("NSE_EQ", [1333])
  → GET https://api.dhan.co/v2/marketfeed/quote?...
  → Rate limiter checks: allowed? → YES
  → Auth headers: "access-token: eyJ..."
  → Response: {"data": {"NSE_EQ": {"1333": {"ltp": 2450.00, ...}}}}

Step 5: Mapping
  → DhanMapper.map_quote(raw, "RELIANCE")
  → Quote(symbol="RELIANCE", ltp=Decimal("2450.00"), open=..., high=..., ...)

Step 6: Cache
  → instrument._cached_quote = quote  # Thread-safe via lock

Step 7: Return
  → User receives Quote value object
```

### 5.3 Execution Flow (with Risk Policy)

```
User calls: response = await platform.account().place_order(request)

Step 1: Account Resolution
  → platform.account()
  → Lazy creation: Account("dhan_default", DhanProvider, risk_policy, event_bus)
  → Cached in platform._account

Step 2: Risk Gate (inside Account.place_order)
  → risk_policy.check(request, provider)
  → _MaxPositionPolicy:
      ├─ quantity=100 > max_quantity=500? → NO → continue
      └─ notional check needed?
          → provider.get_ltp(Instrument("RELIANCE", NSE, provider=...))
          → LTP = 2450.00
          → notional = 2450 × 100 = 245000 > 100000? → YES
          → return RiskDecision.deny("MAX_NOTIONAL", 245000, 100000)

  IF DENIED:
    → event_bus.publish(RISK_REJECTED event)
    → return OrderResponse.fail("Risk denied: MAX_NOTIONAL: 245000 exceeds limit 100000")

Step 3: Execute (if allowed)
  → provider.place_order(request)
  → DhanProvider:
      → resolve security_id (same as market data flow)
      → DhanMapper.build_order_payload(request, "1333", "NSE_EQ", "123")
      → DhanHttpClient.place_order(payload)
      → POST https://api.dhan.co/v2/orders
      → Response: {"orderId": "DHAN-12345", "orderStatus": "PENDING"}

Step 4: Track Order
  → Account._open_orders["DHAN-12345"] = Order(...)
  → event_bus.publish(ORDER_PLACED event)

Step 5: Return
  → OrderResponse.ok(order_id="DHAN-12345", message="Order placed")
```

---

## 6. Module Impact Analysis

### Summary

| Category | Count | Details |
|----------|-------|---------|
| **NEW** | 1 | `brokers/platform.py` |
| **MODIFIED** | 7 | Platform wiring, imports, convenience overload |
| **RENAMED** | 0 | Nothing renamed (backward compat) |
| **REMOVED** | 0 | Nothing removed (backward compat) |
| **UNCHANGED** | ~115 | All auth, domain, provider, infrastructure, tests |

### NEW Files

#### `brokers/platform.py` (~300 lines)
The new Platform class:
- `__init__` — ports from Broker, adds `_token_scheduler` slot
- `connect(provider_name)` — async static method, dispatches to `_connect_dhan/_connect_upstox`
- `_connect_dhan()` — orchestrates CredentialResolver → DhanTotpClient → AuthManager → TokenScheduler → DhanProvider
- `_connect_upstox()` — similar orchestration for Upstox
- `dhan(...)` / `upstox(...)` / `paper(...)` / `compose(...)` — ported from Broker
- `instrument(symbol_or_key, exchange=None)` — convenience overload with colon parsing
- `account()` / `disconnect()` — ported from Broker, disconnect also stops token scheduler
- Properties: `provider`, `capabilities`, `broker_id`, `is_connected` — ported

### MODIFIED Files

#### `brokers/__init__.py`
- Import `Platform` from `brokers.platform`
- Add: `Broker = Platform  # Deprecated alias — use Platform instead`
- Add `Platform` to `__all__`
- Keep `Broker` in `__all__` for backward compat

#### `brokers/broker.py`
- Keep file but add deprecation warning
- Add at top: `warnings.warn("Broker is deprecated, use Platform", DeprecationWarning, stacklevel=2)`
- Could also re-export `Broker = Platform` from `brokers.platform`
- All existing code that imports `from brokers.broker import Broker` still works

#### `brokers/domain/instrument.py`
- Update docstrings: `:class:\`Broker\`` → `:class:\`Platform\``
- No code changes needed

#### `brokers/domain/account.py`
- Update docstrings: `Broker.dhan(...)` → `Platform.connect("dhan")` in examples
- No code changes needed

#### `brokers/dhan/dhan_provider.py`
- Add `update_token(new_token: str)` method for hot-swapping auth headers:
  ```python
  def update_token(self, new_token: str) -> None:
      """Update the access token (called by TokenScheduler on refresh)."""
      self._client.update_access_token(new_token)
  ```

#### `brokers/dhan/client.py`
- Add `update_access_token(token: str)` method to `DhanHttpClient`:
  ```python
  def update_access_token(self, token: str) -> None:
      """Hot-swap the access token in session headers."""
      self._session.headers["access-token"] = token
  ```

#### `brokers/upstox/upstox_provider.py`
- Add `update_token(new_token: str)` method (same pattern as Dhan)

### UNCHANGED Files (~115 files)

All of these require **zero changes**:
- **Auth subsystem:** `credential_resolver.py`, `token_manager.py`, `totp_client.py`, `token_scheduler.py` — work exactly as-is, just wired by `Platform.connect()`
- **Domain layer:** All domain objects, value objects, enums, exceptions, events
- **Provider implementations:** `paper_provider.py`, `dhan_provider.py` (except `update_token`), `upstox_provider.py` (except `update_token`)
- **Infrastructure:** `http_client.py`, `resilience.py`, `rate_config.py`, `cache.py`, `event_bus.py`, `tracing.py`, `metrics.py`, `logging.py`, `health.py`
- **Streaming:** All feed classes, orchestrator, transport, queue, subscription, stream_health
- **Routing:** `composite.py`, `routing.py`
- **Extensions:** `extensions.py`, all extended modules
- **Common:** `instrument_resolver.py`, `instrument_registry.py`, `reconciliation.py`, `idempotency.py`
- **Tests:** All 738 tests continue to pass (they use `Broker.dhan(...)` which is now `Platform.dhan(...)` via alias)

---

## 7. Migration Strategy (Zero-Break, 5 Phases)

### Phase 1: Foundation (Non-breaking)
**Files:** `brokers/platform.py` (NEW), `brokers/__init__.py` (MODIFIED)

- Create `brokers/platform.py` with `Platform` class
- Port all methods from `Broker` to `Platform`
- Update `brokers/__init__.py`: `Broker = Platform` alias
- **After Phase 1:** All existing code works identically. `Broker.dhan(...)` → `Platform.dhan(...)` via alias.

### Phase 2: Convenience Overloads
**Files:** `brokers/platform.py` (MODIFIED)

- Add colon-format parsing to `Platform.instrument()`
- Support both `"NSE:RELIANCE"` and `("RELIANCE", Exchange.NSE)`
- Add tests: `test_platform_convenience_format`

### Phase 3: Auto-Login Wiring
**Files:** `brokers/platform.py` (MODIFIED), `brokers/dhan/dhan_provider.py` (MODIFIED), `brokers/dhan/client.py` (MODIFIED)

- Implement `Platform.connect()` and `Platform._connect_dhan()`
- Add `DhanHttpClient.update_access_token()` for hot-swapping
- Add `DhanProvider.update_token()` as bridge
- Add integration tests: `test_connect_dhan_auto_login`

### Phase 4: Deprecation Communication
**Files:** `brokers/broker.py` (MODIFIED)

- Add `DeprecationWarning` to `brokers/broker.py`
- Update README and docs to show `Platform.connect()` as primary API
- Keep `Broker.dhan()` working but warn

### Phase 5: Cleanup (Future Major Version)
**Files:** `brokers/broker.py` (REMOVED)

- Delete `brokers/broker.py`
- Remove `Broker = Platform` alias from `__init__.py`
- All consumer code uses `Platform` directly

---

## 8. Testing Strategy

### 8.1 Unit Tests (New)

| Test | File | What it validates |
|------|------|-------------------|
| `test_platform_convenience_colon_format` | `tests/test_platform.py` | `"NSE:RELIANCE"` → `Instrument("RELIANCE", Exchange.NSE)` |
| `test_platform_convenience_two_args` | `tests/test_platform.py` | `("RELIANCE", Exchange.NSE)` still works |
| `test_platform_convenience_no_colon_raises` | `tests/test_platform.py` | `"RELIANCE"` without exchange → `ValueError` |
| `test_connect_dhan_missing_creds` | `tests/test_platform.py` | `connect("dhan")` with no `.env.dhan` → `ValueError` |
| `test_connect_dhan_cached_token` | `tests/test_platform.py` | Mocked cached token → no TOTP call |
| `test_connect_dhan_expired_token` | `tests/test_platform.py` | Expired cached token → TOTP refresh called |
| `test_connect_dhan_no_token` | `tests/test_platform.py` | No cached token → TOTP login called |
| `test_connect_dhan_cooldown_active` | `tests/test_platform.py` | Cooldown guard active → `TotpRateLimitError` |
| `test_connect_dhan_network_error` | `tests/test_platform.py` | Network error → `DhanTotpError` |
| `test_connect_dhan_token_receiver` | `tests/test_platform.py` | Scheduler refresh → provider token updated |
| `test_disconnect_stops_scheduler` | `tests/test_platform.py` | `disconnect()` → `scheduler.stop()` called |
| `test_broker_alias_still_works` | `tests/test_platform.py` | `Broker.dhan(...)` → `Platform` instance |
| `test_broker_alias_emits_warning` | `tests/test_platform.py` | `Broker()` → `DeprecationWarning` |

### 8.2 Integration Tests (New)

| Test | What it validates |
|------|-------------------|
| `test_connect_dhan_live` | Real `.env.dhan` → token acquired → quote works |
| `test_token_persistence` | Token saved to JSON → restart → loaded from cache |
| `test_token_scheduler_live` | Scheduler running → token refreshed before expiry |

### 8.3 Backward Compatibility (Existing)

- All 738 existing tests continue to pass
- `Broker.dhan(client_id, access_token)` → still works via alias
- `Broker.upstox(access_token)` → still works
- `Broker.paper()` → still works
- `Broker.compose(primary, secondary)` → still works

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Thread safety: TokenScheduler writes token while HTTP request in-flight | Medium | High | `DhanHttpClient` updates `self._session.headers["access-token"]` — dict assignment is atomic under GIL for single key. Add lock if needed. |
| Process exit: Daemon thread not stopped | Low | Low | `daemon=True` ensures thread dies with process. `disconnect()` explicitly stops it. |
| Rate limit: Dev loop triggers Dhan TOTP cooldown | Medium | Medium | `TotpCooldownGuard` persists cooldown to disk. Survives process restarts. Clear error message tells user wait time. |
| Token file permissions: Token leaked on shared machines | Low | High | `JsonTokenStateStore` sets `0o600` (owner read/write only). Documented in security guide. |
| Existing code breaks: `Broker` alias causes confusion | Low | Low | `Broker = Platform` means all imports resolve. `DeprecationWarning` is only shown when `Broker()` is directly instantiated. |
| Multi-account: Single token file for multiple Dhan accounts | Low | Medium | Future: `Platform.connect("dhan", profile="algo1")` uses separate env prefix and token file. |

---

## 10. Implementation Order (Multi-Agent Parallel)

### Wave A: Foundation (3 files, can be done in parallel)
- **Agent 1:** Create `brokers/platform.py` — port Broker class, add `connect()`, add colon parsing
- **Agent 2:** Update `brokers/__init__.py` — add `Platform` export, `Broker = Platform` alias
- **Agent 3:** Update `brokers/broker.py` — add deprecation warning

### Wave B: Auto-Login Wiring (3 files, sequential)
- **Agent 1:** Implement `Platform._connect_dhan()` using existing auth subsystem
- **Agent 2:** Add `DhanHttpClient.update_access_token()` + `DhanProvider.update_token()`
- **Agent 3:** Add `UpstoxProvider.update_token()` (same pattern)

### Wave C: Tests (2 files, parallel)
- **Agent 1:** Create `brokers/tests/test_platform.py` with 13 unit tests
- **Agent 2:** Create integration tests (marked with `@pytest.mark.integration`)

### Wave D: Validation (parallel)
- **Agent 1:** Run full test suite (738 existing + 13 new)
- **Agent 2:** Run `make mypy` — expect 0 new errors
- **Agent 3:** Run `ruff check` — expect 0 errors
- **Agent 4:** Code review all changes

---

## Appendix A: Before/After API Comparison

### Before (Current)
```python
from brokers import Broker, Exchange

# Manual token — auth details exposed
broker = Broker.dhan(client_id="123", access_token="eyJ...")

reliance = broker.instrument("RELIANCE", Exchange.NSE)
quote = await reliance.quote()
response = await reliance.buy(quantity=10)

account = broker.account()
positions = await account.get_positions()
```

### After (Target)
```python
from brokers import Platform

# Auto-login — zero auth details exposed
platform = await Platform.connect("dhan")

reliance = platform.instrument("NSE:RELIANCE")  # Colon format
quote = await reliance.quote()
response = await reliance.buy(quantity=10)

account = platform.account()
positions = await account.get_positions()

# Explicit disconnect (stops token scheduler)
await platform.disconnect()
```

### After (Advanced — manual token, still works)
```python
from brokers import Platform, Exchange

# Manual token for advanced users
platform = Platform.dhan(client_id="123", access_token="eyJ...")
reliance = platform.instrument("RELIANCE", Exchange.NSE)  # Original format
```

---

## Appendix B: `.env.dhan` Example

```bash
# .env.dhan — placed in project root
DHAN_CLIENT_ID=D123456
DHAN_TOTP_SECRET=JBSWY3DPEHPK3PXP
DHAN_PIN=1234

# Optional: override API endpoint
# DHAN_BASE_URL=https://api.dhan.co/v2
```

---

## Appendix C: File Permissions Security

```
$ ls -la ~/.config/inc_trade/
-rw------- 1 user user 234 Jul  6 10:30 .dhan_token.json
-rw------- 1 user user 150 Jul  6 10:30 dhan-totp-cooldown.json

$ cat ~/.config/inc_trade/.dhan_token.json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "",
  "expires_at": "2026-07-07T10:30:00+00:00",
  "source": "totp",
  "token_type": "bearer",
  "broker_id": "D123456"
}
```

---

*Plan complete. Ready for multi-agent implementation.*
