from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from brokers.common.settings import BrokerSettings, SettingsLoaderBase

UPSTOX_PREFIX = "UPSTOX"

# ── Operational defaults (REF-4) ───────────────────────────────────────────

#: Default REST API rate limit (requests per second).
UPSTOX_DEFAULT_RATE_PER_SECOND: float = 10.0

#: WebSocket keepalive ping interval (seconds).
UPSTOX_WS_PING_INTERVAL_SECONDS: int = 20

#: WebSocket keepalive ping timeout (seconds).
UPSTOX_WS_PING_TIMEOUT_SECONDS: int = 20

#: Default on-disk instrument cache validity (hours).
UPSTOX_INSTRUMENT_CACHE_HOURS: int = 24

#: Default persisted TOTP/OAuth token state used for unattended daily auth.
UPSTOX_DEFAULT_TOKEN_STATE_FILE = Path("runtime/upstox-token-state.json")

VALID_ENVIRONMENTS = ("LIVE", "SANDBOX")
VALID_AUTH_MODES = ("STATIC", "OAUTH", "INTERACTIVE", "EXTENDED", "WEBHOOK", "TOTP")


@dataclass(frozen=True)
class UpstoxConnectionSettings(BrokerSettings):
    """Resolved Upstox connection settings.

    Mirrors Trade_J ``UpstoxConnectionSettings`` (Java record).

    Inherits common fields from :class:`BrokerSettings`:
    ``client_id``, ``access_token``, ``http_timeout``, ``enable_retry``,
    ``pool_connections``, ``pool_maxsize``.
    """

    # Upstox-specific fields
    client_secret: str = ""
    redirect_uri: str = "http://localhost:18080"
    auth_mode: str = "STATIC"
    environment: str = "LIVE"
    rest_base_url: str = ""
    refresh_token: str = ""
    extended_token: str = ""
    analytics_token: str = ""
    analytics_only: bool = False
    token_state_file: Path | None = None
    instrument_cache: Path = field(default_factory=lambda: Path(".cache/upstox/complete.json.gz"))
    refresh_buffer_minutes: int = 30
    redirect_port: int = 18080
    algo_name: str = ""
    static_ip: str = ""
    allow_live_orders: bool = False
    market_protection_default: int = -1
    slice_default: bool = False
    ws_plus_plan: bool = False
    ws_max_connections: int = 2
    ws_auto_reconnect: bool = True
    ws_reconnect_interval_s: int = 10
    ws_reconnect_max_retries: int = 5

    # TOTP-specific fields (for automated token generation)
    mobile: str = ""
    pin: str = ""
    totp_secret: str = ""
    totp_refresh_hour: int = 8  # Default: 8 AM IST
    totp_refresh_minute: int = 0

    @property
    def is_sandbox(self) -> bool:
        return self.environment.upper() == "SANDBOX"

    @property
    def is_live(self) -> bool:
        return self.environment.upper() == "LIVE"

    @property
    def is_static(self) -> bool:
        return self.auth_mode.upper() == "STATIC"

    @property
    def is_oauth(self) -> bool:
        return self.auth_mode.upper() == "OAUTH"

    @property
    def is_interactive(self) -> bool:
        return self.auth_mode.upper() == "INTERACTIVE"

    @property
    def is_extended(self) -> bool:
        return self.auth_mode.upper() == "EXTENDED"

    @property
    def is_webhook(self) -> bool:
        return self.auth_mode.upper() == "WEBHOOK"

    @property
    def is_totp(self) -> bool:
        return self.auth_mode.upper() == "TOTP"

    @property
    def has_totp_config(self) -> bool:
        """Check if all required TOTP credentials are present."""
        return bool(self.mobile and self.pin and self.totp_secret)

    @property
    def has_access_token(self) -> bool:
        return bool(self.access_token)

    @property
    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)

    @property
    def has_extended_token(self) -> bool:
        return bool(self.extended_token)

    @property
    def has_refresh(self) -> bool:
        return bool(self.refresh_token)

    @property
    def rest_base_override(self) -> str:
        return self.rest_base_url.rstrip("/") if self.rest_base_url else ""

    @property
    def instrument_cache_path(self) -> Path:
        """Alias for :attr:`instrument_cache` for older call sites."""
        return self.instrument_cache

    @property
    def base_v2(self) -> str:
        if self.rest_base_url:
            return self.rest_base_url.rstrip("/")
        if self.is_sandbox:
            return "https://sandbox-api.upstox.com"
        return "https://api.upstox.com"

    @property
    def base_hft(self) -> str:
        if self.is_sandbox:
            return "https://sandbox-api-hft.upstox.com"
        return "https://api-hft.upstox.com"


