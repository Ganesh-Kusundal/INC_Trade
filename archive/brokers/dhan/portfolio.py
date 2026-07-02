"""Portfolio adapter — positions, holdings, balance."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.segments import segment_to_exchange
from domain import Balance, Holding, Position, ProductType

logger = logging.getLogger(__name__)


class PortfolioAdapter:
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        # The portfolio adapter is read-side only: it parses Dhan's
        # positions/holdings/balance responses and never builds a
        # security_id-bearing payload. It still receives the identity
        # provider to keep the constructor signature aligned with the
        # rest of the adapter layer; the underlying resolver is the
        # only thing it would ever need.
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def get_positions(self) -> list[Position]:
        data = self._client.get("/positions")
        items = data.get("data", []) if isinstance(data, dict) else []
        positions = []
        for item in items if isinstance(items, list) else []:
            positions.append(
                Position(
                    symbol=str(item.get("tradingSymbol", "")),
                    exchange=segment_to_exchange(item.get("exchangeSegment", "NSE_EQ")),
                    quantity=int(item.get("netQuantity", 0)),
                    avg_price=Decimal(str(item.get("buyAveragePrice", 0))),
                    ltp=Decimal(str(item.get("lastPrice", 0))),
                    unrealized_pnl=Decimal(str(item.get("unrealizedPnl", 0))),
                    realized_pnl=Decimal(str(item.get("realizedPnl", 0))),
                    product_type=_parse_product(item.get("productType", "INTRADAY")),
                )
            )
        logger.info("positions_fetched", extra={"count": len(positions)})
        return positions

    def get_holdings(self) -> list[Holding]:
        data = self._client.get("/holdings")
        items = data.get("data", []) if isinstance(data, dict) else []
        holdings = []
        for item in items if isinstance(items, list) else []:
            qty = int(item.get("totalQty", item.get("quantity", 0)))
            avg_px = Decimal(str(item.get("avgCostPrice", item.get("costPrice", 0))))
            ltp = Decimal(str(item.get("lastTradedPrice", item.get("lastPrice", 0))))
            pnl_raw = item.get("pnlValue")
            if pnl_raw is not None:
                pnl = Decimal(str(pnl_raw))
            elif avg_px > 0 and ltp > 0:
                pnl = (ltp - avg_px) * qty
            else:
                pnl = Decimal("0")
            holdings.append(
                Holding(
                    symbol=str(item.get("tradingSymbol", "")),
                    exchange=segment_to_exchange(item.get("exchangeSegment", "NSE_EQ")),
                    quantity=qty,
                    available_quantity=int(
                        item.get("availableQty", item.get("availableQuantity", 0))
                    ),
                    avg_price=avg_px,
                    ltp=ltp,
                    pnl=pnl,
                )
            )
        logger.info("holdings_fetched", extra={"count": len(holdings)})
        return holdings

    def get_balance(self) -> Balance:
        data = self._client.get("/fundlimit")
        raw = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(raw, dict):
            logger.warning("balance_fetch_failed", extra={"reason": "unexpected_response_type"})
            return Balance()
        balance = Balance(
            available_balance=Decimal(
                str(raw.get("availabelBalance", raw.get("availableBalance", 0)))
            ),
            sod_limit=Decimal(str(raw.get("sodLimit", 0))),
            collateral_amount=Decimal(str(raw.get("collateralAmount", 0))),
            utilized_amount=Decimal(str(raw.get("utilizedAmount", 0))),
            withdrawable_balance=Decimal(str(raw.get("withdrawableBalance", 0))),
        )
        logger.info("balance_fetched", extra={"available_balance": str(balance.available_balance)})
        return balance


def _parse_product(pt: str) -> ProductType:
    try:
        return ProductType(str(pt))
    except ValueError:
        return ProductType.INTRADAY
