"""Startup credential validation — fail early on missing secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from brokers.common.auth.credential_resolver import CredentialResolver


@dataclass(frozen=True)
class CredentialIssue:
    broker: str
    field: str
    message: str
    severity: str = "error"  # "error" | "warning"


class CredentialValidator:
    """Validate that broker credentials are present before bootstrap."""

    @staticmethod
    def validate_broker(
        broker: str,
        env_path: str | Path | None = None,
    ) -> tuple[bool, list[CredentialIssue]]:
        """Return ``(ok, issues)`` for *broker* credential readiness."""
        broker = broker.lower().strip()
        issues: list[CredentialIssue] = []

        path = CredentialResolver.resolve_env_path(broker, env_path)
        if broker == "paper":
            return True, issues

        if path is None:
            issues.append(CredentialIssue(broker, "env_file", "No env file configured", "error"))
            return False, issues

        if not path.exists():
            issues.append(
                CredentialIssue(
                    broker,
                    "env_file",
                    f"Env file missing: {path}",
                    "error",
                )
            )
            return False, issues

        # Load into os.environ for field checks (idempotent).
        CredentialResolver.load_broker_env(broker, path)

        if broker == "dhan":
            issues.extend(CredentialValidator._validate_dhan())
        elif broker == "upstox":
            issues.extend(CredentialValidator._validate_upstox())

        has_errors = any(i.severity == "error" for i in issues)
        return not has_errors, issues

    @staticmethod
    def _validate_dhan() -> list[CredentialIssue]:
        issues: list[CredentialIssue] = []
        client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
        if not client_id:
            issues.append(
                CredentialIssue(
                    "dhan",
                    "DHAN_CLIENT_ID",
                    "DHAN_CLIENT_ID is required",
                    "error",
                )
            )

        access_token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
        pin = os.environ.get("DHAN_PIN", "").strip()
        pin_file = os.environ.get("DHAN_PIN_FILE", "").strip()
        totp_secret = os.environ.get("DHAN_TOTP_SECRET", "").strip()
        totp_file = os.environ.get("DHAN_TOTP_SECRET_FILE", "").strip()

        has_pin = bool(pin) or (pin_file and Path(pin_file).exists())
        has_totp = bool(totp_secret) or (totp_file and Path(totp_file).exists())
        has_token = bool(access_token)

        if not has_token and not (has_pin and has_totp):
            issues.append(
                CredentialIssue(
                    "dhan",
                    "auth",
                    "Need DHAN_ACCESS_TOKEN or TOTP credentials (PIN + secret)",
                    "error",
                )
            )
        elif not has_token and has_pin and has_totp:
            issues.append(
                CredentialIssue(
                    "dhan",
                    "DHAN_ACCESS_TOKEN",
                    "No static token; TOTP refresh will run at bootstrap",
                    "warning",
                )
            )
        return issues

    @staticmethod
    def _validate_upstox() -> list[CredentialIssue]:
        issues: list[CredentialIssue] = []
        client_id = os.environ.get("UPSTOX_CLIENT_ID", "").strip()
        if not client_id:
            issues.append(
                CredentialIssue(
                    "upstox",
                    "UPSTOX_CLIENT_ID",
                    "UPSTOX_CLIENT_ID is required",
                    "error",
                )
            )

        access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
        analytics_token = os.environ.get("UPSTOX_ANALYTICS_TOKEN", "").strip()
        refresh_token = os.environ.get("UPSTOX_REFRESH_TOKEN", "").strip()
        mobile = os.environ.get("UPSTOX_MOBILE", "").strip()
        pin = os.environ.get("UPSTOX_PIN", "").strip()
        pin_file = os.environ.get("UPSTOX_PIN_FILE", "").strip()
        totp_secret = os.environ.get("UPSTOX_TOTP_SECRET", "").strip()
        totp_file = os.environ.get("UPSTOX_TOTP_SECRET_FILE", "").strip()
        auth_mode = os.environ.get("UPSTOX_AUTH_MODE", "STATIC").upper()

        has_pin = bool(pin) or (pin_file and Path(pin_file).exists())

        has_totp_secret = bool(totp_secret) or (totp_file and Path(totp_file).exists())

        has_static = bool(access_token) or bool(analytics_token) or bool(refresh_token)
        has_totp = bool(mobile and has_pin and has_totp_secret)

        if auth_mode == "TOTP" and not has_totp and not has_static:
            issues.append(
                CredentialIssue(
                    "upstox",
                    "totp",
                    "TOTP mode requires UPSTOX_MOBILE, UPSTOX_PIN, UPSTOX_TOTP_SECRET "
                    "(or PIN/TOTP secret files)",
                    "error",
                )
            )
        elif not has_static and not has_totp:
            issues.append(
                CredentialIssue(
                    "upstox",
                    "auth",
                    "Need UPSTOX_ACCESS_TOKEN, UPSTOX_ANALYTICS_TOKEN, refresh token, or TOTP creds",
                    "error",
                )
            )
        return issues

    @staticmethod
    def broker_available(
        broker: str,
        env_path: str | Path | None = None,
    ) -> bool:
        """``True`` when credential validation passes (no errors)."""
        ok, _ = CredentialValidator.validate_broker(broker, env_path)
        return ok
