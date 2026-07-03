# Phase 0 Source Audit — Dhan Broker Foundation

## Scope

This audit covers the archived Dhan broker's foundation layer: configuration, dependency injection, startup/bootstrap, logging, environment handling, secrets, and feature flags. Every file listed below was read in full during discovery.

## Executive Summary

The archived codebase contains **four overlapping configuration systems** plus a separate feature-flag system. The greenfield `brokers/config_app.py` and `brokers/core/di.py` are minimal stubs that preserve almost none of the archived behavior. A faithful greenfield replication must merge or re-implement these systems while keeping the exact environment-variable names and precedence rules, because production deployments and tests depend on them.

## Configuration Systems Inventory

### 1. Central Application Config — `archive/config/schema.py` + `archive/config/defaults.py`

**Responsibility:** Platform-wide app settings (API host/port, log level, Redis, CORS, rate limiting).

**Public API:**

- `AppConfig` (Pydantic v2 BaseModel)
- `get_config()` / `reset_config()` cached singleton helpers
- `load_dhan_config()`, `load_upstox_config()`, `load_api_config()`, `load_trading_config()`

**Key behavior:**

- `AppConfig.from_env()` reads `TRADEX_*` env vars and falls back to legacy names (`APP_ENV`, `XV2_LOG_LEVEL`, `TRADEXV2_DEBUG`, `REDIS_URL`, `API_HOST`, `API_PORT`).
- `TRADEX_*` always wins over legacy names.
- `app_env` is restricted to `Literal["dev", "staging", "prod"]`.
- `log_level` is validated against `{DEBUG, INFO, WARNING, ERROR, CRITICAL}` and normalized to uppercase.
- `api_port` and `observability_port` must be > 0.
- `cors_origins` parses comma-separated env string into a list.
- `rate_limit_max_requests` defaults to `0` (disabled).

**Contradiction / inconsistency:**

- `archive/config/schema.py` default `api_port` is `8080`, but `archive/config/tests/test_config.py` asserts `8000`. The test uses a version of the file that may have drifted; the actual source shows `8080`. This is an unresolved inconsistency in the archived test suite.

### 2. Dhan Connection Settings — `archive/brokers/dhan/settings.py`

**Responsibility:** Broker-specific connection parameters and secrets loading.

**Public API:**

- `DhanConnectionSettings(BrokerSettings)` frozen dataclass
- `DhanSettingsLoader(SettingsLoaderBase)`

**Key behavior:**

- Env prefix: `DHAN_`.
- `DhanSettingsLoader.from_env(env_path=None, prefix="DHAN")` loads `.env.local` or `.env` first, then reads env vars.
- Supports `LIVE` and `SANDBOX` environments; in sandbox mode it reads `DHAN_SANDBOX_CLIENT_ID` and `DHAN_SANDBOX_ACCESS_TOKEN`.
- `DHAN_CLIENT_ID` is mandatory; missing value raises `ValueError`.
- `DHAN_ENVIRONMENT` must be `LIVE` or `SANDBOX`; otherwise raises `ValueError`.
- Secrets (`DHAN_PIN`, `DHAN_TOTP_SECRET`) can come from env vars or files (`DHAN_PIN_FILE`, `DHAN_TOTP_SECRET_FILE`) via `SecretsManager`.
- Base URL defaults to `https://api.dhan.co/v2` in live, `https://sandbox.dhan.co/v2` in sandbox.
- Token state directory defaults to `runtime/` under project root.
- Resilience config is optional; if any `DHAN_RESILIENCE_*` env var is set, it is loaded via `DhanConfigLoader`.

**Derived properties:**

- `resolved_token_state_dir`
- `is_sandbox` / `is_live`
- `has_access_token`
- `has_totp`
- `generate_token_url`

### 3. Dhan Resilience Config — `archive/brokers/dhan/config.py` + `archive/brokers/dhan/config_loader.py`

