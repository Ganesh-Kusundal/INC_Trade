"""Canonical token load/save with env reconciliation."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from brokers.common.auth.jwt_expiry import JwtExpiry
from brokers.common.auth.token import TokenSource, TokenState, TokenStateStore

logger = logging.getLogger(__name__)


def token_state_from_access_token(
    access_token: str,
    *,
    source: TokenSource = TokenSource.STATIC,
    fallback_expires_at: datetime | None = None,
) -> TokenState:
    """Build TokenState using JWT ``exp`` when available."""
    issued_at = datetime.now()
    expires_at = JwtExpiry.parse_expiry_datetime(access_token)
    if expires_at is None:
        expires_at = fallback_expires_at
    return TokenState(
        access_token=access_token,
        source=source,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def _normalize_token_state(state: TokenState | None) -> TokenState | None:
    if state is None:
        return None
    from datetime import timezone

    issued = state.issued_at
    expires = state.expires_at
    if issued is not None and issued.tzinfo is not None:
        issued = issued.astimezone(timezone.utc).replace(tzinfo=None)
    if expires is not None and expires.tzinfo is not None:
        expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
    if issued is state.issued_at and expires is state.expires_at:
        return state
    return TokenState(
        access_token=state.access_token,
        refresh_token=state.refresh_token,
        issued_at=issued,
        expires_at=expires,
        source=state.source,
    )


def _expiry_score(token: str, state: TokenState | None) -> float:
    jwt_exp = JwtExpiry.parse_expiry_epoch_ms(token)
    if jwt_exp > 0:
        return float(jwt_exp)
    if state and state.expires_at:
        return state.expires_at.timestamp()
    return 0.0


class TokenPersistence:
    """Load canonical token state and persist with optional env mirror."""

    @staticmethod
    def load_canonical(
        store: TokenStateStore,
        env_token: str | None = None,
        *,
        fallback_expires_at: datetime | None = None,
    ) -> TokenState | None:
        """Load from JSON store; reconcile with env token if present."""
        stored = _normalize_token_state(store.load())
        env_token = (env_token or "").strip()

        if not env_token and stored is None:
            return None

        if not env_token:
            if stored and stored.access_token:
                return _enrich_expiry(stored, fallback_expires_at)
            return stored

        if stored is None or not stored.access_token:
            return token_state_from_access_token(
                env_token,
                source=TokenSource.STATIC,
                fallback_expires_at=fallback_expires_at,
            )

        if env_token == stored.access_token:
            return _enrich_expiry(stored, fallback_expires_at)

        env_score = _expiry_score(env_token, None)
        store_score = _expiry_score(stored.access_token, stored)
        if env_score >= store_score:
            logger.debug("token_persistence: preferring env token over store")
            return token_state_from_access_token(
                env_token,
                source=stored.source,
                fallback_expires_at=fallback_expires_at,
            )
        return _enrich_expiry(stored, fallback_expires_at)

    @staticmethod
    def save(
        state: TokenState,
        store: TokenStateStore,
        env_path: Path | None = None,
        *,
        env_key: str = "DHAN_ACCESS_TOKEN",
    ) -> None:
        """Write JSON store first, then mirror to env file if configured."""
        enriched = _enrich_expiry(state, state.expires_at)
        store.save(enriched)
        if env_path is not None and env_path.exists() and enriched.access_token:
            if env_key == "DHAN_ACCESS_TOKEN":
                from brokers.common.auth.env_token import update_env_token

                update_env_token(env_path, enriched.access_token, env_key=env_key)
            else:
                logger.debug("token_persistence: no env mirror for key %s", env_key)


def _enrich_expiry(
    state: TokenState,
    fallback_expires_at: datetime | None,
) -> TokenState:
    """Ensure expires_at is set from JWT when missing."""
    if state.expires_at is not None:
        return state
    jwt_exp = JwtExpiry.parse_expiry_datetime(state.access_token)
    if jwt_exp is None and fallback_expires_at is None:
        return state
    return TokenState(
        access_token=state.access_token,
        refresh_token=state.refresh_token,
        issued_at=state.issued_at or datetime.now(),
        expires_at=jwt_exp or fallback_expires_at,
        source=state.source,
    )
