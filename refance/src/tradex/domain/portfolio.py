"""Portfolio aggregate — holdings and positions."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from tradex.domain.enums import ExchangeSegment, PositionType, ProductType


@dataclass
class Holding:
    """A single portfolio holding (demat delivery)."""

    security_id: str = ""
    trading_symbol: str = ""
    exchange: str = ""
    isin: str = ""
    total_quantity: int = 0
    dp_quantity: int = 0
    t1_quantity: int = 0
    available_quantity: int = 0
    collateral_quantity: int = 0
    average_cost_price: Decimal = Decimal("0")
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> Holding:
        return cls(
            security_id=str(data.get("securityId", "")),
            trading_symbol=data.get("tradingSymbol", ""),
            exchange=data.get("exchange", ""),
            isin=data.get("isin", ""),
            total_quantity=int(data.get("totalQty", 0)),
            dp_quantity=int(data.get("dpQty", 0)),
            t1_quantity=int(data.get("t1Qty", 0)),
            available_quantity=int(data.get("availableQty", 0)),
            collateral_quantity=int(data.get("collateralQty", 0)),
            average_cost_price=Decimal(str(data.get("avgCostPrice", 0))),
            raw=data,
        )

    @property
    def is_sellable(self) -> bool:
        """Whether this holding can be sold (requires eDIS for delivery)."""
        return self.available_quantity > 0 and self.exchange in ("NSE_EQ", "BSE_EQ")


@dataclass
class Position:
    """A single intraday/margin position."""

    security_id: str = ""
    trading_symbol: str = ""
    exchange_segment: ExchangeSegment = ExchangeSegment.NSE_EQ
    product_type: ProductType = ProductType.INTRADAY
    position_type: PositionType = PositionType.LONG
    buy_average: Decimal = Decimal("0")
    buy_quantity: int = 0
    sell_average: Decimal = Decimal("0")
    sell_quantity: int = 0
    net_quantity: int = 0
    realized_profit: Decimal = Decimal("0")
    unrealized_profit: Decimal = Decimal("0")
    expiry_date: Optional[str] = None
    option_type: Optional[str] = None
    strike_price: Optional[Decimal] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> Position:
        pos_type_str = data.get("positionType", "LONG")
        pos_type_map = {
            "LONG": PositionType.LONG,
            "SHORT": PositionType.SHORT,
            "CLOSED": PositionType.CLOSED,
        }
        product_map = {
            "CNC": ProductType.CNC,
            "INTRADAY": ProductType.INTRADAY,
            "MARGIN": ProductType.MARGIN,
            "MTF": ProductType.MTF,
        }
        segment_map = {
            "NSE_EQ": ExchangeSegment.NSE_EQ,
            "BSE_EQ": ExchangeSegment.BSE_EQ,
            "NSE_FNO": ExchangeSegment.NSE_FNO,
            "BSE_FNO": ExchangeSegment.BSE_FNO,
            "MCX_COMM": ExchangeSegment.MCX_COMM,
        }

        return cls(
            security_id=str(data.get("securityId", "")),
            trading_symbol=data.get("tradingSymbol", ""),
            exchange_segment=segment_map.get(
                data.get("exchangeSegment", ""), ExchangeSegment.NSE_EQ
            ),
            product_type=product_map.get(data.get("productType", ""), ProductType.INTRADAY),
            position_type=pos_type_map.get(pos_type_str, PositionType.LONG),
            buy_average=Decimal(str(data.get("buyAvg", 0))),
            buy_quantity=int(data.get("buyQty", 0)),
            sell_average=Decimal(str(data.get("sellAvg", 0))),
            sell_quantity=int(data.get("sellQty", 0)),
            net_quantity=int(data.get("netQty", 0)),
            realized_profit=Decimal(str(data.get("realizedProfit", 0))),
            unrealized_profit=Decimal(str(data.get("unrealizedProfit", 0))),
            expiry_date=data.get("drvExpiryDate"),
            option_type=data.get("drvOptionType"),
            strike_price=Decimal(str(data["drvStrikePrice"]))
            if data.get("drvStrikePrice")
            else None,
            raw=data,
        )

    @property
    def is_open(self) -> bool:
        return self.net_quantity != 0

    @property
    def total_pnl(self) -> Decimal:
        return self.realized_profit + self.unrealized_profit

    @property
    def notional(self) -> Decimal:
        """Approximate notional value."""
        avg = (self.buy_average * self.buy_quantity + self.sell_average * self.sell_quantity) / max(
            self.buy_quantity + self.sell_quantity, 1
        )
        return avg * abs(self.net_quantity)


@dataclass
class Portfolio:
    """Portfolio aggregate root — collections of holdings and positions."""

    account_id: str
    holdings: list[Holding] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.is_open]

    @property
    def closed_positions(self) -> list[Position]:
        return [p for p in self.positions if not p.is_open]

    @property
    def total_holdings_value(self) -> Decimal:
        return sum(
            (h.average_cost_price * h.total_quantity for h in self.holdings),
            Decimal("0"),
        )

    @property
    def total_realized_pnl(self) -> Decimal:
        return sum((p.realized_profit for p in self.positions), Decimal("0"))

    @property
    def total_unrealized_pnl(self) -> Decimal:
        return sum((p.unrealized_profit for p in self.positions), Decimal("0"))

    @property
    def total_pnl(self) -> Decimal:
        return self.total_realized_pnl + self.total_unrealized_pnl

    def summary(self) -> dict[str, Any]:
        return {
            "holdings_count": len(self.holdings),
            "open_positions": len(self.open_positions),
            "total_holdings_value": float(self.total_holdings_value),
            "realized_pnl": float(self.total_realized_pnl),
            "unrealized_pnl": float(self.total_unrealized_pnl),
            "total_pnl": float(self.total_pnl),
        }
