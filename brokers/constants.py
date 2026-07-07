"""Centralised constants for the broker SDK.

All cross-cutting default values live here — timeouts, tick sizes,
WebSocket parameters, broker identifiers, and token-scheduler tuning.

Zero dependencies on the rest of the SDK (only stdlib + Decimal).
Values are public (no underscore prefix) and should be imported directly::

    from brokers.constants import DEFAULT_HTTP_TIMEOUT

When adding a new constant, ensure it is genuinely shared (used in
>= 2 places) or serves as the canonical default for a common parameter.
"""

from decimal import Decimal

# ── HTTP / network defaults ────────────────────────────────────────────
DEFAULT_HTTP_TIMEOUT: float = 15.0
DEFAULT_HTTP_MAX_RETRIES: int = 3
DEFAULT_BASE_DELAY_MS: int = 500
DEFAULT_MAX_DELAY_MS: int = 5000
REFRESH_COOLDOWN_SECONDS: float = 60.0
CIRCUIT_BREAKER_RESET_TIMEOUT: float = 30.0
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5

# ── Financial defaults ─────────────────────────────────────────────────
DEFAULT_TICK_SIZE: Decimal = Decimal("0.05")
DEFAULT_LOT_SIZE: int = 1

# ── WebSocket defaults ─────────────────────────────────────────────────
WS_PING_INTERVAL: int = 20
WS_PING_TIMEOUT: int = 10
WS_CLOSE_TIMEOUT: int = 5

# ── Token-scheduler defaults ───────────────────────────────────────────
TOKEN_MIN_CHECK_INTERVAL: int = 30
TOKEN_MAX_BACKOFF: int = 600          # 10 minutes
TOKEN_INITIAL_BACKOFF: int = 120      # 2 minutes
TOKEN_DEFAULT_CHECK_INTERVAL: int = 60
TOKEN_DEFAULT_REFRESH_BUFFER: float = 300.0

# ── TOTP defaults ──────────────────────────────────────────────────────
TOTP_TIME_STEP: int = 30

# ── Broker identifiers (canonical strings) ─────────────────────────────
BROKER_DHAN: str = "dhan"
BROKER_UPSTOX: str = "upstox"
BROKER_PAPER: str = "paper"

__all__ = [
    "BROKER_DHAN",
    "BROKER_UPSTOX",
    "BROKER_PAPER",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_RESET_TIMEOUT",
    "DEFAULT_BASE_DELAY_MS",
    "DEFAULT_HTTP_MAX_RETRIES",
    "DEFAULT_HTTP_TIMEOUT",
    "DEFAULT_LOT_SIZE",
    "DEFAULT_MAX_DELAY_MS",
    "DEFAULT_TICK_SIZE",
    "REFRESH_COOLDOWN_SECONDS",
    "TOKEN_DEFAULT_CHECK_INTERVAL",
    "TOKEN_DEFAULT_REFRESH_BUFFER",
    "TOKEN_INITIAL_BACKOFF",
    "TOKEN_MAX_BACKOFF",
    "TOKEN_MIN_CHECK_INTERVAL",
    "TOTP_TIME_STEP",
    "WS_CLOSE_TIMEOUT",
    "WS_PING_INTERVAL",
    "WS_PING_TIMEOUT",
]
