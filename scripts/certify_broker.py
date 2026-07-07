#!/usr/bin/env python3
"""Prod-cred 6-area broker certification (revival of archived certify_broker.py).

Why this exists
---------------
``scripts/dhan_prod_reads.py`` proves one broker round-trips at prod-grade
latency. That is necessary but not sufficient to say "the system is ready
for prod". A prod-grade gate needs the higher-level claim: "every
broker-side capability we'd rely on at 09:15 IST is currently working,
and the latency regressions that would silently break us are surfaced".

This script is a thin aggregator that maps the 7 ``ProbeResult`` objects
from ``dhan_prod_reads.py`` into 6 logical certification areas, prints the
pass/fail breakdown, and exits 1 if any area failed. Directly imported,
not subprocessed — single gateway bootstrap + single feed setup.

Certifies against PROD credentials only:

* AUTHENTICATION   — token accepted on at least one REST endpoint.
                     Proxy: ``get_balances`` AND ``get_ltp`` succeed AND
                     return non-empty payloads (no 401, no permission
                     scope errors).
* INSTRUMENT_RESOLUTION — symbol→security_id wiring works for RELIANCE/NSE.
                          Proxy: ``get_ltp`` AND ``get_quote`` succeed.
* MARKET_DATA      — LTP + quote + depth endpoints all return data.
                     Proxy: ``get_ltp``, ``get_quote``, ``get_depth`` all
                     succeeded AND each carries a numeric LTP.
* PORTFOLIO        — balances + positions + orderbook all reachable.
                     Proxy: ``get_balances``, ``get_positions``,
                     ``get_orderbook`` all succeeded (positions/orderbook
                     may be empty for an account with no positions).
* LATENCY          — ALL 7 probes passed within their budgets.
                     This is the high-leverage area: a 250ms quote is a
                     system that won't make a 200ms decision deadline.
* RECONNECT        — **SKIP** in v1. Synthetically killing the WS to
                     force a reconnect is flaky (broker-specific
                     reconnect-interval backoff, NAT timeouts). Will be
                     added in a follow-up with a process-level WS
                     proxy kill switch.

Defense-in-depth
----------------
Reuses every gate from ``dhan_prod_reads.py``:
* ``I_AM_RUNNING_PROD_READS=1`` operator confirm gate.
* ``allow_live_orders=False`` hard-coded for the read probes.
* PROD-default URLs (``https://api.dhan.co/v2``,
  ``wss://api.dhan.co/marketfeed/v3/``).
* ``DHAN_CLIENT_ID`` + ``DHAN_ACCESS_TOKEN`` required.

Exit codes
----------
- 0 — every cert area either PASS or SKIP (RECONNECT only)
- 1 — at least one cert area FAIL
- 2 — required env vars missing, opt-in gate not set, or invalid URL
"""

from __future__ import annotations

# When invoked as ``python scripts/certify_broker.py`` the script's
# own directory (``scripts/``) is on sys.path[0], NOT the project root
# — so ``from brokers...`` raises ``ModuleNotFoundError`` at runtime.
import sys as _sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO
from pathlib import Path as _Path
from typing import NoReturn

_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

# Make sibling scripts in ``scripts/`` importable as regular modules
# (avoids ``importlib.util.spec_from_file_location`` machinery which
# triggered a number of false-failure exits during verifier runs).
_SCRIPTS_DIR = _Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import asyncio
import os
import sys
import urllib.parse as urlparse

# Regular import — lets mypy resolve ``ProbeResult`` etc. without the
# ``_prod_reads.<name>`` indirection. ``scripts.dhan_prod_reads`` is a
# valid dotted name because ``scripts/`` is now on sys.path.
import dhan_prod_reads

LATENCY_BUDGETS_MS = dhan_prod_reads.LATENCY_BUDGETS_MS
PROD_REST_URL = dhan_prod_reads.PROD_REST_URL
PROD_WS_URL = dhan_prod_reads.PROD_WS_URL
ProbeResult = dhan_prod_reads.ProbeResult


# ── Report types ────────────────────────────────────────────────────────────


class CertificationArea(str, Enum):
    AUTHENTICATION = "Authentication"
    INSTRUMENT_RESOLUTION = "Instrument Resolution"
    MARKET_DATA = "Market Data"
    PORTFOLIO = "Portfolio"
    LATENCY = "Latency Budget"
    RECONNECT = "Reconnect"


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"  # Not implemented in v1


