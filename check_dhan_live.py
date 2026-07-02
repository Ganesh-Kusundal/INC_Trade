import asyncio
import os
import sys
from dotenv import load_dotenv

# Add current directory to python path
sys.path.insert(0, os.path.abspath("."))

from brokers.dhan.adapter import DhanBrokerAdapter
from brokers.config_app import settings

async def test_live_dhan():
    load_dotenv(".env.local")
    
    # Override settings explicitly for test
    settings.dhan.client_id = os.environ.get("DHAN_CLIENT_ID", "")
    settings.dhan.pin = os.environ.get("DHAN_PIN", "")
    settings.dhan.totp_secret = os.environ.get("DHAN_TOTP_SECRET", "")

    print(f"--- Live Dhan Connection Test (Greenfield HTTPX) ---")
    print(f"Client ID: {settings.dhan.client_id}")
    
    if not (settings.dhan.client_id and settings.dhan.pin and settings.dhan.totp_secret):
        print("Missing credentials in .env.local")
        return
        
    print("Authenticating with Dhan APIs using Greenfield Adapter...")
    try:
        adapter = DhanBrokerAdapter()
        # Force fresh token generation by clearing any expired token from environment
        adapter.access_token = ""
        success = await adapter.authenticate()
        if success and adapter.access_token:
            print(f"   SUCCESS! Token generated: {adapter.access_token[:15]}... (truncated)")
            
            print("Checking /v2/fundlimit...")
            headers = {
                "access-token": adapter.access_token,
                "client-id": settings.dhan.client_id,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            resp = await adapter.http_client.request("GET", "/v2/fundlimit", headers=headers)
            print(f"   Fundlimit Status: {resp.status_code}")
            
            print("Fetching instruments...")
            instruments = await adapter.download_instruments()
            reliance = instruments[0]  # This is the dummy RELIANCE we mapped
            
            print("Fetching historical data for RELIANCE (Last 5 days)...")
            from datetime import datetime, timedelta
            end = datetime.now()
            start = end - timedelta(days=5)
            
            historical = await adapter.get_historical_data(
                instrument=reliance,
                from_date=start.strftime("%Y-%m-%d"),
                to_date=end.strftime("%Y-%m-%d")
            )
            
            if historical.get("status") == "success" and "data" in historical:
                print(f"   SUCCESS! Historical Data fetched.")
                print(f"   Data Keys: {list(historical['data'].keys())}")
                if "close" in historical["data"] and len(historical["data"]["close"]) > 0:
                    print(f"   Most recent close price: {historical['data']['close'][-1]}")
            else:
                print(f"   FAILED to fetch historical data: {historical}")
        else:
            print("   FAILED! Login returned no token.")
    except Exception as e:
        print(f"   FAILED to authenticate: {e}")
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            print(f"   Response Body: {e.response.text}")
    finally:
        await adapter.http_client.close()
        await adapter.auth_client.close()

if __name__ == "__main__":
    asyncio.run(test_live_dhan())
