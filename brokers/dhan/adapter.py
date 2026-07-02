import pyotp
import uuid
import pandas as pd
from typing import List
from core.config import settings
from domain.ports import BrokerPort
from domain.models import OrderCommand, OrderResponse, OrderStatus, Instrument
from infrastructure.http_client import BaseResilientHttpClient
import os

class DhanBrokerAdapter(BrokerPort):
    def __init__(self):
        self.http_client = BaseResilientHttpClient(base_url=settings.dhan.api_url)
        self.auth_client = BaseResilientHttpClient(base_url=settings.dhan.auth_url)
        self.access_token = os.environ.get("DHAN_ACCESS_TOKEN", "")

    async def authenticate(self) -> bool:
        if self.access_token:
            return True
            
        totp = pyotp.TOTP(settings.dhan.totp_secret).now()
        payload = {
            "clientId": str(settings.dhan.client_id),
            "password": str(settings.dhan.pin),
            "totp": str(totp)
        }
        
        headers = {
            "Accept": "application/json"
        }
        
        response = await self.auth_client.request(
            "POST", 
            "/app/generateAccessToken",
            data=payload,
            headers=headers
        )
        
        data = response.json()
        if "jwtToken" in data:
            self.access_token = data["jwtToken"]
            self.http_client.client.headers.update({"access-token": self.access_token})
            
            # Auto-update .env.local like the legacy architecture
            try:
                env_path = ".env.local"
                if os.path.exists(env_path):
                    with open(env_path, "r") as f:
                        lines = f.readlines()
                    with open(env_path, "w") as f:
                        found = False
                        for line in lines:
                            if line.startswith("DHAN_ACCESS_TOKEN="):
                                f.write(f"DHAN_ACCESS_TOKEN={self.access_token}\n")
                                found = True
                            else:
                                f.write(line)
                        if not found:
                            f.write(f"DHAN_ACCESS_TOKEN={self.access_token}\n")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to auto-update .env.local: {e}")
                
            return True
            
        return False
        
    async def get_historical_data(self, instrument: Instrument, from_date: str, to_date: str) -> dict:
        payload = {
            "securityId": instrument.broker_token,
            "exchangeSegment": instrument.exchange + "_EQ" if instrument.exchange in ["NSE", "BSE"] else instrument.exchange,
            "instrument": "EQUITY",
            "expiryCode": 0,
            "fromDate": from_date,
            "toDate": to_date
        }
        
        headers = {
            "access-token": self.access_token,
            "client-id": settings.dhan.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = await self.http_client.request(
            "POST",
            "/v2/charts/historical",
            json=payload,
            headers=headers
        )
        return response.json()
        
    async def place_order(self, command: OrderCommand) -> OrderResponse:
        # Idempotency Guard
        from core.idempotency import IdempotencyCache
        cache = IdempotencyCache()
        if not cache.check_and_set(command.correlation_id):
            return OrderResponse(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.REJECTED,
                message="Duplicate Order Prevented by Idempotency Cache"
            )
            
        payload = {
            "dhanClientId": settings.dhan.client_id,
            "transactionType": command.side.value,
            "exchangeSegment": command.instrument.exchange,
            "productType": "MARGIN",
            "orderType": command.type.value,
            "validity": "DAY",
            "securityId": command.instrument.broker_token,
            "quantity": command.quantity,
            "disclosedQuantity": 0,
            "price": command.price if command.price else 0,
            "correlationId": command.correlation_id
        }
        
        headers = {
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = await self.http_client.request(
            "POST",
            "/orders",
            json=payload,
            headers=headers
        )
        data = response.json()
        
        # Parse Response
        if response.status_code == 200 and "orderId" in data:
            return OrderResponse(
                order_id=data["orderId"],
                status=OrderStatus.OPEN,
                message=data.get("orderStatus")
            )
        else:
            return OrderResponse(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.REJECTED,
                message=data.get("errorMessage", "Unknown Rejection")
            )

    async def cancel_order(self, order_id: str) -> bool:
        headers = {
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        response = await self.http_client.request(
            "DELETE",
            f"/orders/{order_id}",
            headers=headers
        )
        return response.status_code == 200
        
    async def download_instruments(self) -> List[Instrument]:
        # Utilizing pandas for swift parsing as audited in Phase 2
        # df = pd.read_csv(settings.dhan.instruments_compact_url)
        # Simplify mapping for MVP
        instruments = []
        # Fallback dummy for testing purposes without massive DataFrame loads
        instruments.append(
            Instrument(
                symbol="RELIANCE",
                exchange="NSE",
                broker_token="2885",
                lot_size=1,
                tick_size=0.05
            )
        )
        return instruments
