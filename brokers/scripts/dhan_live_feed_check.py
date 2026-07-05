#!/usr/bin/env python3
"""Live Dhan feed verification — REST depth + WS modes (LTP/QUOTE/FULL) + depth-20.

Checks NSE equity, futures, and options with real Dhan credentials.

Usage::

    LIVE_GATE=1 python brokers/scripts/dhan_live_feed_check.py

Optional env:
    DHAN_TEST_THROTTLE_MS=1200   # pause between REST calls (default 1200)
    WS_WAIT_SECONDS=12            # wait for WS ticks/depth (default 12)
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from brokers.adapters.dhan.gateway import DhanGateway

_REPO = Path(__file__).resolve().parents[2]


def _require_gate() -> None:
    if os.getenv("LIVE_GATE") != "1":
        print("Set LIVE_GATE=1 to run live Dhan feed checks", file=sys.stderr)
        sys.exit(1)


def _throttle() -> float:
    raw = os.getenv("DHAN_TEST_THROTTLE_MS", "1200")
    try:
        return max(0.0, int(raw) / 1000.0)
    except ValueError:
        return 1.2


def _ws_wait() -> float:
    try:
        return float(os.getenv("WS_WAIT_SECONDS", "12"))
    except ValueError:
        return 12.0


@dataclass
class InstrumentCase:
    kind: str
    symbol: str
    exchange: str


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _load_gateway() -> DhanGateway:
    from brokers.adapters.dhan.gateway import DhanGateway
    from inc_trade.infrastructure.credentials import CredentialResolver

    resolver = CredentialResolver(project_root=_REPO)
    env_path = resolver.resolve_env_path("dhan") or _REPO / ".env.local"
    if env_path.exists():
        resolver.load_broker_env("dhan")

    client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
    if not client_id:
        print("DHAN_CLIENT_ID required in .env.local", file=sys.stderr)
        sys.exit(1)

    gw = DhanGateway(
        access_token=os.environ.get("DHAN_ACCESS_TOKEN") or None,
        client_id=client_id,
        pin=os.environ.get("DHAN_PIN"),
        totp_secret=os.environ.get("DHAN_TOTP_SECRET"),
        env_path=env_path,
        auto_refresh=True,
    )
    gw.instruments.load()
    return gw


def _resolve_instruments(gw: DhanGateway) -> list[InstrumentCase]:
    cases: list[InstrumentCase] = [
        InstrumentCase("equity", "RELIANCE", "NSE"),
    ]

    fut_chain = gw.futures.get_futures_chain("NIFTY", "NFO")
    if not fut_chain:
        raise RuntimeError("No NIFTY futures contracts found in instrument master")
    cases.append(InstrumentCase("future", fut_chain[0].symbol, "NFO"))

    expiries = gw.options.get_expiries("NIFTY", "NFO")
    if not expiries:
        raise RuntimeError("No NIFTY option expiries returned")
    chain = gw.options.get_option_chain("NIFTY", "NFO", expiries[0])
    if not chain.strikes:
        raise RuntimeError("NIFTY option chain empty")
    # Pick ATM-ish CE with liquidity
    best = min(
        chain.strikes,
        key=lambda s: abs(float(s.strike) - float(chain.spot)),
    )
    opt_symbol = best.call.symbol
    if not opt_symbol:
        raise RuntimeError("Could not resolve option trading symbol from chain")
    cases.append(InstrumentCase("option", opt_symbol, "NFO"))

    return cases


def _check_rest_depth(gw: DhanGateway, case: InstrumentCase) -> CheckResult:
    name = f"rest_depth_{case.kind}"
    try:
        depth = gw.market_data.depth(case.symbol, case.exchange)
        bid_ok = len(depth.bids) >= 1 and depth.bids[0].price > 0
        ask_ok = len(depth.asks) >= 1 and depth.asks[0].price > 0
        ok = bid_ok and ask_ok
        detail = (
            f"bids={len(depth.bids)} asks={len(depth.asks)} "
            f"top_bid={depth.bids[0].price if depth.bids else 0} "
            f"top_ask={depth.asks[0].price if depth.asks else 0}"
        )
        return CheckResult(name, ok, detail, {"symbol": case.symbol, "exchange": case.exchange})
    except Exception as exc:
        return CheckResult(name, False, str(exc), {"symbol": case.symbol})


def _check_rest_ltp_quote(gw: DhanGateway, case: InstrumentCase) -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        ltp = gw.market_data.ltp(case.symbol, case.exchange)
        out.append(
            CheckResult(
                f"rest_ltp_{case.kind}",
                ltp > 0,
                f"ltp={ltp}",
                {"symbol": case.symbol},
            )
        )
    except Exception as exc:
        out.append(CheckResult(f"rest_ltp_{case.kind}", False, str(exc)))
    time.sleep(_throttle())
    try:
        q = gw.market_data.quote(case.symbol, case.exchange)
        ok = q.ltp > 0 and q.high >= q.low
        out.append(
            CheckResult(
                f"rest_quote_{case.kind}",
                ok,
                f"ltp={q.ltp} ohlc={q.open}/{q.high}/{q.low}/{q.close} vol={q.volume}",
                {"symbol": case.symbol},
            )
        )
    except Exception as exc:
        out.append(CheckResult(f"rest_quote_{case.kind}", False, str(exc)))
    return out


def _check_ws_mode(gw: DhanGateway, case: InstrumentCase, mode: str) -> CheckResult:
    name = f"ws_{mode.lower()}_{case.kind}"
    received = threading.Event()
    ticks: list[dict[str, Any]] = []
    wait_s = _ws_wait()

    def on_tick(tick: dict[str, Any]) -> None:
        ticks.append(tick)
        received.set()

    streaming = gw.streaming
    streaming.set_mode(mode)
    try:
        streaming.stop()
        time.sleep(0.3)
        streaming.register_tick_handler(case.symbol, case.exchange, on_tick)
        streaming.subscribe(case.symbol, case.exchange)
        streaming.start()
        got = received.wait(timeout=wait_s)
        ok = bool(got and ticks)
        ltp = ticks[0].get("ltp") if ticks else None
        feed_code = ticks[0].get("raw", {}).get("feed_code") if ticks else None
        detail = f"ticks={len(ticks)} ltp={ltp} feed_code={feed_code}"
        streaming.unsubscribe(case.symbol, case.exchange)
        streaming.stop()
        return CheckResult(name, ok, detail, {"symbol": case.symbol, "mode": mode})
    except Exception as exc:
        with contextlib.suppress(Exception):
            streaming.stop()
        return CheckResult(name, False, str(exc), {"symbol": case.symbol, "mode": mode})


def _check_depth20_ws(gw: DhanGateway, case: InstrumentCase) -> CheckResult:
    name = f"ws_depth20_{case.kind}"
    received = threading.Event()
    updates: list[Any] = []
    wait_s = _ws_wait()

    def on_depth(depth: Any) -> None:
        updates.append(depth)
        if depth.bids and depth.asks:
            received.set()

    feed = gw.depth20_stream
    try:
        feed.stop()
        time.sleep(0.3)
        feed.on_depth(on_depth)
        feed.subscribe(case.symbol, case.exchange)
        ref = gw.resolver.resolve(case.symbol, case.exchange)
        feed.register_symbol(ref.security_id_int(), case.symbol)
        feed.start()
        got = received.wait(timeout=wait_s)
        snap = gw.depth_20_snapshot(case.symbol, case.exchange)
        rest_merge = len(snap.bids) >= 1 and len(snap.asks) >= 1
        ok = bool(got and updates) or rest_merge
        detail = (
            f"ws_updates={len(updates)} snapshot_bids={len(snap.bids)} "
            f"snapshot_asks={len(snap.asks)}"
        )
        feed.stop()
        return CheckResult(name, ok, detail, {"symbol": case.symbol})
    except Exception as exc:
        with contextlib.suppress(Exception):
            feed.stop()
        return CheckResult(name, False, str(exc), {"symbol": case.symbol})


def main() -> int:
    _require_gate()
    sys.path.insert(0, str(_REPO))

    throttle = _throttle()
    results: list[CheckResult] = []

    gw = _load_gateway()
    try:
        instruments = _resolve_instruments(gw)
        print("=== Instruments under test ===")
        for c in instruments:
            print(f"  {c.kind:6s}  {c.symbol}  ({c.exchange})")
        print()

        for case in instruments:
            results.extend(_check_rest_ltp_quote(gw, case))
            time.sleep(throttle)
            results.append(_check_rest_depth(gw, case))
            time.sleep(throttle)

        for mode in ("LTP", "QUOTE", "FULL"):
            for case in instruments:
                results.append(_check_ws_mode(gw, case, mode))
                time.sleep(0.5)

        for case in instruments:
            results.append(_check_depth20_ws(gw, case))
            time.sleep(0.5)

    finally:
        gw.close()

    passed = sum(1 for r in results if r.ok)
    failed = [r for r in results if not r.ok]

    print("=== Results ===")
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"[{status}] {r.name}: {r.detail}")
    print()
    print(f"Summary: {passed}/{len(results)} passed, {len(failed)} failed")

    report_path = _REPO / "runtime" / "dhan_live_feed_check.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": len(results),
                "results": [asdict(r) for r in results],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Report: {report_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
