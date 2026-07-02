import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from brokers.adapters.dhan.gateway import DhanGateway

def test_dhan_live():
    load_dotenv(".env.local")
    
    client_id = os.environ.get("DHAN_CLIENT_ID")
    pin = os.environ.get("DHAN_PIN")
    totp_secret = os.environ.get("DHAN_TOTP_SECRET")
    
    if not (client_id and pin and totp_secret):
        print("Missing Dhan credentials in .env.local")
        return
        
    print(f"Initializing DhanGateway for Client ID: {client_id}")
    
    # Initialize gateway with existing access token to bypass TOTP generation delay
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    gateway = DhanGateway(
        client_id=client_id,
        pin=pin,
        totp_secret=totp_secret,
        access_token=access_token
    )
    
    token = gateway.auth.get_token()
    print(f"1. Token generated: {token[:15]}...{token[-10:] if len(token) > 25 else ''}")
    
    # Check instruments loading
    print("2. Loading instruments...")
    gateway.instruments.load()
    reliance = gateway.instruments.resolve("RELIANCE", "NSE")
    if reliance:
        print(f"   Found {reliance.symbol} (Lot: {reliance.lot_size}) on {reliance.exchange}")
    else:
        print("   Could not resolve RELIANCE")
        
    # Check market data (LTP and Quote)
    try:
        print("3. Fetching Market Data...")
        ltp = gateway.market_data.ltp("RELIANCE", "NSE")
        print(f"   RELIANCE LTP: {ltp}")
        quote = gateway.market_data.quote("RELIANCE", "NSE")
        print(f"   RELIANCE Quote -> Open: {quote.open}, High: {quote.high}, Low: {quote.low}, Close: {quote.close}")
    except Exception as e:
        print(f"   Market Data error: {e}")
        
    # Check historical data
    try:
        print("4. Fetching Historical Data (last 5 days)...")
        end = datetime.now()
        start = end - timedelta(days=5)
        candles = gateway.historical.get_historical_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1D"
        )
        print(f"   Fetched {len(candles)} candles.")
        if candles:
            print(f"   Most recent candle: {candles[-1]}")
    except Exception as e:
        print(f"   Historical Data error: {e}")

    # Check portfolio positions
    try:
        print("5. Fetching Portfolio Positions...")
        positions = gateway.portfolio.positions()
        print(f"   Positions found: {len(positions)}")
    except Exception as e:
        print(f"   Portfolio error: {e}")

    print("\nLive test complete!")

if __name__ == "__main__":
    test_dhan_live()
