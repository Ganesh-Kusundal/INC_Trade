# Phase 0 State Machine — Dhan Broker Foundation

## 1. Application Configuration State

```
UNLOADED --get_config()--> LOADING --AppConfig.from_env()--> LOADED
                                      |
                                      └--validation error--> VALIDATION_FAILED
```

### States

| State | Description |
|-------|-------------|
| `UNLOADED` | No `AppConfig` instance cached. `_cached` is `None` in `archive/config/defaults.py`. |
| `LOADING` | Transient state while `AppConfig.from_env()` reads environment. |
| `LOADED` | Cached `AppConfig` available; subsequent `get_config()` calls return same instance. |
| `VALIDATION_FAILED` | Pydantic validation rejected a value; raised as `ValidationError`. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNLOADED` | `get_config()` called | `LOADING` | `archive/config/defaults.py:31-36` |
| `LOADING` | `AppConfig.from_env()` succeeds | `LOADED` | `archive/config/defaults.py:35` |
| `LOADING` | Pydantic validation fails | `VALIDATION_FAILED` | `archive/config/schema.py:47-62` |
| `LOADED` | `reset_config()` called | `UNLOADED` | `archive/config/defaults.py:39-42` |

## 2. Dhan Connection Settings State

```
UNLOADED --from_env()--> LOADING --frozen dataclass--> LOADED
                              |
                              └--missing client_id/invalid env--> ERROR
```

### States

| State | Description |
|-------|-------------|
| `UNLOADED` | No `DhanConnectionSettings` instance exists for this call. |
| `LOADING` | Env file and env vars being read and parsed. |
| `LOADED` | Frozen `DhanConnectionSettings` returned. |
| `ERROR` | `ValueError` raised for missing `DHAN_CLIENT_ID` or invalid `DHAN_ENVIRONMENT`. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNLOADED` | `DhanSettingsLoader.from_env()` called | `LOADING` | `archive/brokers/dhan/settings.py:125-145` |
| `LOADING` | Required fields present and valid | `LOADED` | `archive/brokers/dhan/settings.py:186-209` |
| `LOADING` | `DHAN_CLIENT_ID` missing | `ERROR` | `archive/brokers/dhan/settings.py:160-162` |
| `LOADING` | `DHAN_ENVIRONMENT` invalid | `ERROR` | `archive/brokers/dhan/settings.py:151-155` |

## 3. Dhan Resilience Config State

```
UNLOADED --load()--> LOADING --from_dict()--> LOADED
                         |
                         └--invalid JSON--> ERROR
```

### States

| State | Description |
|-------|-------------|
| `UNLOADED` | No resilience config loaded. |
| `LOADING` | Env vars or file being parsed. |
| `LOADED` | Frozen `DhanResilienceConfig` available. |
| `ERROR` | Invalid JSON file raises `json.JSONDecodeError`; missing file raises `FileNotFoundError`. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNLOADED` | `DhanConfigLoader.load()` called | `LOADING` | `archive/brokers/dhan/config_loader.py:322-361` |
| `LOADING` | Parsing succeeds | `LOADED` | `archive/brokers/dhan/config_loader.py:361` |
| `LOADING` | Invalid JSON file | `ERROR` | `archive/brokers/dhan/config_loader.py:225-250` |
| `LOADED` | `from_dict({})` or `from_dict(None)` | `LOADED` (defaults) | `archive/brokers/dhan/config.py:205-215` |

## 4. Gateway Factory State

```
UNREGISTERED --create()--> CHECKING_REGISTRY
                                |
                                ├--key exists--> RETURN_EXISTING
                                |
                                └--key absent--> BUILDING
                                                      |
                                                      ├--token ok--> REGISTERED
                                                      |
                                                      └--token fail--> ERROR
