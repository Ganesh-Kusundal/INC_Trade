"""Tests for event-driven reconciliation — Upstox + Dhan parity."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.common.reconciliation import ReconciliationDrift
from brokers.dhan.extended.reconciliation import DhanReconciliation
from brokers.domain.events import DomainEvent, EventType, make_payload
from brokers.infrastructure.event_bus import EventBus
from brokers.upstox.extended.reconciliation import UpstoxReconciliation


# ── UpstoxReconciliation: sync backward compat ───────────────────────────────


class TestUpstoxSync:
    def test_compare_orders_no_drift(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [
                {"order_id": "O1", "status": "COMPLETE"},
                {"order_id": "O2", "status": "OPEN"},
            ]
        }
        recon = UpstoxReconciliation(client=mock_client)
        drift = recon.compare_orders({"O1": "COMPLETE", "O2": "OPEN"})
        assert drift.has_drift is False
        assert drift.total_count == 0

    def test_compare_orders_with_status_mismatch(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [
                {"order_id": "O1", "status": "FILLED"},
                {"order_id": "O3", "status": "OPEN"},
            ]
        }
        recon = UpstoxReconciliation(client=mock_client)
        local = {"O1": "OPEN", "O2": "OPEN"}
        drift = recon.compare_orders(local)
        assert drift.has_drift is True
        assert "O3" in drift.missing_in_local
        assert "O2" in drift.missing_in_broker
        assert drift.total_count == 3

    def test_compare_orders_handles_fetch_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("network down")
        recon = UpstoxReconciliation(client=mock_client)
        drift = recon.compare_orders({"O1": "OPEN"})
        # All local orders appear missing in broker (empty fetch)
        assert "O1" in drift.missing_in_broker


# ── UpstoxReconciliation: event emission ──────────────────────────────────────


class TestUpstoxWithEvents:
    def test_no_bus_returns_drift_unchanged(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [{"order_id": "O1", "status": "OPEN"}]
        }
        recon = UpstoxReconciliation(client=mock_client)
        drift = recon.compare_orders_with_events({"O1": "OPEN"}, bus=None)
        assert drift.has_drift is False

    def test_emits_ok_and_completed_when_no_drift(self) -> None:
        bus = EventBus()
        captured: list[DomainEvent] = []
        bus.subscribe("RECONCILIATION_OK", lambda e: captured.append(e))
        bus.subscribe("RECONCILIATION_COMPLETED", lambda e: captured.append(e))

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [{"order_id": "O1", "status": "COMPLETE"}]
        }
        recon = UpstoxReconciliation(client=mock_client)
        recon.compare_orders_with_events({"O1": "COMPLETE"}, bus=bus)

        types = [e.event_type for e in captured]
        assert types == ["RECONCILIATION_OK", "RECONCILIATION_COMPLETED"]
        completed = captured[-1]
        assert completed.payload["drift_count"] == 0
        assert completed.source == "upstox_reconciliation"

    def test_emits_drift_per_item(self) -> None:
        bus = EventBus()
        drift_events: list[DomainEvent] = []
        completed_events: list[DomainEvent] = []
        bus.subscribe("RECONCILIATION_DRIFT", lambda e: drift_events.append(e))
        bus.subscribe(
            "RECONCILIATION_COMPLETED", lambda e: completed_events.append(e)
        )

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [
                {"order_id": "O1", "status": "FILLED"},
                {"order_id": "O3", "status": "OPEN"},
            ]
        }
        recon = UpstoxReconciliation(client=mock_client)
        local = {"O1": "OPEN", "O2": "OPEN"}
        drift = recon.compare_orders_with_events(local, bus=bus)

        # 1 status mismatch (O1) + 1 missing_in_local (O3) + 1 missing_in_broker (O2) = 3
        assert len(drift_events) == drift.total_count == 3
        for event in drift_events:
            assert event.event_type == "RECONCILIATION_DRIFT"
            assert make_payload(
                EventType.RECONCILIATION_DRIFT, event.payload, validate=True
            )
        assert len(completed_events) == 1
        assert completed_events[0].payload["drift_count"] == 3

    def test_drift_payload_contract_satisfies_required(self) -> None:
        """Single missing-in-local order should produce exactly 1 DRIFT event."""
        bus = EventBus()
        captured: list[DomainEvent] = []
        bus.subscribe("RECONCILIATION_DRIFT", lambda e: captured.append(e))

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [{"order_id": "O9", "status": "OPEN"}]
        }
        recon = UpstoxReconciliation(client=mock_client)
        # Empty local so O9 is only missing-in-local; no other-source drift
        recon.compare_orders_with_events({}, bus=bus)

        assert len(captured) == 1
        payload = captured[0].payload
        # Required keys per EVENT_PAYLOADS contract
        assert payload["symbol"] == "O9"
        assert payload["internal"] == "missing"
        assert payload["broker"] == "present"
        assert payload["order_id"] == "O9"


# ── DhanReconciliation: parity ────────────────────────────────────────────────


class TestDhanSync:
    def test_dhan_compare_orders_no_drift(self) -> None:
        mock_client = MagicMock()
        # Dhan response uses orderId + orderStatus keys
        mock_client.get.return_value = {
            "data": [
                {"orderId": "D1", "orderStatus": "TRADED"},
                {"orderId": "D2", "orderStatus": "PENDING"},
            ]
        }
        recon = DhanReconciliation(client=mock_client)
        drift = recon.compare_orders({"D1": "TRADED", "D2": "PENDING"})
        assert drift.has_drift is False

    def test_dhan_compare_orders_handles_unexpected_response_shape(self) -> None:
        """Dhan response without ``data`` returns empty list, no crash."""
        mock_client = MagicMock()
        mock_client.get.return_value = {"error": "rate-limited"}
        recon = DhanReconciliation(client=mock_client)
        drift = recon.compare_orders({"D1": "TRADED"})
        assert "D1" in drift.missing_in_broker

    def test_dhan_compare_orders_handles_fetch_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = ConnectionError("unreachable")
        recon = DhanReconciliation(client=mock_client)
        drift = recon.compare_orders({"D1": "TRADED"})
        assert "D1" in drift.missing_in_broker


class TestDhanWithEvents:
    def test_dhan_no_bus_returns_drift_unchanged(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [{"orderId": "D1", "orderStatus": "TRADED"}]
        }
        recon = DhanReconciliation(client=mock_client)
        drift = recon.compare_orders_with_events({"D1": "TRADED"}, bus=None)
        assert drift.has_drift is False

    def test_dhan_emits_drift_with_correct_keys(self) -> None:
        bus = EventBus()
        captured: list[DomainEvent] = []
        completed: list[DomainEvent] = []
        bus.subscribe("RECONCILIATION_DRIFT", lambda e: captured.append(e))
        bus.subscribe("RECONCILIATION_COMPLETED", lambda e: completed.append(e))

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [{"orderId": "D2", "orderStatus": "TRADED"}]
        }
        recon = DhanReconciliation(client=mock_client)
        recon.compare_orders_with_events({"D1": "TRADED"}, bus=bus)

        # D2 missing in local, D1 missing in broker → 2 drifts + 1 completed
        assert len(captured) == 2
        assert len(completed) == 1
        # First drift (missing_in_local iteration runs first)
        assert captured[0].payload["symbol"] == "D2"
        assert captured[0].payload["internal"] == "missing"
        # Second drift (missing_in_broker)
        assert captured[1].payload["symbol"] == "D1"
        assert captured[1].payload["internal"] == "present"
        assert captured[1].source == "dhan_reconciliation"

    def test_dhan_emits_ok_event_when_no_drift(self) -> None:
        bus = EventBus()
        captured: list[DomainEvent] = []
        bus.subscribe("RECONCILIATION_OK", lambda e: captured.append(e))

        mock_client = MagicMock()
        mock_client.get.return_value = {
            "data": [{"orderId": "D1", "orderStatus": "TRADED"}]
        }
        recon = DhanReconciliation(client=mock_client)
        recon.compare_orders_with_events({"D1": "TRADED"}, bus=bus)
        assert len(captured) == 1
        assert captured[0].event_type == "RECONCILIATION_OK"


# ── Drift dataclass ───────────────────────────────────────────────────────────


class TestDriftDataclass:
    def test_total_count_zero_when_empty(self) -> None:
        assert ReconciliationDrift().total_count == 0

    def test_total_count_sums_all_categories(self) -> None:
        drift = ReconciliationDrift(
            missing_in_local=["a", "b"],
            missing_in_broker=["c"],
            status_mismatches=(
                ("d", "OPEN", "FILLED"),
                ("e", "PENDING", "CANCELLED"),
            ),
        )
        assert drift.total_count == 5
