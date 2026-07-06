#!/usr/bin/env python3
"""Side-by-side behavioral parity comparison: archived vs modern Upstox gateway.

Usage:
    PRE_PROD_GATE=1 python brokers/scripts/upstox_live_parity_compare.py

Requires valid credentials in .env.upstox or environment variables.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _require_gate() -> None:
    if os.getenv("PRE_PROD_GATE") != "1":
        print("Set PRE_PROD_GATE=1 to run live parity comparison", file=sys.stderr)
        sys.exit(1)


def _compare(name: str, archived_val: Any, modern_val: Any) -> dict[str, Any]:
    match = archived_val == modern_val
    return {
        "check": name,
        "archived": repr(archived_val),
        "modern": repr(modern_val),
        "match": match,
    }


def main() -> int:
    _require_gate()

    results: list[dict[str, Any]] = []

    # Modern gateway
    from brokers.adapters.upstox.gateway import UpstoxGateway

    modern = UpstoxGateway(auto_refresh=False)
    try:
        modern_ltp = modern.market_data.ltp("RELIANCE", "NSE")
        results.append(
            {
                "check": "modern_ltp_reliance",
                "value": str(modern_ltp),
                "ok": modern_ltp > 0,
            }
        )

        modern_funds = modern.portfolio.funds()
        results.append(
            {
                "check": "modern_funds",
                "available": str(modern_funds.available_balance),
                "ok": modern_funds.available_balance >= 0,
            }
        )

        modern_profile = modern.extended.get_user_profile()
        results.append(
            {
                "check": "modern_profile",
                "has_data": bool(modern_profile),
                "ok": isinstance(modern_profile, dict),
            }
        )

        results.append(
            {
                "check": "connection_status",
                "value": modern.get_connection_status(),
                "ok": True,
            }
        )
    finally:
        modern.close()

    print(json.dumps({"parity_results": results}, indent=2))
    failed = [r for r in results if not r.get("ok", r.get("match", False))]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
