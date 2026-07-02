import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath("."))

from brokers.adapters.dhan.auth import DhanAuth

def main():
    load_dotenv(".env.local")
    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    pin = os.environ.get("DHAN_PIN", "")
    totp = os.environ.get("DHAN_TOTP_SECRET", "")
    
    auth = DhanAuth(client_id=client_id, pin=pin, totp_secret=totp)
    try:
        print("Generating using legacy code...")
        token = auth.generate_token()
        print(f"SUCCESS: {token[:10]}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    main()
