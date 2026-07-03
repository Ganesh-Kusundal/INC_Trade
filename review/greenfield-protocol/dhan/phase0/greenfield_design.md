# Phase 0 Greenfield Design — Dhan Broker Foundation

## Design Goal

Preserve every externally observable behavior documented in the source audit, runtime sequence, public contract, and failure analysis, while replacing the archived foundation with a cleaner, more maintainable architecture. No behavior changes are proposed unless explicitly noted and justified.

## Guiding Principles

1. **Explicit over implicit.** Side effects (env file writes, scheduler start, health check registration) must be visible in the bootstrap API.
2. **Single source of truth for each config concern.** Merge or consolidate the four overlapping archived config systems where possible without breaking env-var names.
3. **Backward-compatible env vars.** All documented `TRADEX_*`, `DHAN_*`, `DHAN_RESILIENCE_*`, and `FEATURE_*` names must continue to work.
4. **Testable seams.** Every component must be constructible with explicit dependencies; avoid global mutable state.
5. **Layered architecture.** Keep platform concerns (`logging`, `DI`, `health`) separate from broker concerns (`settings`, `factory`, `bootstrap`).

## Proposed Module Structure

```
brokers/
├── config_app.py                 # Extended AppConfig (platform-wide)
├── core/
│   ├── di.py                     # Keep existing type-keyed Container
│   ├── secrets.py                # Consolidated env/file secret reader
│   ├── feature_flags.py          # Ported FeatureFlags with deterministic hashing
│   └── logging.py                # configure_logging + redaction + correlation
└── adapters/
    └── dhan/
        ├── config.py             # DhanResilienceConfig + DhanConnectionConfig
        ├── settings.py           # DhanSettingsLoader behavior
        ├── bootstrap.py          # Explicit DhanBootstrapper
        └── bootstrap_result.py   # Gateway + scheduler + token state
```

## 1. Unified Configuration Layer

### Platform Config — Extend `brokers/config_app.py`

**Current state:** Minimal `AppConfig` with `environment`, `log_level`, `dhan`, `upstox`.

**Required additions:**

- `app_env: Literal["dev", "staging", "prod"]` defaulting to `"dev"`
- `api_host: str` default `"127.0.0.1"`
- `api_port: int` default `8080`
- `observability_port: int` default `8765`
- `cors_origins: list[str]` default `["http://localhost:5173"]`
- `redis_url: str | None` default `None`
- `rate_limit_max_requests: int` default `0`
- `rate_limit_window_seconds: float` default `60.0`
- Preserve legacy env var aliases (`APP_ENV`, `XV2_LOG_LEVEL`, etc.) with `TRADEX_*` taking precedence.

**Design decision:** Use `pydantic_settings` with explicit `env_prefix="TRADEX_"` and override `from_env()` or use `model_config` to support legacy aliases. Do not change existing `brokers/config_app.py` field names; add new fields only.

### Broker Config — `brokers/adapters/dhan/config.py`

**Consolidate:**

- `DhanConnectionConfig` (Pydantic model) replaces `DhanConnectionSettings` frozen dataclass.
- `DhanResilienceConfig` (frozen dataclass) remains separate because it is passed deep into the HTTP client and must be hashable/serializable.

**Env var names to preserve:**

- `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`, `DHAN_ENVIRONMENT`
- `DHAN_PIN`, `DHAN_TOTP_SECRET`, `DHAN_PIN_FILE`, `DHAN_TOTP_SECRET_FILE`
- `DHAN_BASE_URL`, `DHAN_SANDBOX_*`
- `DHAN_HTTP_TIMEOUT`, `DHAN_ENABLE_RETRY`, `DHAN_POOL_CONNECTIONS`, `DHAN_POOL_MAXSIZE`
- `DHAN_TOKEN_LIFETIME_SECONDS`, `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS`, `DHAN_TOKEN_REFRESH_BUFFER_SECONDS`
- `DHAN_ALLOW_LIVE_ORDERS`, `DHAN_TOKEN_STATE_DIR`
- All `DHAN_RESILIENCE_*` vars

**Design decision:** Use a hybrid approach:

- `DhanConnectionConfig` is a Pydantic `BaseSettings` model with `env_prefix="DHAN_"`.
- `DhanResilienceConfig` is loaded separately by a small loader that reads `DHAN_RESILIENCE_*` and merges into the frozen dataclass.