```

### States

| State | Description |
|-------|-------------|
| `UNREGISTERED` | No gateway exists for the `(broker_id, client_id)` pair. |
| `CHECKING_REGISTRY` | `AccountConnectionRegistry.get_or_create()` holds the class lock and checks for existing gateway. |
| `BUILDING` | `_build_gateway()` is executing. |
| `REGISTERED` | Gateway stored in registry and returned to caller. |
| `RETURN_EXISTING` | Existing gateway returned; no new construction. |
| `ERROR` | Token acquisition failed; `ConfigurationError` raised. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNREGISTERED` | `BrokerFactory.create()` called | `CHECKING_REGISTRY` | `archive/brokers/dhan/factory.py:48-61` |
| `CHECKING_REGISTRY` | Existing key found | `RETURN_EXISTING` | `archive/brokers/dhan/account_registry.py:29-35` |
| `CHECKING_REGISTRY` | No existing key | `BUILDING` | `archive/brokers/dhan/account_registry.py:36-42` |
| `BUILDING` | Token resolved successfully | `REGISTERED` | `archive/brokers/dhan/factory.py:75-126` |
| `BUILDING` | Token cannot be resolved | `ERROR` | `archive/brokers/dhan/factory.py:174-177` |
| `REGISTERED` | `AccountConnectionRegistry.release()` called | `UNREGISTERED` | `archive/brokers/dhan/account_registry.py:50-60` |

## 5. Feature Flags State

```
UNINITIALIZED --any access--> INITIALIZING --env vars parsed--> INITIALIZED
                                     |
                                     └--(always succeeds)--> INITIALIZED

INITIALIZED --set_flag()--> INITIALIZED
INITIALIZED --set_rollout_percentage()--> INITIALIZED
INITIALIZED --reset()--> INITIALIZING --> INITIALIZED
```

### States

| State | Description |
|-------|-------------|
| `UNINITIALIZED` | `_initialized` is `False`; `_flags` and `_rollout_percentages` are `None`. |
| `INITIALIZING` | Double-checked lock held; reading `FEATURE_*` env vars. |
| `INITIALIZED` | Flags loaded; runtime toggles and queries are active. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNINITIALIZED` | `is_enabled()`, `set_flag()`, etc. called | `INITIALIZING` | `archive/config/feature_flags.py:181-184` |
| `INITIALIZING` | Env vars parsed | `INITIALIZED` | `archive/config/feature_flags.py:147-173` |
| `INITIALIZED` | `set_flag(name, value)` | `INITIALIZED` | `archive/config/feature_flags.py:298-333` |
| `INITIALIZED` | `set_rollout_percentage(name, pct)` | `INITIALIZED` | `archive/config/feature_flags.py:264-296` |
| `INITIALIZED` | `reset()` | `INITIALIZING` → `INITIALIZED` | `archive/config/feature_flags.py:376-394` |

### Note on concurrent access

- Initialization is thread-safe via double-checked locking.
- Runtime mutations (`set_flag`, `set_rollout_percentage`) are not atomic with respect to concurrent reads; however, dict operations in CPython are thread-safe for individual key access.

## 6. Logging State

```
UNCONFIGURED --configure_logging()--> CONFIGURED
```

### States

| State | Description |
|-------|-------------|
| `UNCONFIGURED` | Default Python logging configuration active. |
| `CONFIGURED` | `logging.config.dictConfig()` installed with filters and formatters. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNCONFIGURED` | `configure_logging()` called | `CONFIGURED` | `archive/infrastructure/logging_config.py:186-266` |
| `CONFIGURED` | `configure_logging()` called again | `CONFIGURED` (overwrites) | `archive/infrastructure/logging_config.py:260` |

### Format selection sub-state

Within `CONFIGURED`, the formatter is chosen based on `APP_ENV`:

| `APP_ENV` | Formatter |
|-----------|-----------|
| `prod` or `production` | `StructuredFormatter` (JSON) |
| anything else | `HumanReadableFormatter` |

**Evidence:** `archive/infrastructure/logging_config.py:208-215`.

## 7. Health Check Registration State

```
UNREGISTERED --register_broker_health_check()--> REGISTERED
REGISTERED --register_broker_health_check()--> REGISTERED (replaces previous)
```

