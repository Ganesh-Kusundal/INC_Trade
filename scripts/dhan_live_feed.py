#!/usr/bin/env python3
"""Dhan live market data test — print real ticks streaming via the v2 provider.

Wiring: env vars → DhanProvider → Broker → Instrument → subscribe_quotes()

Exit codes
----------
- 0  — WS connected, at least one tick landed before the window closed
- 1  — broker rejected; verbatim error to stderr; DEBUG=1 adds traceback
- 2  — required env vars missing OR WS URL / duration invalid
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
from typing import NoReturn

from brokers import Broker, Exchange, Quote

DEFAULT_WS_URL = "wss://sandbox.api.dhan.co/marketfeed/v3/"
DEFAULT_DURATION_SECONDS = 10


def _exit_missing_creds() -> NoReturn:
    print(
        "ERROR: Dhan live feed requires both env vars:\n"
        "  - DHAN_SANDBOX_CLIENT_ID\n"
        "  - DHAN_SANDBOX_ACCESS_TOKEN\n"
        "Set them in .env.local or export before running.",
        file=sys.stderr,
    )
    sys.exit(2)


def _exit_invalid_url(env_var_name: str, raw: str, reason: str) -> NoReturn:
    print(f"BROKER ERROR: {env_var_name}={raw!r} invalid: {reason}.", file=sys.stderr)
    sys.exit(2)


def _resolve_ws_url() -> str:
    candidates: list[tuple[str, str]] = [
        ("DHAN_SANDBOX_WS_URL", os.environ.get("DHAN_SANDBOX_WS_URL") or ""),
        ("DHAN_WS_URL", os.environ.get("DHAN_WS_URL") or ""),
        ("<default>", DEFAULT_WS_URL),
    ]
    for name, raw in candidates:
        if not raw:
            continue
        try:
            parsed = urlparse.urlparse(raw)
        except (ValueError, TypeError) as exc:
            _exit_invalid_url(name, raw, f"not parseable: {exc}")
        if parsed.scheme not in ("ws", "wss") or not parsed.netloc:
            _exit_invalid_url(name, raw, "scheme must be ws/wss with netloc")
        return raw
    raise RuntimeError("unreachable")


async def _run_feed(
    client_id: str,
    access_token: str,
    *,
    ws_url: str,
    duration_seconds: int,
) -> int:
    """Wire up Broker → Instrument → subscribe_quotes, drain ticks."""
    broker = Broker.dhan(
        client_id=client_id,
        access_token=access_token,
        instruments={"RELIANCE:NSE": "2885"},
    )
    await broker.connect()

    reliance = broker.instrument("RELIANCE", Exchange.NSE)

    ticks: list[Quote] = []
    print(
        f"OK: connecting → {ws_url}; window={duration_seconds}s",
        flush=True,
    )

    def _on_tick(q: Quote) -> None:
        ticks.append(q)
        print(
            f"TICK ltp={q.ltp} o={q.open} h={q.high} l={q.low} "
            f"c={q.close} vol={q.volume} ts={q.timestamp.isoformat()}",
            flush=True,
        )

    try:
        sub = await reliance.subscribe_quotes(on_tick=_on_tick)
        # Wait for the duration window
        await asyncio.sleep(duration_seconds)
        await sub.cancel()
    except Exception as exc:
        # subscribe_quotes currently raises NotSupportedError for Dhan
        # streaming — surface that clearly
        raise
    finally:
        await broker.disconnect()

    return len(ticks)


def main() -> int:
    client_id = os.environ.get("DHAN_SANDBOX_CLIENT_ID")
    access_token = os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN")
    if not client_id or not access_token:
        _exit_missing_creds()

    verbose = os.environ.get("DHAN_LIVE_FEED_DEBUG", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    ws_url = _resolve_ws_url()
    duration = int(
        os.environ.get("DHAN_LIVE_FEED_DURATION_SECONDS", str(DEFAULT_DURATION_SECONDS))
    )
    if duration <= 0:
        _exit_invalid_url(
            "DHAN_LIVE_FEED_DURATION_SECONDS", str(duration),
            "must be a positive integer (seconds)",
        )

    try:
        tick_count = asyncio.run(
            _run_feed(
                client_id, access_token,
                ws_url=ws_url, duration_seconds=duration,
            )
        )
    except Exception as exc:
        msg = str(exc).strip() or f"{type(exc).__name__} (no message)"
        print(f"BROKER ERROR: {msg}", file=sys.stderr)
        if verbose:
            traceback.print_exc(file=sys.stderr)
        return 1

    if tick_count <= 0:
        print(
            "BROKER ERROR: 0 ticks in window. Outside market hours, "
            "or streaming not yet implemented for this provider.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {tick_count} ticks over {duration}s window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
