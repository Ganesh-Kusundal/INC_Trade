# Phase 0 Runtime Sequence — Dhan Broker Foundation

## Primary Path: `BrokerFactory.create(...)`

This is the dominant entry point for obtaining a Dhan gateway. The sequence below was traced from `archive/brokers/dhan/factory.py` and its direct dependencies.

```
BrokerFactory.create(
    env_path=None,
    load_instruments=True,
    event_bus=None,
    risk_manager=None,
    lifecycle=None,
    backfill_callback=None,
    reconciliation_service=None,
)
```

### Step 1 — Resolve connection settings

1. `DhanSettingsLoader.from_env(env_path=env_path)` is called.
2. `_load_default_env(env_path)` loads `.env.local` if it exists, otherwise `.env`, into `os.environ` via `brokers.common.env_loader.load_env_file()`.
3. `SecretsManager()` is instantiated to support file-based secrets.
4. `DHAN_ENVIRONMENT` is read (default `LIVE`); validated against `("LIVE", "SANDBOX")`.
5. If sandbox: `DHAN_SANDBOX_CLIENT_ID` and `DHAN_SANDBOX_ACCESS_TOKEN` are read.
   If live: `DHAN_CLIENT_ID` (required) and `DHAN_ACCESS_TOKEN` are read.
6. `DHAN_PIN` / `DHAN_TOTP_SECRET` are read (env or file fallback).
7. Base URL is resolved: sandbox → `Dhan.sandbox()`, live → `Dhan.REST_BASE` or `DHAN_BASE_URL`.
8. Resilience config is loaded if any `DHAN_RESILIENCE_*` env var is present.
9. A frozen `DhanConnectionSettings` is returned.

**Evidence:** `archive/brokers/dhan/settings.py`, lines 125–209.

### Step 2 — Account connection registry lookup

1. `AccountConnectionRegistry.get_or_create(BrokerId.DHAN, client_id, factory_fn)` is invoked.
2. Registry key is `(broker_id.lower(), client_id)`.
3. If a gateway already exists for the key, it is returned immediately and no further construction occurs.
4. Otherwise, `_build_gateway(...)` is called inside the factory lambda.

**Evidence:** `archive/brokers/dhan/factory.py`, lines 43–61; `archive/brokers/dhan/account_registry.py`, lines 19–42.

### Step 3 — Build gateway (`_build_gateway`)

#### 3a. Authentication and token acquisition (`_create_auth`)

1. `token_state_dir` is created if missing (`mkdir(parents=True, exist_ok=True)`).
2. `JsonTokenStateStore(token_state_dir / "dhan-token-state.json")` is created.
3. `AuthManager` is created with:
   - `client_id`
   - `token_store`
   - `token_source=TokenSource.TOTP`
   - `on_acquire=_generate_totp_token`
   - `on_refresh=_generate_totp_token`
   - `token_lifetime_seconds=settings.token_lifetime_seconds`
4. If `settings.access_token` is provided, it is used directly.
5. Otherwise:
   - `auth.acquire()` loads persisted `TokenState` from the JSON store.
   - If the persisted state is invalid/missing, `_generate_totp_token(settings)` is called.
   - If TOTP generation succeeds, a new `TokenState` is constructed with `issued_at=now` and `expires_at=next 00:30 UTC`.
   - If TOTP generation fails (no pin/secret or network failure), `state = None`.
6. If no valid token is obtained, `ConfigurationError` is raised with message:
   `"DHAN_ACCESS_TOKEN not configured and TOTP refresh failed"`.
7. If a new token was generated and `env_file.exists()`, `_update_env_token(env_file, token)` is called.

**Evidence:** `archive/brokers/dhan/factory.py`, lines 130–183.

#### 3b. HTTP client construction (`_create_http_client`)

1. `DhanResilienceConfig` is resolved:
   - `settings.resilience_config` if not None.
   - Else `DhanConfigLoader.load_from_environment()`.
   - If that equals `DEFAULT_CONFIG`, use `DEFAULT_CONFIG`.
2. Circuit breakers are created:
   - If custom thresholds are present, four breakers are built manually: `orders`, `market_data`, `portfolio`, `admin`.
   - Else `create_circuit_breakers()` is called from `brokers.dhan.resilience`.
3. `create_rate_limiter()` is called (currently ignores config values; hardcoded defaults).
4. `DhanHttpClient` is instantiated with:
   - `client_id`, `access_token`, `base_url`, `timeout`, `enable_retry`
   - `token_refresh_fn=lambda: _refresh_via_auth(auth, env_file, refresh_lock)`
   - `config=resilience_config`
   - Legacy circuit breaker names: `read_circuit_breaker`, `write_circuit_breaker`, `admin_circuit_breaker`
   - `_rate_limiter`, `_circuit_breakers`

**Evidence:** `archive/brokers/dhan/factory.py`, lines 185–294.

#### 3c. Connection and gateway construction (`_create_connection_and_gateway`)

1. `DhanConnection` is instantiated with the HTTP client, event bus, risk manager, callbacks, lifecycle, `allow_live_orders`, and `auth`.
2. Dhan status mappings are registered via `brokers.dhan.status_mapper.register_mappings()`.
3. `BrokerGateway(connection)` is returned.

**Evidence:** `archive/brokers/dhan/factory.py`, lines 296–322.

### Step 4 — Load instruments

1. If `load_instruments=True`, `gateway.load_instruments()` is called.
2. This triggers instrument master download/cache behavior (Phase 2, out of Phase 0 scope).