### States

| State | Description |
|-------|-------------|
| `UNREGISTERED` | No health check for `broker.{broker_id}` in `health_registry`. |
| `REGISTERED` | `BrokerConnectivityHealthCheck` stored under `broker.{broker_id}`. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `UNREGISTERED` | Factory calls `register_broker_health_check(...)` | `REGISTERED` | `archive/brokers/common/observability/health_check.py:124-140` |
| `REGISTERED` | Re-registration | `REGISTERED` | `archive/infrastructure/health.py:59-69` |

## 8. Token Refresh Scheduler State

```
NOT_CREATED --factory setup--> CREATED
CREATED --lifecycle.register()--> REGISTERED_WITH_LIFECYCLE
CREATED --no lifecycle--> STARTED_WITH_ATEXIT
STARTED_WITH_ATEXIT --process exit--> STOPPED (via atexit)
REGISTERED_WITH_LIFECYCLE --lifecycle shutdown--> STOPPED
```

### States

| State | Description |
|-------|-------------|
| `NOT_CREATED` | No scheduler exists. |
| `CREATED` | `TokenRefreshScheduler` instantiated but not registered with a lifecycle manager. |
| `REGISTERED_WITH_LIFECYCLE` | Scheduler registered with a lifecycle manager; lifecycle controls start/stop. |
| `STARTED_WITH_ATEXIT` | Scheduler started immediately and `atexit.register(scheduler.stop)` called. |
| `STOPPED` | Scheduler no longer running. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `NOT_CREATED` | `_setup_token_refresh_scheduler()` called | `CREATED` | `archive/brokers/dhan/factory.py:384-390` |
| `CREATED` | `lifecycle` provided | `REGISTERED_WITH_LIFECYCLE` | `archive/brokers/dhan/factory.py:391-393` |
| `CREATED` | `lifecycle` is None | `STARTED_WITH_ATEXIT` | `archive/brokers/dhan/factory.py:395-399` |
| `STARTED_WITH_ATEXIT` | Process exit | `STOPPED` | `archive/brokers/dhan/factory.py:397` |
| `REGISTERED_WITH_LIFECYCLE` | Lifecycle shutdown | `STOPPED` | inferred from `lifecycle.register(scheduler)` pattern |

## 9. Environment File Bootstrap State

```
NOT_LOADED --bootstrap_environment()--> LOADED (or SKIPPED)
LOADED --bootstrap_environment() again--> LOADED (re-reads file, overwrites env)
```

### States

| State | Description |
|-------|-------------|
| `NOT_LOADED` | Env file has not been processed by `bootstrap_environment()`. |
| `LOADED` | Env file contents copied into `os.environ`. |
| `SKIPPED` | File missing or empty; no env vars changed. |

### Transitions

| From | Event | To | Evidence |
|------|-------|-----|----------|
| `NOT_LOADED` | File exists and non-empty | `LOADED` | `archive/brokers/common/auth/environment_bootstrap.py:26-37` |
| `NOT_LOADED` | File missing or empty | `SKIPPED` | `archive/brokers/common/auth/environment_bootstrap.py:38-39` |
| `LOADED` | `bootstrap_environment()` called again | `LOADED` (re-read) | `archive/brokers/common/auth/tests/test_environment_bootstrap.py:37-49` |

## Summary of Critical State Transitions

The most behaviorally significant transitions are:

1. **Factory duplicate suppression:** `CHECKING_REGISTRY → RETURN_EXISTING` prevents multiple gateways for the same account.
2. **Token fallback:** `BUILDING → ERROR` when no static token, persisted token, or TOTP credentials are available.
3. **Scheduler fallback:** `CREATED → STARTED_WITH_ATEXIT` when no lifecycle is supplied; this is a hidden side effect.
4. **Feature flag lazy init:** `UNINITIALIZED → INITIALIZED` on first access; tests rely on `reset()` to return to a clean state.