This preserves the existing env-var surface while unifying the code path.

## 2. Explicit Bootstrap Lifecycle

### Replace hidden factory side effects with `DhanBootstrapper`

```python
@dataclass(frozen=True)
class DhanBootstrapResult:
    gateway: BrokerGateway
    scheduler: TokenRefreshScheduler | None
    auth_manager: AuthManager
    token_state: TokenState
```

### `DhanBootstrapper.bootstrap(settings, options) -> DhanBootstrapResult`

**Steps (same as archived runtime sequence):**

1. Resolve or create auth manager and token.
2. Build HTTP client with resilience config.
3. Build connection and gateway.
4. Optionally load instruments.
5. Optionally wire WebSocket services.
6. Optionally create token refresh scheduler.
7. Return result without registering health checks or starting lifecycle-managed services.

**What is removed from the factory:**

- No automatic `AccountConnectionRegistry` lookup; the caller decides whether to reuse.
- No automatic health check registration.
- No automatic `atexit` scheduler start.
- No automatic `.env.local` write; token persistence is handled by an explicit `TokenPersistence` policy.

**Why:** The archived factory mixed construction, global state, and process lifecycle. The greenfield design separates these so tests and callers can compose behavior explicitly.

### Optional `DhanLifecycleBundle`

For callers who want the archived "one call and run" behavior:

```python
class DhanLifecycleBundle:
    def __init__(self, result: DhanBootstrapResult, health_registry, lifecycle):
        ...

    def register_health_check(self) -> None:
        ...

    def start_scheduler(self) -> None:
        ...
```

This preserves the observable behavior while making every side effect opt-in.

## 3. Secrets Abstraction

### `brokers/core/secrets.py`

```python
class SecretsReader:
    def __init__(self, project_root: Path | None = None): ...

    def get_env_or_file(self, key: str, file_key: str, default: str = "") -> str: ...
```

**Behavior to preserve:**

- Read env var first.
- If empty, read path from `*_FILE` env var relative to project root.
- Return default if neither exists.

**Consolidation:** Replace both `archive/config/secrets_manager.py` and `archive/brokers/dhan/secret_utils.py` with this single implementation.

## 4. Feature Flags

### `brokers/core/feature_flags.py`

Port `archive/config/feature_flags.py` with the following preserved behaviors:

- Default False for all flags.
- Env var format `FEATURE_<FLAG_NAME>`.
- Boolean parsing: `1`, `true`, `yes`, `on` → True.
- Lazy initialization with double-checked locking.
- `is_enabled()`, `is_enabled_for_user()`, `set_flag()`, `set_rollout_percentage()`, `get_rollout_percentage()`, `get_flag_info()`, `get_all_flags()`, `reset()`.
- Deterministic SHA-256 rollout hashing: `flag_name:user_id`, first 8 hex chars, modulo 100.
- Metrics hooks with no-op fallback.

**Improvement:** Make the class instantiable (non-singleton) for tests, while keeping a module-level default instance for convenience. This removes global mutable state from tests.

## 5. Logging

### `brokers/core/logging.py`

Port `archive/infrastructure/logging_config.py` with preserved behaviors:

- `configure_logging(service, level, log_format, log_file, enable_redaction)`.
- Default level from `XV2_LOG_LEVEL` or `INFO`.
- JSON formatter in production, human formatter otherwise.
- Token redaction filter.
- Correlation filter.
- Quiet loggers for `urllib3`, `httpx`, `websockets`, `asyncio`.

**Improvement:** Move `infrastructure.correlation` import to module level in the correlation filter to avoid per-record import overhead.

**Open design question:** Whether to keep the 32-character catch-all redaction regex. Behavioral parity argues for keeping it; usability argues for removing it. This must be approved before implementation.

## 6. Dependency Injection

### Keep `brokers/core/di.py` Container

The existing type-keyed container is simpler than the archived string-keyed container. Continue using it for greenfield components.

**Registration plan:**

- `AppConfig` as singleton.
- `SecretsReader` as singleton.
- `FeatureFlags` default instance as singleton.
- `DhanBootstrapper` as transient or factory.

**Decision:** Do not replicate the archived `infrastructure.di.Container` string-keyed API; the greenfield container is a deliberate architectural simplification. Ensure no archived code path depends on string-keyed resolution in Phase 0 scope.