class UpstoxSettingsLoader(SettingsLoaderBase):
    """Load :class:`UpstoxConnectionSettings` from env / dotenv / .properties.

    Mirrors Trade_J ``UpstoxConnectionSettings`` env conventions.

    Inherits env var accessors and value parsers from :class:`SettingsLoaderBase`.
    Overrides :meth:`_get` to support multiple candidate env-var keys and
    legacy aliases for backward compatibility.
    """

    PREFIX = UPSTOX_PREFIX
    DEFAULT_ENV_PATHS = (Path(".env.upstox"), Path(".env.local"))

    @classmethod
    def from_env(
        cls,
        *,
        env_path: Path | None = None,
        prefix: str = PREFIX,
    ) -> UpstoxConnectionSettings:
        cls._load_default_env(env_path)

        environment = cls._get(prefix, "ENVIRONMENT", default="LIVE").upper()
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"UPSTOX_ENVIRONMENT must be one of {VALID_ENVIRONMENTS}, got {environment!r}"
            )
        is_sandbox = environment == "SANDBOX"
        client_id = (
            cls._get(prefix, "SANDBOX_CLIENT_ID")
            or cls._get(prefix, "CLIENT_ID")
            or cls._get(prefix, "client.clientId")
        )
        if not client_id:
            raise ValueError("UPSTOX_CLIENT_ID is required")

        if is_sandbox and cls._get(prefix, "SANDBOX_REST_BASE_URL"):
            rest_base_url = cls._get(prefix, "SANDBOX_REST_BASE_URL")
        else:
            rest_base_url = cls._get(prefix, "REST_BASE_URL") or ""

        auth_mode = cls._get(prefix, "AUTH_MODE", default="STATIC").upper()
        if auth_mode not in VALID_AUTH_MODES:
            raise ValueError(
                f"UPSTOX_AUTH_MODE must be one of {VALID_AUTH_MODES}, got {auth_mode!r}"
            )

        client_secret = (
            cls._get(prefix, "SANDBOX_CLIENT_SECRET") or cls._get(prefix, "CLIENT_SECRET")
        ) or ""
        access_token = (
            cls._get(prefix, "SANDBOX_ACCESS_TOKEN") or cls._get(prefix, "ACCESS_TOKEN")
        ) or ""
        refresh_token = cls._get(prefix, "REFRESH_TOKEN") or ""
        extended_token = cls._get(prefix, "EXTENDED_TOKEN") or ""
        analytics_token = cls._get(prefix, "ANALYTICS_TOKEN") or ""
        algo_name = cls._get(prefix, "ALGO_NAME") or ""
        static_ip = cls._get(prefix, "STATIC_IP") or ""
        analytics_only = cls._get_bool(prefix, "ANALYTICS_ONLY", default=False)
        allow_live_orders = cls._get_bool(prefix, "ALLOW_LIVE_ORDERS", default=False)
        ws_plus_plan = cls._get_bool(prefix, "WS_PLUS_PLAN", default=False)
        slice_default = cls._get_bool(prefix, "SLICE_DEFAULT", default=False)
        market_protection_default = cls._get_int(prefix, "MARKET_PROTECTION_DEFAULT", default=-1)
        redirect_port = cls._get_int(prefix, "REDIRECT_PORT", default=18080)
        refresh_buffer_minutes = cls._get_int(prefix, "REFRESH_BUFFER_MINUTES", default=30)

        # TOTP configuration
        from config.secrets_manager import SecretsManager

        secrets = SecretsManager()
        mobile = cls._get(prefix, "MOBILE", default="")
        pin = cls._get(prefix, "PIN", default="") or secrets.get_upstox_pin()
        totp_secret = (
            cls._get(prefix, "TOTP_SECRET", default="") or secrets.get_upstox_totp_secret()
        )
        totp_refresh_hour = cls._get_int(prefix, "TOTP_REFRESH_HOUR", default=8)
        totp_refresh_minute = cls._get_int(prefix, "TOTP_REFRESH_MINUTE", default=0)

        token_state_file_path = cls._get(prefix, "TOKEN_STATE_FILE")
        token_state_file = (
            Path(token_state_file_path)
            if token_state_file_path
            else UPSTOX_DEFAULT_TOKEN_STATE_FILE
            if auth_mode == "TOTP"
            else None
        )
        instrument_cache_str = cls._get(
            prefix, "INSTRUMENT_CACHE", default=".cache/upstox/complete.json.gz"
        )
        instrument_cache = Path(instrument_cache_str)

        return UpstoxConnectionSettings(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=cls._get(
                prefix, "REDIRECT_URI", default=f"http://localhost:{redirect_port}"
            ),
            auth_mode=auth_mode,
            environment=environment,
            rest_base_url=rest_base_url,
            access_token=access_token,
            refresh_token=refresh_token,
            extended_token=extended_token,
            analytics_token=analytics_token,
            analytics_only=analytics_only,
            token_state_file=token_state_file,
            instrument_cache=instrument_cache,
            refresh_buffer_minutes=refresh_buffer_minutes,
            redirect_port=redirect_port,
            algo_name=algo_name,
            static_ip=static_ip,
            allow_live_orders=allow_live_orders,
            market_protection_default=market_protection_default,
            slice_default=slice_default,
            ws_plus_plan=ws_plus_plan,
            mobile=mobile,
            pin=pin,
            totp_secret=totp_secret,
            totp_refresh_hour=totp_refresh_hour,
            totp_refresh_minute=totp_refresh_minute,
        )

    @classmethod
    def from_properties(cls, path: Path, *, prefix: str = "upstox") -> UpstoxConnectionSettings:
        """Load from a Trade_J-style ``upstox-live.properties`` file."""
        values = cls._read_properties(path)
        environment = (values.get("upstox.environment") or "LIVE").upper()
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"upstox.environment must be one of {VALID_ENVIRONMENTS}, got {environment!r}"
            )
        client_id = values.get(f"{prefix}.clientId")
        if not client_id:
            raise ValueError(f"{path} must contain {prefix}.clientId")

        auth_mode = (values.get(f"{prefix}.authMode") or "STATIC").upper()
        if auth_mode not in VALID_AUTH_MODES:
            raise ValueError(
                f"{prefix}.authMode must be one of {VALID_AUTH_MODES}, got {auth_mode!r}"
            )

        configured_token_state_file = cls._path_from_env(values.get(f"{prefix}.tokenStateFile"))
        if auth_mode == "TOTP":
            token_state_file = configured_token_state_file or UPSTOX_DEFAULT_TOKEN_STATE_FILE
        else:
            token_state_file = configured_token_state_file

        return UpstoxConnectionSettings(
            client_id=client_id,
            client_secret=values.get(f"{prefix}.clientSecret", ""),
            redirect_uri=values.get(f"{prefix}.redirectUri", "http://localhost:18080"),
            access_token=values.get(f"{prefix}.accessToken", ""),
            refresh_token=values.get(f"{prefix}.refreshToken", ""),
            extended_token=values.get(f"{prefix}.extendedToken", ""),
            analytics_token=values.get(f"{prefix}.analyticsToken", ""),
            analytics_only=cls._parse_bool(values.get(f"{prefix}.analyticsOnly"), False),
            auth_mode=auth_mode,
            environment=environment,
            rest_base_url=values.get(f"{prefix}.restBaseUrl", ""),
            token_state_file=token_state_file,
            instrument_cache=cls._path_from_env(
                values.get(f"{prefix}.instrumentCache"), Path(".cache/upstox/complete.json.gz")
            ),
            refresh_buffer_minutes=cls._parse_int(values.get(f"{prefix}.refreshBufferMinutes"), 30),
            redirect_port=cls._parse_int(values.get(f"{prefix}.redirectPort"), 18080),
            algo_name=values.get(f"{prefix}.algoName", ""),
            static_ip=values.get(f"{prefix}.staticIp", ""),
            allow_live_orders=cls._parse_bool(values.get(f"{prefix}.allowLiveOrders"), False),
            ws_plus_plan=cls._parse_bool(values.get(f"{prefix}.wsPlusPlan"), False),
            market_protection_default=cls._parse_int(
                values.get(f"{prefix}.marketProtectionDefault"), -1
            ),
            slice_default=cls._parse_bool(values.get(f"{prefix}.sliceDefault"), False),
            mobile=values.get(f"{prefix}.mobile", ""),
            pin=values.get(f"{prefix}.pin", ""),
            totp_secret=values.get(f"{prefix}.totpSecret", ""),
            totp_refresh_hour=cls._parse_int(values.get(f"{prefix}.totpRefreshHour"), 8),
            totp_refresh_minute=cls._parse_int(values.get(f"{prefix}.totpRefreshMinute"), 0),
        )

    @staticmethod
    def _read_properties(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        if not path.exists():
            return values
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _get(prefix: str, name: str, default: str = "") -> str:
        upper_name = name.upper()
        normalized = upper_name.replace(".", "_")
        candidates = [
            f"{prefix.upper()}_{normalized}",
            f"{prefix.upper()}.{name}",
            f"{prefix.lower()}.{name}",
        ]
        # Backward-compat fallbacks for legacy env var names.
        name_lower = name.lower()
        if name_lower == "client_id":
            candidates.insert(0, f"{prefix.upper()}_API_KEY")
        elif name_lower == "client_secret":
            candidates.insert(0, f"{prefix.upper()}_API_SECRET")
        elif name_lower == "access_token":
            candidates.insert(0, f"{prefix.upper()}_API_ACCESS_TOKEN")
        for candidate in candidates:
            value = os.environ.get(candidate)
            if value:
                return value
        return default

    @staticmethod
    def _path_from_env(value: str | None, default: Path | None = None) -> Path | None:
        if not value:
            return default
        return Path(value)
