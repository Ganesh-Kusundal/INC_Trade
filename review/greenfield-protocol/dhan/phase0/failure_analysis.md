# Phase 0 Failure Analysis — Dhan Broker Foundation

This document maps every failure path in the Phase 0 foundation, including timeouts, retries, exceptions, recovery, race conditions, deadlocks, and partial failures. Each entry cites the source file and line range as evidence.

## 1. Configuration Failures

### 1.1 Missing `DHAN_CLIENT_ID`

- **Trigger:** `DhanSettingsLoader.from_env()` called without `DHAN_CLIENT_ID` set and live environment selected.
- **Behavior:** Raises `ValueError("DHAN_CLIENT_ID is required")`.
- **Recovery:** Operator must set `DHAN_CLIENT_ID`.
- **Evidence:** `archive/brokers/dhan/settings.py:160-162`.

### 1.2 Invalid `DHAN_ENVIRONMENT`

- **Trigger:** `DHAN_ENVIRONMENT` is not `LIVE` or `SANDBOX`.
- **Behavior:** Raises `ValueError("DHAN_ENVIRONMENT must be one of ('LIVE', 'SANDBOX'), got '...'")`.
- **Recovery:** Set environment to a valid value.
- **Evidence:** `archive/brokers/dhan/settings.py:151-155`.

### 1.3 Invalid `.env` file parse

- **Trigger:** `DhanConfigLoader.load()` or `SettingsLoaderBase._load_default_env()` reads a malformed `.env` file.
- **Behavior:** The internal `load_env_file()` does not validate values; it splits on `=` and assigns raw strings. Invalid values are later coerced to defaults by `_get_int`/`_get_float`/`_get_bool`.
- **Recovery:** Defaults are used silently; fix the `.env` file to get intended values.
- **Evidence:** `archive/brokers/common/env_loader.py:12-30`; `archive/brokers/common/settings.py:87-121`.

### 1.4 Invalid JSON config file

- **Trigger:** `load_from_file()` reads a non-JSON file.
- **Behavior:** Raises `json.JSONDecodeError`.
- **Recovery:** Caller must handle or provide valid JSON.
- **Evidence:** `archive/brokers/dhan/config_loader.py:201-220`.

### 1.5 Unknown resilience env vars ignored

- **Trigger:** Operator sets `DHAN_RESILIENCE_UNKNOWN_KEY`.
- **Behavior:** Variable is silently dropped because it is not in `ENV_KEY_MAPPING`.
- **Recovery:** Use documented `DHAN_RESILIENCE_*` keys.
- **Evidence:** `archive/brokers/dhan/config_loader.py:144-146`.

### 1.6 `AppConfig` validation errors

- **Trigger:** Invalid `TRADEX_LOG_LEVEL`, `TRADEX_API_PORT=0`, etc.
- **Behavior:** Raises Pydantic `ValidationError` with descriptive message.
- **Recovery:** Fix env var values.
- **Evidence:** `archive/config/schema.py:47-62`.

### 1.7 Config validator strict-mode failures

- **Trigger:** `ConfigValidator.validate()` with staging/prod profile and missing `DHAN_CLIENT_ID` or `DHAN_ACCESS_TOKEN`.
- **Behavior:** Returns `ValidationResult` with `valid=False` and errors; `validate_or_raise()` raises `ConfigValidationError`.
- **Recovery:** Provide required credentials.
- **Evidence:** `archive/config/validator.py:210-249`.

## 2. Secret Failures

### 2.1 Missing pin or TOTP secret

- **Trigger:** `_generate_totp_token()` called but `DHAN_PIN` and `DHAN_TOTP_SECRET` are both absent.
- **Behavior:** Returns `None`; factory then raises `ConfigurationError`.
- **Recovery:** Provide pin and TOTP secret, or provide a static `DHAN_ACCESS_TOKEN`.
- **Evidence:** `archive/brokers/dhan/factory.py:477-478`, `174-177`.

