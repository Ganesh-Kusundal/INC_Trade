"""``python -m brokers.upstox.auth.login`` — interactive Upstox OAuth flow.

Mirrors Trade_J ``UpstoxOAuthTokenIntegrationTest`` flow:

1. Read settings (UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI).
2. Generate PKCE pair.
3. Start local redirect server.
4. Print auth URL and open the browser.
5. Capture code from the callback.
6. Exchange code for access+refresh tokens.
7. Persist to UPSTOX_TOKEN_STATE_FILE (default ``.upstox-token.json``).
8. Print completion message (tokens NEVER printed to stdout for security).

Usage::

    UPSTOX_CLIENT_ID=xxx UPSTOX_CLIENT_SECRET=yyy \\
        python -m brokers.upstox.auth.login

The script intentionally avoids importing the trade_xv2 ``Broker`` stack so it
can be run as a stand-alone pre-step (e.g. in a CI container).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

from .config import UpstoxConnectionSettings, UpstoxSettingsLoader
from .pkce import PkcePair, UpstoxPkceUtil
from .redirect_server import UpstoxRedirectServer

logger = logging.getLogger("brokers.upstox.auth.login")


def _parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run interactive Upstox OAuth PKCE flow.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to a .env file with UPSTOX_* variables (optional).",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=None,
        help="Override UPSTOX_TOKEN_STATE_FILE for this run.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open the browser; print the URL only.",
    )
    # --print-tokens removed for security: tokens should never be printed to stdout
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Seconds to wait for the OAuth callback.",
    )
    return parser.parse_args(argv)


def build_auth_url(
    settings: UpstoxConnectionSettings,
    code_challenge: str,
    state: str | None = None,
) -> str:
    """Build the Upstox authorization dialog URL for the given PKCE challenge."""
    params: dict[str, str] = {
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    if state:
        params["state"] = state
    from urllib.parse import urlencode

    base = "https://sandbox-api.upstox.com" if settings.is_sandbox else "https://api.upstox.com"
    return f"{base}/v2/login/authorization/dialog?{urlencode(params)}"


def _open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        print("(Could not open browser automatically; copy the URL manually.)")


async def _capture_code(
    settings: UpstoxConnectionSettings,
    timeout: float,
    open_browser: bool,
) -> str:
    pkce = UpstoxPkceUtil.generate()
    auth_url = build_auth_url(settings, pkce.code_challenge, state=None)
    if open_browser:
        _open_browser(auth_url)
    server = UpstoxRedirectServer(settings, path=_redirect_path(settings.redirect_uri))
    try:
        return await server.capture_code(timeout=timeout)
    finally:
        await server.stop()


def _redirect_path(redirect_uri: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(redirect_uri)
    return parsed.path or "/"


def perform_login(
    settings: UpstoxConnectionSettings,
    pkce_pair: PkcePair | None = None,
    *,
    timeout: float = 300.0,
    open_browser: bool = True,
) -> Any:
    """End-to-end login: run PKCE, capture code, exchange tokens.

    Returns a mapping like ``{"access_token": ..., "refresh_token": ...}``.
    Mock-friendly — tests can replace this with a fake response.
    """
    code = asyncio.run(_capture_code(settings, timeout=timeout, open_browser=open_browser))
    pkce = pkce_pair or UpstoxPkceUtil.generate()
    from .oauth_client import UpstoxOAuthClient

    oauth = UpstoxOAuthClient(base_url=settings.base_v2)
    resp = oauth.exchange_code(
        code=code,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        redirect_uri=settings.redirect_uri,
        code_verifier=pkce.code_verifier,
    )
    return {
        "access_token": resp.access_token,
        "refresh_token": resp.refresh_token,
        "expires_in_seconds": resp.expires_in_seconds,
        "issued_at_ms": resp.issued_at_ms,
    }


def _persist_state(settings: UpstoxConnectionSettings, result: dict) -> None:
    if not settings.token_state_file:
        return
    settings.token_state_file.parent.mkdir(parents=True, exist_ok=True)
    expires_at_ms = int(time.time() * 1000) + int(result.get("expires_in_seconds", 86400)) * 1000
    state = {
        "access_token": result.get("access_token", ""),
        "refresh_token": result.get("refresh_token"),
        "expires_at_ms": expires_at_ms,
        "issued_at_ms": int(result.get("issued_at_ms", int(time.time() * 1000))),
        "source": "OAUTH",
    }
    settings.token_state_file.write_text(json.dumps(state, indent=2))
    # Set file permissions to owner-only read/write (0o600)
    try:
        os.chmod(settings.token_state_file, 0o600)
    except OSError as exc:
        logger.warning(
            "token_file_permissions_failed",
            extra={"file": str(settings.token_state_file), "error": str(exc)},
        )
    logger.info("token_state_persisted", extra={"file": str(settings.token_state_file)})


def main(argv: list | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    args = _parse_args(argv)
    # Logging already initialized by cli/main.py configure_logging()
    # If run standalone, initialize here
    if not logging.getLogger().handlers:
        from infrastructure.logging_config import configure_logging

        configure_logging()

    try:
        settings = UpstoxSettingsLoader.from_env(env_path=args.env_file)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.state_file is not None:
        settings = UpstoxConnectionSettings(
            **{**settings.__dict__, "token_state_file": args.state_file}
        )

    if not settings.client_secret:
        print(
            "ERROR: UPSTOX_CLIENT_SECRET is required for the OAuth flow. "
            "Set it in env or in --env-file.",
            file=sys.stderr,
        )
        return 2

    print("=" * 72)
    print("Upstox OAuth PKCE flow")
    print("=" * 72)
    print(f"Environment : {settings.environment}")
    print(f"Client ID   : {settings.client_id}")
    print(f"Redirect URI: {settings.redirect_uri}")
    print()

    try:
        result = perform_login(
            settings,
            timeout=args.timeout,
            open_browser=not args.no_browser,
        )
    except KeyboardInterrupt:
        print("Aborted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.exception("OAuth flow failed: %s", exc)
        return 1

    _persist_state(settings, result)

    # Tokens are written to file only - never printed to stdout for security
    logger.info("authorization_complete", extra={"token_file": str(settings.token_state_file)})
    print()
    print("Authorization complete. Tokens persisted to secure file.")
    print(f"Token file: {settings.token_state_file}")
    print("Re-running this broker is now token-less.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
