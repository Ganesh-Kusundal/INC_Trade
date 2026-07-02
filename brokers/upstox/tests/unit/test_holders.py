from __future__ import annotations

import pytest

from brokers.upstox.auth.holders import (
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)


def test_static_holder_rejects_blank():
    with pytest.raises(ValueError):
        UpstoxStaticTokenHolder("")
    with pytest.raises(ValueError):
        UpstoxStaticTokenHolder("   ")


def test_static_holder_returns_token_and_expiry():
    h = UpstoxStaticTokenHolder("opaque-non-jwt-token")
    assert h.bearer_token() == "opaque-non-jwt-token"
    assert h.expiry_epoch_ms() > 0
    assert h.analytics_only() is False


def test_analytics_holder_rejects_blank():
    with pytest.raises(ValueError):
        UpstoxAnalyticsTokenHolder("")


def test_analytics_holder_always_read_only():
    h = UpstoxAnalyticsTokenHolder("opaque-token")
    assert h.analytics_only() is True


def test_extended_holder_rejects_blank():
    with pytest.raises(ValueError):
        UpstoxExtendedTokenHolder("")


def test_extended_holder_always_read_only():
    h = UpstoxExtendedTokenHolder("opaque-token")
    assert h.analytics_only() is True


def test_abstract_holder_default_bearer_token_raises():
    with pytest.raises(NotImplementedError):
        UpstoxTokenHolder().bearer_token()
