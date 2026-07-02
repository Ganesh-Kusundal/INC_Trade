"""Tests for UpstoxApiError and UpstoxAuthError."""

from __future__ import annotations

import pytest

from brokers.common.resilience.errors import BrokerError
from brokers.upstox.auth.exceptions import UpstoxApiError, UpstoxAuthError


class TestUpstoxApiError:
    def test_basic(self):
        e = UpstoxApiError("boom", status_code=500, body={"errors": ["oops"]})
        assert e.status_code == 500
        assert e.body == {"errors": ["oops"]}
        assert "boom" in str(e)
        assert isinstance(e, BrokerError)  # UpstoxApiError extends BrokerError

    def test_default_status_code(self):
        e = UpstoxApiError("x")
        assert e.status_code is None
        assert e.body is None

    def test_repr_includes_message_and_status(self):
        e = UpstoxApiError("kaboom", status_code=429)
        r = repr(e)
        assert "UpstoxApiError" in r
        assert "kaboom" in r
        assert "429" in r


class TestUpstoxAuthError:
    def test_is_subclass(self):
        e = UpstoxAuthError("denied", status_code=401, body={"message": "x"})
        assert isinstance(e, UpstoxApiError)
        assert e.status_code == 401
        assert e.body == {"message": "x"}
        assert "denied" in str(e)

    def test_catchable_as_api_error(self):
        with pytest.raises(UpstoxApiError):
            raise UpstoxAuthError("denied")
