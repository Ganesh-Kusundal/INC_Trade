"""Tests for enhanced MarginAdapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.dhan.domain import MarginRequest, MarginResponse
from brokers.dhan.margin import MarginAdapter


class TestMarginDomain:
    """Test margin domain types."""

    def test_margin_request_creation(self):
        """MarginRequest should create successfully."""
        req = MarginRequest(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=1,
            product_type="INTRADAY",
            order_type="MARKET",
        )
        assert req.symbol == "RELIANCE"
        assert req.quantity == 1

    def test_margin_request_with_price(self):
        """MarginRequest should accept optional price."""
        req = MarginRequest(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=1,
            product_type="INTRADAY",
            order_type="LIMIT",
            price=Decimal("2500.00"),
        )
        assert req.price == Decimal("2500.00")

    def test_margin_response_creation(self):
        """MarginResponse should create successfully."""
        resp = MarginResponse(
            total_margin=Decimal("1234.50"),
            order_margin=Decimal("1000.00"),
            exposure_margin=Decimal("234.50"),
        )
        assert resp.total_margin == Decimal("1234.50")
        assert resp.order_margin == Decimal("1000.00")
        assert resp.exposure_margin == Decimal("234.50")


class TestMarginAdapter:
    """Test margin adapter functionality."""

    def test_calculate_margin_success(self, fake_client, resolver):
        """Should calculate margin and return MarginResponse."""
        fake_client.set_response(
            "POST",
            "/margincalculator",
            {
                "data": {
                    "totalMargin": 1234.50,
                    "orderMargin": 1000.00,
                    "exposureMargin": 234.50,
                }
            },
        )

        adapter = MarginAdapter(fake_client, resolver)
        result = adapter.calculate(
            MarginRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=1,
                product_type="INTRADAY",
                order_type="MARKET",
            )
        )

        assert isinstance(result, MarginResponse)
        assert result.total_margin == Decimal("1234.50")
        assert result.order_margin == Decimal("1000.00")
        assert result.exposure_margin == Decimal("234.50")

    def test_calculate_margin_validation_negative_quantity(self, fake_client, resolver):
        """Should reject negative quantity."""
        adapter = MarginAdapter(fake_client, resolver)

        with pytest.raises(ValueError, match="Quantity must be positive"):
            adapter.calculate(
                MarginRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    quantity=-1,
                    product_type="INTRADAY",
                    order_type="MARKET",
                )
            )

    def test_calculate_margin_validation_zero_quantity(self, fake_client, resolver):
        """Should reject zero quantity."""
        adapter = MarginAdapter(fake_client, resolver)

        with pytest.raises(ValueError, match="Quantity must be positive"):
            adapter.calculate(
                MarginRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    quantity=0,
                    product_type="INTRADAY",
                    order_type="MARKET",
                )
            )

    def test_calculate_margin_validation_limit_no_price(self, fake_client, resolver):
        """Should reject LIMIT order without price."""
        adapter = MarginAdapter(fake_client, resolver)

        with pytest.raises(ValueError, match="require price"):
            adapter.calculate(
                MarginRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    quantity=1,
                    product_type="INTRADAY",
                    order_type="LIMIT",
                )
            )

    def test_calculate_margin_with_price(self, fake_client, resolver):
        """Should include price in API payload for LIMIT orders."""
        fake_client.set_response(
            "POST",
            "/margincalculator",
            {
                "data": {
                    "totalMargin": 500.00,
                    "orderMargin": 400.00,
                    "exposureMargin": 100.00,
                }
            },
        )

        adapter = MarginAdapter(fake_client, resolver)
        adapter.calculate(
            MarginRequest(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=1,
                product_type="INTRADAY",
                order_type="LIMIT",
                price=Decimal("2500.00"),
            )
        )

        # Verify price was sent in payload
        payloads = fake_client.calls_for("POST", "/margincalculator")
        assert len(payloads) == 1
        assert "price" in payloads[0]
        assert payloads[0]["price"] == 2500.00
