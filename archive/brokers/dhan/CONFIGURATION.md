# Dhan Broker Configuration Reference

This document describes the runtime configuration system for the Dhan broker implementation in Trade XV2. The system replaces hardcoded values with configurable parameters, enabling customization without code changes.

## Overview

The Dhan broker configuration system is built on the following principles:

- **Type Safety**: All configuration uses Python dataclasses for compile-time type checking
- **Immutability**: Configuration objects are frozen (immutable) to prevent accidental modifications
- **Backwards Compatibility**: Existing code continues to work without changes
- **Environment Overrides**: Configuration can be overridden via environment variables
- **File-based Configuration**: Support for JSON configuration files
- **Dependency Injection**: Configuration is injected into components at creation time

## Configuration Structure

The configuration is organized into a hierarchy of dataclasses:

```
DhanResilienceConfig (Main Configuration)
├── DhanRateLimitConfig (Rate Limiting)
│   ├── limits: dict[str, float] (Endpoint-specific intervals)
│   ├── read_prefixes: tuple[str, ...] (Read endpoint categorization)
│   ├── write_prefixes: tuple[str, ...] (Write endpoint categorization)
│   └── bucket_map: dict[str, str] (CB category to rate limiter bucket mapping)
│
├── DhanRetryConfig (Retry Behavior)
│   ├── max_retries: int (Maximum retry attempts)
│   ├── base_delay_ms: int (Base delay for exponential backoff)
│   └── max_delay_ms: int (Maximum delay cap)
│
├── DhanCircuitBreakerConfig (Circuit Breaker Settings)
│   ├── read_prefixes: tuple[str, ...] (Read endpoint prefixes)
│   ├── write_prefixes: tuple[str, ...] (Write endpoint prefixes)
│   ├── orders_failure_threshold: int (Orders CB failure threshold)
│   ├── default_failure_threshold: int (Other CBs failure threshold)
│   ├── recovery_timeout_ms: int (Recovery timeout in milliseconds)
│   └── success_threshold: int (Successes needed to close half-open CB)
│
└── DhanTokenConfig (Token Refresh)
    ├── refresh_cooldown_seconds: float (Minimum time between refreshes)
    └── rate_limit_backoff_seconds: float (Backoff on rate limit hit)
```

## Default Values

All configuration has sensible defaults that match the original hardcoded values:

### Rate Limit Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `limits` | `{"/marketfeed/quote": 1.0, "/marketfeed/ltp": 0.15, ...}` | Per-endpoint minimum intervals (seconds) |
| `read_prefixes` | `("/marketfeed/ltp", "/marketfeed/quote", "/charts/", ...)` | Endpoints categorized as read |
| `write_prefixes` | `("/orders", "/killswitch", "/sliceorder")` | Endpoints categorized as write |
| `bucket_map` | `{"read": "market_data", "write": "orders", "admin": "admin"}` | Circuit breaker to rate limiter bucket mapping |

### Retry Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | `3` | Maximum number of retry attempts |
| `base_delay_ms` | `500` | Base delay for exponential backoff (milliseconds) |
| `max_delay_ms` | `5000` | Maximum delay cap (milliseconds) |

### Circuit Breaker Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `read_prefixes` | Same as rate_limit.read_prefixes | Endpoints for read circuit breaker |
| `write_prefixes` | Same as rate_limit.write_prefixes | Endpoints for write circuit breaker |
| `orders_failure_threshold` | `3` | Failure threshold for orders CB |
| `default_failure_threshold` | `5` | Failure threshold for other CBs |
| `recovery_timeout_ms` | `30000` | Time before CB attempts recovery (milliseconds) |
| `success_threshold` | `3` | Consecutive successes to close half-open CB |

### Token Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `refresh_cooldown_seconds` | `60` | Minimum time between token refresh attempts (seconds) |
| `rate_limit_backoff_seconds` | `130` | Backoff when Dhan rate limits token generation (seconds) |

## Configuration Loading