**Evidence:** `archive/brokers/dhan/factory.py`, lines 104–105.

### Step 5 — Wire WebSocket services

1. If `lifecycle` is None or `event_bus` is None, this step is skipped.
2. `access_token_fn` is defined to return `client.access_token`.
3. `gateway._conn.create_market_feed(access_token=token, instruments=[], access_token_fn=access_token_fn)`.
4. `gateway._conn.create_order_stream(access_token=token, access_token_fn=access_token_fn)`.

**Evidence:** `archive/brokers/dhan/factory.py`, lines 324–357.

### Step 6 — Token refresh scheduler

1. `_on_token_refresh(new_token)` callback is defined to:
   - Update the HTTP client token.
   - Update `.env.local` if it exists.
   - Broadcast the token via `gateway._conn.broadcast_token(new_token)`.
2. `TokenRefreshScheduler` is created with:
   - `auth`, `interval_seconds`, `buffer_seconds`, `refresh_lock`, `on_refresh`
3. If `lifecycle` is provided: `lifecycle.register(scheduler)` and `gateway._conn.token_scheduler = scheduler`.
4. Else: `scheduler.start()`, `gateway._conn.token_scheduler = scheduler`, `atexit.register(scheduler.stop)`, and a warning is logged.

**Evidence:** `archive/brokers/dhan/factory.py`, lines 359–403.

### Step 7 — Health check registration

1. `register_broker_health_check(BrokerId.DHAN, gateway)` is called.
2. A `BrokerConnectivityHealthCheck` is registered under `broker.dhan` in the global `health_registry`.

**Evidence:** `archive/brokers/dhan/factory.py`, lines 121–124; `archive/brokers/common/observability/health_check.py`, lines 124–144.

### Step 8 — Return gateway

1. The constructed `BrokerGateway` is returned to the caller.
2. If this was the first construction, the registry stores it under `("dhan", client_id)`.

## Alternative Bootstrap Path 1: `bootstrap_environment()`

Used by CLI and process entry points to load canonical env files before any factory is invoked.

```
bootstrap_environment(project_root=None, brokers=("dhan", "upstox"))
```

1. For each broker in `brokers`:
   - Skip if broker is `"paper"`.
   - Look up canonical env file path from `CANONICAL_ENV_FILES`.
   - If file exists and is non-empty, call `CredentialResolver.load_broker_env(broker, path)`.
   - Record loaded path (or `None`) in result dict.
2. `CredentialResolver.load_broker_env()` calls `load_env_file(path)`, which parses `key=value` lines and writes them into `os.environ`.

**Evidence:** `archive/brokers/common/auth/environment_bootstrap.py`; `archive/brokers/common/auth/credential_resolver.py`; `archive/brokers/common/env_loader.py`.

## Alternative Bootstrap Path 2: `bootstrap_from_gateways()`

Used when legacy gateway instances already exist and must be wrapped into common infrastructure.

```
await bootstrap_from_gateways(
    gateways=[("dhan", dhan_gw), ("upstox", upstox_gw)],
    policy=None,
)
```

1. `policy_from_env()` selects routing policy from `TRADEX_BROKER_POLICY` and `TRADEX_EXECUTION_BROKER`.
2. For each `(broker_id, legacy_gw)`:
   - `build_extension_bundle(broker_id, legacy_gw)` constructs broker-specific extension registry.
   - `wrap_market_gateway(legacy_gw, broker_id, extensions=...)` creates a common adapter.
3. `build_infrastructure(common_gateways, policy, bundles=...)` builds `BrokerInfrastructure`.

**Evidence:** `archive/brokers/common/bootstrap.py`, lines 21–56.

## Alternative Bootstrap Path 3: `create_intelligent_gateway()`

High-level helper that combines infrastructure wrapping with intelligent routing.

```
await create_intelligent_gateway(
    gateways=[("dhan", dhan_gw)],
    smart=True,
    policy=None,
    primary_broker=None,
)
```

1. Raises `ValueError` if `gateways` is empty.
2. Resolves `primary_broker` to first broker id if not provided.
3. Calls `bootstrap_from_gateways(gateways, policy=policy)`.
4. Returns `IntelligentMarketDataGateway(infra, smart=smart, primary_broker=primary_broker)`.

**Evidence:** `archive/brokers/common/bootstrap.py`, lines 78–129.

## Configuration Loading Precedence Summary

Within a single process, the effective configuration is the result of multiple layered loads:

1. **Code defaults** (lowest priority)
2. **`.env` file** loaded by `pydantic_settings` if configured
3. **`.env.local` or `.env`** loaded explicitly by `SettingsLoaderBase._load_default_env()`
4. **`bootstrap_environment()` / `CredentialResolver.load_broker_env()`** overwriting env vars
5. **Actual environment variables** (highest priority for most loaders)

**Note:** Because several loaders overwrite `os.environ` from files, the final effective value depends on the order in which bootstrap functions are called. This is a global side effect that greenfield design should make explicit.

## Observations for Greenfield Design

- The factory is both a constructor and a lifecycle manager. It writes env files, starts schedulers, and registers health checks. A cleaner greenfield design should separate these concerns.
- `AccountConnectionRegistry` ensures duplicate gateway construction is impossible, but it also makes the factory non-idempotent in behavior: the second call returns the same instance and ignores new parameters.
- The scheduler is started either by a lifecycle manager or by `atexit`; the fallback path is a hidden side effect.
