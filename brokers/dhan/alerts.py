"""Conditional alerts adapter — create, manage price alerts."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.domain import Alert, AlertRequest
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_payload
from domain.utils.price import to_wire_float

logger = logging.getLogger(__name__)


class AlertsAdapter:
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def place(self, request: AlertRequest) -> Alert:
        """Create a new price alert.

        Args:
            request: AlertRequest with alert details

        Returns:
            Alert with created alert information
        """
        # Validate request
        errors = self._validate_request(request)
        if errors:
            msg = "; ".join(errors)
            logger.warning(
                "alert_validation_failed",
                extra={
                    "symbol": request.symbol,
                    "errors": errors,
                },
            )
            raise ValueError(f"Alert request validation failed: {msg}")

        # Resolve instrument via the identity provider. The carrier
        # (DhanInstrumentRef) is the only thing that can flow into the
        # payload builder; the provider enforces the Dhan-internal
        # contract.
        ref = self._identity.resolve_ref(request.symbol, request.exchange)
        segment = ref.exchange_segment

        # Build API payload
        payload = {
            "dhanClientId": self._client.client_id,
            "exchangeSegment": segment,
            "securityId": ref.security_id_str(),
            "alertCondition": request.condition,
            "triggerPrice": to_wire_float(request.trigger_price),
        }

        if request.valid_until:
            payload["validTill"] = request.valid_until

        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_payload(payload, context="alerts.place")

        # Call API
        data = self._client.post("/alerts", json=payload)

        # Parse response
        alert_data = data.get("data", data)
        alert = Alert(
            alert_id=str(alert_data.get("alertId", alert_data.get("id", ""))),
            symbol=request.symbol,
            exchange=request.exchange,
            condition=request.condition,
            trigger_price=request.trigger_price,
            active=True,
            created_at=alert_data.get("createdAt"),
        )

        logger.info(
            "alert_placed",
            extra={
                "alert_id": alert.alert_id,
                "symbol": request.symbol,
                "trigger_price": str(request.trigger_price),
            },
        )

        return alert

    def get(self, alert_id: str) -> Alert:
        """Get details of a specific alert.

        Args:
            alert_id: Alert ID

        Returns:
            Alert with alert details
        """
        data = self._client.get(f"/alerts/{alert_id}")
        alert_data = data.get("data", data)

        alert = self._parse_alert(alert_data)
        logger.info("alert_fetched", extra={"alert_id": alert_id})
        return alert

    def list_all(self) -> list[Alert]:
        """List all active alerts.

        Returns:
            List of Alert objects
        """
        data = self._client.get("/alerts")
        items = data.get("data", []) if isinstance(data, dict) else []

        alerts = [self._parse_alert(item) for item in (items if isinstance(items, list) else [])]
        logger.info("alerts_listed", extra={"count": len(alerts)})
        return alerts

    def delete(self, alert_id: str) -> bool:
        """Delete an alert.

        Args:
            alert_id: Alert ID to delete

        Returns:
            True if deletion successful
        """
        data = self._client.delete(f"/alerts/{alert_id}")
        success = isinstance(data, dict)
        logger.info("alert_deleted", extra={"alert_id": alert_id, "success": success})
        return success

    def _validate_request(self, request: AlertRequest) -> list[str]:
        """Validate alert request. Returns list of errors (empty = valid)."""
        errors = []

        if request.trigger_price <= 0:
            errors.append(f"Trigger price must be positive, got {request.trigger_price}")

        valid_conditions = {"LTP_CROSSES_ABOVE", "LTP_CROSSES_BELOW"}
        if request.condition not in valid_conditions:
            errors.append(
                f"Invalid condition: {request.condition}. Must be one of {valid_conditions}"
            )

        return errors

    def _parse_alert(self, data: dict) -> Alert:
        """Parse alert from API response."""
        return Alert(
            alert_id=str(data.get("alertId", data.get("id", ""))),
            symbol=data.get("symbol", ""),
            exchange=data.get("exchange", "NSE"),
            condition=data.get("condition", data.get("alertCondition", "")),
            trigger_price=Decimal(str(data.get("triggerPrice", 0))),
            active=data.get("status", "ACTIVE").upper() == "ACTIVE",
            created_at=data.get("createdAt"),
        )
