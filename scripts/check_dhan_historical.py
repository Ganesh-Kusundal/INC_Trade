import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Add the project root to sys.path so we can import 'brokers'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brokers import connect as create_broker


def main():
    # Load credentials from .env.local in the root directory
    env_path = Path(__file__).resolve().parent.parent / ".env.local"
    load_dotenv(env_path)

    # Attempt to fetch credentials from environment variables
    client_id = os.environ.get("DHAN_CLIENT_ID") or os.environ.get("CLIENT_ID")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN") or os.environ.get("ACCESS_TOKEN")

    if not client_id or not access_token:
        print(f"Error: Could not find Dhan credentials in {env_path}.")
        print("Please ensure DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN are set.")
        sys.exit(1)

    print("Initializing Dhan Broker Session...")
    # Using auto_refresh=False for a quick one-off script
    broker = create_broker(
        "dhan", client_id=client_id, access_token=access_token, auto_refresh=False
    )

    symbol = "HEG"
    exchange = "NSE"
    # IMPORTANT: Use uppercase '1D' because Dhan adapter is case-sensitive for daily intervals
    interval = "1D"

    # Let's fetch data for the last 30 days
    to_date = datetime.now()
    from_date = to_date - timedelta(days=30)

    print(f"\nFetching historical {interval} candles for {symbol} on {exchange}...")
    print(f"Time range: {from_date.strftime('%Y-%m-%d')} to {to_date.strftime('%Y-%m-%d')}")

    try:
        candles = broker.market.ohlcv(
            symbol=symbol,
            exchange=exchange,
            start_time=from_date,
            end_time=to_date,
            resolution=interval,
        )

        if not candles:
            print(
                "No candles returned. (Is the market closed for the entire duration, or invalid credentials?)"
            )
        else:
            print(f"\nSuccess! Retrieved {len(candles)} candles.")
            print("Showing the last 5 candles:")
            for candle in candles[-5:]:
                print(
                    f"  Time: {candle.timestamp}, Open: {candle.open}, High: {candle.high}, Low: {candle.low}, Close: {candle.close}, Vol: {candle.volume}"
                )

    except Exception as e:
        print(f"\nError occurred while fetching data: {e}")
    finally:
        broker.close()


if __name__ == "__main__":
    main()