Configuration can be loaded from multiple sources with the following priority (highest to lowest):

1. **Environment Variables** (`DHAN_RESILIENCE_*` prefix)
2. **`.env` File** (`.env.local` or `.env`)
3. **Default Values** (Hardcoded in configuration classes)

### Environment Variables

All environment variables use the prefix `DHAN_RESILIENCE_` and follow a flat naming convention with underscores:

```bash
# Retry configuration
export DHAN_RESILIENCE_RETRY_MAX_RETRIES=5
export DHAN_RESILIENCE_RETRY_BASE_DELAY_MS=1000
export DHAN_RESILIENCE_RETRY_MAX_DELAY_MS=10000

# Token configuration
export DHAN_RESILIENCE_TOKEN_REFRESH_COOLDOWN_SECONDS=120.0
export DHAN_RESILIENCE_TOKEN_RATE_LIMIT_BACKOFF_SECONDS=200.0

# Circuit breaker configuration
export DHAN_RESILIENCE_CB_ORDERS_FAILURE_THRESHOLD=5
export DHAN_RESILIENCE_CB_DEFAULT_FAILURE_THRESHOLD=3
```

### Environment Variable Reference

| Environment Variable | Config Path | Type | Default |
|----------------------|-------------|------|---------|
| `DHAN_RESILIENCE_RETRY_MAX_RETRIES` | `retry.max_retries` | int | 3 |
| `DHAN_RESILIENCE_RETRY_BASE_DELAY_MS` | `retry.base_delay_ms` | int | 500 |
| `DHAN_RESILIENCE_RETRY_MAX_DELAY_MS` | `retry.max_delay_ms` | int | 5000 |
| `DHAN_RESILIENCE_TOKEN_REFRESH_COOLDOWN_SECONDS` | `token.refresh_cooldown_seconds` | float | 60.0 |
| `DHAN_RESILIENCE_TOKEN_RATE_LIMIT_BACKOFF_SECONDS` | `token.rate_limit_backoff_seconds` | float | 130.0 |
| `DHAN_RESILIENCE_CB_ORDERS_FAILURE_THRESHOLD` | `circuit_breaker.orders_failure_threshold` | int | 3 |
| `DHAN_RESILIENCE_CB_DEFAULT_FAILURE_THRESHOLD` | `circuit_breaker.default_failure_threshold` | int | 5 |
| `DHAN_RESILIENCE_CB_RECOVERY_TIMEOUT_MS` | `circuit_breaker.recovery_timeout_ms` | int | 30000 |
| `DHAN_RESILIENCE_CB_SUCCESS_THRESHOLD` | `circuit_breaker.success_threshold` | int | 3 |

### JSON Configuration Files

Configuration can also be loaded from JSON files:

```json
{
  "retry": {
    "max_retries": 5,
    "base_delay_ms": 1000,
    "max_delay_ms": 10000
  },
  "rate_limit": {
    "limits": {
      "/marketfeed/quote": 0.5,
      "/marketfeed/ltp": 0.1
    }
  },
  "circuit_breaker": {
    "orders_failure_threshold": 5,
    "default_failure_threshold": 3
  },
  "token": {
    "refresh_cooldown_seconds": 120.0,
    "rate_limit_backoff_seconds": 200.0
  }
}
```

Load from file:

```python
from pathlib import Path
from brokers.dhan.config_loader import load_from_file

config = load_from_file(Path("config/dhan.json"))
```

## Usage Examples

### Programmatic Configuration

```python
from brokers.dhan.config import DhanResilienceConfig, DhanRetryConfig

# Create custom configuration
config = DhanResilienceConfig(
    retry=DhanRetryConfig(
        max_retries=5,
        base_delay_ms=1000,
        max_delay_ms=10000
    )
)

# Use with DhanHttpClient
from brokers.dhan.http_client import DhanHttpClient

client = DhanHttpClient(
    client_id="your_client_id",
    access_token="your_access_token",
    config=config
)
```

