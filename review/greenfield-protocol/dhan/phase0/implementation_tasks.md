# Phase 0 Implementation Tasks — Dhan Broker Foundation

These tasks are to be executed **only after** the Phase 0 discovery review is approved. Each task includes acceptance criteria derived from archived behavior. No task begins until the review board issues a formal "Ready for Greenfield Implementation" decision.

## Task Dependencies

```
Task 1 (Platform Config)
   |
   v
Task 2 (Secrets) ───> Task 3 (Feature Flags)
   |                       |
   v                       v
Task 4 (Logging) <─── Task 5 (Dhan Config)
   |
   v
Task 6 (Bootstrapper)
   |
   v
Task 7 (DI Wiring)
   |
   v
Task 8 (Parity Test Suite)
```

Tasks 2, 3, 4, and 5 depend on Task 1. Tasks 6 and 7 can begin after Task 5. Task 8 must run after all implementation is complete.

## Task 1: Extend Platform Configuration

**File:** `brokers/config_app.py`

**Objective:** Reproduce the archived `AppConfig` behavior in the greenfield settings module.

**Acceptance criteria:**

- [ ] `AppConfig` includes all fields from `archive/config/schema.py`:
  - `app_env` with `Literal["dev", "staging", "prod"]` and default `"dev"`
  - `log_level` validated against `{DEBUG, INFO, WARNING, ERROR, CRITICAL}`, normalized uppercase, default `"INFO"`
  - `debug` bool default `False`
  - `redis_url: str | None` default `None`
  - `api_host` default `"127.0.0.1"`
  - `api_port` default `8080`
  - `observability_port` default `8765`
  - `cors_origins` default `["http://localhost:5173"]`
  - `rate_limit_max_requests` default `0`
  - `rate_limit_window_seconds` default `60.0`
- [ ] `TRADEX_*` env vars take precedence over legacy aliases (`APP_ENV`, `XV2_LOG_LEVEL`, `TRADEXV2_DEBUG`, `REDIS_URL`, `API_HOST`, `API_PORT`).
- [ ] `TRADEX_CORS_ORIGINS` parses comma-separated string into list.
- [ ] Empty `TRADEX_REDIS_URL` resolves to `None`.
- [ ] Cached singleton helper functions `get_config()` and `reset_config()` exist and behave as in `archive/config/defaults.py`.
- [ ] All assertions from `archive/config/tests/test_config.py` pass against greenfield code.

**Parallelizable:** No (foundation for other tasks).

## Task 2: Consolidated Secrets Reader

**File:** `brokers/core/secrets.py`

**Objective:** Replace `archive/config/secrets_manager.py` and `archive/brokers/dhan/secret_utils.py` with a single module.

**Acceptance criteria:**

- [ ] `SecretsReader` class accepts optional `project_root`.
- [ ] `get_env_or_file(key, file_key, default="")` returns env var value if non-empty.
- [ ] Falls back to reading file path from `file_key` env var, resolved relative to `project_root`.
- [ ] Returns `default` if neither exists.
- [ ] Broker-specific helpers exist: `get_dhan_pin()`, `get_dhan_totp_secret()`, `get_upstox_pin()`, `get_upstox_totp_secret()`.
- [ ] `require(key)` raises `ValueError` if env var missing.
- [ ] Unit tests cover env-only, file-only, env-precedence, missing, and `require()` cases.

**Parallelizable:** After Task 1.

## Task 3: Feature Flags Module

**File:** `brokers/core/feature_flags.py`

**Objective:** Port archived `FeatureFlags` behavior.

**Acceptance criteria:**

- [ ] `FlagDefinition` frozen dataclass with `name`, `default=False`, `description`, `rollout_percentage=100`, validating 0–100.
- [ ] Known flags: `SMART_ROUTING`, `INTELLIGENT_GATEWAY`, `ADVANCED_ORDER_TYPES`, `EXPERIMENTAL_STRATEGIES`, `COMPOSER_EXECUTION`.
- [ ] Env var format `FEATURE_<FLAG_NAME>`; values `1`, `true`, `yes`, `on` → True; others → False.
- [ ] Lazy initialization with double-checked locking.
- [ ] `is_enabled(flag)` returns `False` for unknown flags.
- [ ] `is_enabled_for_user(flag, user_id)` uses SHA-256 of `flag:user_id`, first 8 hex chars, modulo 100.
- [ ] `set_flag(flag, value)` and `set_rollout_percentage(flag, pct)` raise `ValueError` for unknown flags.
- [ ] `set_rollout_percentage` validates 0–100.
- [ ] `get_flag_info()` and `get_all_flags()` return documented metadata dicts.
- [ ] `reset()` reloads from env.
- [ ] Module-level convenience functions exist.
- [ ] Metrics hooks increment evaluation/change counters when available; no-op fallback otherwise.
- [ ] Class is instantiable for tests while keeping a module-level default instance.
- [ ] All assertions from `archive/config/tests/test_feature_flags.py` and `archive/config/test_feature_flags_enhanced.py` pass.

**Parallelizable:** After Task 1.

## Task 4: Logging Module

**File:** `brokers/core/logging.py`

**Objective:** Port archived logging configuration with token redaction and correlation.

**Acceptance criteria:**