**Responsibility:** Rate limits, retry policy, circuit breaker thresholds, token refresh timing.

**Public API:**

- `DhanResilienceConfig` (frozen dataclass aggregating rate/retry/CB/token configs)
- `DhanRateLimitConfig`, `DhanRetryConfig`, `DhanCircuitBreakerConfig`, `DhanTokenConfig`
- `DhanConfigLoader` static helpers

**Key behavior:**

- Env prefix: `DHAN_RESILIENCE_`.
- `DhanConfigLoader.load()` precedence: defaults → `.env` file → env vars.
- Whitelist-based mapping in `ENV_KEY_MAPPING`; unknown `DHAN_RESILIENCE_*` vars are silently ignored.
- Defaults are hardcoded in `config.py`:
  - Rate limits: quote 1 s, ltp/ohlc/charts 0.15 s, optionchain 0.35 s, orders 0.04 s.
  - Retry: 3 attempts, 500 ms base, 5000 ms cap, exponential `2^(attempt-1)`.
  - Circuit breaker: orders threshold 3, default 5, recovery 30 s, success threshold 3.
  - Token refresh cooldown 60 s, rate-limit backoff 130 s.
- `DhanResilienceConfig.from_dict()` and `.to_dict()` support round-trip serialization.
- All dataclasses are frozen.

**Dead code / unused branches:**

- `_parse_env_value()` in `config_loader.py` is defined but never called; parsing is done inline in `_build_nested_dict()`.

### 4. Environment Profiles — `archive/config/profiles/*.py`

**Responsibility:** Environment-specific behavioral policy (log level, strictness, mock brokers, encryption, rate limiting, CORS).

**Public API:**

- `EnvironmentProfile` (abstract base)
- `BaseProfile`, `DevProfile`, `StagingProfile`, `ProdProfile`
- `load_profile(name=None)`

**Key behavior:**

- `load_profile()` reads `APP_ENV`, defaults to `dev`, raises `ValueError` for unknown profiles.
- Profiles are mutable dataclasses with private fields exposed as read-only properties.
- `to_dict()` returns a flat dictionary of all policy values.
- Dev: DEBUG, mocks allowed, relaxed validation, no encryption.
- Staging: INFO, no mocks, strict validation, encryption + auth required, 120 req/min rate limit.
- Prod: WARNING, no mocks, strict validation, encryption + auth required, 60 req/min rate limit.

**Observation:**

- Profiles are defined but are **not wired into** `AppConfig` or `DhanSettingsLoader`. They appear to be consulted separately by higher-level code. This is a seam that must be preserved in greenfield or explicitly deprecated.

### 5. Feature Flags — `archive/config/feature_flags.py`

**Responsibility:** Runtime toggles for experimental behavior with deterministic user rollouts.

**Public API:**

- `FeatureFlags` class
- `FlagDefinition` frozen dataclass
- Module-level `is_enabled`, `is_enabled_for_user`, `set_flag`, `set_rollout_percentage`, `get_rollout_percentage`, `get_flag_info`, `get_all_flags`

**Key behavior:**

- Env var format: `FEATURE_<FLAG_NAME>`.
- Boolean parsing: `1`, `true`, `yes`, `on` → True; anything else → False.
- Flags default to False (opt-in).
- Lazy initialization on first access, guarded by double-checked locking (`_init_lock`).
- `is_enabled_for_user()` uses SHA-256 of `flag_name:user_id`, first 8 hex chars, modulo 100.
- Rollout percentage 0–100; 100 means always enabled, 0 means always disabled.
- `set_flag()` and `set_rollout_percentage()` raise `ValueError` for unknown flags.
- `is_enabled()` returns `False` for unknown flags.
- Metrics counters are lazily resolved from `infrastructure.metrics.metrics_registry`; fallback to no-op.

**Known flags:**

- `SMART_ROUTING`
- `INTELLIGENT_GATEWAY`
- `ADVANCED_ORDER_TYPES`
- `EXPERIMENTAL_STRATEGIES`
- `COMPOSER_EXECUTION`

