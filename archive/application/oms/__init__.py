"""Application OMS stubs for test compatibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TradingContext:
    """Stub trading context."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class OrderManager:
    """Stub order manager."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class OmsOrderCommand:
    """Stub OMS order command."""

    def __init__(self, **kwargs: Any) -> None:
        pass


@dataclass
class OrderRequest:
    """Stub order request."""
    symbol: str = ""
    exchange: str = "NSE"
    side: Any = None
    quantity: int = 0
    order_type: Any = None
    product: Any = None
    validity: Any = None
    price: float = 0.0
    trigger_price: float = 0.0
    tag: str = ""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class PositionManager:
    """Stub position manager."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class RiskConfig:
    """Stub risk configuration."""
    max_order_quantity: int = 100000
    max_order_value: float = 10_000_000.0
    max_open_positions: int = 50
    max_day_loss: float = 100_000.0

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class RiskManager:
    """Stub risk manager."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class DailyPnlResetScheduler:
    """Stub daily PnL reset scheduler."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass
