"""Tests for UpstoxAdapterContext."""

from __future__ import annotations

from brokers.common.resilience.retry import RetryExecutor
from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.context import UpstoxAdapterContext
from brokers.upstox.auth.http import UpstoxHttpClient
from brokers.upstox.auth.oauth_client import UpstoxOAuthClient
from brokers.upstox.auth.token_manager import UpstoxTokenManager
from brokers.upstox.auth.urls import UpstoxApiUrlResolver


def _settings() -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="cid",
        client_secret="sec",
        access_token="abc",
        auth_mode="STATIC",
        environment="LIVE",
        algo_name="alpha",
    )


class TestUpstoxAdapterContext:
    def test_basic_wiring(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        assert ctx.settings is s
        assert ctx.token_provider() == "abc"
        assert isinstance(ctx.url_resolver, UpstoxApiUrlResolver)
        assert isinstance(ctx.http_client, UpstoxHttpClient)
        assert isinstance(ctx.oauth_client, UpstoxOAuthClient)
        assert isinstance(ctx.token_manager, UpstoxTokenManager)

    def test_make_retry_executor_orders(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        r = ctx.make_retry_executor("orders")
        assert isinstance(r, RetryExecutor)

    def test_make_retry_executor_quotes(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        r = ctx.make_retry_executor("quotes")
        assert isinstance(r, RetryExecutor)

    def test_make_retry_executor_data(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        r = ctx.make_retry_executor("data")
        assert isinstance(r, RetryExecutor)

    def test_make_retry_executor_default(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        r = ctx.make_retry_executor("unknown-category")
        assert isinstance(r, RetryExecutor)

    def test_http_client_uses_settings_algo(self):
        s = _settings()
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc")
        assert ctx.http_client.settings.algo_name == "alpha"

    def test_custom_token_manager_passthrough(self):
        s = _settings()
        m = UpstoxTokenManager(s)
        ctx = UpstoxAdapterContext(settings=s, token_provider=lambda: "abc", token_manager=m)
        assert ctx.token_manager is m
