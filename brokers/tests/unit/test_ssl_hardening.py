"""Tests for SSL hardening."""

from __future__ import annotations

import ssl

from inc_trade.infrastructure.ssl_hardening import (
    HardenedHTTPSAdapter,
    create_pinned_session,
    hardened_ssl_context,
)


class TestHardenedSSLContext:
    def test_minimum_tls_1_2(self):
        ctx = hardened_ssl_context()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_no_compression(self):
        ctx = hardened_ssl_context()
        assert ctx.options & ssl.OP_NO_COMPRESSION

    def test_no_renegotiation(self):
        ctx = hardened_ssl_context()
        assert ctx.options & ssl.OP_NO_RENEGOTIATION

    def test_returns_ssl_context(self):
        ctx = hardened_ssl_context()
        assert isinstance(ctx, ssl.SSLContext)


class TestCreatePinnedSession:
    def test_returns_session(self):
        import requests

        session = create_pinned_session()
        assert isinstance(session, requests.Session)
        session.close()

    def test_has_https_adapter(self):
        session = create_pinned_session()
        adapter = session.get_adapter("https://example.com")
        assert isinstance(adapter, HardenedHTTPSAdapter)
        session.close()

    def test_no_http_adapter(self):
        session = create_pinned_session()
        adapter = session.get_adapter("http://example.com")
        assert not isinstance(adapter, HardenedHTTPSAdapter)
        session.close()