### Factory Integration

The `BrokerFactory` automatically loads configuration from:

1. `settings.resilience_config` (if provided in DhanConnectionSettings)
2. Environment variables (`DHAN_RESILIENCE_*`)
3. Default values

```python
from brokers.dhan.factory import BrokerFactory
from pathlib import Path

# Load from .env file
gateway = BrokerFactory.create(env_path=Path(".env.local"))
```

### With Environment Variables

```bash
# Set custom retry configuration
export DHAN_RESILIENCE_RETRY_MAX_RETRIES=5
export DHAN_RESILIENCE_RETRY_BASE_DELAY_MS=1000

# Create gateway - will use env vars
python your_script.py
```

## Configuration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        BrokerFactory.create()                        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     DhanSettingsLoader.from_env()                    │
│  - Loads .env file if specified                                      │
│  - Reads DHAN_* environment variables                                  │
│  - Creates DhanConnectionSettings with resilience_config field      │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    _create_http_client()                              │
│  - Checks settings.resilience_config                                  │
│  - Falls back to DhanConfigLoader.load_from_environment()             │
│  - Falls back to DEFAULT_CONFIG if no custom config                 │
│  - Creates circuit breakers with config-based thresholds           │
│  - Passes config to DhanHttpClient                                   │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                       DhanHttpClient                                   │
│  - Stores config in self._config                                     │
│  - Uses config for rate limits, retries, circuit breakers, tokens    │
│  - Maintains backwards compatibility with legacy code               │
└─────────────────────────────────────────────────────────────────┘
```

## Backwards Compatibility

The configuration system is fully backwards compatible:

1. **Legacy Constants**: All original hardcoded constants (`_RATE_LIMITS`, `_MAX_RETRIES`, etc.) are still defined and derived from `DEFAULT_CONFIG`
2. **Existing Code**: Code that doesn't pass a `config` parameter will use `DEFAULT_CONFIG` automatically
3. **Default Behavior**: All defaults match the original hardcoded values
4. **Factory Pattern**: The factory pattern continues to work as before

### Migration Path

Existing code requires no changes. To adopt configuration:

1. **Optional**: Set environment variables for custom values
2. **Optional**: Pass custom config to `DhanHttpClient`
3. **Optional**: Use `DhanConnectionSettings` with `resilience_config` field

## Testing

Comprehensive tests are provided in `brokers/dhan/tests/test_config.py`:

- Configuration dataclass creation and validation
- Loading from environment variables
- Loading from JSON files
- Backwards compatibility checks
- Integration with DhanHttpClient

Run tests:

```bash
# Run configuration tests
pytest brokers/dhan/tests/test_config.py -v

# Run all Dhan tests
pytest brokers/dhan/tests/ -v
```

## Production Considerations

### Security

- Configuration files should have appropriate permissions (640 or 600)
- Sensitive values should use environment variables or secret management
- `.env.local` should be in `.gitignore`

### Performance

- Configuration loading happens once at startup
- Config objects are immutable and can be safely shared across threads
- No runtime overhead compared to hardcoded values

### Observability

- Configuration values are logged at startup when debug logging is enabled
- Config can be serialized to JSON for debugging
- Changes to configuration require application restart

## Files

| File | Purpose |
|------|---------|
| `brokers/dhan/config.py` | Configuration dataclasses and defaults |
| `brokers/dhan/config_loader.py` | Configuration loading from various sources |
| `brokers/dhan/settings.py` | Extended with resilience_config field |
| `brokers/dhan/http_client.py` | Updated to use config instead of hardcoded values |
| `brokers/dhan/factory.py` | Updated to load and inject configuration |
| `brokers/dhan/tests/test_config.py` | Configuration unit tests |
| `brokers/dhan/CONFIGURATION.md` | This documentation |

## Support

For issues or questions:

1. Check the test suite for usage examples
2. Review the configuration defaults in `config.py`
3. Verify environment variables are set correctly
4. Open an issue with reproduction steps
