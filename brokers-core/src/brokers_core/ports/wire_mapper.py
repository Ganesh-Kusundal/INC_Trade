"""Wire mapper protocol — translates domain enums to broker wire codes.

Every broker adapter must implement this protocol to formalize the
domain-enum → broker-wire-code translation. This eliminates inline
mapping dicts scattered across adapter config files.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from inc_trade.domain.enums import OrderType, ProductType, Side, Validity


@runtime_checkable
class WireMapper(Protocol):
    """Protocol for translating domain enums to broker wire codes.

    Each broker adapter implements this protocol to provide
    broker-specific wire format mappings.
    """

    def map_side(self, side: Side) -> str | int:
        """Translate domain Side to broker wire code."""
        ...

    def map_order_type(self, order_type: OrderType) -> str | int:
        """Translate domain OrderType to broker wire code."""
        ...

    def map_product_type(self, product_type: ProductType) -> str | int:
        """Translate domain ProductType to broker wire code."""
        ...

    def map_validity(self, validity: Validity) -> str | int:
        """Translate domain Validity to broker wire code."""
        ...

    def unmap_order_type(self, wire_code: str) -> OrderType:
        """Translate broker wire code back to domain OrderType."""
        ...

    def unmap_product_type(self, wire_code: str) -> ProductType:
        """Translate broker wire code back to domain ProductType."""
        ...

    def unmap_side(self, wire_code: str) -> Side:
        """Translate broker wire code back to domain Side."""
        ...