### 2.2 TOTP rate limit

- **Trigger:** Dhan token endpoint returns message containing `"once every 2 minutes"`.
- **Behavior:** Raises `RuntimeError("Dhan token rate limit: ...")`.
- **Recovery:** Wait for Dhan's 2-minute cooldown.
- **Evidence:** `archive/brokers/dhan/factory.py:497-502`.

### 2.3 TOTP network failure

- **Trigger:** `requests.post()` to token URL fails.
- **Behavior:** Exception logged, returns `None`; factory raises `ConfigurationError`.
- **Recovery:** Check network and credentials.
- **Evidence:** `archive/brokers/dhan/factory.py:514-516`.

### 2.4 Read-only env file

- **Trigger:** `_update_env_token()` cannot write to `.env.local` due to `PermissionError`.
- **Behavior:** Logs info and continues; token is persisted only to `JsonTokenStateStore`.
- **Recovery:** None required; behavior degrades gracefully.
- **Evidence:** `archive/brokers/dhan/factory.py:577-580`.

### 2.5 Secret file missing

- **Trigger:** `DHAN_PIN_FILE` or `DHAN_TOTP_SECRET_FILE` points to a non-existent path.
- **Behavior:** Returns empty string / None and falls back to no secret.
- **Recovery:** Ensure file exists at the configured path.
- **Evidence:** `archive/config/secrets_manager.py:32-43`; `archive/brokers/dhan/secret_utils.py:9-31`.

## 3. Factory Failures

### 3.1 Token acquisition fails

- **Trigger:** No static token, no persisted token, and no TOTP credentials or TOTP fails.
- **Behavior:** Raises `ConfigurationError("DHAN_ACCESS_TOKEN not configured and TOTP refresh failed")`.
- **Recovery:** Provide static access token or valid TOTP credentials.
- **Evidence:** `archive/brokers/dhan/factory.py:174-177`.

### 3.2 Duplicate `client_id` returns stale gateway

- **Trigger:** `BrokerFactory.create()` called twice for the same `client_id`.
- **Behavior:** Returns existing gateway; new `env_path`, `load_instruments`, `lifecycle`, etc. are ignored.
- **Recovery:** Call `AccountConnectionRegistry.release("dhan", client_id)` first, or use a different client id.
- **Evidence:** `archive/brokers/dhan/account_registry.py:29-35`.

### 3.3 No lifecycle provided

- **Trigger:** `BrokerFactory.create()` called with `lifecycle=None`.
- **Behavior:** Token scheduler is started immediately and `atexit.register(scheduler.stop)` is invoked.
- **Risk:** Scheduler runs for the lifetime of the process; may outlive intended usage.
- **Recovery:** Provide a lifecycle manager.
- **Evidence:** `archive/brokers/dhan/factory.py:395-403`.

### 3.4 Health check registration failure

- **Trigger:** `register_broker_health_check()` called with a gateway that does not implement `describe()`.
- **Behavior:** Health check is still registered; at poll time it returns `UNHEALTHY`.
- **Recovery:** Ensure gateway implements required interface.
- **Evidence:** `archive/brokers/common/observability/health_check.py:58-70`.

## 4. Race Conditions and Concurrency

### 4.1 Account registry lock

- **Pattern:** Class-level `threading.Lock` protects `_gateways` dict.
- **Risk:** Low. The lock is held only during lookup/insert; factory execution occurs outside the lock via the lambda.
- **Evidence:** `archive/brokers/dhan/account_registry.py:16`, `28-42`.

### 4.2 Feature flag double-checked locking

- **Pattern:** `FeatureFlags._init_lock` with double-checked locking for lazy initialization.
- **Risk:** Low for initialization. However, `_flags` and `_rollout_percentages` are mutable dicts shared across threads; `set_flag()` and `is_enabled()` may race but individual dict operations are atomic in CPython.
- **Evidence:** `archive/config/feature_flags.py:111-113`, `176-184`.

