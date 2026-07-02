from typing import Protocol, List
from domain.models import OrderCommand, OrderResponse, Instrument

class BrokerPort(Protocol):
    async def authenticate(self) -> bool:
        ...
        
    async def place_order(self, command: OrderCommand) -> OrderResponse:
        ...
        
    async def cancel_order(self, order_id: str) -> bool:
        ...
        
    async def download_instruments(self) -> List[Instrument]:
        ...
        
    async def get_historical_data(self, instrument: Instrument, from_date: str, to_date: str) -> dict:
        ...
