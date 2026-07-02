## Overview
TradeXV2 uses a centralized logging system built on Python's standard `logging` module, configured via `dictConfig` in `brokers/common/logging_config.py`. The system is initialized once at application startup (typically in `cli/main.py`) and provides a consistent logging interface across all modules.

## Key Components

### 1. Central Configuration (`brokers/common/logging_config.py`)
- **Initialization**: `setup_logging()` is called early in the application lifecycle (e.g., `cli/main.py` line 21) before any other imports that might log.
- **Log Level**: Controlled by the `XV2_LOG_LEVEL` environment variable (default: `INFO`). Can be overridden programmatically or via the `--verbose` CLI flag (which sets level to `DEBUG`).
- **Handlers**: 
  - `console`: Streams to `sys.stderr` with a standard formatter.
  - `file`: Optional file handler if `log_file` is specified.
- **Formatters**:
  - `standard`: `% (asctime)s %(name)s %(levelname)s %(message)s`
  - `json`: Optional JSON formatter using `python-json-logger` if available and `json_format=True`.
- **Third-party Silence**: Noisy libraries (`urllib3`, `websockets`, `aiohttp`, `requests`) are silenced to `WARNING` level.

### 2. Security: Token Redaction Filter
A custom `TokenRedactionFilter` is installed on all handlers by default to prevent accidental leakage of sensitive credentials in logs.
- **Patterns Redacted**:
  - `access_token=<value>`
  - `refresh_token=<value>`
  - `api_key=<value>`
  - `authorization: Bearer <value>`
  - Environment variables like `DHAN_ACCESS_TOKEN=...`
  - Heuristic: Any standalone base64url-like string >= 32 characters.
- **Mechanism**: The filter modifies `record.msg` and clears `record.args` in-place to ensure redaction persists through formatting.
- **Testing**: Covered by `brokers/common/tests/test_logging_redaction.py`.

### 3. Observability Metrics (`brokers/common/observability/`)
While not strictly "logging," the system includes an `EventMetrics` class for structured, in-process counter tracking (e.g., `published`, `handler_error`, `dead_letter`). These metrics are exposed via an HTTP observability server and can be rendered as Prometheus text format.

## Conventions & Rules

1. **Logger Initialization**: Always use `logging.getLogger(__name__)` to create module-level loggers. Do not use `basicConfig` anywhere else in the codebase.
2. **Structured Logging**: Prefer using `extra={}` dictionaries for structured fields (e.g., `logger.info("msg", extra={"client_id": id})`).
3. **No Secrets in Logs**: Never manually format secrets into log messages. Rely on the `TokenRedactionFilter` as a safety net, but code review should prevent secret logging entirely.
4. **Log Levels**:
   - `DEBUG`: Detailed diagnostic information (enabled via `--verbose`).
   - `INFO`: General operational messages (default).
   - `WARNING`: Unexpected but handled situations.
   - `ERROR`: Serious issues requiring attention.
5. **JSON Output**: For machine-readable logs, enable `json_format=True` in `setup_logging()` (requires `python-json-logger`).

## Key Files
- `brokers/common/logging_config.py`: Core configuration and redaction logic.
- `cli/main.py`: Entry point that initializes logging.
- `brokers/common/observability/event_metrics.py`: Structured metrics collection.
- `domain/constants/observability.py`: Constants for observability server configuration.