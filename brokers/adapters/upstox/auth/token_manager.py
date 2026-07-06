"""Upstox OAuth 2.0 token lifecycle manager.

Full PKCE flow, refresh-token grant, proactive refresh using
``refresh_buffer_minutes``, JSON state persistence, and a webhook upgrade path.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from brokers.infrastructure.jwt_expiry import parse_jwt_expiry as _parse_jwt
from brokers.infrastructure.storage.token_store import (
    JsonTokenStateStore,
    TokenSource,
    TokenState,
)
from brokers.config.endpoints import Upstox

from .exceptions import UpstoxAuthError
from .holders import (
    ThreadSafeTokenHolder,
    TokenSnapshot,
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)
from .oauth_client import UpstoxOAuthClient
from .pkce import PkcePair, UpstoxPkceUtil
from .token_expiry import UpstoxTokenExpiry
from .totp_client import UpstoxTotpClient

logger = logging.getLogger(__name__)

_REFRESH_WAIT_SECONDS = 30.0


def _parse_expiry_epoch_ms(token: str) -> int:
    exp = _parse_jwt(token)
    if exp is None:
        return -1
    return int(exp.timestamp() * 1000)


class UpstoxTokenManager:
    """Upstox token lifecycle: bootstrap, refresh, persist, upgrade-from-webhook.

    Modes:

    * **STATIC** — fixed access token, no refresh, no 3:30 AM IST fallback.
    * **OAUTH** — bootstrap from configured access+refresh, then refresh proactively.
    * **EXTENDED** — 1-year read-only token, no refresh.
    * **WEBHOOK** — daily token delivered via Upstox notifier URL.
    * **INTERACTIVE** — run PKCE browser flow once at startup.
    * **TOTP** — automated daily TOTP generation.
    """

    def __init__(
        self,
        settings: Any,
        oauth_client: UpstoxOAuthClient | None = None,
        state_store: JsonTokenStateStore | None = None,
        refresh_lock: threading.Lock | None = None,
    ) -> None:
        self._settings = settings
        base_v2 = getattr(settings, "base_v2", Upstox.PROD_V2)
        self._oauth_client = oauth_client or UpstoxOAuthClient(base_url=base_v2)
        self._state_store = state_store or (
            JsonTokenStateStore(Path(getattr(settings, "token_state_file", "")))
            if getattr(settings, "token_state_file", None)
            else None
        )
        self._lock = threading.RLock()
        self._refresh_lock = refresh_lock or threading.Lock()
        self._refresh_done = threading.Event()
        self._refresh_done.set()
        self._state: TokenSnapshot | None = None
        self._holder: ThreadSafeTokenHolder = ThreadSafeTokenHolder(
            self._build_initial_holder()
        )

    def _build_initial_holder(self) -> UpstoxTokenHolder:
        s = self._settings
        if getattr(s, "analytics_only", False):
            return UpstoxAnalyticsTokenHolder(
                getattr(s, "analytics_token", "") or getattr(s, "access_token", "")
            )
        if getattr(s, "is_extended", False) and getattr(s, "extended_token", ""):
            return UpstoxExtendedTokenHolder(s.extended_token)
        if getattr(s, "is_totp", False):
            return UpstoxStaticTokenHolder("placeholder-totp-will-refresh")
        if getattr(s, "is_static", False) or (
            getattr(s, "access_token", "") and not getattr(s, "refresh_token", "")
        ):
            if not getattr(s, "access_token", ""):
                return UpstoxStaticTokenHolder("placeholder-no-token")
            return UpstoxStaticTokenHolder(
                s.access_token, analytics_only=False, label="Upstox access token"
            )
        if getattr(s, "access_token", "") and getattr(s, "refresh_token", ""):
            return UpstoxStaticTokenHolder(
                s.access_token,
                analytics_only=False,
                label="Upstox access token (bootstrapped from refresh)",
            )
        return UpstoxStaticTokenHolder("placeholder-no-token")

    @property
    def settings(self) -> Any:
        return self._settings

    @property
    def oauth_client(self) -> UpstoxOAuthClient:
        return self._oauth_client

    @property
    def state_store(self) -> JsonTokenStateStore | None:
        return self._state_store

    def get_holder(self) -> UpstoxTokenHolder:
        return self._holder

    def bearer_token(self) -> str:
        self.ensure_valid()
        with self._lock:
            return self._holder.bearer_token()

    def current_token(self) -> str | None:
        with self._lock:
            return self._holder.bearer_token() if self._holder else None

    def current_state(self) -> TokenSnapshot | None:
        with self._lock:
            return self._state

    def ensure_valid(self) -> None:
        if getattr(self._settings, "analytics_only", False):
            return
        if getattr(self._settings, "is_extended", False) and getattr(
            self._settings, "extended_token", ""
        ):
            return
        if not self._needs_proactive_refresh():
            return
        if getattr(self._settings, "is_totp", False):
            self._run_exclusive_refresh(self._do_totp_force_refresh)
            return
        with self._lock:
            if self._state and self._state.refresh_token:
                logger.info(
                    "Upstox token at/near expiry; refreshing proactively (expiry=%d)",
                    self._effective_expiry_ms(),
                )
        self._run_exclusive_refresh(self._do_oauth_refresh)

    def try_refresh_on_401(self) -> bool:
        if getattr(self._settings, "analytics_only", False):
            return False
        try:
            if getattr(self._settings, "is_totp", False):
                self._run_exclusive_refresh(self._do_totp_refresh)
            elif self._state and self._state.refresh_token:
                self._run_exclusive_refresh(self._do_oauth_refresh)
            else:
                return False
            return bool(self.current_token())
        except Exception as exc:
            logger.warning("Upstox token refresh on 401 failed: %s", exc)
            return False

    def force_refresh(self) -> TokenSnapshot | None:
        if getattr(self._settings, "is_totp", False):
            return self._run_exclusive_refresh(self._do_totp_force_refresh)
        with self._lock:
            if not self._state or not self._state.refresh_token:
                raise UpstoxAuthError(
                    "Cannot force_refresh: no refresh token available"
                )
        return self._run_exclusive_refresh(self._do_oauth_refresh)

    def refresh_totp(self) -> TokenSnapshot:
        result = self._run_exclusive_refresh(self._do_totp_force_refresh)
        if result is None:
            raise UpstoxAuthError("TOTP refresh did not produce a token")
        return result

    def bootstrap(self) -> TokenSnapshot:
        with self._lock:
            if getattr(self._settings, "is_totp", False):
                return self._bootstrap_totp_if_needed()

            if self._state_store is not None:
                persisted = self._state_store.load()
                if persisted and self._valid_persisted(persisted):
                    self._state = self._from_persisted(persisted)
                    self._holder.replace(
                        UpstoxStaticTokenHolder(
                            self._state.access_token,
                            analytics_only=False,
                            label="Upstox token (persisted)",
                        )
                    )
                    return self._state
            return self._acquire_initial()

    def perform_interactive_oauth(
        self,
        pkce_pair: PkcePair | None = None,
        redirect_uri: str | None = None,
        browser_opener: Callable[..., None] | None = None,
    ) -> PkcePair:
        pkce = pkce_pair or UpstoxPkceUtil.generate()
        redirect = redirect_uri or self._settings.redirect_uri
        params = {
            "client_id": self._settings.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": pkce.code_challenge,
        }
        base_v2 = getattr(self._settings, "base_v2", Upstox.PROD_V2)
        auth_url = f"{base_v2}/v2/login/authorization/dialog?{urlencode(params)}"
        if browser_opener is not None:
            try:
                browser_opener(auth_url)
            except Exception:
                logger.info("Could not open browser automatically; copy URL manually")
        return pkce

    def complete_interactive_oauth(
        self, code: str, pkce_pair: PkcePair, redirect_uri: str | None = None
    ) -> TokenSnapshot:
        resp = self._oauth_client.exchange_code(
            code=code,
            client_id=self._settings.client_id,
            client_secret=self._settings.client_secret,
            redirect_uri=redirect_uri or self._settings.redirect_uri,
            code_verifier=pkce_pair.code_verifier,
        )
        new_state = TokenSnapshot(
            access_token=resp.access_token,
            refresh_token=resp.refresh_token,
            expires_at_ms=int(time.time() * 1000) + resp.expires_in_seconds * 1000,
            issued_at_ms=resp.issued_at_ms,
            source="OAUTH",
        )
        with self._lock:
            self._state = new_state
            self._holder.replace(
                UpstoxStaticTokenHolder(
                    new_state.access_token,
                    analytics_only=False,
                    label="Upstox token (interactive)",
                )
            )
            self._persist(new_state)
        return new_state

    def upgrade_from_webhook(self, access_token: str, expires_at_ms: int) -> bool:
        if not access_token or not access_token.strip():
            raise ValueError("accessToken must not be blank")
        if expires_at_ms <= 0:
            raise ValueError("expiresAtMs must be positive")
        with self._lock:
            current = self._state
            now_ms = int(time.time() * 1000)
            should_replace = (
                current is None
                or current.expires_at_ms <= now_ms
                or expires_at_ms > current.expires_at_ms
            )
            if not should_replace:
                logger.debug(
                    "upgrade_from_webhook skipped — incoming expiry %d <= current %d",
                    expires_at_ms,
                    current.expires_at_ms if current else 0,
                )
                return False
            preserved_refresh = current.refresh_token if current else None
            new_state = TokenSnapshot(
                access_token=access_token,
                refresh_token=preserved_refresh,
                expires_at_ms=expires_at_ms,
                issued_at_ms=now_ms,
                source="WEBHOOK",
            )
            self._state = new_state
            self._holder.replace(
                UpstoxStaticTokenHolder(
                    access_token,
                    analytics_only=False,
                    label="Upstox token (webhook)",
                )
            )
            self._persist(new_state)
            logger.info(
                "Upstox token upgraded via webhook; expiresAt=%d", expires_at_ms
            )
            return True

    def invalidate(self, access_token: str | None = None) -> bool:
        with self._lock:
            current = self._state
            if current is None:
                return True
            if access_token and access_token != current.access_token:
                logger.debug(
                    "invalidate ignored — current token does not match supplied access_token"
                )
                return False
            now_ms = int(time.time() * 1000)
            return not (current.expires_at_ms and current.expires_at_ms > now_ms)

    @classmethod
    def create_extended(cls, extended_token: str) -> UpstoxExtendedTokenHolder:
        return UpstoxExtendedTokenHolder(extended_token)

    @classmethod
    def create_analytics(cls, analytics_token: str) -> UpstoxAnalyticsTokenHolder:
        return UpstoxAnalyticsTokenHolder(analytics_token)

    @classmethod
    def create_static(cls, access_token: str) -> UpstoxStaticTokenHolder:
        return UpstoxStaticTokenHolder(access_token)

    def _needs_proactive_refresh(self) -> bool:
        now_ms = int(time.time() * 1000)
        exp_ms = self._effective_expiry_ms()
        if exp_ms <= 0:
            return getattr(self._settings, "is_totp", False)
        buffer_ms = (
            int(getattr(self._settings, "refresh_buffer_minutes", 30) or 30) * 60 * 1000
        )
        return now_ms >= exp_ms - buffer_ms

    def _effective_expiry_ms(self) -> int:
        with self._lock:
            if self._state and self._state.expires_at_ms:
                return int(self._state.expires_at_ms)
            exp = self._holder.expiry_epoch_ms()
            if exp > 0:
                return int(exp)
            token = self._holder.bearer_token() if self._holder else None
        if token:
            return _parse_expiry_epoch_ms(token)
        return 0

    def _run_exclusive_refresh(
        self,
        action: Callable[[], TokenSnapshot],
    ) -> TokenSnapshot | None:
        with self._refresh_lock:
            if self._refresh_done.is_set():
                self._refresh_done.clear()
                leader = True
            else:
                leader = False
        if leader:
            try:
                return action()
            finally:
                self._refresh_done.set()
        if not self._refresh_done.wait(timeout=_REFRESH_WAIT_SECONDS):
            logger.warning("Timed out waiting for in-flight Upstox token refresh")
        with self._lock:
            return self._state

    def _do_totp_refresh(self) -> TokenSnapshot:
        return self._bootstrap_totp_if_needed()

    def _do_totp_force_refresh(self) -> TokenSnapshot:
        return self._bootstrap_totp()

    def _do_oauth_refresh(self) -> TokenSnapshot:
        self._refresh_now()
        with self._lock:
            if self._state is None:
                raise UpstoxAuthError("OAuth refresh completed without state")
            return self._state

    def _apply_token_state(self, state: TokenSnapshot, *, label: str) -> TokenSnapshot:
        with self._lock:
            self._state = state
            self._holder.replace(
                UpstoxStaticTokenHolder(
                    state.access_token,
                    analytics_only=False,
                    label=label,
                )
            )
            self._persist(state)
        return state

    def _bootstrap_totp_if_needed(self) -> TokenSnapshot:
        with self._lock:
            if self._state and self._valid_snapshot(self._state):
                logger.debug("Upstox TOTP refresh: reusing in-memory valid token")
                return self._state
        if self._state_store is not None:
            persisted = self._state_store.load()
            if persisted and self._valid_persisted(persisted):
                self._state = self._from_persisted(persisted)
                self._holder.replace(
                    UpstoxStaticTokenHolder(
                        self._state.access_token,
                        analytics_only=False,
                        label="Upstox token (persisted TOTP)",
                    )
                )
                logger.debug("Upstox TOTP bootstrap: reusing persisted token")
                return self._state
        return self._bootstrap_totp()

    def _acquire_initial(self) -> TokenSnapshot:
        s = self._settings
        if getattr(s, "access_token", ""):
            if getattr(s, "refresh_token", ""):
                exp = self._oauth_client.fetch_profile(s.access_token)
                if exp <= 0:
                    exp = _parse_expiry_epoch_ms(s.access_token)
                if exp <= 0:
                    exp = UpstoxTokenExpiry.next_expiry_epoch_ms()
                state = TokenSnapshot(
                    access_token=s.access_token,
                    refresh_token=s.refresh_token,
                    expires_at_ms=exp,
                    issued_at_ms=int(time.time() * 1000),
                    source="OAUTH",
                )
                self._state = state
                self._holder.replace(
                    UpstoxStaticTokenHolder(
                        s.access_token,
                        analytics_only=False,
                        label="Upstox token (bootstrap)",
                    )
                )
                self._persist(state)
                return state
            jwt_exp = _parse_expiry_epoch_ms(s.access_token)
            exp = jwt_exp if jwt_exp > 0 else UpstoxTokenExpiry.next_expiry_epoch_ms()
            state = TokenSnapshot(
                access_token=s.access_token,
                refresh_token=None,
                expires_at_ms=exp,
                issued_at_ms=int(time.time() * 1000),
                source="STATIC",
            )
            self._state = state
            self._holder.replace(
                UpstoxStaticTokenHolder(
                    s.access_token, analytics_only=False, label="Upstox token"
                )
            )
            self._persist(state)
            return state
        raise UpstoxAuthError(
            "No Upstox access token available. Paste UPSTOX_ACCESS_TOKEN in env or run "
            "perform_interactive_oauth()."
        )

    def _refresh_now(self) -> None:
        state = self._state
        if state is None or not state.refresh_token:
            raise UpstoxAuthError("Cannot refresh token: no refresh token available")
        resp = self._oauth_client.refresh_token(
            refresh_token=state.refresh_token,
            client_id=self._settings.client_id,
            client_secret=self._settings.client_secret,
        )
        new_state = TokenSnapshot(
            access_token=resp.access_token,
            refresh_token=resp.refresh_token,
            expires_at_ms=int(time.time() * 1000) + resp.expires_in_seconds * 1000,
            issued_at_ms=resp.issued_at_ms,
            source="OAUTH",
        )
        self._state = new_state
        self._holder.replace(
            UpstoxStaticTokenHolder(
                new_state.access_token,
                analytics_only=False,
                label="Upstox token (refreshed)",
            )
        )
        self._persist(new_state)

    def _persist(self, state: TokenSnapshot) -> None:
        if self._state_store is None:
            return
        try:
            from datetime import datetime
            issued = datetime.fromtimestamp(state.issued_at_ms / 1000, tz=UTC) if state.issued_at_ms else None
            expires = datetime.fromtimestamp(state.expires_at_ms / 1000, tz=UTC) if state.expires_at_ms else None

            ts = TokenState(
                access_token=state.access_token,
                refresh_token=state.refresh_token,
                issued_at=issued,
                expires_at=expires,
                source=TokenSource.OAUTH,
            )
            self._state_store.save(ts)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Failed to persist Upstox token state: %s", exc)

    def _valid_persisted(self, persisted: Any) -> bool:
        if not getattr(persisted, "access_token", None):
            return False
        if getattr(persisted, "expires_at", None) is None:
            return False
        return bool(persisted.is_valid())

    def _valid_snapshot(self, state: TokenSnapshot) -> bool:
        if not state.access_token:
            return False
        exp = int(state.expires_at_ms or 0)
        if exp <= 0:
            return False
        return exp > int(time.time() * 1000)

    def _from_persisted(self, persisted: Any) -> TokenSnapshot:
        return TokenSnapshot(
            access_token=persisted.access_token,
            refresh_token=persisted.refresh_token,
            expires_at_ms=int(persisted.expires_at.timestamp() * 1000) if persisted.expires_at else 0,
            issued_at_ms=int(persisted.issued_at.timestamp() * 1000) if persisted.issued_at else 0,
            source=persisted.source.value if getattr(persisted, "source", None) else "OAUTH",
        )

    def _bootstrap_totp(self) -> TokenSnapshot:
        try:
            logger.info("Attempting TOTP token generation...")
            totp_client = UpstoxTotpClient(self._settings)

            if not totp_client.validate_config():
                raise UpstoxAuthError(
                    "TOTP configuration incomplete. Set UPSTOX_MOBILE, UPSTOX_PIN, "
                    "and UPSTOX_TOTP_SECRET environment variables."
                )

            result = totp_client.generate_token()
            access_token = result["access_token"]

            exp = _parse_expiry_epoch_ms(access_token)
            if exp <= 0:
                exp = UpstoxTokenExpiry.next_expiry_epoch_ms()

            state = TokenSnapshot(
                access_token=access_token,
                refresh_token=None,
                expires_at_ms=exp,
                issued_at_ms=int(time.time() * 1000),
                source="TOTP",
            )

            self._apply_token_state(state, label="Upstox token (TOTP)")
            logger.info("TOTP token bootstrap successful, expires at: %d", exp)
            return state

        except Exception as exc:
            logger.warning("TOTP bootstrap failed: %s", exc)
            if getattr(self._settings, "refresh_token", ""):
                logger.info("Falling back to refresh-token mechanism")
                return self._acquire_initial()
            raise UpstoxAuthError(
                f"TOTP authentication failed and no fallback available: {exc}"
            ) from exc
