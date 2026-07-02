The TradeXV2 repository employs a centralized, standard-library-based logging system designed for security (token redaction) and observability (structured metrics and Prometheus integration). It avoids third-party logging frameworks like `structlog` or `loguru` in favor of Python's built-in `logging` module, extended with custom filters and middleware.

### 1. Core Logging Framework
- **System**: Python `logging` module configured via `dictConfig`.
- **Initialization**: Centralized in `brokers/common/logging_config.py`. The `setup_logging()` function is called once at the application entry point (`cli/main.py`) before any other imports that might log.
- **Configuration**: 
  - **Log Level**: Controlled by the `XV2_LOG_LEVEL` environment variable (default: `INFO`). Can be overridden programmatically or via the `--verbose` CLI flag (sets to `DEBUG`).
  - **Format**: Standard text format: `%(asctime)s %(name)s %(levelname)s %(message)s`.
  - **JSON Support**: Optional JSON formatting is supported if `python-json-logger` is installed, enabled via the `json_format` argument in `setup_logging`.
  - **Handlers**: Configures a `StreamHandler` (stderr) by default. An optional `FileHandler` can be added by specifying a `log_file` path.
  - **Noise Reduction**: Explicitly silences noisy third-party libraries (`urllib3`, `websockets`, `aiohttp`, `requests`) at `WARNING` level.

### 2. Security: Token Redaction
- **Mechanism**: A custom `TokenRedactionFilter` (subclass of `logging.Filter`) is installed on all handlers by default.
- **Function**: Intercepts log records and redacts sensitive substrings in the message before emission.
- **Patterns Redacted**:
  - Key-value pairs: `access_token=...`, `refresh_token=...`, `api_key=...`, `api_secret=...`, `password=...`.
  - Authorization headers: `authorization: Bearer ...`.
  - Environment variables: `DHAN_ACCESS_TOKEN=...`, `UPSTOX_ACCESS_TOKEN=...`.
  - Heuristic: Any standalone base64url-like string of 32+ characters (catches JWTs and opaque tokens).
- **Implementation**: Modifies `record.msg` and clears `record.args` in-place to ensure the formatted output is redacted.

### 3. Observability and Metrics
- **HTTP Request Logging**: The FastAPI datalake API (`datalake/api/main.py`) uses `RequestLoggingMiddleware` (`datalake/api/middleware.py`).
  - **Correlation IDs**: Generates or propagates `X-Request-ID` for traceability.
  - **Structured Logs**: Logs every request as `METHOD PATH STATUS DURATION_MS [REQUEST_ID]`.
  - **Metrics**: Maintains thread-safe in-process counters for `request_total` and `request_duration_ms`, normalized by path (replacing numeric IDs with `{id}` to limit cardinality).
- **Prometheus Integration**: 
  - **Event Metrics**: `brokers/common/observability/event_metrics.py` provides `EventMetrics`, a thread-safe counter store for business events (e.g., `TICK published`, `ORDER handler_error`).
  - **Observability Server**: `brokers/common/observability/http_server.py` runs a lightweight `aiohttp` server on localhost (default port 8765) exposing:
    - `/healthz`: Liveness probe.
    - `/readyz`: Readiness probe (checks `LifecycleManager` state).
    - `/metrics`: Prometheus text exposition format, rendering `EventMetrics` snapshots and service health gauges.

### 4. Architecture and Conventions
- **Logger Naming**: Uses standard `logging.getLogger(__name__)` pattern across all modules.
- **Entry Points**:
  - **CLI**: `cli/main.py` calls `setup_logging()` immediately after imports.
  - **API**: `datalake/api/main.py` relies on the standard logging configuration, with additional request-level logging via middleware.
- **Extra Fields**: Supports structured data via the `extra` dict in log calls (e.g., `logger.info("msg", extra={"key": "value"})`), though the default formatter does not explicitly render these unless JSON mode is active.
- **Lifecycle Integration**: Logging is integrated with the `LifecycleManager` for service health reporting, ensuring that startup/shutdown events and service states are observable via the `/metrics` endpoint.

### 5. Rules for Developers
- **Initialization**: Never call `logging.basicConfig()` directly. Use `setup_logging()` from `brokers.common.logging_config`.
- **Sensitive Data**: Never log secrets directly. The redaction filter is a safety net, not a substitute for secure coding. Prefer logging identifiers (e.g., `client_id`) over tokens.
- **Log Levels**:
  - `DEBUG`: Detailed diagnostic information (enabled via `--verbose` or `XV2_LOG_LEVEL=DEBUG`).
  - `INFO`: General operational messages (default).
  - `WARNING`: Unexpected but handled situations.
  - `ERROR`: Failure of a specific operation.
  - `CRITICAL`: System-wide failures.
- **Performance**: Avoid expensive string formatting in debug logs that are disabled in production. Use lazy evaluation where possible (though `logging` handles this well with `%` formatting).
- **Observability**: For business-critical events (orders, trades, errors), increment counters in `EventMetrics` to ensure they are visible in Prometheus scrapes.