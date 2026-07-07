"""Validation framework.

Provider-agnostic validation with clear error messages.
"""

from __future__ import annotations

from typing import Any

from tradex.core.errors import ValidationError


class Validator:
    """Builder for validation rules."""

    def __init__(self, value: Any, field_name: str = "field") -> None:
        self._value = value
        self._field = field_name
        self._errors: list[str] = []

    @classmethod
    def check(cls, value: Any, field_name: str = "field") -> Validator:
        """Start validating a value."""
        return cls(value, field_name)

    def required(self) -> Validator:
        """Value must not be None or empty."""
        if self._value is None:
            self._errors.append(f"{self._field} is required")
        elif isinstance(self._value, str) and not self._value.strip():
            self._errors.append(f"{self._field} must not be empty")
        return self

    def not_none(self) -> Validator:
        """Value must not be None."""
        if self._value is None:
            self._errors.append(f"{self._field} must not be None")
        return self

    def min_value(self, minimum: float) -> Validator:
        """Value must be >= minimum."""
        if self._value is not None and self._value < minimum:
            self._errors.append(f"{self._field} must be >= {minimum}, got {self._value}")
        return self

    def max_value(self, maximum: float) -> Validator:
        """Value must be <= maximum."""
        if self._value is not None and self._value > maximum:
            self._errors.append(f"{self._field} must be <= {maximum}, got {self._value}")
        return self

    def positive(self) -> Validator:
        """Value must be > 0."""
        if self._value is not None and self._value <= 0:
            self._errors.append(f"{self._field} must be positive, got {self._value}")
        return self

    def non_negative(self) -> Validator:
        """Value must be >= 0."""
        if self._value is not None and self._value < 0:
            self._errors.append(f"{self._field} must be non-negative, got {self._value}")
        return self

    def one_of(self, allowed: list[Any]) -> Validator:
        """Value must be one of the allowed values."""
        if self._value is not None and self._value not in allowed:
            self._errors.append(f"{self._field} must be one of {allowed}, got {self._value}")
        return self

    def in_range(self, minimum: float, maximum: float) -> Validator:
        """Value must be in [minimum, maximum]."""
        if self._value is not None and (self._value < minimum or self._value > maximum):
            self._errors.append(
                f"{self._field} must be in [{minimum}, {maximum}], got {self._value}"
            )
        return self

    def matches(self, pattern: str, description: str = "required format") -> Validator:
        """Value must match a regex pattern."""
        import re

        if self._value is not None and not re.match(pattern, str(self._value)):
            self._errors.append(f"{self._field} must match {description}")
        return self

    def custom(self, check_fn: Any, message: str) -> Validator:
        """Custom validation check."""
        if self._value is not None and not check_fn(self._value):
            self._errors.append(message)
        return self

    @property
    def is_valid(self) -> bool:
        """Whether all validation checks passed."""
        return len(self._errors) == 0

    @property
    def errors(self) -> list[str]:
        """Collected error messages."""
        return list(self._errors)

    def raise_if_invalid(self) -> None:
        """Raise ValidationError if any checks failed."""
        if self._errors:
            raise ValidationError(
                "; ".join(self._errors),
                code="VALIDATION_ERROR",
            )


def validate_order_params(
    security_id: str,
    exchange: str,
    side: str,
    quantity: int,
    order_type: str,
    product_type: str,
    price: float = 0.0,
    trigger_price: float = 0.0,
) -> None:
    """Validate common order parameters."""
    (Validator.check(security_id, "security_id").required().raise_if_invalid())
    (Validator.check(exchange, "exchange").required().raise_if_invalid())
    (Validator.check(side, "side").one_of(["BUY", "SELL"]).raise_if_invalid())
    (Validator.check(quantity, "quantity").required().positive().raise_if_invalid())
    (
        Validator.check(order_type, "order_type")
        .one_of(["LIMIT", "MARKET", "STOP_LOSS", "STOP_LOSS_MARKET"])
        .raise_if_invalid()
    )
    (
        Validator.check(product_type, "product_type")
        .one_of(["CNC", "INTRADAY", "MARGIN", "MTF"])
        .raise_if_invalid()
    )

    if order_type in ("LIMIT", "STOP_LOSS"):
        Validator.check(price, "price").positive().raise_if_invalid()

    if order_type in ("STOP_LOSS", "STOP_LOSS_MARKET"):
        Validator.check(trigger_price, "trigger_price").positive().raise_if_invalid()
