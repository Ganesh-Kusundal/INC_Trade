"""Authenticated broker readiness probes — real API calls before live trading."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brokers.common.auth.credential_resolver import CredentialResolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthProbeResult:
    """Outcome of an authenticated readiness probe."""

    ok: bool
    probe_name: str | None = None
    error: str | None = None
    token_rejected: bool = False
    refreshed_token: bool = False


def is_token_rejection(exc: BaseException) -> bool:
    """Return True when *exc* indicates broker rejected the access token."""
    name = type(exc).__name__
    if name in ("AuthenticationError", "UpstoxAuthError"):
        return True
    msg = str(exc).lower()
    if "401" in msg or "403" in msg:
        return True
    if "dh-906" in msg or "dh-808" in msg:
        return True
    if "invalid token" in msg or "token rejected" in msg:
        return True
    return bool("unauthorized" in msg or "forbidden" in msg)


def execute_read_only_probe(gateway: Any, broker: str) -> AuthProbeResult:
    """Perform a single read-only authenticated API call."""
    broker = broker.lower().strip()
    if broker == "paper":
        return AuthProbeResult(ok=True, probe_name="paper_skip")

    if broker == "dhan":
        return _probe_dhan(gateway)
    if broker == "upstox":
        return _probe_upstox(gateway)

    return AuthProbeResult(ok=False, error=f"unsupported broker: {broker}")


def authenticated_readiness_probe(
    gateway: Any,
    broker: str,
    env_path: str | Path | None = None,
) -> AuthProbeResult:
    """Probe broker API auth; on token rejection force one refresh and retry."""
    broker = broker.lower().strip()
    if broker == "paper":
        return AuthProbeResult(ok=True, probe_name="paper_skip")

    first = execute_read_only_probe(gateway, broker)
    if first.ok:
        return first

    if not first.token_rejected and not is_token_rejection_from_result(first):
        return first

    logger.info(
        "authenticated_probe_token_rejected",
        extra={"broker": broker, "probe": first.probe_name},
    )
    refreshed = _force_token_refresh(gateway, broker, env_path=env_path)
    if not refreshed:
        return AuthProbeResult(
            ok=False,
            probe_name=first.probe_name,
            error=first.error or "token rejected and refresh failed",
            token_rejected=True,
            refreshed_token=False,
        )

    second = execute_read_only_probe(gateway, broker)
    if second.ok:
        return AuthProbeResult(
            ok=True,
            probe_name=second.probe_name,
            token_rejected=True,
            refreshed_token=True,
        )
    return AuthProbeResult(
        ok=False,
        probe_name=second.probe_name,
        error=second.error or "authenticated probe failed after token refresh",
        token_rejected=True,
        refreshed_token=True,
    )


def is_token_rejection_from_result(result: AuthProbeResult) -> bool:
    return result.token_rejected


def _probe_dhan(gateway: Any) -> AuthProbeResult:
    probe_name = "dhan.funds"
    try:
        gateway.funds()
        return AuthProbeResult(ok=True, probe_name=probe_name)
    except Exception as exc:
        rejected = is_token_rejection(exc)
        return AuthProbeResult(
            ok=False,
            probe_name=probe_name,
            error=str(exc),
            token_rejected=rejected,
        )


def _probe_upstox(gateway: Any) -> AuthProbeResult:
    broker_obj = getattr(gateway, "_broker", None)
    probe_name = "upstox.profile"

    if broker_obj is not None:
        tm = getattr(broker_obj, "token_manager", None)
        if tm is not None and hasattr(tm, "oauth_client"):
            try:
                token = tm.bearer_token()
                if not token:
                    return AuthProbeResult(
                        ok=False,
                        probe_name=probe_name,
                        error="Upstox bearer token is empty",
                        token_rejected=True,
                    )
                exp_ms = tm.oauth_client.fetch_profile(token)
                now_ms = int(time.time() * 1000)
                if exp_ms > now_ms:
                    return AuthProbeResult(ok=True, probe_name=probe_name)
                if exp_ms > 0:
                    return AuthProbeResult(
                        ok=False,
                        probe_name=probe_name,
                        error="Upstox token expired (profile token_expiry in past)",
                        token_rejected=True,
                    )
                # fetch_profile returned -1 (401/unavailable) — fall through to funds()
            except Exception as exc:
                rejected = is_token_rejection(exc)
                return AuthProbeResult(
                    ok=False,
                    probe_name=probe_name,
                    error=str(exc),
                    token_rejected=rejected,
                )

    probe_name = "upstox.funds"
    try:
        gateway.funds()
        return AuthProbeResult(ok=True, probe_name=probe_name)
    except Exception as exc:
        rejected = is_token_rejection(exc)
        return AuthProbeResult(
            ok=False,
            probe_name=probe_name,
            error=str(exc),
            token_rejected=rejected,
        )


def _force_token_refresh(
    gateway: Any,
    broker: str,
    env_path: str | Path | None = None,
) -> bool:
    broker = broker.lower().strip()
    if broker == "dhan":
        return _force_dhan_token_refresh(gateway, env_path=env_path)
    if broker == "upstox":
        return _force_upstox_token_refresh(gateway)
    return False


def _resolve_dhan_env_path(env_path: str | Path | None) -> Path:
    resolved = CredentialResolver.resolve_env_path("dhan", env_path)
    return resolved if resolved is not None else Path(".env.local")


def _force_dhan_token_refresh(
    gateway: Any,
    env_path: str | Path | None = None,
) -> bool:
    conn = getattr(gateway, "_conn", None)
    if conn is None:
        return False
    auth = getattr(conn, "_auth", None)
    client = getattr(conn, "_client", None)
    if auth is None:
        return False
    try:
        state = auth.force_refresh()
        if not state or not state.access_token:
            return False
        if client is not None:
            client.update_token(state.access_token)
        if hasattr(conn, "broadcast_token"):
            conn.broadcast_token(state.access_token)
        try:
            from brokers.common.auth import JsonTokenStateStore
            from brokers.common.auth.token_persistence import TokenPersistence

            dhan_env = _resolve_dhan_env_path(env_path)
            store = JsonTokenStateStore(Path("runtime/dhan-token-state.json"))
            TokenPersistence.save(state, store, dhan_env)
        except Exception as exc:
            logger.debug("dhan_env_token_update_skipped: %s", exc)
        return True
    except Exception as exc:
        logger.warning("dhan_force_token_refresh_failed: %s", exc)
        return False


def _force_upstox_token_refresh(gateway: Any) -> bool:
    broker_obj = getattr(gateway, "_broker", None)
    if broker_obj is None:
        return False
    tm = getattr(broker_obj, "token_manager", None)
    if tm is None:
        return False
    settings = getattr(tm, "settings", None) or getattr(broker_obj, "settings", None)
    try:
        if settings is not None and getattr(settings, "is_totp", False):
            tm.refresh_totp()
        elif settings is not None and getattr(settings, "has_refresh", False):
            tm.force_refresh()
        else:
            return False
        return bool(tm.current_token())
    except Exception as exc:
        logger.warning("upstox_force_token_refresh_failed: %s", exc)
        return False