### 4.3 Token refresh lock

- **Pattern:** `refresh_lock = threading.Lock()` shared between HTTP 401 handler and background scheduler.
- **Behavior:** `_refresh_via_auth()` acquires lock with 5-second timeout; if timeout, returns `None`.
- **Risk:** Medium. A refresh triggered by the scheduler can block an HTTP 401 retry for up to 5 seconds.
- **Evidence:** `archive/brokers/dhan/factory.py:83`, `406-434`.

### 4.4 Env file atomic update

- **Pattern:** `_update_env_token()` uses `fcntl.flock(LOCK_EX)` and temp-file + `os.replace()`.
- **Behavior:** Cross-process exclusion for env file updates.
- **Risk:** Low on Unix. Non-Unix systems (Windows) lack `fcntl`; the function logs a warning and returns without updating the file.
- **Evidence:** `archive/brokers/dhan/factory.py:519-594`.

### 4.5 Health registry lock

- **Pattern:** `HealthRegistry` uses `threading.Lock` for `register()`.
- **Risk:** Low. Registration is infrequent and brief.
- **Evidence:** `archive/infrastructure/health.py:57`, `59-69`.

### 4.6 DI container RLock

- **Pattern:** `Container` uses `threading.RLock()` to allow nested resolves.
- **Risk:** Low. Factory calls occur outside the lock to avoid deadlocks during resolution.
- **Evidence:** `archive/infrastructure/di.py:65`, `121-188`.

## 5. Logging Failures

### 5.1 Over-redaction of long strings

- **Trigger:** Any log message containing a 32+ character alphanumeric string.
- **Behavior:** The catch-all regex `\b([A-Za-z0-9_\-]{32,})\b` replaces the string with `<REDACTED>`.
- **Impact:** Benign data (UUIDs, instrument keys, hex digests) may be redacted.
- **Recovery:** Adjust regex or accept over-redaction.
- **Evidence:** `archive/infrastructure/logging_config.py:45`, `89-93`.

### 5.2 Correlation filter repeated import

- **Trigger:** Every log record processed by `CorrelationFilter`.
- **Behavior:** `from infrastructure.correlation import get_current_correlation_id` is executed inside `filter()`.
- **Impact:** Small runtime overhead; no functional failure.
- **Recovery:** Move import to module level in greenfield design.
- **Evidence:** `archive/infrastructure/logging_config.py:104-117`.

### 5.3 Missing `service_name` or `correlation_id`

- **Trigger:** Log records emitted before `CorrelationFilter` is installed.
- **Behavior:** Formatter uses empty strings for missing attributes.
- **Impact:** None; graceful fallback.
- **Evidence:** `archive/infrastructure/logging_config.py:140-145`, `167-172`.

## 6. Bootstrap Failures

### 6.1 Canonical env file missing

- **Trigger:** `bootstrap_environment()` called in a directory without `.env.local` or `.env.upstox`.
- **Behavior:** Returns mapping with `None` values; no exception.
- **Recovery:** Create env file or set env vars separately.
- **Evidence:** `archive/brokers/common/auth/environment_bootstrap.py:33-39`.

### 6.2 Empty env file skipped

- **Trigger:** Env file exists but has zero bytes.
- **Behavior:** Treated as missing; `None` returned.
- **Recovery:** Populate env file.
- **Evidence:** `archive/brokers/common/auth/environment_bootstrap.py:34`.

### 6.3 Idempotent re-load overwrites env

- **Trigger:** `bootstrap_environment()` called twice after file contents change.
- **Behavior:** Second call re-reads file and overwrites `os.environ`.
- **Impact:** Can surprise callers who modified env vars after first call.
- **Recovery:** Treat bootstrap as authoritative and avoid manual env changes after bootstrap.
- **Evidence:** `archive/brokers/common/auth/tests/test_environment_bootstrap.py:37-49`.

## 7. Partial Failures

### 7.1 Mixed config sources

