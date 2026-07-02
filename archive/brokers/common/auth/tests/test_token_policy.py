"""Tests for token generation policy."""

from __future__ import annotations

from datetime import datetime, timedelta

from brokers.common.auth.token import TokenSource, TokenState
from brokers.common.auth.token_policy import should_generate_token


def test_should_not_generate_when_valid():
    state = TokenState(
        access_token="valid",
        source=TokenSource.TOTP,
        expires_at=datetime.now() + timedelta(hours=2),
    )
    assert should_generate_token(state) is False


def test_should_generate_when_missing():
    assert should_generate_token(None) is True


def test_should_generate_when_expired():
    state = TokenState(
        access_token="expired",
        source=TokenSource.TOTP,
        expires_at=datetime.now() - timedelta(minutes=1),
    )
    assert should_generate_token(state) is True


def test_should_generate_on_broker_rejection_even_if_valid():
    state = TokenState(
        access_token="valid",
        source=TokenSource.TOTP,
        expires_at=datetime.now() + timedelta(hours=2),
    )
    assert should_generate_token(state, broker_rejected=True) is True


def test_proactive_refresh_disabled_by_default():
    state = TokenState(
        access_token="near_expiry",
        source=TokenSource.TOTP,
        issued_at=datetime.now() - timedelta(hours=23, minutes=55),
        expires_at=datetime.now() + timedelta(minutes=4),
    )
    assert should_generate_token(state, buffer_seconds=300) is False


def test_proactive_refresh_when_explicitly_allowed():
    state = TokenState(
        access_token="near_expiry",
        source=TokenSource.TOTP,
        issued_at=datetime.now() - timedelta(hours=23, minutes=55),
        expires_at=datetime.now() + timedelta(minutes=4),
    )
    assert should_generate_token(state, allow_proactive=True, buffer_seconds=300) is True