- [ ] `configure_logging(service="tradexv2", level=None, log_format=None, log_file=None, enable_redaction=True)` exists.
- [ ] Default level from `XV2_LOG_LEVEL` or `INFO`.
- [ ] `log_format` defaults to `"json"` when `APP_ENV` is `prod`/`production`, else `"human"`.
- [ ] `StructuredFormatter` outputs JSON with timestamp, service, level, logger, message, module, function, line, thread, process, correlation_id, service_name, exception, and extras.
- [ ] `HumanReadableFormatter` outputs colored human-readable lines with correlation id and extras.
- [ ] `TokenRedactionFilter` redacts access/refresh tokens, API keys, passwords, bearer tokens, query-string `token`, and 32+ char alphanumeric strings (if parity decision keeps catch-all).
- [ ] `CorrelationFilter` injects `correlation_id` and `service_name`.
- [ ] Quiet loggers for `urllib3`, `httpx`, `websockets`, `asyncio` at WARNING.
- [ ] Tests verify redaction of token patterns and JSON validity.

**Parallelizable:** After Task 1.

## Task 5: Dhan Configuration Module

**Files:** `brokers/adapters/dhan/config.py`, `brokers/adapters/dhan/settings.py`, `brokers/adapters/dhan/endpoints.py`

**Objective:** Port Dhan connection and resilience configuration.

**Acceptance criteria:**

- [ ] `DhanConnectionConfig` Pydantic model preserves all archived `DhanConnectionSettings` fields and defaults.
- [ ] Env var prefix `DHAN_`.
- [ ] Sandbox/live switching reads `DHAN_SANDBOX_CLIENT_ID` and `DHAN_SANDBOX_ACCESS_TOKEN` when `DHAN_ENVIRONMENT=SANDBOX`.
- [ ] `DHAN_CLIENT_ID` required in live mode; missing raises `ValueError`.
- [ ] Invalid `DHAN_ENVIRONMENT` raises `ValueError`.
- [ ] Secrets integration uses `SecretsReader` from Task 2.
- [ ] `DhanResilienceConfig` frozen dataclass with rate limit, retry, circuit breaker, token sub-configs.
- [ ] Default rate limits match archived values exactly.
- [ ] Default retry: 3 attempts, 500 ms base, 5000 ms cap, exponential `2^(attempt-1)`.
- [ ] Default circuit breaker thresholds match archived values.
- [ ] `DhanResilienceConfig.from_dict()` and `.to_dict()` round-trip correctly.
- [ ] Env loader for `DHAN_RESILIENCE_*` uses whitelist and silently ignores unknown keys.
- [ ] Dhan endpoint constants preserved in `brokers/adapters/dhan/endpoints.py`.
- [ ] All assertions from `archive/brokers/dhan/tests/test_config.py` pass.

**Parallelizable:** After Tasks 1 and 2.

## Task 6: Dhan Bootstrapper

**File:** `brokers/adapters/dhan/bootstrap.py`

**Objective:** Replace archived `BrokerFactory` with an explicit bootstrapper.

**Acceptance criteria:**

- [ ] `DhanBootstrapResult` dataclass returns `gateway`, `scheduler`, `auth_manager`, `token_state`.
- [ ] `DhanBootstrapper.bootstrap(settings, options) -> DhanBootstrapResult` exists.
- [ ] Runtime sequence matches archived `BrokerFactory._build_gateway()`:
  1. Create auth manager and resolve token.
  2. Build HTTP client with resilience config.
  3. Build connection and gateway.
  4. Optionally load instruments.
  5. Optionally wire WebSocket services.
  6. Optionally create scheduler.
- [ ] No automatic health check registration.
- [ ] No automatic `atexit` scheduler start.
- [ ] Optional `DhanLifecycleBundle` provides opt-in health check registration and scheduler start for callers who need archived behavior.
- [ ] Token persistence to `.env.local` is configurable, not hardcoded.
- [ ] Errors match archived behavior: `ConfigurationError` when token unavailable.

**Parallelizable:** After Task 5.

## Task 7: DI Wiring

**File:** `brokers/core/di.py`

**Objective:** Register greenfield Phase 0 components in the existing container.

**Acceptance criteria:**

- [ ] `AppConfig` registered as singleton.
- [ ] `SecretsReader` registered as singleton.
- [ ] `FeatureFlags` default instance registered as singleton.
- [ ] `DhanBootstrapper` registered as factory or singleton.
- [ ] `resolve()` returns configured instances.
- [ ] Tests verify container wiring.

**Parallelizable:** After Tasks 2, 3, and 6.

## Task 8: Parity Test Suite

**Directory:** `brokers/tests/phase0/`

**Objective:** Prove greenfield behavior matches archived behavior.

**Acceptance criteria:**

- [ ] Port all relevant archived tests:
  - `archive/brokers/dhan/tests/test_config.py`
  - `archive/config/tests/test_config.py`
  - `archive/config/tests/test_profiles.py`
  - `archive/config/tests/test_validator.py`
  - `archive/config/tests/test_feature_flags.py`
  - `archive/config/test_feature_flags_enhanced.py`
  - `archive/brokers/common/auth/tests/test_environment_bootstrap.py`
- [ ] Add tests for greenfield-specific behavior:
  - Explicit bootstrapper returns result without side effects unless opted in.
  - DI container resolves all Phase 0 components.
  - Secrets reader consolidated behavior.
- [ ] All tests pass in project venv using `pytest`.
- [ ] Code passes `ruff` linting and `mypy` type checking (if configured).

**Parallelizable:** No (final verification).

## Completion Gate

Before Phase 0 is marked complete, the following gates from project rule `rule1.md` must be satisfied:

1. **Second-Level Review:** Another review of the deliverables and implementation.
2. **Related Test Verifications:** All ported tests pass; new tests added for gaps.
3. **Clean Code & Refactoring:** Remove dead code, unused imports, unnecessary comments.
4. **Static Code Analysis:** Run `ruff` and `mypy`; address warnings.
5. **Regression:** Run full test suite or targeted regression for affected modules.

## Evidence Matrix Update

After implementation, update `evidence_matrix.md` to reflect that all Phase 0 capabilities have moved from `Partial`/`Missing` to `Verified` with greenfield test evidence.