- **Trigger:** Some values from `.env.local`, some from env vars, some defaults.
- **Behavior:** Each loader applies its own precedence; inconsistent values can result if files are loaded multiple times.
- **Example:** `bootstrap_environment()` overwrites env vars from file, but `DhanSettingsLoader.from_env()` also loads the file. If a process env var was set before bootstrap, it may be overwritten.
- **Recovery:** Establish a single bootstrap order and document it.
- **Evidence:** `archive/brokers/common/auth/environment_bootstrap.py:26-37`; `archive/brokers/dhan/settings.py:144`.

### 7.2 Resilience config fallback

- **Trigger:** `DHAN_RESILIENCE_*` vars absent.
- **Behavior:** `DhanConfigLoader.load()` returns defaults; factory later compares to `DEFAULT_CONFIG` and uses the singleton.
- **Impact:** None functional, but creates redundant config objects.
- **Evidence:** `archive/brokers/dhan/factory.py:212-218`; `archive/brokers/dhan/settings.py:211-250`.

### 7.3 Token state dir fallback

- **Trigger:** `DHAN_TOKEN_STATE_DIR` not set.
- **Behavior:** `resolved_token_state_dir` derives path from `__file__`: `Path(__file__).resolve().parents[2] / "runtime"`.
- **Impact:** Token state file location depends on the source file's location; moving the module changes the path.
- **Recovery:** Explicitly configure `DHAN_TOKEN_STATE_DIR` in production.
- **Evidence:** `archive/brokers/dhan/settings.py:76-86`.

## 8. Deadlock and Timeout Risks

| Location | Mechanism | Risk | Mitigation |
|----------|-----------|------|------------|
| `AccountConnectionRegistry` | `threading.Lock` | Factory lambda called inside lock? No, called after lookup. | Low risk. |
| `FeatureFlags` | DCL + mutable class attrs | Concurrent `set_flag`/`is_enabled` possible but dict ops are atomic. | Acceptable for current usage. |
| `_refresh_via_auth` | `Lock.acquire(timeout=5.0)` | HTTP refresh can block other refreshers up to 5s. | Timeout prevents indefinite wait. |
| `_update_env_token` | `fcntl.flock(LOCK_EX)` | Blocks other processes writing env file. | Temp file + atomic rename minimizes window. |
| `Container._resolve_singleton` | `RLock` | Factory called outside lock to avoid deadlocks. | Well-designed. |

## 9. Failure Recovery Matrix

| Failure | Exception | Default Behavior | Recovery Action |
|---------|-----------|------------------|-----------------|
| Missing `DHAN_CLIENT_ID` | `ValueError` | Fatal | Set env var |
| Invalid `DHAN_ENVIRONMENT` | `ValueError` | Fatal | Fix env var |
| Missing access token + no TOTP | `ConfigurationError` | Fatal | Set `DHAN_ACCESS_TOKEN` or TOTP creds |
| TOTP rate limit | `RuntimeError` | Fatal | Wait 2 minutes |
| Invalid JSON config file | `json.JSONDecodeError` | Fatal | Fix JSON |
| Read-only env file | None (logged) | Degraded | Token stored in JSON state file |
| Unknown resilience env var | None | Silent ignore | Use documented keys |
| Duplicate factory call | None | Reuse existing gateway | Release or use new client id |
| Missing lifecycle | None | Scheduler started with atexit | Provide lifecycle manager |
| Invalid `AppConfig` value | `ValidationError` | Fatal | Fix env var |
| Missing env file in bootstrap | None | Continue without loading | Create env file |

## 10. Open Failure-Related Questions

1. Should the greenfield factory raise on duplicate `client_id` instead of returning the existing gateway?
2. Should the token scheduler fail fast if no lifecycle is provided, rather than falling back to `atexit`?
3. Should the greenfield logging redaction drop the 32-character catch-all regex to reduce over-redaction?
4. Should `bootstrap_environment()` warn when it overwrites existing env vars?