**Thread-safety note:**

- Class attributes (`FeatureFlags.SMART_ROUTING`, etc.) are mutated at runtime by `set_flag()`. This is global mutable state shared across tests.

## Secrets Management

### `archive/config/secrets_manager.py`

**Responsibility:** Unified env-var → file fallback for credentials.

**Public API:**

- `SecretsManager(project_root=None)`
- `get_env(key, default)`
- `get_file(relative_path, strip=True)`
- `get_env_or_file(key, file_key, default)`
- Broker-specific helpers: `get_dhan_pin()`, `get_dhan_totp_secret()`, `get_upstox_pin()`, `get_upstox_totp_secret()`

**Key behavior:**

- Reads env var first; if empty, reads path from `*_FILE` env var relative to project root.
- `require(key)` raises `ValueError` if missing.

### `archive/brokers/dhan/secret_utils.py`

**Responsibility:** Dhan-specific thin wrapper around env/file lookup.

**Public API:**

- `read_secret(env_key: str, file_key: str) -> str | None`

**Key behavior:**

- Identical to `SecretsManager.get_env_or_file()` but does not require a project root.
- Returns `None` when both env var and file are absent.

## Factory and Bootstrap

### `archive/brokers/dhan/factory.py`

**Responsibility:** Construct a fully wired `BrokerGateway` for Dhan.

**Public API:**

- `BrokerFactory.create(...)`

**Key behavior:**

- Uses `AccountConnectionRegistry` to ensure one gateway per `(broker_id, client_id)`.
- Loads `DhanConnectionSettings` from env via `DhanSettingsLoader.from_env()`.
- Builds `AuthManager` + `JsonTokenStateStore`.
- Resolves access token: env var → token store → TOTP generation.
- Generates TOTP token via Dhan's `https://auth.dhan.co/app/generateAccessToken` endpoint if needed.
- Persists new token back to `.env.local` atomically using `fcntl.flock`.
- Creates `DhanHttpClient` with circuit breakers and rate limiter.
- Creates `DhanConnection` + `BrokerGateway`, registers Dhan status mappings.
- Optionally loads instruments.
- Wires WebSocket market feed and order stream if `lifecycle` and `event_bus` are provided.
- Sets up `TokenRefreshScheduler`; registers with lifecycle or falls back to `atexit`.
- Registers broker health check with global `health_registry`.

**Side effects (must be preserved or made explicit):**

- Writes `DHAN_ACCESS_TOKEN` to `.env.local`.
- Starts a background token refresh scheduler.
- Registers a global health check.

### `archive/brokers/dhan/account_registry.py`

**Public API:**

- `AccountConnectionRegistry.get_or_create(broker_id, account_id, factory_fn)`
- `AccountConnectionRegistry.get(...)`
- `AccountConnectionRegistry.release(...)`
- `AccountConnectionRegistry.release_all()`
- `AccountConnectionRegistry.active_count()`

**Key behavior:**

- Thread-safe via class-level `threading.Lock`.
- Key is `(broker_id.lower(), account_id)`.
- No eviction policy; gateways live until `release()` is called.
- `release()` calls `gateway.close()` if present, swallowing exceptions.

### `archive/brokers/common/bootstrap.py`

**Responsibility:** Wrap legacy gateways into common infrastructure.

**Public API:**

- `policy_from_env()`
- `bootstrap_from_gateways(gateways, policy=None)`
- `bootstrap_from_broker_registry(broker_names, ...)`
- `create_intelligent_gateway(gateways, smart=True, ...)`

**Key behavior:**

- Reads `TRADEX_BROKER_POLICY` (`auto`, `dhan`, `upstox`) and `TRADEX_EXECUTION_BROKER`.
- Builds extension bundles and wraps gateways with `market_data_gateway_adapter`.
- Constructs `BrokerInfrastructure` and `IntelligentMarketDataGateway`.

