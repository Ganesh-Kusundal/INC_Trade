"""Tests for shared JWT expiry parsing."""

from __future__ import annotations

import jwt as pyjwt

from brokers.common.auth.jwt_expiry import JwtExpiry


def test_jwt_expiry_parses_exp_claim():
    exp = 1_700_000_000
    token = pyjwt.encode({"exp": exp}, "secret", algorithm="HS256")
    ms = JwtExpiry.parse_expiry_epoch_ms(token)
    assert abs(ms - exp * 1000) < 1000


def test_jwt_expiry_returns_minus_one_for_invalid_token():
    assert JwtExpiry.parse_expiry_epoch_ms("not.a.jwt") == -1
    assert JwtExpiry.parse_expiry_epoch_ms("") == -1
    assert JwtExpiry.parse_expiry_epoch_ms(None) == -1


def test_jwt_expiry_without_exp_claim():
    token = pyjwt.encode({"sub": "x"}, "secret", algorithm="HS256")
    assert JwtExpiry.parse_expiry_epoch_ms(token) == -1
