"""Tests for :mod:`brokers.common.ssl_hardening` (REF-38).

These tests run against the in-process objects — no network calls.
The goal is to validate the hardening policy, not to assert that
certificates chain to a real CA.
"""

from __future__ import annotations

import ssl

import pytest
import requests

from brokers.common.ssl_hardening import (
    HardenedHTTPSAdapter,
    assert_secure_session,
    create_pinned_session,
    hardened_ssl_context,
)

# ---------- context-level tests ----------


class TestHardenedSslContext:
    def test_returns_ssl_context(self):
        ctx = hardened_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_minimum_tls_version_is_1_2(self):
        ctx = hardened_ssl_context()
        # ``TLSVersion`` enum values are ordered by integer value in
        # Python 3.10+. We compare the underlying numeric to be
        # portable across minor versions.
        assert int(ctx.minimum_version) >= int(ssl.TLSVersion.TLSv1_2)

    def test_disables_compression(self):
        ctx = hardened_ssl_context()
        assert ctx.options & ssl.OP_NO_COMPRESSION

    def test_requires_certificate_verification(self):
        ctx = hardened_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_check_hostname_enabled(self):
        ctx = hardened_ssl_context()
        assert ctx.check_hostname is True


# ---------- session-level tests ----------


class TestCreatePinnedSession:
    def test_returns_requests_session(self):
        session = create_pinned_session()
        assert isinstance(session, requests.Session)

    def test_https_adapter_is_hardened(self):
        session = create_pinned_session()
        adapter = session.get_adapter("https://example.invalid/")
        assert isinstance(adapter, HardenedHTTPSAdapter)

    def test_verify_is_true(self):
        session = create_pinned_session()
        assert session.verify is True


# ---------- guard tests ----------


class TestAssertSecureSession:
    def test_passes_for_pinned_session(self):
        assert_secure_session(create_pinned_session())

    def test_raises_when_verify_false(self):
        session = requests.Session()
        session.verify = False
        with pytest.raises(RuntimeError, match="insecure session: verify"):
            assert_secure_session(session)

    def test_raises_when_https_adapter_not_hardened(self):
        session = requests.Session()
        # Default adapter is not HardenedHTTPSAdapter.
        with pytest.raises(RuntimeError, match="HardenedHTTPSAdapter"):
            assert_secure_session(session)


class TestHardenedHTTPSAdapter:
    def test_init_poolmanager_passes_hardened_ssl_context(self):
        # Run the real ``init_poolmanager`` and inspect the
        # ``poolmanager`` attribute it sets. The hardened context is
        # passed as ``ssl_context`` to the underlying ``PoolManager``,
        # which stores it on ``connection_pool_kw`` and re-uses it
        # for every connection in the pool.
        adapter = HardenedHTTPSAdapter()
        adapter.init_poolmanager(connections=2, maxsize=2)
        pm = adapter.poolmanager
        # The connection-pool kw dict is private to urllib3 but
        # accessible via ``connection_pool_kw`` on the PoolManager.
        pool_kw = getattr(pm, "connection_pool_kw", {})
        assert "ssl_context" in pool_kw, (
            f"expected ssl_context in connection_pool_kw, got {pool_kw!r}"
        )
        assert isinstance(pool_kw["ssl_context"], ssl.SSLContext)
