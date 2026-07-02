"""Typed bootstrap results — replace silent ``None`` gateway returns."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BootstrapStatus(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    FAILED = "failed"


@dataclass(frozen=True)
class BootstrapResult:
    """Outcome of broker gateway construction + readiness probes."""

    status: BootstrapStatus
    broker: str
    gateway: Any | None = None
    error: str | None = None
    probe_passed: bool = False
    authenticated: bool = False
    probe_name: str | None = None
    refreshed_token: bool = False

    @property
    def ok(self) -> bool:
        return self.status == BootstrapStatus.READY and self.gateway is not None

    @property
    def live_ready(self) -> bool:
        """True when gateway is ready and authenticated probe passed."""
        return self.ok and self.authenticated


def structural_readiness_probe(gateway: Any, broker: str) -> tuple[bool, str | None]:
    """Lightweight structural check — token present on connection object.

    Does not call broker APIs; verifies the factory wired auth state.
    """
    broker = broker.lower().strip()
    try:
        if broker == "dhan":
            conn = getattr(gateway, "_conn", None)
            if conn is None:
                return False, "gateway missing _conn"
            token = getattr(conn, "access_token", None)
            client = getattr(conn, "_client", None) or getattr(conn, "client", None)
            if not token and client is not None:
                token = getattr(client, "access_token", None)
            if not token:
                auth = getattr(conn, "_auth", None)
                state = getattr(auth, "_state", None) if auth else None
                if state and getattr(state, "access_token", None):
                    token = state.access_token
            if not token:
                return False, "no access token on Dhan connection"
            return True, None

        if broker == "upstox":
            broker_obj = getattr(gateway, "_broker", None)
            if broker_obj is None:
                return False, "gateway missing _broker"
            tm = getattr(broker_obj, "token_manager", None)
            if tm is not None:
                token = tm.current_token()
                if token and token != "placeholder-totp-will-refresh":
                    return True, None
                return False, "Upstox token manager has no valid token"
            settings = getattr(broker_obj, "settings", None)
            if settings and (
                getattr(settings, "access_token", None)
                or getattr(settings, "analytics_token", None)
            ):
                return True, None
            return False, "no Upstox token in settings or manager"

        if broker == "paper":
            return True, None
    except Exception as exc:
        return False, str(exc)
    return True, None


def classify_exception(exc: BaseException) -> BootstrapStatus:
    """Map exceptions to bootstrap status."""
    name = type(exc).__name__
    module = type(exc).__module__ or ""
    if "Auth" in name or "Configuration" in name or "credential" in str(exc).lower():
        return BootstrapStatus.REAUTH_REQUIRED
    if "ProductionReadiness" in name:
        return BootstrapStatus.FAILED
    if module.startswith("brokers.") and ("auth" in module or "config" in module):
        return BootstrapStatus.REAUTH_REQUIRED
    return BootstrapStatus.FAILED
