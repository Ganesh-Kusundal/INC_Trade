import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from brokers.adapters.dhan.gateway import DhanGateway

def test_dhan_fast():
    load_dotenv(".env.local")
    
    client_id = os.environ.get("DHAN_CLIENT_ID")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN")
    
    print(f"Initializing DhanGateway for Client ID: {client_id}")
    
    gateway = DhanGateway(
        client_id=client_id,
        access_token=access_token
    )
    
    print("Testing Auth: Is authenticated?", gateway.auth.is_authenticated())
    
    try:
        print("Testing Portfolio Funds (No CSV needed)...")
        funds = gateway.portfolio.funds()
        print(f"Available Cash: {funds.available_cash}")
    except Exception as e:
        print(f"Funds error: {e}")

if __name__ == "__main__":
    test_dhan_fast()
