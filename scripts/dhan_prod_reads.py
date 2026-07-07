#!/usr/bin/env python3
"""Dhan PROD-cred live reads with latency budgets — Tier-3 prod-grade CI.

Uses the v2 ``Broker.dhan()`` → ``Provider`` path against PRODUCTION
credentials during live market hours, with latency budgets hard-fail.

Runs 6 REST probes timed against archived latency budgets:
  - ``get_ltp``        budget 200 ms
  - ``get_quote``      budget 200 ms
  - ``get_depth``      budget 300 ms
  - ``get_balance``    budget 400 ms
  - ``get_positions``  budget 400 ms
  - ``get_orders``     budget 400 ms

Defense-in-depth:
  - ``I_AM_RUNNING_PROD_READS=1`` MUST be exported — operator confirm gate
  - PROD URL is HARD-CODED — no env override for REST base URL

Exit codes
----------
- 0  — every probe under budget
- 1  — broker error OR any probe exceeded latency budget
- 2  — required env vars missing or opt-in gate not set
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
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, NoReturn

from brokers import Broker, Exchange
from brokers.domain.values import Balance

LATENCY_BUDGETS_MS: dict[str, int] = {
    "get_ltp": 200,
    "get_quote": 200,
    "get_depth": 300,
    "get_balance": 400,
    "get_positions": 400,
    "get_orders": 400,
}

PROD_REST_URL = "https://api.dhan.co/v2"


def _exit_missing_prereqs() -> NoReturn:
    print(
        "ERROR: dhan-prod-reads requires ALL of:\n"
        "  - DHAN_CLIENT_ID                          (prod)\n"
        "  - DHAN_ACCESS_TOKEN                        (live token)\n"
        "  - I_AM_RUNNING_PROD_READS=1               (operator confirm gate)\n",
        file=sys.stderr,
    )
    sys.exit(2)


@dataclass
class ProbeResult:
    name: str
    latency_ms: float
    budget_ms: int
    passed: bool
    error: str | None = None


async def _timed_probe(
    name: str, factory: Callable[[], Awaitable[Any]], budget_ms: int
) -> ProbeResult:
    start = time.perf_counter()
    try:
        await factory()
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return ProbeResult(
            name=name, latency_ms=latency_ms, budget_ms=budget_ms,
            passed=False, error=str(exc).strip()[:200] or type(exc).__name__,
        )
    latency_ms = (time.perf_counter() - start) * 1000
    return ProbeResult(
        name=name, latency_ms=latency_ms, budget_ms=budget_ms,
        passed=latency_ms <= budget_ms,
    )


async def _run_rest_probes(client_id: str, access_token: str) -> list[ProbeResult]:
    """6 REST probes timed via the v2 Provider path."""
    broker = Broker.dhan(
        client_id=client_id,
        access_token=access_token,
        instruments={"RELIANCE:NSE": "2885"},
        base_url=PROD_REST_URL,
    )
    await broker.connect()
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    account = broker.account()

    probes: list[tuple[str, int, Callable[[], Awaitable[Any]]]] = [
        ("get_ltp", LATENCY_BUDGETS_MS["get_ltp"], lambda: reliance.ltp()),
        ("get_quote", LATENCY_BUDGETS_MS["get_quote"], lambda: reliance.quote()),
        ("get_depth", LATENCY_BUDGETS_MS["get_depth"], lambda: reliance.depth()),
        ("get_balance", LATENCY_BUDGETS_MS["get_balance"], lambda: account.get_balance()),
        ("get_positions", LATENCY_BUDGETS_MS["get_positions"], lambda: account.get_positions()),
        ("get_orders", LATENCY_BUDGETS_MS["get_orders"], lambda: account.get_orders()),
    ]

    results: list[ProbeResult] = []
    for name, budget, factory in probes:
        res = await _timed_probe(name, factory, budget)
        results.append(res)
        status = "✓" if res.passed else "✗"
        suffix = f"  ERR={res.error}" if res.error else ""
        print(
            f"PROBE {status} {name:<16s} {res.latency_ms:7.1f}ms  budget={budget}ms{suffix}",
            flush=True,
            file=sys.stderr if not res.passed else sys.stdout,
        )

    await broker.disconnect()
    return results


def main() -> int:
    if os.environ.get("I_AM_RUNNING_PROD_READS", "").strip() != "1":
        _exit_missing_prereqs()

    client_id = os.environ.get("DHAN_CLIENT_ID")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    if not client_id or not access_token:
        _exit_missing_prereqs()

    verbose = os.environ.get("DHAN_PROD_READS_DEBUG", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    print(f"OK: prod-cred Tier-3 starting. REST={PROD_REST_URL} (HARDCODED)", flush=True)

    try:
        results = asyncio.run(_run_rest_probes(client_id, access_token))
    except Exception as exc:
        msg = str(exc).strip() or f"{type(exc).__name__} (no message)"
        print(f"BROKER ERROR: {msg}", file=sys.stderr)
        if verbose:
            traceback.print_exc(file=sys.stderr)
        return 1

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(
        f"\nSUMMARY: {passed}/{len(results)} probes under budget; "
        f"{failed} over budget or errored.",
        flush=True,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
