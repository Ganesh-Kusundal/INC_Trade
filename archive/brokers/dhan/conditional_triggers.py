"""Conditional Triggers adapter — price-based alert orders (v2.5)."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.domain import ConditionalTrigger, ConditionalTriggerRequest
from brokers.dhan.exceptions import ConditionalTriggerError
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_payload

logger = logging.getLogger(__name__)


class ConditionalTriggersAdapter:
    """Adapter for Dhan Conditional Triggers API (v2.5).

    Conditional Triggers fire orders when price conditions are met.
    Only PRICE_WITH_VALUE comparison type is supported (not indicators).
    """

    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def place_trigger(self, request: ConditionalTriggerRequest) -> ConditionalTrigger:
        """Place a conditional trigger order.

        Args:
            request: ConditionalTriggerRequest with trigger details

        Returns:
            ConditionalTrigger with created trigger information

        Raises:
            ValueError: If validation fails
            ConditionalTriggerError: If API call fails
        """
        errors = self._validate_trigger(request)
        if errors:
            msg = "; ".join(errors)
            logger.warning(
                "conditional_trigger_validation_failed",
                extra={
                    "symbol": request.symbol,
                    "operator": request.operator,
                    "errors": errors,
                },
            )
            raise ValueError(f"Conditional trigger validation failed: {msg}")

        ref = self._identity.resolve_ref(request.symbol, request.exchange)
        segment = ref.exchange_segment

        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "comparisonType": request.comparison_type,
            "operator": request.operator,
            "comparingValue": float(request.comparing_value),
            "expDate": request.exp_date,
            "frequency": request.frequency,
        }

        if request.orders:
            payload["orders"] = request.orders
        if request.user_note:
            payload["userNote"] = request.user_note

        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="conditional_triggers.place_trigger")

        try:
            data = self._client.post("/alerts/orders", json=payload)
        except Exception as exc:
            raise ConditionalTriggerError(f"Conditional trigger placement failed: {exc}") from exc

        trigger_data = data.get("data", data)
        trigger = self._parse_trigger(trigger_data)

        logger.info(
            "conditional_trigger_placed",
            extra={
                "alert_id": trigger.alert_id,
                "symbol": request.symbol,
                "operator": request.operator,
                "comparing_value": str(request.comparing_value),
            },
        )

        return trigger

    def modify_trigger(
        self,
        alert_id: str,
        request: ConditionalTriggerRequest,
    ) -> ConditionalTrigger:
        """Modify an existing conditional trigger.

        Args:
            alert_id: Alert ID to modify
            request: ConditionalTriggerRequest with updated details

        Returns:
            ConditionalTrigger with updated trigger information

        Raises:
            ConditionalTriggerError: If API call fails
        """
        ref = self._identity.resolve_ref(request.symbol, request.exchange)
        segment = ref.exchange_segment

        payload = {
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "comparisonType": request.comparison_type,
            "operator": request.operator,
            "comparingValue": float(request.comparing_value),
            "expDate": request.exp_date,
            "frequency": request.frequency,
        }

        if request.orders:
            payload["orders"] = request.orders
        if request.user_note:
            payload["userNote"] = request.user_note

        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="conditional_triggers.modify_trigger")

        try:
            data = self._client.put(f"/alerts/orders/{alert_id}", json=payload)
        except Exception as exc:
            raise ConditionalTriggerError(
                f"Conditional trigger modification failed: {exc}"
            ) from exc

        trigger_data = data.get("data", data)
        trigger = self._parse_trigger(trigger_data)

        logger.info(
            "conditional_trigger_modified",
            extra={
                "alert_id": alert_id,
            },
        )

        return trigger

    def delete_trigger(self, alert_id: str) -> bool:
        """Delete a conditional trigger.

        Args:
            alert_id: Alert ID to delete

        Returns:
            True if deletion successful

        Raises:
            ConditionalTriggerError: If API call fails
        """
        try:
            data = self._client.delete(f"/alerts/orders/{alert_id}")
        except Exception as exc:
            raise ConditionalTriggerError(f"Conditional trigger deletion failed: {exc}") from exc

        success = isinstance(data, dict) and data.get("status") == "success"
        logger.info(
            "conditional_trigger_deleted",
            extra={
                "alert_id": alert_id,
                "success": success,
            },
        )
        return success

    def get_trigger(self, alert_id: str) -> ConditionalTrigger:
        """Get a specific conditional trigger by ID.

        Args:
            alert_id: Alert ID to fetch

        Returns:
            ConditionalTrigger with trigger details

        Raises:
            ConditionalTriggerError: If API call fails
        """
        try:
            data = self._client.get(f"/alerts/orders/{alert_id}")
        except Exception as exc:
            raise ConditionalTriggerError(f"Failed to fetch conditional trigger: {exc}") from exc

        trigger_data = data.get("data", data)
        trigger = self._parse_trigger(trigger_data)

        logger.info(
            "conditional_trigger_fetched",
            extra={
                "alert_id": alert_id,
            },
        )
        return trigger

    def get_all_triggers(self) -> list[ConditionalTrigger]:
        """Get all conditional triggers.

        Returns:
            List of ConditionalTrigger objects

        Raises:
            ConditionalTriggerError: If API call fails
        """
        try:
            data = self._client.get("/alerts/orders")
        except Exception as exc:
            raise ConditionalTriggerError(f"Failed to fetch conditional triggers: {exc}") from exc

        items = data.get("data", []) if isinstance(data, dict) else []
        triggers = [
            self._parse_trigger(item) for item in (items if isinstance(items, list) else [])
        ]

        logger.info("conditional_triggers_fetched", extra={"count": len(triggers)})
        return triggers

    def _validate_trigger(self, request: ConditionalTriggerRequest) -> list[str]:
        """Validate conditional trigger request. Returns list of errors (empty = valid)."""
        errors = []

        valid_operators = {"CROSSING_UP", "CROSSING_DOWN", "GREATER_THAN", "LESS_THAN"}
        if request.operator not in valid_operators:
            errors.append(f"Invalid operator: {request.operator}. Must be one of {valid_operators}")

        if request.comparing_value <= 0:
            errors.append(f"comparing_value must be positive, got {request.comparing_value}")

        if request.comparison_type != "PRICE_WITH_VALUE":
            errors.append(
                f"Only PRICE_WITH_VALUE comparison type is supported, got {request.comparison_type}"
            )

        return errors

    def _parse_trigger(self, data: dict) -> ConditionalTrigger:
        """Parse conditional trigger from API response."""
        return ConditionalTrigger(
            alert_id=str(data.get("alertId", "")),
            alert_status=data.get("alertStatus", ""),
            comparison_type=data.get("comparisonType", ""),
            exchange_segment=data.get("exchangeSegment", ""),
            security_id=str(data.get("securityId", "")),
            operator=data.get("operator", ""),
            comparing_value=Decimal(str(data.get("comparingValue", 0))),
            exp_date=data.get("expDate", ""),
            frequency=data.get("frequency", "ONCE"),
            orders=data.get("orders", []),
            created_time=data.get("createdAt"),
            triggered_time=data.get("triggeredAt"),
            last_price=Decimal(str(data["lastPrice"]))
            if data.get("lastPrice") is not None
            else None,
            user_note=data.get("userNote"),
        )
