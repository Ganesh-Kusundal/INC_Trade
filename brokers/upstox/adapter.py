import uuid
import logging
from typing import List
from core.config import settings
from domain.ports import BrokerPort
from domain.models import OrderCommand, OrderResponse, OrderStatus, Instrument
from infrastructure.http_client import BaseResilientHttpClient

logger = logging.getLogger(__name__)

class UpstoxBrokerAdapter(BrokerPort):
    def __init__(self):
        self.http_client = BaseResilientHttpClient(base_url="https://api.upstox.com/v2")
        self.access_token = ""

    async def authenticate(self) -> bool:
        """
        Upstox natively relies on an interactive PKCE OAuth flow. 
        For automation parity with legacy, we assume the token is provisioned out-of-band via webhook or env.
        """
        import os
        self.access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
        if self.access_token:
            self.http_client.client.headers.update({
                "Authorization": f"Bearer {self.access_token}",
                "Api-Version": "2.0"
            })
            return True
        return False

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
            "quantity": command.quantity,
            "product": "D", # Delivery/Margin
            "validity": "DAY",
            "price": command.price if command.price else 0,
            "tag": command.correlation_id,
            "instrument_token": command.instrument.broker_token,
            "order_type": command.type.value,
            "transaction_type": command.side.value,
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False
        }
        
        try:
            response = await self.http_client.request(
                "POST",
                "/order/place",
                json=payload
            )
            data = response.json()
            if data.get("status") == "success":
                return OrderResponse(
                    order_id=data["data"]["order_id"],
                    status=OrderStatus.OPEN,
                    message="Placed successfully via V3."
                )
            else:
                # Upstox returns 200 OK even for some logical rejections, catching here
                return OrderResponse(
                    order_id=str(uuid.uuid4()),
                    status=OrderStatus.REJECTED,
                    message=data.get("errors", [{"message": "Unknown"}])[0]["message"]
                )
        except Exception as e:
            logger.error(f"Upstox place_order failed: {e}")
            return OrderResponse(
                order_id=str(uuid.uuid4()),
                status=OrderStatus.REJECTED,
                message=str(e)
            )

    async def cancel_order(self, order_id: str) -> bool:
        try:
            response = await self.http_client.request(
                "DELETE",
                "/order/cancel",
                params={"order_id": order_id}
            )
            data = response.json()
            return data.get("status") == "success"
        except Exception:
            return False

    async def download_instruments(self) -> List[Instrument]:
        """
        Upstox pushes a heavy JSON.gz file for instruments.
        MVP: Stubbing the massive download to prevent blocking the async loop.
        """
        # In a full implementation, this uses a chunked stream reader to prevent memory explosion.
        return [
            Instrument(
                symbol="NIFTY 50",
                exchange="NSE",
                broker_token="NSE_INDEX|Nifty 50",
                lot_size=1,
                tick_size=0.05
            )
        ]
