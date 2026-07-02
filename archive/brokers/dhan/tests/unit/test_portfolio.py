"""Unit tests for PortfolioAdapter."""

from decimal import Decimal

from brokers.dhan.domain import ProductType
from brokers.dhan.portfolio import PortfolioAdapter


def test_get_positions_parsing(fake_client, resolver):
    fake_client.set_response(
        "GET",
        "/positions",
        {
            "data": [
                {
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "netQuantity": 10,
                    "buyAveragePrice": 2440.0,
                    "lastPrice": 2455.0,
                    "unrealizedPnl": 150.0,
                    "realizedPnl": 0.0,
                    "productType": "INTRADAY",
                },
                {
                    "tradingSymbol": "NIFTY 26 JUN FUT",
                    "exchangeSegment": "NSE_FNO",
                    "netQuantity": -75,
                    "buyAveragePrice": 24600.0,
                    "lastPrice": 24550.0,
                    "unrealizedPnl": -3750.0,
                    "realizedPnl": 500.0,
                    "productType": "MARGIN",
                },
            ]
        },
    )
    adapter = PortfolioAdapter(fake_client, resolver)
    positions = adapter.get_positions()
    assert len(positions) == 2

    first = positions[0]
    assert first.symbol == "RELIANCE"
    assert first.exchange == "NSE"
    assert first.quantity == 10
    assert first.avg_price == Decimal("2440.0")
    assert first.ltp == Decimal("2455.0")
    assert first.unrealized_pnl == Decimal("150.0")
    assert first.realized_pnl == Decimal("0.0")
    assert first.product_type == ProductType.INTRADAY

    second = positions[1]
    assert second.symbol == "NIFTY 26 JUN FUT"
    assert second.quantity == -75
    assert second.unrealized_pnl == Decimal("-3750.0")
    assert second.product_type == ProductType.MARGIN


def test_get_holdings_computes_pnl(fake_client, resolver):
    """When pnlValue is absent, PnL should be computed as (ltp - avg) * qty."""
    fake_client.set_response(
        "GET",
        "/holdings",
        {
            "data": [
                {
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "totalQty": 50,
                    "availableQty": 50,
                    "avgCostPrice": 2400.0,
                    "lastTradedPrice": 2450.0,
                    # No pnlValue — should be computed
                },
            ]
        },
    )
    adapter = PortfolioAdapter(fake_client, resolver)
    holdings = adapter.get_holdings()
    assert len(holdings) == 1

    h = holdings[0]
    expected_pnl = (Decimal("2450.0") - Decimal("2400.0")) * 50
    assert h.pnl == expected_pnl
    assert h.pnl == Decimal("2500.0")


def test_get_holdings_uses_dhan_field_names(fake_client, resolver):
    """Verify that Dhan-specific field names (totalQty, availableQty, avgCostPrice, lastTradedPrice) are used."""
    fake_client.set_response(
        "GET",
        "/holdings",
        {
            "data": [
                {
                    "tradingSymbol": "RELIANCE",
                    "exchangeSegment": "NSE_EQ",
                    "totalQty": 100,
                    "availableQty": 80,
                    "avgCostPrice": 2350.5,
                    "lastTradedPrice": 2450.75,
                    "pnlValue": 10025.0,
                },
            ]
        },
    )
    adapter = PortfolioAdapter(fake_client, resolver)
    holdings = adapter.get_holdings()
    assert len(holdings) == 1

    h = holdings[0]
    assert h.quantity == 100
    assert h.available_quantity == 80
    assert h.avg_price == Decimal("2350.5")
    assert h.ltp == Decimal("2450.75")
    assert h.pnl == Decimal("10025.0")


def test_get_balance_dhan_typo(fake_client, resolver):
    """Dhan uses 'availabelBalance' (a typo) in their API response."""
    fake_client.set_response(
        "GET",
        "/fundlimit",
        {
            "data": {
                "availabelBalance": 500000.0,
                "sodLimit": 1000000.0,
                "collateralAmount": 200000.0,
                "utilizedAmount": 300000.0,
                "withdrawableBalance": 400000.0,
            }
        },
    )
    adapter = PortfolioAdapter(fake_client, resolver)
    balance = adapter.get_balance()
    assert balance.available_balance == Decimal("500000.0")
    assert balance.sod_limit == Decimal("1000000.0")
    assert balance.collateral_amount == Decimal("200000.0")
    assert balance.utilized_amount == Decimal("300000.0")
    assert balance.withdrawable_balance == Decimal("400000.0")
