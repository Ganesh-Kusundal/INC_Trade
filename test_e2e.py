import asyncio
import os
import uuid
from brokers.dhan.adapter import DhanBrokerAdapter
from brokers.upstox.adapter import UpstoxBrokerAdapter
from core.reconciliation import ReconciliationEngine
from domain.models import OrderCommand, OrderSide, OrderType

async def run_e2e_test():
    print("--- Greenfield E2E Verification ---")
    
    # 1. Dhan Setup
    dhan = DhanBrokerAdapter()
    os.environ["DHAN_ACCESS_TOKEN"] = "mock_token_123"
    dhan.access_token = "mock_token_123"
    await dhan.authenticate()
    dhan_instruments = await dhan.download_instruments()
    
    # 2. Upstox Setup
    upstox = UpstoxBrokerAdapter()
    os.environ["UPSTOX_ACCESS_TOKEN"] = "mock_upstox_123"
    await upstox.authenticate()
    upstox_instruments = await upstox.download_instruments()
    
    # 3. Reconciliation Engine
    engine = ReconciliationEngine(broker=dhan, sync_interval_seconds=1)
    engine.start()
    
    print(f"Dhan loaded: {dhan_instruments[0].symbol}")
    print(f"Upstox loaded: {upstox_instruments[0].symbol}")
    
    # 4. Order Placements
    cmd1 = OrderCommand(
        instrument=dhan_instruments[0],
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=1,
        correlation_id=str(uuid.uuid4())
    )
    cmd2 = OrderCommand(
        instrument=upstox_instruments[0],
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=1,
        correlation_id=str(uuid.uuid4())
    )
    
    try:
        r1 = await dhan.place_order(cmd1)
        print(f"Dhan Order 1: {r1.status}")
    except Exception as e:
        print(f"Dhan Order cleanly rejected: {e}")
        
    try:
        # Duplicate command test for Idempotency
        r1_dup = await dhan.place_order(cmd1)
        print(f"Dhan Duplicate Order: {r1_dup.status} - {r1_dup.message}")
    except Exception as e:
        pass
        
    try:
        r2 = await upstox.place_order(cmd2)
        print(f"Upstox Order 1: {r2.status} - {r2.message}")
    except Exception as e:
        print(f"Upstox Order cleanly rejected: {e}")
        
    try:
        # Duplicate command test for Idempotency
        r2_dup = await upstox.place_order(cmd2)
        print(f"Upstox Duplicate Order: {r2_dup.status} - {r2_dup.message}")
    except Exception as e:
        pass
        
    # Let recon engine run for a second
    await asyncio.sleep(2)
    await engine.stop()
    
    await dhan.http_client.close()
    await dhan.auth_client.close()
    await upstox.http_client.close()
    print("--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(run_e2e_test())
