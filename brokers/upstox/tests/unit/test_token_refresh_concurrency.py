"""Concurrency tests for Upstox token refresh single-flight behavior."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.token_manager import UpstoxTokenManager


def _totp_settings() -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="CID",
        client_secret="CSEC",
        auth_mode="TOTP",
        mobile="9999999999",
        pin="1234",
        totp_secret="SECRET",
        refresh_buffer_minutes=30,
    )


def test_concurrent_bearer_token_single_totp_call():
    """Near-expiry concurrent bearer_token() calls must trigger one TOTP refresh."""
    settings = _totp_settings()
    mgr = UpstoxTokenManager(settings=settings, oauth_client=MagicMock())
    from brokers.upstox.auth.holders import TokenSnapshot

    future_exp = int(time.time() * 1000) + 60_000
    mgr._state = TokenSnapshot(
        access_token="old-token",
        refresh_token=None,
        expires_at_ms=future_exp,
        issued_at_ms=int(time.time() * 1000),
        source="TOTP",
    )
    call_count = {"n": 0}
    lock = threading.Lock()

    def slow_bootstrap():
        with lock:
            call_count["n"] += 1
        time.sleep(0.05)
        from brokers.upstox.auth.holders import TokenSnapshot as TS

        state = TS(
            access_token="new-token",
            refresh_token=None,
            expires_at_ms=int(time.time() * 1000) + 3_600_000,
            issued_at_ms=int(time.time() * 1000),
            source="TOTP",
        )
        mgr._apply_token_state(state, label="test")
        return state

    with patch.object(mgr, "_needs_proactive_refresh", return_value=True):
        with patch.object(mgr, "_bootstrap_totp", side_effect=slow_bootstrap):
            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(mgr.bearer_token) for _ in range(10)]
                for f in as_completed(futures):
                    f.result()

    assert call_count["n"] == 1
    assert mgr.bearer_token() == "new-token"


def test_concurrent_401_single_refresh():
    """HTTP 401 recovery should refresh once across concurrent callers."""
    settings = _totp_settings()
    mgr = UpstoxTokenManager(settings=settings, oauth_client=MagicMock())
    refresh_count = {"n": 0}
    lock = threading.Lock()

    def refresh_once():
        with lock:
            refresh_count["n"] += 1
        time.sleep(0.05)
        from brokers.upstox.auth.holders import TokenSnapshot

        state = TokenSnapshot(
            access_token="refreshed",
            refresh_token=None,
            expires_at_ms=int(time.time() * 1000) + 3_600_000,
            issued_at_ms=int(time.time() * 1000),
            source="TOTP",
        )
        mgr._apply_token_state(state, label="test")
        return state

    with patch.object(mgr, "_bootstrap_totp", side_effect=refresh_once):
        results = []

        def attempt():
            results.append(mgr.try_refresh_on_401())

        threads = [threading.Thread(target=attempt) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert refresh_count["n"] == 1
    assert all(results)
    assert mgr.current_token() == "refreshed"


def test_http_client_retries_once_after_refresh():
    """UpstoxHttpClient should retry once when on_auth_failure succeeds."""
    from brokers.upstox.auth.http import UpstoxHttpClient

    calls = {"refresh": 0, "request": 0}

    def on_auth_failure() -> bool:
        calls["refresh"] += 1
        return True

    client = UpstoxHttpClient(
        token_provider=lambda: "token",
        settings=MagicMock(),
        on_auth_failure=on_auth_failure,
        enable_circuit_breaker=False,
    )

    class FakeResponse:
        def __init__(self, status_code: int, text: str = '{"status": "success"}'):
            self.status_code = status_code
            self.text = text

        def json(self):
            return {"status": "success"}

    responses = [FakeResponse(401), FakeResponse(200)]

    def fake_request(*args, **kwargs):
        calls["request"] += 1
        return responses.pop(0)

    client._session.request = fake_request  # type: ignore[method-assign]
    body = client.get_json("https://api.upstox.com/v2/user/profile")
    assert body["status"] == "success"
    assert calls["refresh"] == 1
    assert calls["request"] == 2
