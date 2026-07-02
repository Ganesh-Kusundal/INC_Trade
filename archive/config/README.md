# TradeXV2 Configuration Guide

Complete documentation for the TradeXV2 configuration system including environment variables, feature flags, environment profiles, and troubleshooting.

## Table of Contents

- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
  - [Required Variables](#required-variables)
  - [Optional Variables](#optional-variables)
  - [Broker-Specific Variables](#broker-specific-variables)
  - [Trading Runtime Variables](#trading-runtime-variables)
- [Feature Flags](#feature-flags)
- [Environment Profiles](#environment-profiles)
- [Secret Encryption](#secret-encryption)
- [Startup Validation](#startup-validation)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

1. Copy the example environment file:
   ```bash
   cp .env.example .env.local
   ```

2. Edit `.env.local` and set required variables:
   ```bash
   DHAN_CLIENT_ID=your_client_id
   DHAN_ACCESS_TOKEN=your_access_token
   ```

3. Set your environment profile (optional, defaults to `dev`):
   ```bash
   export APP_ENV=prod
   ```

4. Start the application - configuration is validated automatically at startup.

---

## Environment Variables

### Required Variables

These variables **must** be set for the application to start (in `prod` and `staging` profiles):

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `DHAN_CLIENT_ID` | string | - | Dhan broker client ID | `1106251237` |
| `DHAN_ACCESS_TOKEN` | string | - | Dhan broker access token (JWT) | `eyJ0eXAiOiJKV1Qi...` |

**Conditional Required:**

| Variable | Condition | Description |
|----------|-----------|-------------|
| `UPSTOX_API_KEY` | Required when `TRADEX_PRIMARY_BROKER=upstox` | Upstox API key |

### Optional Variables

These variables have sensible defaults and can be omitted:

| Variable | Type | Default | Description | Example |
|----------|------|---------|-------------|---------|
| `XV2_LOG_LEVEL` | string | `INFO` | Application log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | `DEBUG` |
| `API_HOST` | string | `127.0.0.1` | API server bind address | `0.0.0.0` |
| `API_PORT` | integer | `8000` | API server port (1-65535) | `8080` |
| `DB_PATH` | string | `runtime/tradexv2.db` | Database file path | `/var/lib/tradexv2/db.sqlite` |
| `CACHE_TTL` | integer | `300` | Default cache TTL in seconds | `600` |
| `APP_ENV` | string | `dev` | Environment profile (dev, staging, prod) | `prod` |
| `AUTH_MODE` | string | `none` | API authentication mode (none, api_key) | `api_key` |
| `API_KEY` | string | - | API key when AUTH_MODE=api_key | `your-api-key` |
| `SECRET_ENCRYPTION_KEY` | string | - | Fernet encryption key for token state files | `gAAAAAB...` |

### Broker-Specific Variables

#### Dhan Broker

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DHAN_CLIENT_ID` | **Yes** | - | Dhan client ID |
| `DHAN_ACCESS_TOKEN` | **Yes** | - | Dhan access token |
| `DHAN_ENVIRONMENT` | No | `LIVE` | Environment (LIVE or SANDBOX) |
| `DHAN_REST_BASE_URL` | No | - | Custom REST API base URL |
| `DHAN_PIN` | No | - | Dhan account PIN |
| `DHAN_TOTP_SECRET` | No | - | TOTP secret for automated login |
| `DHAN_TOKEN_STATE_FILE` | No | `runtime/dhan-token-state.json` | Token state file path |
| `DHAN_REFRESH_BUFFER_MINUTES` | No | `10` | Token refresh buffer in minutes |
| `DHAN_ALLOW_LIVE_ORDERS` | No | `0` | Allow live orders (0=blocked, 1=allowed) |
| `DHAN_SANDBOX_CLIENT_ID` | No | - | Sandbox client ID |
| `DHAN_SANDBOX_ACCESS_TOKEN` | No | - | Sandbox access token |
| `DHAN_SANDBOX_ENVIRONMENT` | No | `SANDBOX` | Sandbox environment |
| `DHAN_SANDBOX_REST_BASE_URL` | No | `https://sandbox.dhan.co/v2` | Sandbox REST URL |

#### Upstox Broker

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `UPSTOX_CLIENT_ID` | No | - | Upstox client ID |
| `UPSTOX_CLIENT_SECRET` | No | - | Upstox client secret |
| `UPSTOX_ACCESS_TOKEN` | No | - | Upstox access token |
| `UPSTOX_ANALYTICS_TOKEN` | No | - | Upstox analytics token |
| `UPSTOX_ENVIRONMENT` | No | `LIVE` | Environment (LIVE or SANDBOX) |
| `UPSTOX_AUTH_MODE` | No | `STATIC` | Auth mode (STATIC or TOTP) |
| `UPSTOX_REDIRECT_URI` | No | `http://127.0.0.1:18080/callback` | OAuth redirect URI |
| `UPSTOX_TOKEN_STATE_FILE` | No | `runtime/upstox-token-state.json` | Token state file path |
| `UPSTOX_ANALYTICS_ONLY` | No | `0` | Analytics-only mode (0=full, 1=read-only) |
| `UPSTOX_ALLOW_LIVE_ORDERS` | No | `0` | Allow live orders (0=blocked, 1=allowed) |
| `UPSTOX_MOBILE` | No | - | Mobile number for TOTP auth |
| `UPSTOX_PIN` | No | - | Upstox account PIN |
| `UPSTOX_TOTP_SECRET` | No | - | TOTP secret for automated login |
| `UPSTOX_TOTP_REFRESH_HOUR` | No | `8` | TOTP refresh hour (24h format) |
| `UPSTOX_TOTP_REFRESH_MINUTE` | No | `0` | TOTP refresh minute |

### Trading Runtime Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ORCHESTRATOR_DRY_RUN` | boolean | `1` | Run orchestrator in dry-run mode |
| `ORCHESTRATOR_MIN_CONFIDENCE` | float | `0.7` | Minimum confidence for trades (0.0-1.0) |
| `ENABLE_INTELLIGENT_GATEWAY` | boolean | `0` | Enable intelligent gateway |
| `SKIP_PARITY_GATE` | boolean | `0` | Skip parity gate checks |
| `TRADEX_SMART_ROUTING` | boolean | `true` | Enable smart broker routing |
| `TRADEX_PRIMARY_BROKER` | string | `dhan` | Primary broker (dhan or upstox) |

---

## Feature Flags

Feature flags control experimental features. All flags default to `False` (opt-in model).

| Flag | Env Variable | Default | Description |
|------|--------------|---------|-------------|
| `SMART_ROUTING` | `FEATURE_SMART_ROUTING` | `False` | Enable intelligent broker routing for automatic broker selection |
| `INTELLIGENT_GATEWAY` | `FEATURE_INTELLIGENT_GATEWAY` | `False` | Enable intelligent gateway for advanced order routing |
| `ADVANCED_ORDER_TYPES` | `FEATURE_ADVANCED_ORDER_TYPES` | `False` | Enable advanced order types (bracket, cover, etc.) |
| `EXPERIMENTAL_STRATEGIES` | `FEATURE_EXPERIMENTAL_STRATEGIES` | `False` | Enable experimental trading strategies |

### Usage

```python
from config.feature_flags import FeatureFlags

# Type-safe access
if FeatureFlags.SMART_ROUTING:
    # Use smart routing logic
    route_order_smartly()

# Check flag dynamically
if FeatureFlags.is_enabled("INTELLIGENT_GATEWAY"):
    # Use intelligent gateway
    pass

# Runtime toggle (admin endpoints)
FeatureFlags.set_flag("SMART_ROUTING", True)
```

### Setting Flags

Add to `.env.local`:
```bash
FEATURE_SMART_ROUTING=true
FEATURE_INTELLIGENT_GATEWAY=false
```

---

## Environment Profiles

Profiles control validation strictness and feature availability. Set via `APP_ENV` environment variable.

### Profile Comparison

| Setting | `dev` | `staging` | `prod` |
|---------|-------|-----------|--------|
| **Log Level** | DEBUG | INFO | WARNING |
| **Debug Endpoints** | ✅ Enabled | ✅ Enabled | ❌ Disabled |
| **Mock Brokers** | ✅ Allowed | ❌ Blocked | ❌ Blocked |
| **Validation** | Relaxed | Strict | Maximum |
| **Live Orders** | ❌ Blocked | ❌ Blocked | ❌ Blocked |
| **Encryption** | Optional | Required | Required |
| **API Auth** | Optional | Required | Required |
| **Rate Limiting** | Disabled | 120 req/min | 60 req/min |
| **CORS Origins** | localhost only | staging + localhost | production only |
| **Observability** | Disabled | Enabled | Enabled |

### Development Profile (`dev`)

- **Default profile** if `APP_ENV` is not set
- Relaxed validation (missing tokens allowed)
- Verbose DEBUG logging
- Mock brokers and sandbox mode allowed
- All debug endpoints enabled
- No encryption required

```bash
export APP_ENV=dev
```

### Staging Profile (`staging`)

- Strict validation (all required vars must be set)
- INFO level logging
- Real brokers only (no mocks)
- Debug endpoints enabled for testing
- Encryption required for token state files
- API authentication required
- Rate limiting enabled (120 req/min)

```bash
export APP_ENV=staging
```

### Production Profile (`prod`)

- **Maximum strictness**
- WARNING level logging (reduce noise)
- Real brokers only
- No debug endpoints
- Encryption required
- API authentication required
- Strict rate limiting (60 req/min)
- Production CORS origins only

```bash
export APP_ENV=prod
```

---

## Secret Encryption

Token state files can be encrypted at rest using Fernet symmetric encryption.

### Setup

1. Generate an encryption key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Set the environment variable:
   ```bash
   export SECRET_ENCRYPTION_KEY="gAAAAAB..."
   ```

3. Token state files are now automatically encrypted when saved.

### Backward Compatibility

- Existing unencrypted token files are still readable (with a warning)
- Encryption is **opt-in** - if `SECRET_ENCRYPTION_KEY` is not set, files remain unencrypted
- In `prod` and `staging` profiles, encryption is required

### Token Rotation

```python
from infrastructure.security.secret_manager import EncryptedTokenStore

store = EncryptedTokenStore("runtime/dhan-token-state.json")

# Rotate token
store.rotate_token(new_token_state)
```

---

## Startup Validation

Configuration is validated automatically at application startup before any broker connections are established.

### Validation Behavior by Profile

**Dev Profile:**
- Only `DHAN_CLIENT_ID` is strictly required
- Missing tokens generate warnings, not errors
- Allows empty values for testing

**Staging/Prod Profiles:**
- All required variables must be set
- Value constraints enforced (port ranges, log levels, etc.)
- Fail-fast on misconfiguration

### Example Validation Errors

```
Configuration validation failed with 2 error(s):
  - Missing required env var: DHAN_ACCESS_TOKEN
  - API_PORT must be between 1 and 65535, got 99999
```

### Validation Rules

| Variable | Rule | Error Message |
|----------|------|---------------|
| `API_PORT` | Must be 1-65535 | "API_PORT must be between 1 and 65535" |
| `XV2_LOG_LEVEL` | Must be valid log level | "XV2_LOG_LEVEL must be one of {...}" |
| `CACHE_TTL` | Must be non-negative integer | "CACHE_TTL must be non-negative" |
| `DHAN_ALLOW_LIVE_ORDERS` (prod) | Must be 0 or 1 | "DHAN_ALLOW_LIVE_ORDERS must be 0 or 1" |

---

## Troubleshooting

### Common Issues

#### "Missing required env var: DHAN_ACCESS_TOKEN"

**Cause:** Required environment variable not set.

**Solution:**
```bash
# Check if set
echo $DHAN_ACCESS_TOKEN

# Set in .env.local
DHAN_ACCESS_TOKEN=your_token_here

# Or export directly
export DHAN_ACCESS_TOKEN=your_token_here
```

#### "API_PORT must be between 1 and 65535"

**Cause:** Invalid port number in configuration.

**Solution:**
```bash
# Set valid port
export API_PORT=8000
```

#### "SECRET_ENCRYPTION_KEY not set"

**Cause:** Encryption key missing (warning in prod/staging).

**Solution:**
```bash
# Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set in environment
export SECRET_ENCRYPTION_KEY="generated_key_here"
```

#### "Unknown APP_ENV 'xyz'"

**Cause:** Invalid environment profile name.

**Solution:** Use one of: `dev`, `staging`, `prod`
```bash
export APP_ENV=dev
```

#### Token state file is encrypted but encryption is not enabled

**Cause:** Token file was encrypted but `SECRET_ENCRYPTION_KEY` is not set.

**Solution:**
```bash
# Set the encryption key that was used to encrypt the file
export SECRET_ENCRYPTION_KEY="original_key_here"
```

### Debug Mode

Enable verbose logging to diagnose configuration issues:

```bash
export XV2_LOG_LEVEL=DEBUG
export APP_ENV=dev
```

### Validate Configuration Manually

```python
from config.validator import ConfigValidator, ValidationProfile

# Validate with specific profile
validator = ConfigValidator(profile=ValidationProfile.PROD)
result = validator.validate()

if not result.valid:
    print("Errors:", result.errors)
    print("Warnings:", result.warnings)
else:
    print("Configuration is valid!")
```

### Check Feature Flags

```python
from config.feature_flags import FeatureFlags

# Print all flags
print(FeatureFlags.get_all_flags())

# Get flag info
print(FeatureFlags.get_flag_info("SMART_ROUTING"))
```

### Check Environment Profile

```python
from config.profiles import load_profile

profile = load_profile()
print(f"Profile: {profile.name}")
print(f"Debug enabled: {profile.debug_enabled}")
print(f"Strict validation: {profile.strict_validation}")
```

---

## Security Best Practices

1. **Never commit `.env.local`** - It's in `.gitignore` for a reason
2. **Use strong encryption keys** - Generate with `Fernet.generate_key()`
3. **Rotate tokens regularly** - Use `rotate_token()` method
4. **Enable API auth in production** - Set `AUTH_MODE=api_key`
5. **Use environment profiles** - Set `APP_ENV=prod` for production
6. **Monitor logs** - Check for encryption warnings
7. **Limit CORS origins** - Restrict to known domains in production

---

## Migration Guide

### From Previous Versions

If you're upgrading from a version without configuration validation:

1. **Add missing variables** to `.env.local`:
   ```bash
   # Add these if missing
   APP_ENV=dev
   XV2_LOG_LEVEL=INFO
   ```

2. **Test with dev profile first**:
   ```bash
   export APP_ENV=dev
   python -m api_server
   ```

3. **Gradually enable features** via feature flags:
   ```bash
   FEATURE_SMART_ROUTING=true
   ```

4. **Enable encryption** (optional but recommended):
   ```bash
   export SECRET_ENCRYPTION_KEY="your_key_here"
   ```

---

## Support

For issues or questions:
- Check this documentation
- Review validation error messages
- Enable DEBUG logging
- Consult the troubleshooting section above
