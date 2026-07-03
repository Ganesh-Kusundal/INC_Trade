# Phase 0 Public Contract — Dhan Broker Foundation

This document specifies the observable inputs, outputs, errors, timing, and side effects for every public API in the Phase 0 scope. Behavior changes in the greenfield implementation are prohibited unless explicitly approved.

## 1. Central Application Config

### `AppConfig.from_env() -> AppConfig`

**Inputs:** Reads from `os.environ`.

**Precedence:**

1. `TRADEX_*` prefixed variables
2. Legacy variables (`APP_ENV`, `XV2_LOG_LEVEL`, `TRADEXV2_DEBUG`, `REDIS_URL`, `API_HOST`, `API_PORT`)
3. Constructor defaults

**Outputs:** `AppConfig` instance with validated fields.

**Errors:**

- `ValidationError` if `log_level` is not one of `{DEBUG, INFO, WARNING, ERROR, CRITICAL}`.
- `ValidationError` if `api_port` or `observability_port` <= 0.

**Side effects:** None.

**Timing:** Synchronous; reads env vars only.

**Evidence:** `archive/config/schema.py:64-124`.

### `get_config() -> AppConfig`

**Inputs:** None.

**Outputs:** Cached `AppConfig`; first call triggers `AppConfig.from_env()`.

**Side effects:** Caches instance globally.

**Timing:** Synchronous.

**Evidence:** `archive/config/defaults.py:31-36`.

### `reset_config() -> None`

**Inputs:** None.

**Outputs:** None.

**Side effects:** Clears global `_cached` config.

**Timing:** Synchronous.

**Evidence:** `archive/config/defaults.py:39-42`.

## 2. Dhan Connection Settings

### `DhanSettingsLoader.from_env(env_path=None, prefix="DHAN") -> DhanConnectionSettings`

**Inputs:**

- `env_path`: optional `Path` to a `.env` file to load first.
- `prefix`: env var prefix; default `"DHAN"`.

**Env vars read:**

- `DHAN_ENVIRONMENT` (default `LIVE`)
- `DHAN_CLIENT_ID` (required in live; `DHAN_SANDBOX_CLIENT_ID` in sandbox)
- `DHAN_ACCESS_TOKEN` (or `DHAN_SANDBOX_ACCESS_TOKEN`)
- `DHAN_BASE_URL` / `DHAN_SANDBOX_REST_BASE_URL`
- `DHAN_HTTP_TIMEOUT` (default 15.0)
- `DHAN_ENABLE_RETRY` (default True)
- `DHAN_POOL_CONNECTIONS` (default 50)
- `DHAN_POOL_MAXSIZE` (default 100)
- `DHAN_PIN` / `DHAN_PIN_FILE`
- `DHAN_TOTP_SECRET` / `DHAN_TOTP_SECRET_FILE`
- `DHAN_TOKEN_LIFETIME_SECONDS` (default from `domain.constants.auth`)
- `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS`
- `DHAN_TOKEN_REFRESH_BUFFER_SECONDS`
- `DHAN_ALLOW_LIVE_ORDERS` (default False)
- `DHAN_TOKEN_STATE_DIR`
- `DHAN_RESILIENCE_*` (optional)

**Outputs:** Frozen `DhanConnectionSettings` dataclass.

**Errors:**

- `ValueError` if `DHAN_CLIENT_ID` is missing in live mode.
- `ValueError` if `DHAN_ENVIRONMENT` is not `LIVE` or `SANDBOX`.

**Side effects:**

- Loads `.env.local` or `.env` into `os.environ` if `env_path` not provided.
- Reads secret files if configured.

**Timing:** Synchronous.

**Evidence:** `archive/brokers/dhan/settings.py:125-209`.

## 3. Dhan Resilience Config

### `DhanConfigLoader.load(env_path=None, env_prefix="DHAN_RESILIENCE_") -> DhanResilienceConfig`

**Inputs:**

- `env_path`: optional `.env` file path.
- `env_prefix`: prefix for resilience env vars.

**Outputs:** `DhanResilienceConfig` with merged defaults, file values, and env var overrides.

**Env vars read (whitelist):**

- `DHAN_RESILIENCE_RATE_LIMIT_LIMITS`
- `DHAN_RESILIENCE_RATE_LIMIT_READ_PREFIXES`
- `DHAN_RESILIENCE_RATE_LIMIT_WRITE_PREFIXES`
- `DHAN_RESILIENCE_RATE_LIMIT_BUCKET_MAP`
- `DHAN_RESILIENCE_RETRY_MAX_RETRIES`
- `DHAN_RESILIENCE_RETRY_BASE_DELAY_MS`
- `DHAN_RESILIENCE_RETRY_MAX_DELAY_MS`
- `DHAN_RESILIENCE_CB_READ_PREFIXES`
- `DHAN_RESILIENCE_CB_WRITE_PREFIXES`
- `DHAN_RESILIENCE_CB_ORDERS_FAILURE_THRESHOLD`
- `DHAN_RESILIENCE_CB_DEFAULT_FAILURE_THRESHOLD`
- `DHAN_RESILIENCE_CB_RECOVERY_TIMEOUT_MS`
- `DHAN_RESILIENCE_CB_SUCCESS_THRESHOLD`
- `DHAN_RESILIENCE_TOKEN_REFRESH_COOLDOWN_SECONDS`
- `DHAN_RESILIENCE_TOKEN_RATE_LIMIT_BACKOFF_SECONDS`
- `DHAN_RESILIENCE_BASE_URL`