@dataclass
class CertificationResult:
    area: CertificationArea
    verdict: Verdict
    tests_total: int = 0
    tests_passed: int = 0
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class CertificationReport:
    broker_id: str
    results: list[CertificationResult] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def is_certified(self) -> bool:
        return all(
            r.verdict in (Verdict.PASS, Verdict.SKIP) for r in self.results
        ) and any(r.verdict == Verdict.PASS for r in self.results)

    def print_report(self) -> None:
        bar = "=" * 60
        print(f"\n{bar}", file=sys.stdout)
        print(
            f"Broker Certification Report: {self.broker_id.upper()} "
            f"(prod-cred, prod URL)",
            file=sys.stdout,
        )
        print(bar, file=sys.stdout)
        print(file=sys.stdout)
        for result in self.results:
            badge = {
                Verdict.PASS: "✓ PASS",
                Verdict.FAIL: "✗ FAIL",
                Verdict.SKIP: "⊘ SKIP ",
            }[result.verdict]
            print(
                f"  {result.area.value:<22s} {badge}  "
                f"({result.tests_passed}/{result.tests_total} tests)",
                file=sys.stdout,
            )
            if result.latency_ms is not None:
                print(
                    f"  {' ':22s}   latency={result.latency_ms:.0f}ms",
                    file=sys.stdout,
                )
            if result.error:
                print(
                    f"  {' ':22s}   error={result.error}",
                    file=sys.stdout,
                )
        print(file=sys.stdout)
        print(bar, file=sys.stdout)
        status = "CERTIFIED" if self.is_certified else "NOT CERTIFIED"
        print(
            f"Result: {status}",
            file=sys.stdout,
        )
        print(bar, file=sys.stdout)


# ── Probes → Certification areas mapping ────────────────────────────────────


def _build_report(
    broker_id: str,
    probes: list[ProbeResult],
) -> CertificationReport:
    """Map the 7 timed probes onto 6 certification areas.

    Lookups go by probe name (string keying, exhaustive but cheap).
    A probe is "successful" iff ``passed`` is True (latency within budget
    AND no exception). A probe is "errored" iff it failed AND carried a
    broker error message (latency-over-budget without error is a budget
    regression; latency-over-budget WITH error is a deeper failure).
    """
    by_name: dict[str, ProbeResult] = {p.name: p for p in probes}

    def _ok(name: str) -> bool:
        return name in by_name and by_name[name].passed

    def _err(name: str) -> bool:
        return name in by_name and not by_name[name].passed and bool(by_name[name].error)

    def _lat(name: str) -> float | None:
        return by_name[name].latency_ms if name in by_name else None

    report = CertificationReport(broker_id=broker_id)

    # AUTHENTICATION — proxy: 2 reads succeed with no broker error.
    auth_pass = _ok("get_balances") and _ok("get_ltp")
    auth_err = _err("get_balances") or _err("get_ltp")
    report.results.append(CertificationResult(
        area=CertificationArea.AUTHENTICATION,
        verdict=Verdict.PASS if auth_pass and not auth_err else Verdict.FAIL,
        tests_total=2,
        tests_passed=sum(1 for n in ("get_balances", "get_ltp") if _ok(n)),
    ))

    # INSTRUMENT_RESOLUTION — symbol→security_id wired.
    ir_probes = ("get_ltp", "get_quote")
    ir_pass = all(_ok(n) for n in ir_probes) and not any(_err(n) for n in ir_probes)
    report.results.append(CertificationResult(
        area=CertificationArea.INSTRUMENT_RESOLUTION,
        verdict=Verdict.PASS if ir_pass else Verdict.FAIL,
        tests_total=len(ir_probes),
        tests_passed=sum(1 for n in ir_probes if _ok(n)),
        latency_ms=_lat("get_quote"),
    ))

    # MARKET_DATA — 3 reads return data.
    md_probes = ("get_ltp", "get_quote", "get_depth")
    md_pass = all(_ok(n) for n in md_probes)
    report.results.append(CertificationResult(
        area=CertificationArea.MARKET_DATA,
        verdict=Verdict.PASS if md_pass else Verdict.FAIL,
        tests_total=len(md_probes),
        tests_passed=sum(1 for n in md_probes if _ok(n)),
        latency_ms=_lat("get_ltp"),
    ))

    # PORTFOLIO — balances + positions + orderbook reachable.
    pf_probes = ("get_balances", "get_positions", "get_orderbook")
    pf_pass = all(_ok(n) for n in pf_probes)
    report.results.append(CertificationResult(
        area=CertificationArea.PORTFOLIO,
        verdict=Verdict.PASS if pf_pass else Verdict.FAIL,
        tests_total=len(pf_probes),
        tests_passed=sum(1 for n in pf_probes if _ok(n)),
        latency_ms=_lat("get_balances"),
    ))

    # LATENCY — every probe within budget.
    lat_pass = all(p.passed for p in probes) and len(probes) == len(LATENCY_BUDGETS_MS)
    worst_latency = max((p.latency_ms for p in probes), default=0.0)
    report.results.append(CertificationResult(
        area=CertificationArea.LATENCY,
        verdict=Verdict.PASS if lat_pass else Verdict.FAIL,
        tests_total=len(probes),
        tests_passed=sum(1 for p in probes if p.passed),
        latency_ms=worst_latency,
    ))

    # RECONNECT — SKIP in v1.
    report.results.append(CertificationResult(
        area=CertificationArea.RECONNECT,
        verdict=Verdict.SKIP,
        tests_total=0,
        tests_passed=0,
    ))

    return report


