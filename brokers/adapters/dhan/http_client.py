"""Dhan HTTP client factory and response mapping."""

import urllib.parse
from typing import Any, Callable

import requests

from brokers.adapters.dhan.config import ENDPOINTS, RATE_LIMITS, READ_PREFIXES, WRITE_PREFIXES
from brokers.domain.exceptions import BrokerError, BrokerServerError, RateLimitError
from brokers.infrastructure.http.resilient_client import ResilientHttpClient, TokenRefreshSignal


def _dhan_categorize(endpoint: str) -> str:
    path = urllib.parse.urlparse(endpoint).path
    for prefix in READ_PREFIXES:
        if path.startswith(prefix):
            return "read"
    for prefix in WRITE_PREFIXES:
        if path.startswith(prefix):
            return "write"
    return "admin"


def _is_token_error(status_code: int, error_code: str, message: str) -> bool:
    if status_code == 401:
        return True
    if error_code in {"DH-906", "DH-808"}:
        return True
    if "invalid token" in message.lower():
        return True
    return False


def _parse_retry_after(resp: requests.Response) -> float:
    try:
        val = resp.headers.get("Retry-After")
        if val is not None:
            return max(0.01, float(val))
    except (ValueError, TypeError):
        pass
    return 30.0


def _dhan_handle_response(resp: requests.Response) -> dict[str, Any]:
    if resp.status_code == 401:
        raise TokenRefreshSignal("Token expired or invalid")

    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp)
        raise RateLimitError("Rate limit exceeded", retry_after=retry_after)

    if resp.status_code >= 500:
        try:
            body = resp.json()
            msg = body.get("remarks", {}).get("error_msg", resp.text)
        except Exception:
            msg = resp.text
        raise BrokerServerError(f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code))

    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {}
        msg = body.get("remarks", {}).get("error_msg", resp.text)
        error_code = body.get("remarks", {}).get("errorCode", "")
        if _is_token_error(resp.status_code, error_code, msg):
            raise TokenRefreshSignal(f"Token rejected: {msg}")
        raise BrokerError(f"HTTP {resp.status_code}: {msg}", code=str(resp.status_code))

    try:
        data: dict[str, Any] = resp.json()
    except Exception:
        return {"data": resp.text}

    if isinstance(data, dict) and data.get("status") == "failure":
        remarks = data.get("remarks", "unknown error")
        raise BrokerError(f"API failure: {remarks}")

    return data


def create_dhan_http_client(
    client_id: str,
    access_token: str,
    token_refresh_fn: Callable[[], str | None] | None = None,
    base_url: str = "",
) -> ResilientHttpClient:
    base_url = base_url or ENDPOINTS["orders"].rsplit("/orders", 1)[0]

    def _build_url(endpoint: str) -> str:
        if endpoint.startswith("http"):
            return endpoint
        return f"{base_url}{endpoint}"

    client = ResilientHttpClient(
        rate_limits=RATE_LIMITS,
        categorize_fn=_dhan_categorize,
        url_builder_fn=_build_url,
        response_handler_fn=_dhan_handle_response,
        token_refresh_fn=token_refresh_fn,
        client_id=client_id,
    )
    client.session.headers.update(
        {
            "access-token": access_token,
            "client-id": client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    return client