**Unknown `DHAN_RESILIENCE_*` vars:** Silently ignored.

**Errors:**

- `FileNotFoundError` if `load_from_file()` called with missing path.
- `json.JSONDecodeError` if JSON file is malformed.

**Side effects:** Loads `.env.local` or `.env` if `env_path` not provided.

**Timing:** Synchronous.

**Evidence:** `archive/brokers/dhan/config_loader.py:184-408`.

## 4. Broker Factory

### `BrokerFactory.create(...)`

**Signature:**

```python
def create(
    self,
    *,
    env_path: Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    risk_manager: Any | None = None,
    lifecycle: Any | None = None,
    backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
    reconciliation_service: object | None = None,
) -> MarketDataGateway
```

**Inputs:** Optional env path and wiring dependencies.

**Outputs:** A `BrokerGateway` instance (returned as `MarketDataGateway`).

**Side effects:**

- Creates `runtime/` directory for token state if needed.
- Writes `DHAN_ACCESS_TOKEN` to `.env.local` if a new token is generated.
- Starts a `TokenRefreshScheduler` (either via lifecycle or `atexit`).
- Registers a health check under `broker.dhan` in the global registry.
- Loads instruments if `load_instruments=True`.

**Errors:**

- `ValueError` from settings loader for missing client id or invalid environment.
- `ConfigurationError` if no access token can be obtained.

**Timing:** Synchronous; may block on TOTP HTTP request and token state I/O.

**Duplicate call behavior:** If a gateway already exists for the same `client_id`, the existing instance is returned and all parameters are ignored.

**Evidence:** `archive/brokers/dhan/factory.py:32-126`.

## 5. Account Connection Registry

### `AccountConnectionRegistry.get_or_create(broker_id, account_id, factory_fn) -> Any`

**Inputs:**

- `broker_id`: canonical broker identifier (lowercased for key).
- `account_id`: account identifier.
- `factory_fn`: callable returning the gateway.

**Outputs:** Existing gateway if present; otherwise result of `factory_fn()`.

**Side effects:** Stores new gateway in class-level `_gateways` dict.

**Errors:** None (propagates factory exceptions).

**Timing:** Synchronous; holds class-level `threading.Lock` during lookup/insert.

**Evidence:** `archive/brokers/dhan/account_registry.py:19-42`.

## 6. Secrets Manager

### `SecretsManager.get_env_or_file(key, file_key, default="") -> str`

**Inputs:**

- `key`: env var name.
- `file_key`: env var holding a file path.
- `default`: fallback string.

**Outputs:** Secret value from env var, file, or default.

**Precedence:**

1. `os.environ[key]` if non-empty.
2. Path from `os.environ[file_key]` if file exists.
3. `default`.

**Side effects:** Reads file from disk.

**Timing:** Synchronous.

**Evidence:** `archive/config/secrets_manager.py:32-43`.

## 7. Feature Flags

### `FeatureFlags.is_enabled(flag_name: str) -> bool`

**Inputs:** Flag name string.

**Outputs:** `True` if flag is enabled, otherwise `False`.

**Unknown flags:** Returns `False`.

**Side effects:** Lazy initialization on first call.

**Timing:** Synchronous; thread-safe initialization.

**Evidence:** `archive/config/feature_flags.py:186-197`.

### `FeatureFlags.is_enabled_for_user(flag_name: str, user_id: str) -> bool`

**Inputs:** Flag name and user identifier.

**Outputs:** `True` if flag is globally enabled and the deterministic hash bucket is below the rollout percentage.

**Unknown flags:** Returns `False`.

**Side effects:** Increments evaluation metric counter if metrics available.

**Timing:** Synchronous.

**Evidence:** `archive/config/feature_flags.py:199-242`.

### `FeatureFlags.set_flag(flag_name: str, value: bool) -> None`

**Inputs:** Known flag name and boolean value.

**Outputs:** None.

**Side effects:** Updates flag state and class attribute; increments change metric counter.

**Errors:** `ValueError` for unknown flag.

**Timing:** Synchronous.

**Evidence:** `archive/config/feature_flags.py:298-333`.

### `FeatureFlags.set_rollout_percentage(flag_name: str, percentage: int) -> None`

**Inputs:** Known flag name and integer 0–100.

**Outputs:** None.

**Side effects:** Updates rollout percentage; increments change metric counter.

**Errors:**

- `ValueError` for unknown flag.
- `ValueError` if percentage not in `[0, 100]`.

**Timing:** Synchronous.

**Evidence:** `archive/config/feature_flags.py:264-296`.

### `FeatureFlags.reset() -> None`

**Inputs:** None.

**Outputs:** None.

**Side effects:** Clears all state and reloads from env.