## 7. Environment Bootstrap

### `brokers/core/env_bootstrap.py`

Port `bootstrap_environment()` behavior:

- Load canonical env files for specified brokers.
- Skip `paper` broker.
- Skip empty files.
- Overwrite `os.environ` so fresh tokens take effect.
- Return mapping of broker to loaded path or `None`.

**Improvement:** Add an optional `warn_on_overwrite` flag (default False for parity) so callers can detect unexpected env overwrites.

## 8. Health Checks

### Keep health check registration explicit

Do not auto-register health checks inside the bootstrapper. Provide a helper:

```python
def register_dhan_health_check(broker_id: str, gateway, health_registry) -> None:
    ...
```

This preserves the archived `register_broker_health_check` behavior but makes the registry dependency explicit.

## 9. State Machine Preservation

The greenfield design must preserve the following state transitions:

| Archived State | Greenfield Equivalent |
|----------------|----------------------|
| `AppConfig` cached singleton | `AppConfig` cached in DI container |
| `DhanConnectionSettings` frozen dataclass | `DhanConnectionConfig` Pydantic model |
| `DhanResilienceConfig` frozen dataclass | Same, unchanged |
| `AccountConnectionRegistry` | Optional registry or caller-managed reuse |
| `FeatureFlags` global class state | Default global instance + instantiable class |
| Logging configured globally | Same global `configure_logging` |
| Health check registered globally | Explicit registration helper |
| Scheduler lifecycle via `atexit` or lifecycle manager | Explicit scheduler start/stop |

## 10. Proposed File-by-File Mapping

| Archived File | Greenfield File | Notes |
|---------------|-----------------|-------|
| `archive/config/schema.py` | `brokers/config_app.py` | Extend existing AppConfig |
| `archive/config/defaults.py` | `brokers/config_app.py` + DI | Cache via DI singleton |
| `archive/config/feature_flags.py` | `brokers/core/feature_flags.py` | Port with instantiable option |
| `archive/config/secrets_manager.py` | `brokers/core/secrets.py` | Consolidate with secret_utils |
| `archive/config/validator.py` | `brokers/core/config_validator.py` | Port if needed |
| `archive/config/profiles/*.py` | `brokers/core/profiles.py` | Optional; orphan layer |
| `archive/config/endpoints.py` | `brokers/adapters/dhan/endpoints.py` | Dhan portion only |
| `archive/brokers/dhan/config.py` | `brokers/adapters/dhan/config.py` | Resilience config |
| `archive/brokers/dhan/config_loader.py` | `brokers/adapters/dhan/config.py` | Loader merged |
| `archive/brokers/dhan/settings.py` | `brokers/adapters/dhan/settings.py` | Pydantic-based |
| `archive/brokers/dhan/secret_utils.py` | `brokers/core/secrets.py` | Consolidated |
| `archive/brokers/dhan/factory.py` | `brokers/adapters/dhan/bootstrap.py` | Explicit bootstrapper |
| `archive/brokers/common/bootstrap.py` | `brokers/adapters/common/bootstrap.py` | Future phase |
| `archive/brokers/common/auth/environment_bootstrap.py` | `brokers/core/env_bootstrap.py` | Port |
| `archive/brokers/common/env_loader.py` | `brokers/core/env_loader.py` | Port |
| `archive/infrastructure/logging_config.py` | `brokers/core/logging.py` | Port |
| `archive/infrastructure/health.py` | `brokers/core/health.py` | Port if not present |
| `archive/infrastructure/di.py` | `brokers/core/di.py` | Keep existing simplification |

## 11. Design Decisions Requiring Approval

The following are improvements that change observable structure but not behavior. They require review-board approval before implementation:

1. **Remove automatic `.env.local` token writes from bootstrapper.** Token persistence moves to an explicit policy; the archived behavior can be re-enabled via `DhanLifecycleBundle`.
2. **Remove automatic `atexit` scheduler fallback.** Callers must provide a lifecycle manager or explicitly start the scheduler.
3. **Make `FeatureFlags` instantiable.** The module-level default instance preserves convenience; tests use fresh instances.
4. **Drop the 32-character catch-all redaction regex.** Reduces over-redaction but changes log output for long alphanumeric strings.
5. **Do not replicate the archived string-keyed DI container.** The type-keyed greenfield container is the intended replacement.
