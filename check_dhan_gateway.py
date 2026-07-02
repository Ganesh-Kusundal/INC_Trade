import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))
from brokers.dhan.adapter import DhanBrokerAdapter
from brokers.domain.enums import OrderType, Side as OrderSide
from brokers.config_app import settings

async def main():
    load_dotenv(".env.local")
    
    settings.dhan.client_id = os.environ.get("DHAN_CLIENT_ID", "")
    settings.dhan.pin = os.environ.get("DHAN_PIN", "")
    settings.dhan.totp_secret = os.environ.get("DHAN_TOTP_SECRET", "")
    
    print("--- Testing Greenfield Gateway (DhanBrokerAdapter) ---")
    gateway = DhanBrokerAdapter()
    
    # 1. Authentication
    print("\n1. Testing Authentication...")
    auth_success = await gateway.authenticate()
    print(f"Auth Success: {auth_success}")
    if not auth_success:
        print("Stopping tests. Please manually update DHAN_ACCESS_TOKEN in .env.local.")
        return
    print(f"Active Token: {gateway.access_token[:10]}... (truncated)")
        
    # 2. Instruments
    print("\n2. Testing Instruments...")
    instruments = await gateway.download_instruments()
    reliance = instruments[0]
    print(f"Loaded Instrument: {reliance.symbol} on {reliance.exchange}")
    
    # 3. Historical Data
    print("\n3. Testing Historical Data...")
    end = datetime.now()
    start = end - timedelta(days=5)
    hist_data = await gateway.get_historical_data(
        reliance, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    )
    if "status" in hist_data or "data" in hist_data:
        print(f"Historical Data Response Keys: {list(hist_data.keys())}")
    else:
        print(f"Historical Data Error/Unknown: {hist_data}")
        
    # 4. Order Management (Safe rejection/Idempotency check)
    print("\n4. Testing Order Management (Idempotency)...")
    corr_id = str(uuid.uuid4())
    cmd = OrderCommand(
        instrument=reliance,
        type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=1,
        correlation_id=corr_id
    )
    try:
        resp1 = await gateway.place_order(cmd)
        print(f"Order 1 Response: {resp1.status} - {resp1.message}")
    except Exception as e:
        print(f"Order 1 Exception: {e}")
        
    # Idempotency check with the exact same correlation_id
    try:
        resp2 = await gateway.place_order(cmd)
        print(f"Order 2 (Duplicate) Response: {resp2.status} - {resp2.message}")
    except Exception as e:
        print(f"Order 2 Exception: {e}")

    await gateway.http_client.close()
    await gateway.auth_client.close()
    print("\n--- Gateway Test Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