**Timing:** Synchronous.

**Evidence:** `archive/config/feature_flags.py:376-394`.

## 8. Logging

### `configure_logging(service="tradexv2", level=None, log_format=None, log_file=None, enable_redaction=True) -> None`

**Inputs:**

- `service`: service name in logs.
- `level`: log level; defaults to `XV2_LOG_LEVEL` or `INFO`.
- `log_format`: `"json"` or `"human"`; defaults based on `APP_ENV`.
- `log_file`: optional rotating file path.
- `enable_redaction`: whether to install token redaction filter.

**Outputs:** None.

**Side effects:** Calls `logging.config.dictConfig()` with filters, formatters, and handlers.

**Format selection:**

- `json` if `APP_ENV` is `prod` or `production`.
- `human` otherwise.

**Timing:** Synchronous.

**Evidence:** `archive/infrastructure/logging_config.py:186-266`.

## 9. Environment Bootstrap

### `bootstrap_environment(project_root=None, brokers=("dhan", "upstox")) -> dict[str, Path | None]`

**Inputs:**

- `project_root`: root for resolving env file paths; defaults to `Path.cwd()`.
- `brokers`: tuple of broker names to load.

**Outputs:** Mapping of broker name to loaded path or `None`.

**Side effects:** Loads canonical env files into `os.environ`, overwriting existing values.

**Behavior per broker:**

- `dhan` → `.env.local`
- `upstox` → `.env.upstox` (or `.env.local` fallback, resolved by `CredentialResolver`)
- `paper` → skipped

**Timing:** Synchronous.

**Evidence:** `archive/brokers/common/auth/environment_bootstrap.py:13-41`.

## 10. Health Check Registration

### `register_broker_health_check(broker_id: str, gateway: Any) -> None`

**Inputs:**

- `broker_id`: canonical broker identifier.
- `gateway`: gateway instance supporting `describe()` and optionally `get_connection_status()`.

**Outputs:** None.

**Side effects:** Registers or replaces a `BrokerConnectivityHealthCheck` under `broker.{broker_id}` in `health_registry`.

**Timing:** Synchronous.

**Evidence:** `archive/brokers/common/observability/health_check.py:124-144`.

## 11. Config Validator

### `ConfigValidator.validate() -> ValidationResult`

**Inputs:** Profile and env dict; defaults read from `APP_ENV` and `os.environ`.

**Outputs:** `ValidationResult` with `valid`, `errors`, `warnings`, `validated_vars`.

**Behavior by profile:**

- **dev:** Only `DHAN_CLIENT_ID` is required as a warning; empty tokens allowed; mocks allowed.
- **staging/prod:** Both `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` required; no mocks; no empty tokens.

**Production-specific checks:**

- `DHAN_ALLOW_LIVE_ORDERS` must be one of `0`, `1`, `true`, `false`, `yes`, `no`.
- Warns if `AUTH_MODE=none`.
- Warns if `SECRET_ENCRYPTION_KEY` missing.

**Value constraints:**

- `API_PORT` must be 1–65535.
- `XV2_LOG_LEVEL` must be valid.
- `CACHE_TTL` must be non-negative integer.

**Side effects:** None.

**Timing:** Synchronous.

**Evidence:** `archive/config/validator.py:173-394`.

## Contract Summary Table

| API | Inputs | Outputs | Errors | Side Effects |
|-----|--------|---------|--------|--------------|
| `AppConfig.from_env()` | `os.environ` | `AppConfig` | `ValidationError` | None |
| `get_config()` | None | `AppConfig` | None | Caches config |
| `reset_config()` | None | None | None | Clears cache |
| `DhanSettingsLoader.from_env()` | env path, prefix | `DhanConnectionSettings` | `ValueError` | Loads env file |
| `DhanConfigLoader.load()` | env path, prefix | `DhanResilienceConfig` | `FileNotFoundError`, `JSONDecodeError` | Loads env file |
| `BrokerFactory.create()` | wiring kwargs | `BrokerGateway` | `ValueError`, `ConfigurationError` | Writes env, starts scheduler, registers health check |
| `AccountConnectionRegistry.get_or_create()` | broker_id, account_id, factory | gateway | None (propagates) | Stores gateway |
| `SecretsManager.get_env_or_file()` | key, file_key | secret string | None | Reads file |
| `FeatureFlags.is_enabled()` | flag name | bool | None | Lazy init |
| `FeatureFlags.is_enabled_for_user()` | flag name, user_id | bool | None | Metrics increment |
| `FeatureFlags.set_flag()` | flag name, bool | None | `ValueError` | Updates state |
| `FeatureFlags.set_rollout_percentage()` | flag name, int | None | `ValueError` | Updates rollout |
| `FeatureFlags.reset()` | None | None | None | Reloads from env |
| `configure_logging()` | service, level, format, file, redaction | None | None | Configures root logger |
| `bootstrap_environment()` | project_root, brokers | dict | None | Overwrites `os.environ` |
| `register_broker_health_check()` | broker_id, gateway | None | None | Registers health check |
| `ConfigValidator.validate()` | profile, env | `ValidationResult` | None | None |