### `archive/brokers/common/auth/environment_bootstrap.py`

**Public API:**

- `bootstrap_environment(project_root=None, brokers=("dhan", "upstox"))`

**Key behavior:**

- Loads canonical env files (`.env.local` for Dhan, `.env.upstox` for Upstox) into `os.environ`.
- Skips empty files and the `paper` broker.
- Idempotent in the sense that it can be called repeatedly; each call re-reads files.

### `archive/brokers/common/auth/credential_resolver.py`

**Public API:**

- `CredentialResolver.resolve_env_path(broker, env_path=None)`
- `CredentialResolver.load_broker_env(broker, env_path=None)`
- `CredentialResolver.env_file_exists(...)`

**Key behavior:**

- Canonical paths: `dhan` → `.env.local`, `upstox` → `.env.upstox` (with `.env.upstox` then `.env.local` fallback for Upstox).
- `load_broker_env()` delegates to `brokers.common.env_loader.load_env_file()`.

### `archive/brokers/common/env_loader.py`

**Public API:**

- `load_env_file(path: Path)`

**Key behavior:**

- Minimal parser; no `python-dotenv` dependency.
- Overwrites existing env vars so fresh tokens take effect.
- Strips surrounding quotes from values.

### `archive/brokers/common/settings.py`

**Public API:**

- `BrokerSettings` frozen dataclass
- `SettingsLoaderBase`

**Key behavior:**

- Common fields: `client_id`, `access_token`, `http_timeout=15.0`, `enable_retry=True`, `pool_connections=50`, `pool_maxsize=100`.
- Base loader reads `.env.local` → `.env`, provides `_get`, `_get_int`, `_get_float`, `_get_bool`.
- Bool parsing accepts `1`, `true`, `yes`, `y`, `on`.

## Logging

### `archive/infrastructure/logging_config.py`

**Responsibility:** Centralized structured logging with token redaction.

**Public API:**

- `configure_logging(service="tradexv2", level=None, log_format=None, log_file=None, enable_redaction=True)`
- `get_logger(name)`
- `set_production_mode(enabled)`
- `TokenRedactionFilter`, `CorrelationFilter`, `StructuredFormatter`, `HumanReadableFormatter`

**Key behavior:**

- Default level from `XV2_LOG_LEVEL` or `INFO`.
- Format defaults to `json` when `APP_ENV` is `prod`/`production`, otherwise `human`.
- Installs `TokenRedactionFilter` and `CorrelationFilter` on all handlers.
- Redacts access/refresh tokens, API keys, passwords, bearer tokens, query-string `token`, and any 32+ char alphanumeric string.
- Structured formatter outputs JSON with timestamp, service, level, logger, message, module/function/line, thread/process, correlation_id, service_name, exception, and extra fields.
- Human formatter uses ANSI colors.
- Adds quiet loggers for `urllib3`, `httpx`, `websockets`, `asyncio` at WARNING.

**Potential behavioral quirk:**

- The 32+ character catch-all regex may redact benign long strings (e.g., instrument symbols, UUIDs, hex hashes).
- `CorrelationFilter` imports `infrastructure.correlation` on every `filter()` call.

## Dependency Injection

### `archive/infrastructure/di.py`

**Responsibility:** String-keyed DI container with singleton/transient/request scopes.

**Public API:**

- `Container`
- `container` module singleton

**Key behavior:**

- Thread-safe via `RLock`.
- Detects circular dependencies.
- Supports `register(name, factory, scope)`, `register_instance(name, instance)`, `resolve(name)`, `reset()`, `has(name)`, `registrations()`.

### Greenfield `brokers/core/di.py`

**Current state:**

- Type-keyed `Container` with `register_singleton(interface, instance)`, `register_factory(interface, factory)`, `resolve(interface)`.
- Global `container` singleton.
- No scopes, no circular-dependency detection.

