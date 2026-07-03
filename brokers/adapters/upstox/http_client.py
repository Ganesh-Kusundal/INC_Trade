"""Upstox HTTP client factory and response mapping."""

from typing import Any, Callable
import requests
from brokers.infrastructure.http.resilient_client import ResilientHttpClient, TokenRefreshSignal
from brokers.adapters.upstox.config import RATE_LIMITS, READ_PREFIXES, WRITE_PREFIXES
from brokers.domain.exceptions import AuthenticationError, RateLimitError, BrokerServerError, BrokerError

def _upstox_categorize(endpoint: str) -> str:
    for prefix in READ_PREFIXES:
        if endpoint.startswith(prefix):
            return "read"
    for prefix in WRITE_PREFIXES:
        if endpoint.startswith(prefix):
            return "write"
    return "admin"

def _upstox_handle_response(resp: requests.Response) -> dict[str, Any]:
    if resp.status_code in (401, 403):
        raise TokenRefreshSignal("Token expired or invalid")
    if resp.status_code == 429:
        raise RateLimitError("Rate limit exceeded", retry_after=30.0)
    if resp.status_code >= 500:
        try:
            body = resp.json()
            errors = body.get("errors", [])
            msg = errors[0].get("message", resp.text) if errors else resp.text
        except Exception:
            msg = resp.text
        raise BrokerServerError(f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code))
    if resp.status_code >= 400:
        try:
            body = resp.json()
            errors = body.get("errors", [])
            msg = errors[0].get("message", resp.text) if errors else resp.text
        except Exception:
            msg = resp.text
        raise BrokerError(f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code))
    try:
        return resp.json()  # type: ignore[no-any-return]
    except Exception:
        return {"data": resp.text}

def create_upstox_http_client(
    access_token: str,
    token_refresh_fn: Callable[[], str | None] | None = None,
    base_url_v2: str = "",
    base_url_hft: str = "",
) -> ResilientHttpClient:
    base_v2 = base_url_v2 or "https://api.upstox.com"
    base_hft = base_url_hft or "https://api-hft.upstox.com"
    
    def _build_url(endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        if "/v3/" in endpoint:
            return f"{base_hft}{endpoint}"
        return f"{base_v2}{endpoint}"
        
    client = ResilientHttpClient(
        rate_limits=RATE_LIMITS,
        categorize_fn=_upstox_categorize,
        url_builder_fn=_build_url,
        response_handler_fn=_upstox_handle_response,
        token_refresh_fn=token_refresh_fn,
    )
    client.session.headers.update({
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    return client
