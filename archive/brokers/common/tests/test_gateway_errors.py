"""Tests for :class:`brokers.common.gateway_errors.UnsupportedGatewayOperation`.

Since the REF-18 LSP fix, :class:`~datalake.gateway.DataLakeGateway` no longer
inherits the full ``MarketDataGateway`` contract.  Trading and portfolio methods
are intentionally absent — calling them on a DataLakeGateway raises
``AttributeError`` (not ``UnsupportedGatewayOperation``).  Only ``stream()``
still raises ``UnsupportedGatewayOperation``.
"""

from __future__ import annotations

import pytest

from brokers.common.gateway_errors import (
    UnsupportedGatewayOperationError as UnsupportedGatewayOperation,
)
from datalake.gateway import DataLakeGateway


def test_exception_carries_gateway_and_operation() -> None:
    exc = UnsupportedGatewayOperation("DataLakeGateway", "trading")

    assert exc.gateway == "DataLakeGateway"
    assert exc.operation == "trading"
    assert str(exc) == "DataLakeGateway does not support trading"
    assert isinstance(exc, NotImplementedError)


@pytest.mark.parametrize(
    ("method_name",),
    [
        ("place_order",),
        ("cancel_order",),
        ("get_orderbook",),
        ("get_trade_book",),
        ("positions",),
        ("holdings",),
        ("funds",),
        ("trades",),
    ],
)
def test_datalake_gateway_raises_attribute_error_for_removed_methods(
    method_name: str,
) -> None:
    """DataLakeGateway no longer has trading/portfolio methods (REF-18 LSP fix).
    Accessing them raises ``AttributeError``."""
    gw = DataLakeGateway(root="market_data")

    with pytest.raises(AttributeError):
        getattr(gw, method_name)


def test_datalake_stream_raises_unsupported() -> None:
    gw = DataLakeGateway(root="market_data")
    with pytest.raises(UnsupportedGatewayOperation) as exc_info:
        gw.stream(["RELIANCE"], exchange="NSE")
    assert exc_info.value.gateway == "DataLakeGateway"
    assert exc_info.value.operation == "streaming"
