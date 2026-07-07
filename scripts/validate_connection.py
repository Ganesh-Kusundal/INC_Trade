"""Live connection validation — tests real broker APIs without exposing credentials.

Usage:
    python scripts/validate_connection.py dhan
    python scripts/validate_connection.py upstox
    python scripts/validate_connection.py both

Credentials are loaded from .env.local via CredentialResolver.
No credentials are printed or logged.
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in Python path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env.local into os.environ before importing anything
def load_env():
    env_file = Path(__file__).parent.parent / ".env.local"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

load_env()


async def validate_dhan():
    """Validate Dhan connection, profile, and funds."""
    print("=" * 60)
    print("DHAN VALIDATION")
    print("=" * 60)

    try:
        from brokers.platform import Platform

        print("\n[1] Connecting via Platform.connect('dhan')...")
        platform = await Platform.connect("dhan")
        print(f"    OK: broker_id={platform.broker_id}, connected={platform.is_connected}")

        print("\n[2] Fetching account balance...")
        account = platform.account()
        balance = await account.get_balance()
        print(f"    Available balance: Rs. {balance.available_balance}")
        print(f"    Used margin: Rs. {balance.used_margin}")
        print(f"    Total value: Rs. {balance.total_value}")

        print("\n[3] Fetching positions...")
        positions = await account.get_positions()
        print(f"    Open positions: {len(positions)}")
        for pos in positions[:5]:
            print(f"      {pos.symbol}: qty={pos.quantity}, avg={pos.average_price}, pnl={pos.unrealized_pnl}")

        print("\n[4] Fetching holdings...")
        holdings = await account.get_holdings()
        print(f"    Holdings: {len(holdings)}")
        for h in holdings[:5]:
            print(f"      {h.symbol}: qty={h.quantity}, avg={h.average_price}, ltp={h.ltp}")

        print("\n[5] Fetching orders...")
        orders = await account.get_orders()
        print(f"    Orders: {len(orders)}")

        print("\n[6] Testing quote...")
        reliance = platform.instrument("NSE:RELIANCE")
        quote = await reliance.quote()
        print(f"    RELIANCE LTP: Rs. {quote.ltp}")

        print("\n[7] Disconnecting...")
        await platform.disconnect()
        print("    OK")

        print("\n" + "=" * 60)
        print("DHAN VALIDATION: PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n    FAILED: {e}")
        print("\n" + "=" * 60)
        print("DHAN VALIDATION: FAILED")
        print("=" * 60)
        return False


async def validate_upstox():
    """Validate Upstox connection, profile, and funds."""
    print("\n" + "=" * 60)
    print("UPSTOX VALIDATION")
    print("=" * 60)

    try:
        from brokers.platform import Platform

        print("\n[1] Connecting via Platform.connect('upstox')...")
        platform = await Platform.connect("upstox")
        print(f"    OK: broker_id={platform.broker_id}, connected={platform.is_connected}")

        print("\n[2] Fetching account balance...")
        account = platform.account()
        balance = await account.get_balance()
        print(f"    Available balance: Rs. {balance.available_balance}")
        print(f"    Used margin: Rs. {balance.used_margin}")
        print(f"    Total value: Rs. {balance.total_value}")

        print("\n[3] Fetching positions...")
        positions = await account.get_positions()
        print(f"    Open positions: {len(positions)}")
        for pos in positions[:5]:
            print(f"      {pos.symbol}: qty={pos.quantity}, avg={pos.average_price}, pnl={pos.unrealized_pnl}")

        print("\n[4] Fetching holdings...")
        holdings = await account.get_holdings()
        print(f"    Holdings: {len(holdings)}")
        for h in holdings[:5]:
            print(f"      {h.symbol}: qty={h.quantity}, avg={h.average_price}, ltp={h.ltp}")

        print("\n[5] Fetching orders...")
        orders = await account.get_orders()
        print(f"    Orders: {len(orders)}")

        print("\n[6] Testing quote...")
        reliance = platform.instrument("NSE:RELIANCE")
        quote = await reliance.quote()
        print(f"    RELIANCE LTP: Rs. {quote.ltp}")

        print("\n[7] Disconnecting...")
        await platform.disconnect()
        print("    OK")

        print("\n" + "=" * 60)
        print("UPSTOX VALIDATION: PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n    FAILED: {e}")
        print("\n" + "=" * 60)
        print("UPSTOX VALIDATION: FAILED")
        print("=" * 60)
        return False


async def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "both"

    results = {}
    if target in ("dhan", "both"):
        results["dhan"] = await validate_dhan()
    if target in ("upstox", "both"):
        results["upstox"] = await validate_upstox()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for broker, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {broker.upper()}: {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
