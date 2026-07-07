#!/usr/bin/env python3
"""Dhan sandbox connectivity smoke check — Tier 1 pre-flight.

Verifies REST connectivity to the Dhan sandbox by performing two probes:
1. ``get_ltp`` for RELIANCE on NSE — smallest price lookup.
2. ``get_balance`` — balance lookup on a different verb.

Uses the v2 ``Broker.dhan()`` factory and the unified ``Provider`` protocol.

Exit codes
----------
- 0  — broker reachable, auth valid, both probes succeeded, balance > 0
- 1  — broker rejected (auth, rate-limit, network, zero balance)
- 2  — required env vars missing OR URL invalid
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

import asyncio
import os
import sys
import traceback
import urllib.parse as urlparse
from typing import Any, NoReturn

from brokers import Broker, Exchange
from brokers.domain.values import Balance

PER_PROBE_TIMEOUT_SECONDS = 15.0


def _exit_missing_creds() -> NoReturn:
    print(
        "ERROR: Dhan sandbox smoke requires both env vars:\n"
        "  - DHAN_SANDBOX_CLIENT_ID\n"
        "  - DHAN_SANDBOX_ACCESS_TOKEN\n"
        "Set them in .env.local or export before running `make dhan-smoke`.",
        file=sys.stderr,
    )
    sys.exit(2)


def _exit_invalid_url(env_var_name: str, raw: str, reason: str) -> NoReturn:
    print(
        f"BROKER ERROR: {env_var_name}={raw!r} is invalid: {reason}.",
        file=sys.stderr,
    )
    sys.exit(2)


def _resolve_sandbox_url() -> str:
    candidates: list[tuple[str, str]] = [
        ("DHAN_SANDBOX_BASE_URL", os.environ.get("DHAN_SANDBOX_BASE_URL") or ""),
        ("DHAN_BASE_URL", os.environ.get("DHAN_BASE_URL") or ""),
        ("<default>", "https://sandbox.api.dhan.co/v2"),
    ]
    for name, raw in candidates:
        if not raw:
            continue
        try:
            parsed = urlparse.urlparse(raw)
        except (ValueError, TypeError) as exc:
            _exit_invalid_url(name, raw, f"not parseable: {exc}")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            _exit_invalid_url(name, raw, "missing http/https scheme or netloc")
        return raw
    raise RuntimeError("unreachable")


async def _probe_ltp(broker: Broker) -> Any:
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    return await asyncio.wait_for(
        reliance.ltp(),
        timeout=PER_PROBE_TIMEOUT_SECONDS,
    )


async def _probe_balance(broker: Broker) -> Any:
    account = broker.account()
    return await asyncio.wait_for(
        account.get_balance(),
        timeout=PER_PROBE_TIMEOUT_SECONDS,
    )


async def _run_smoke(
    client_id: str, access_token: str, *, base_url: str
) -> tuple[Any, Any, str]:
    broker = Broker.dhan(
        client_id=client_id,
        access_token=access_token,
        instruments={"RELIANCE:NSE": "2885"},
        base_url=base_url,
    )
    await broker.connect()
    ltp = await _probe_ltp(broker)
    bal = await _probe_balance(broker)
    bal_str = (
        f"available_balance={bal.available_balance}"
        if isinstance(bal, Balance)
        else f"balance={bal!r}"
    )
    await broker.disconnect()
    return ltp, bal, bal_str


def _validate_balance(bal: Any) -> int | None:
    if not isinstance(bal, Balance):
        return None
    if bal.available_balance <= 0:
        print(
            "BROKER ERROR: connect OK but available_balance="
            f"{bal.available_balance} — sandbox in non-trading state.",
            file=sys.stderr,
        )
        return 1
    return None


def _print_broker_error(exc: Exception, *, verbose: bool) -> None:
    msg = str(exc).strip() or f"{type(exc).__name__} (no message)"
    print(f"BROKER ERROR: {msg}", file=sys.stderr)
    if verbose:
        traceback.print_exc(file=sys.stderr)


def main() -> int:
    client_id = os.environ.get("DHAN_SANDBOX_CLIENT_ID")
    access_token = os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN")
    if not client_id or not access_token:
        _exit_missing_creds()

    verbose = os.environ.get("DHAN_SMOKE_DEBUG", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    base_url = _resolve_sandbox_url()

    try:
        ltp, bal, bal_str = asyncio.run(
            _run_smoke(client_id, access_token, base_url=base_url),
        )
    except asyncio.TimeoutError:
        _print_broker_error(
            TimeoutError(
                f"probe exceeded {PER_PROBE_TIMEOUT_SECONDS}s timeout — "
                "broker unreachable or rate-limit backoff"
            ),
            verbose=verbose,
        )
        return 1
    except Exception as exc:
        _print_broker_error(exc, verbose=verbose)
        return 1

    if not ltp or (isinstance(ltp, str) and ltp == "0"):
        print(
            "BROKER ERROR: get_ltp returned empty/zero — market closed or "
            "symbol missing.",
            file=sys.stderr,
        )
        return 1

    bad = _validate_balance(bal)
    if bad is not None:
        return bad

    print(f"OK: Dhan ({base_url}) LTP for RELIANCE (NSE) = {ltp}; {bal_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
