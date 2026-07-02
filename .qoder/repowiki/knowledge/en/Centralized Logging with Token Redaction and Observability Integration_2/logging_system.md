## Overview

TradeXV2 uses Python's standard `logging` module configured via a centralized `dictConfig` in `brokers/common/logging_config.py`. The system provides structured log formatting, token redaction for security, optional JSON output, and integration with an observability layer that exposes metrics via Prometheus endpoints.

## Core Architecture

### Centralized Configuration (`brokers/common/logging_config.py`)

All logging is initialized through a single `setup_logging()` function called early in the application lifecycle (e.g., `cli/main.py` line 24). This ensures consistent configuration across all modules before any logger instances are created.

**Key features:**
- **Single initialization guard**: Uses `_initialized` flag to prevent duplicate configuration
- **Environment-driven log level**: Reads `XV2_LOG_LEVEL` env var (default: `INFO`)
- **Configurable outputs**: Supports console (stderr), optional file handler, and optional JSON formatter
- **Third-party noise suppression**: Explicitly sets `urllib3`, `websockets`, `aiohttp`, `requests` to `WARNING`

### Token Redaction Filter (`TokenRedactionFilter`)

A custom `logging.Filter` class provides defense-in-depth against credential leakage. It intercepts every log record and redacts sensitive patterns:

**Patterns matched:**
- `access_token=<value>`
- `refresh_token=<value>`
- `api_key=<value>`, `api_secret=<value>`
- `password=<value>`
- `authorization: Bearer <value>`
- Environment variable patterns: `DHAN_ACCESS_TOKEN=...`, `UPSTOX_ACCESS_TOKEN=...`
- Heuristic: Any standalone 32+ character base64url-looking substring

The filter modifies `record.msg` and clears `record.args` in-place so downstream formatters see redacted text. Enabled by default; can be disabled via `enable_redaction=False` for debugging only.

### Log Format

**Standard format** (default):
```
%(asctime)s %(name)s %(levelname)s %(message)s
```
With date format: `%Y-%m-%d %H:%M:%S`

**JSON format** (optional):
When `json_format=True` is passed to `setup_logging()`, the system attempts to use `pythonjsonlogger.jsonlogger.JsonFormatter`. Falls back to standard format if the package is not installed.

## Structured Logging Conventions

### Use of `extra` Parameter

Developers should pass structured context via the `extra` parameter rather than embedding values in message strings. This enables downstream aggregation and avoids accidental secret leakage:

```python
logger.info("token_refresh_failed", extra={"client_id": self.client_id, "error": str(exc)})
logger.debug("command_timing", extra={"command": subcommand, "elapsed_seconds": round(elapsed, 3)})
```

Common structured fields observed across the codebase:
- `client_id` — broker client identifier
- `alert_id`, `order_id` — entity identifiers
- `count`, `load_time_s` — performance metrics
- `host`, `port` — network endpoints
- `level`, `file` — logging configuration state
- `new_state`, `previous` — state transitions
- `reset_count`, `poll_interval_s` — scheduler metrics

### Logger Naming Convention

Loggers follow the standard Python pattern `logging.getLogger(__name__)`, producing hierarchical names like:
- `brokers.common.logging_config`
- `brokers.dhan.connection`
- `analytics.backtest.engine`
- `datalake.api.main`

This enables fine-grained log level control per module if needed.

## Observability Integration

### EventMetrics (`brokers/common/observability/event_metrics.py`)

A thread-safe in-process counter store tracks operational metrics keyed by `(event_type, outcome)`. Outcomes include:
- `published`, `dispatched`, `handler_ok`, `handler_error`
- `dead_letter`, `log_error`, `duplicated_trade`

Supports both cumulative counters and timestamped entries for rate-based alerting (events per second over a configurable window).

### HTTP Observability Server (`brokers/common/observability/http_server.py`)

An aiohttp-based `ManagedService` exposing:
- `/healthz` — liveness probe (always 200 if process is up)
- `/readyz` — readiness probe (503 if any ManagedService is FAILED/UNHEALTHY)
- `/metrics` — Prometheus text exposition format rendering `EventMetrics` snapshot and `LifecycleManager` health states

Default binding: `127.0.0.1:8765` (loopback only).

### Alerting Engine (`brokers/common/observability/alerting.py`)

A threshold-based alerting system monitors `EventMetrics` and fires alerts when rules are breached. Predefined production rules include:
- High error rate (>5% handler errors) → CRITICAL
- Dead letter queue growth (>10 in 60s) → WARNING
- Circuit breaker OPEN → CRITICAL
- Broker fallback storm (>20 in 60s) → WARNING
- Log write failures (>5) → CRITICAL

Alerts support deduplication via cooldown periods (default 300s) and custom callbacks for delivery to external systems.

## Log Level Strategy

| Level | Usage |
|-------|-------|
| `DEBUG` | Verbose diagnostic info (enabled via `--verbose` CLI flag) |
| `INFO` | Default level; operational events, state changes, command execution |
| `WARNING` | Non-critical issues, validation failures, degraded states |
| `ERROR` | Handler failures, connection errors, unrecoverable conditions |
| `CRITICAL` | Reserved for alerting engine severity (not directly used in log calls) |

Third-party libraries (`urllib3`, `websockets`, `aiohttp`, `requests`) are pinned to `WARNING` to reduce noise.

## Key Files

| File | Purpose |
|------|---------|
| `brokers/common/logging_config.py` | Central logging configuration, token redaction filter |
| `brokers/common/core/constants/__init__.py` | `DEFAULT_LOG_LEVEL`, `THIRD_PARTY_LOG_LEVEL` constants |
| `brokers/common/observability/event_metrics.py` | In-process metric counters |
| `brokers/common/observability/http_server.py` | HTTP server exposing /healthz, /readyz, /metrics |
| `brokers/common/observability/alerting.py` | Threshold-based alerting engine |
| `cli/main.py` | Calls `setup_logging()` at startup; demonstrates `--verbose` flag |
| `api_server.py` | API server entry point (uses basic `logging.basicConfig` fallback) |
| `datalake/api/main.py` | FastAPI app factory with lifespan logging |

## Developer Rules

1. **Never call `logging.basicConfig()`** — use `setup_logging()` from `brokers.common.logging_config` instead. The only exception is `api_server.py` which runs independently.

2. **Never log secrets in message strings** — even with redaction, prefer `extra={"field": value}` for non-secret context. The redaction filter is defense-in-depth, not a substitute for code review.

3. **Use semantic log messages** — prefer short, searchable message strings like `"token_refresh_failed"` over verbose sentences. Include dynamic data via `extra` or format args.

4. **Respect log levels** — `DEBUG` for verbose diagnostics, `INFO` for normal operations, `WARNING` for recoverable issues, `ERROR` for failures requiring attention.

5. **Enable JSON format for production** — set `json_format=True` when deploying to environments with log aggregators (requires `python-json-logger` package).

6. **Control verbosity via environment** — set `XV2_LOG_LEVEL` env var or use `--verbose` CLI flag rather than hardcoding log levels.

7. **Monitor observability endpoints** — use `/metrics` for Prometheus scraping and `/readyz` for health checks in deployment pipelines.