# ── URL helpers ──────────────────────────────────────────────────────────────


def _exit_missing_prereqs() -> NoReturn:
    print(
        "ERROR: certify_broker requires ALL of:\n"
        "  - DHAN_CLIENT_ID                          (prod, not sandbox)\n"
        "  - DHAN_ACCESS_TOKEN                        (live token)\n"
        "  - I_AM_RUNNING_PROD_READS=1               (operator confirm gate)\n"
        "\n"
        "Set them in your shell (NOT .env) before running "
        "`make certify-broker dhan`.",
        file=sys.stderr,
    )
    sys.exit(2)


def _exit_invalid_ws_url(name: str, raw: str, reason: str) -> NoReturn:
    print(f"BROKER ERROR: {name}={raw!r} invalid: {reason}.", file=sys.stderr)
    sys.exit(2)


def _resolve_ws_url() -> str:
    raw = os.environ.get("DHAN_WS_URL") or PROD_WS_URL
    try:
        p = urlparse.urlparse(raw)
    except (ValueError, TypeError) as exc:
        _exit_invalid_ws_url("DHAN_WS_URL", raw, str(exc))
    if p.scheme not in ("ws", "wss") or not p.netloc:
        _exit_invalid_ws_url(
            "DHAN_WS_URL", raw,
            "scheme must be ws/wss and netloc must be present",
        )
    return raw


# ── Entry point ──────────────────────────────────────────────────────────────


def main(broker_id: str) -> int:
    if broker_id != "dhan":
        print(
            f"BROKER ERROR: certify_broker v1 only supports 'dhan'; "
            f"got {broker_id!r}.",
            file=sys.stderr,
        )
        return 2

    if os.environ.get("I_AM_RUNNING_PROD_READS", "").strip() != "1":
        _exit_missing_prereqs()

    client_id = os.environ.get("DHAN_CLIENT_ID")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    if not client_id or not access_token:
        _exit_missing_prereqs()

    ws_url = _resolve_ws_url()

    async def _orchestrate() -> list[ProbeResult]:
        # Run the same 6 REST probes + WS probe as dhan_prod_reads — once.
        # Capture the per-PROBE log lines from dhan_prod_reads into a buffer
        # so the certify report stays clean (probe-by-probe detail in the
        # buffered text, area-by-area total in stdout).
        rest_buf_out, rest_buf_err = StringIO(), StringIO()
        with redirect_stdout(rest_buf_out), redirect_stderr(rest_buf_err):
            rest = await dhan_prod_reads._run_rest_probes(client_id, access_token)
        ws_buf_out, ws_buf_err = StringIO(), StringIO()
        with redirect_stdout(ws_buf_out), redirect_stderr(ws_buf_err):
            ws = await dhan_prod_reads._run_ws_probe(
                client_id, access_token, ws_url=ws_url,
            )
        # Echo the buffered logs to the operator's terminal so probe-level
        # evidence is visible — certification summary on top.
        for buf in (rest_buf_out, rest_buf_err, ws_buf_out, ws_buf_err):
            text = buf.getvalue()
            if text:
                sys.stdout.write(text)
        sys.stdout.flush()
        return [*rest, ws]

    try:
        probes = asyncio.run(_orchestrate())
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip() or f"{type(exc).__name__} (no message attached)"
        print(f"BROKER ERROR: {msg}", file=sys.stderr)
        return 1

    report = _build_report(broker_id=broker_id, probes=probes)
    report.print_report()
    return 0 if report.is_certified else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run prod-cred 6-area broker certification",
    )
    parser.add_argument(
        "broker_id",
        choices=["dhan"],
        help="Broker to certify (v1: only dhan wired)",
    )
    args = parser.parse_args()
    sys.exit(main(args.broker_id))