**Gap:** The greenfield container is a different abstraction (type-based vs. string-keyed, no scopes). Any greenfield port must decide whether to replicate the archived container or adapt the new one.

## Health Checks

### `archive/infrastructure/health.py`

**Public API:**

- `HealthStatus` enum
- `HealthResult` dataclass
- `HealthCheck` abstract base
- `HealthRegistry`
- `health_registry` singleton

**Key behavior:**

- `register(name, check)` is decorator-capable and thread-safe.
- `run_all()` runs all checks, catching exceptions and reporting `UNHEALTHY`.
- `summary()` computes overall status: healthy if all healthy, unhealthy if any unhealthy, degraded if any degraded.

### `archive/brokers/common/observability/health_check.py`

**Public API:**

- `BrokerConnectivityHealthCheck`
- `register_broker_health_check(broker_id, gateway)`

**Key behavior:**

- Checks REST reachability via `gateway.describe()`.
- Checks WebSocket streams via `gateway.get_connection_status()` if present.
- Registers under `broker.{broker_id}` in global `health_registry`.
- Idempotent: re-registering replaces the previous check.

## Endpoints and Constants

### `archive/config/endpoints.py`

**Dhan endpoints used in Phase 0:**

- `REST_BASE = "https://api.dhan.co/v2"`
- `SANDBOX_REST_BASE = "https://sandbox.dhan.co/v2"`
- `GENERATE_TOKEN_URL = "https://auth.dhan.co/app/generateAccessToken"`

### `archive/domain/constants/auth.py`

**Constants used by Dhan settings/factory:**

- `DHAN_TOKEN_LIFETIME_SECONDS = 86_400`
- `DHAN_TOKEN_REFRESH_BUFFER_SECONDS = 600`
- `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS = 1_200`
- `DHAN_REFRESH_COOLDOWN_SECONDS = 60`
- `TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS = 300`
- `TOKEN_CLOCK_SKEW_SECONDS = 30`

## Greenfield Baseline Assessment

### `brokers/config_app.py`

**Current behavior:**

- Uses `pydantic_settings.BaseSettings` with `env_nested_delimiter="__"`.
- Defines `DhanConfig` with: `client_id`, `pin`, `totp_secret`, `api_url`, `auth_url`, `instruments_compact_url`.
- Defines `UpstoxConfig` with OAuth/TOTP fields.
- `AppConfig.environment` defaults to `"production"`; `log_level` to `"INFO"`.
- Reads `.env` file only.

**Missing archived behavior:**

- No `TRADEX_*` app-level settings (host, port, CORS, Redis, observability port, rate limiting).
- No sandbox/live switching, no `DHAN_ACCESS_TOKEN`, no `DHAN_ENVIRONMENT`.
- No resilience config loading.
- No `DHAN_ALLOW_LIVE_ORDERS`, token lifetime, scheduler interval, or refresh buffer.
- Uses `__` nested delimiter, which differs from the archived flat `DHAN_*` pattern.

### `brokers/core/di.py`

**Current behavior:**

- Type-keyed container.
- Singleton + factory resolution only.

**Missing archived behavior:**

- No named/string-keyed registrations.
- No transient/request scopes.
- No circular-dependency detection.

## Open Questions from Audit

1. **Profile wiring:** `config/profiles` defines policies but they are not referenced by `AppConfig` or `DhanSettingsLoader`. Is the greenfield expected to preserve `load_profile()` as a standalone capability?
2. **API port inconsistency:** `archive/config/schema.py` says `8080`; archived test asserts `8000`. Which is authoritative?
3. **Greenfield env delimiter:** `brokers/config_app.py` uses `__` nested delimiter. Should the greenfield Dhan config continue to use flat `DHAN_*` env vars for backward compatibility?
4. **TOTP generation:** `pyotp` and `requests` are in `archive/requirements.txt`. Is TOTP token generation a required greenfield behavior, or should static access tokens be the only supported path?
