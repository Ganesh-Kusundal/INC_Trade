from __future__ import annotations

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.urls import UpstoxApiUrlResolver


def _settings(env: str = "LIVE", rest_base_url: str = "") -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="x",
        client_secret="y",
        redirect_uri="http://localhost:18080/callback",
        environment=env,
        rest_base_url=rest_base_url,
    )


def test_resolver_uses_hft_for_order_place_in_live():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.place_order_v3_url() == "https://api-hft.upstox.com/v3/order/place"


def test_resolver_uses_hft_for_modify_and_cancel_in_live():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.modify_order_v3_url() == "https://api-hft.upstox.com/v3/order/modify"
    assert r.cancel_order_v3_url() == "https://api-hft.upstox.com/v3/order/cancel"


def test_resolver_uses_sandbox_for_order_place():
    r = UpstoxApiUrlResolver(_settings("SANDBOX"))
    assert r.place_order_v3_url() == "https://sandbox-api-hft.upstox.com/v3/order/place"
    assert r.profile_url() == "https://sandbox-api.upstox.com/v2/user/profile"


def test_resolver_honours_explicit_base_url_override():
    r = UpstoxApiUrlResolver(_settings("LIVE", rest_base_url="https://proxy.local"))
    assert r.place_order_v3_url() == "https://api-hft.upstox.com/v3/order/place"
    assert r.profile_url() == "https://proxy.local/v2/user/profile"


def test_resolver_known_quote_endpoints():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.market_quote_ltp_url() == "https://api.upstox.com/v2/market-quote/ltp"
    assert r.market_quote_full_url() == "https://api.upstox.com/v2/market-quote/quotes"
    assert r.market_quote_ohlc_url() == "https://api.upstox.com/v2/market-quote/ohlc"


def test_resolver_market_intelligence_endpoints():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.oi_url() == "https://api.upstox.com/v2/market/oi"
    assert r.max_pain_url() == "https://api.upstox.com/v2/market/max-pain"
    assert r.pcr_url() == "https://api.upstox.com/v2/market/pcr"
    assert r.fii_url() == "https://api.upstox.com/v2/market/fii"
    assert r.dii_url() == "https://api.upstox.com/v2/market/dii"


def test_resolver_user_risk_endpoints():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.kill_switch_url() == "https://api.upstox.com/v2/user/kill-switch"
    assert r.static_ip_url() == "https://api.upstox.com/v2/user/ip"


def test_resolver_gtt_endpoints_use_hft():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.gtt_place_url() == "https://api-hft.upstox.com/v3/order/gtt/place"
    assert r.gtt_modify_url() == "https://api-hft.upstox.com/v3/order/gtt/modify"


def test_resolver_websocket_authorize_endpoints():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert (
        r.feed_authorize_v3_url() == "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    )
    assert (
        r.portfolio_stream_authorize_url()
        == "https://api.upstox.com/v2/feed/portfolio-stream-feed/authorize"
    )


def test_resolver_auth_endpoints():
    r = UpstoxApiUrlResolver(_settings("LIVE"))
    assert r.auth_dialog_url() == "https://api.upstox.com/v2/login/authorization/dialog"
    assert r.auth_token_url() == "https://api.upstox.com/v2/login/authorization/token"
    assert r.token_request_v3_url("CID") == "https://api.upstox.com/v3/login/auth/token/request/CID"
