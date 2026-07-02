from enum import Enum
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class Instrument(BaseModel):
    symbol: str
    exchange: str
    broker_token: str
    lot_size: int = 1
    tick_size: float = 0.05

class OrderCommand(BaseModel):
    instrument: Instrument
    side: OrderSide
    type: OrderType
    quantity: int
    price: Optional[float] = None
    correlation_id: str

class OrderResponse(BaseModel):
    order_id: str
    status: OrderStatus
    message: Optional[str] = None
    average_price: float = 0.0
    filled_quantity: int = 0
