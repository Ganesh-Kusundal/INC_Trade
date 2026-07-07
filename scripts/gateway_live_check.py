#!/usr/bin/env python3
"""Live check — connection, funds, and historical data via the v2 Broker API.

Goes through the unified ``Broker.dhan()`` → ``Provider`` path and runs
three probes:

1. **Connection**  — ``instrument.ltp()`` proves auth + REST path.
2. **Funds**       — ``account.balance()`` proves portfolio read path.
3. **Historical**  — ``instrument.history()`` proves chart data path.

``allow_live_orders`` is not needed — the v2 architecture has no order
wrapper that could place orders without explicit intent.

Exit codes
----------
- 0  — all probes succeeded
- 1  — one or more probes failed
- 2  — required env vars missing
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
import time
import traceback
from datetime import date, timedelta
from typing import Any

from brokers import Broker, Exchange
from brokers.domain.values import Balance

_INSTRUMENTS = {"RELIANCE:NSE": "2885"}
_SANDBOX_URL = "https://sandbox.dhan.co/v2"
_PROD_URL = "https://api.dhan.co/v2"
_PROBE_TIMEOUT = 20.0


def _exit_missing_creds() -> None:
    use_prod = os.environ.get("DHAN_GATEWAY_USE_PROD", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if use_prod:
        print(
            "ERROR: DHAN_GATEWAY_USE_PROD=1 but DHAN_CLIENT_ID / "
            "DHAN_ACCESS_TOKEN not set.",
            file=sys.stderr,
        )
    else:
        print(
            "ERROR: requires sandbox creds:\n"
            "  - DHAN_SANDBOX_CLIENT_ID\n"
            "  - DHAN_SANDBOX_ACCESS_TOKEN",
            file=sys.stderr,
        )
    sys.exit(2)


def _resolve_creds_and_url() -> tuple[str, str, str]:
    use_prod = os.environ.get("DHAN_GATEWAY_USE_PROD", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if use_prod:
        cid = os.environ.get("DHAN_CLIENT_ID", "")
        tok = os.environ.get("DHAN_ACCESS_TOKEN", "")
        url = os.environ.get("DHAN_BASE_URL", _PROD_URL)
    else:
        cid = os.environ.get("DHAN_SANDBOX_CLIENT_ID", "")
        tok = os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN", "")
        url = os.environ.get("DHAN_SANDBOX_REST_BASE_URL", _SANDBOX_URL)
    if not cid or not tok:
        _exit_missing_creds()
    return cid, tok, url


async def _probe_ltp(broker: Broker) -> dict[str, Any]:
    start = time.perf_counter()
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    ltp = await asyncio.wait_for(reliance.ltp(), timeout=_PROBE_TIMEOUT)
    ms = (time.perf_counter() - start) * 1000
    return {"name": "get_ltp", "ok": True, "ms": ms, "value": str(ltp)}


async def _probe_funds(broker: Broker) -> dict[str, Any]:
    start = time.perf_counter()
    bal = await asyncio.wait_for(broker.account().get_balance(), timeout=_PROBE_TIMEOUT)
    ms = (time.perf_counter() - start) * 1000
    if isinstance(bal, Balance):
        return {
            "name": "get_balance", "ok": True, "ms": ms,
            "available": str(bal.available_balance),
            "used": str(bal.used_margin),
        }
    return {"name": "get_balance", "ok": True, "ms": ms, "value": repr(bal)}


async def _probe_history(broker: Broker) -> dict[str, Any]:
    to_date = date.today()
    from_date = to_date - timedelta(days=30)
    start = time.perf_counter()
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    series = await asyncio.wait_for(
        reliance.history(timeframe="1D", from_date=from_date, to_date=to_date),
        timeout=_PROBE_TIMEOUT,
    )
    ms = (time.perf_counter() - start) * 1000
    count = len(series.bars) if hasattr(series, "bars") else 0
    sample = series.bars[0] if count > 0 else None
    return {
        "name": "get_history", "ok": True, "ms": ms,
        "bar_count": count,
        "sample": str(sample)[:120] if sample else "<none>",
    }


async def _run_all(broker: Broker) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for probe_fn in (_probe_ltp, _probe_funds, _probe_history):
        try:
            r = await probe_fn(broker)
            results.append(r)
        except Exception as exc:
            results.append({
                "name": probe_fn.__name__.replace("_probe_", ""),
                "ok": False,
                "error": str(exc).strip()[:200] or type(exc).__name__,
            })
    return results


def main() -> int:
    client_id, access_token, base_url = _resolve_creds_and_url()
    broker = Broker.dhan(
        client_id=client_id,
        access_token=access_token,
        instruments=_INSTRUMENTS,
        base_url=base_url,
    )

    print(f"Live check — Dhan ({base_url})", flush=True)
    print(f"  client_id: {client_id[:4]}***", flush=True)
    print(f"  probes: get_ltp, get_balance, get_history", flush=True)
    print(flush=True)

    verbose = os.environ.get("GATEWAY_CHECK_DEBUG", "").strip().lower() in (
        "1", "true", "yes", "on",
    )

    async def _go() -> list[dict[str, Any]]:
        await broker.connect()
        try:
            return await _run_all(broker)
        finally:
            await broker.disconnect()

    try:
        results = asyncio.run(_go())
    except Exception as exc:
        msg = str(exc).strip() or f"{type(exc).__name__} (no message)"
        print(f"FATAL: {msg}", file=sys.stderr)
        if verbose:
            traceback.print_exc(file=sys.stderr)
        return 1

    all_ok = True
    for r in results:
        name = r["name"]
        if r["ok"]:
            ms = r.get("ms", 0)
            if name == "get_ltp":
                print(f"  ✓ {name:<16s} {ms:7.1f}ms  LTP={r['value']}")
            elif name == "get_balance":
                print(f"  ✓ {name:<16s} {ms:7.1f}ms  available={r.get('available','?')} used={r.get('used','?')}")
            elif name == "get_history":
                print(f"  ✓ {name:<16s} {ms:7.1f}ms  bars={r['bar_count']}  sample={r['sample']}")
            else:
                print(f"  ✓ {name:<16s} {ms:7.1f}ms  {r}")
        else:
            all_ok = False
            print(f"  ✗ {name:<16s}  ERROR={r.get('error','unknown')}", file=sys.stderr)

    print(flush=True)
    ok_count = sum(1 for r in results if r["ok"])
    print(f"SUMMARY: {ok_count}/{len(results)} probes passed.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
