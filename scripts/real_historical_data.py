"""
Real live test of DhanGateway endpoints.
No mocks. No fabricated data. Real API or explicit failure.
"""
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)

from brokers.adapters.dhan.gateway import DhanGateway

client_id    = os.environ["DHAN_CLIENT_ID"]
access_token = os.environ["DHAN_ACCESS_TOKEN"]
pin          = os.environ["DHAN_PIN"]
totp_secret  = os.environ["DHAN_TOTP_SECRET"]

print(f"Connecting: client_id={client_id}")

gateway = DhanGateway(
    client_id=client_id,
    access_token=access_token,
    pin=pin,
    totp_secret=totp_secret,
    auto_refresh=True,
)

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def run(label, fn):
    try:
        result = fn()
        print(f"\n{PASS}  {label}")
        if isinstance(result, list) and result:
            try:
                if hasattr(result[0], "__dict__"):
                    print(pd.DataFrame([vars(r) for r in result[:3]]).to_string(index=False))
                else:
                    print(result[:3])
            except Exception:
                print(result[:3])
        elif isinstance(result, dict):
            print(pd.DataFrame([result]).to_string(index=False))
        else:
            print(repr(result))
        results.append((label, True, None))
        return result
    except Exception as e:
        print(f"\n{FAIL}  {label}")
        traceback.print_exc()
        results.append((label, False, str(e)))
        return None

# ── 1. Instrument Resolution ──────────────────────────────────────────────────
reliance = run("Resolve RELIANCE (NSE Equity)",
               lambda: gateway.instruments.resolve("RELIANCE", "NSE"))

nifty = run("Resolve NIFTY (Index)",
            lambda: gateway.instruments.resolve("NIFTY", "NSE"))

crude = run("Resolve CRUDEOIL (MCX Commodity)",
            lambda: gateway.instruments.resolve("CRUDEOIL", "MCX"))

silver = run("Resolve SILVER (MCX Commodity)",
             lambda: gateway.instruments.resolve("SILVER", "MCX"))

# ── 2. Historical — NSE Equity ────────────────────────────────────────────────
end = datetime.now(tz=timezone.utc)
start = end - timedelta(days=5)

run("Historical NSE Equity RELIANCE (daily)",
    lambda: gateway.historical.get_historical_candles(
        "RELIANCE", "NSE", start, end, "1D"))

# ── 3. Historical — NSE Futures ───────────────────────────────────────────────
nifty_fut = run("Futures: NIFTY CURRENT (NSE)",
                lambda: gateway.futures.get_contract("NIFTY", "NSE", "CURRENT"))

if nifty_fut:
    run("Historical NSE Futures NIFTY (daily)",
        lambda: gateway.historical.get_historical_candles(
            nifty_fut.symbol, "NFO", start, end, "1D"))

# ── 4. Historical — MCX Commodity ────────────────────────────────────────────
silver_fut = run("Futures: SILVER CURRENT (MCX)",
                 lambda: gateway.futures.get_contract("SILVER", "MCX", "CURRENT"))

if silver_fut:
    run("Historical MCX Futures SILVER (daily)",
        lambda: gateway.historical.get_historical_candles(
            silver_fut.symbol, "MCX", start, end, "1D"))

# ── 5. Options — NSE Expiries + Chain ────────────────────────────────────────
nse_expiries = run("Options Expiries NIFTY (NSE)",
                   lambda: gateway.get_option_expiries("NIFTY", "NSE"))

if nse_expiries:
    nearest_nse = nse_expiries[0]
    run(f"Options Chain NIFTY (NSE) expiry={nearest_nse}",
        lambda: gateway.options.get_option_chain("NIFTY", "NSE", nearest_nse))

# ── 6. Options — MCX Expiries + Chain ────────────────────────────────────────
mcx_expiries = run("Options Expiries CRUDEOIL (MCX)",
                   lambda: gateway.get_option_expiries("CRUDEOIL", "MCX"))

if mcx_expiries:
    nearest_mcx = mcx_expiries[0]
    run(f"Options Chain CRUDEOIL (MCX) expiry={nearest_mcx}",
        lambda: gateway.options.get_option_chain("CRUDEOIL", "MCX", nearest_mcx))

# ── 7. Futures Chain ──────────────────────────────────────────────────────────
run("Futures Chain SILVER (MCX)",
    lambda: gateway.futures.get_futures_chain("SILVER", "MCX"))

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n\n" + "="*60)
print("LIVE ENDPOINT SUMMARY")
print("="*60)
for label, ok, err in results:
    status = PASS if ok else FAIL
    suffix = f" — {err}" if err else ""
    print(f"{status}  {label}{suffix}")

gateway.close()
