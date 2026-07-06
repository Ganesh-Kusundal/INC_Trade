"""Unit tests for SubscriptionManager — reference counting, dedup, callbacks."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest
from inc_trade.market.subscription_manager import SubscriptionManager, SubscriptionState


class TestSubscriptionState:
    """SubscriptionState state machine transitions."""

    def test_initial_state_is_inactive(self) -> None:
        state = SubscriptionState()
        assert state.state == SubscriptionState.INACTIVE
        assert not state.is_active

    def test_transition_inactive_to_subscribing(self) -> None:
        state = SubscriptionState()
        state.transition_to(SubscriptionState.SUBSCRIBING)
        assert state.state == SubscriptionState.SUBSCRIBING

    def test_transition_subscribing_to_active(self) -> None:
        state = SubscriptionState()
        state.transition_to(SubscriptionState.SUBSCRIBING)
        state.transition_to(SubscriptionState.ACTIVE)
        assert state.is_active

    def test_transition_active_to_unsubscribing(self) -> None:
        state = SubscriptionState()
        state.transition_to(SubscriptionState.SUBSCRIBING)
        state.transition_to(SubscriptionState.ACTIVE)
        state.transition_to(SubscriptionState.UNSUBSCRIBING)
        assert state.state == SubscriptionState.UNSUBSCRIBING

    def test_transition_unsubscribing_to_inactive(self) -> None:
        state = SubscriptionState()
        state.transition_to(SubscriptionState.SUBSCRIBING)
        state.transition_to(SubscriptionState.ACTIVE)
        state.transition_to(SubscriptionState.UNSUBSCRIBING)
        state.transition_to(SubscriptionState.INACTIVE)
        assert state.state == SubscriptionState.INACTIVE

    def test_transition_active_to_inactive_fast_path(self) -> None:
        state = SubscriptionState()
        state.transition_to(SubscriptionState.SUBSCRIBING)
        state.transition_to(SubscriptionState.ACTIVE)
        state.transition_to(SubscriptionState.INACTIVE)  # Fast path
        assert state.state == SubscriptionState.INACTIVE

    def test_transition_subscribing_to_inactive_failure_path(self) -> None:
        state = SubscriptionState()
        state.transition_to(SubscriptionState.SUBSCRIBING)
        state.transition_to(SubscriptionState.INACTIVE)  # Failure path
        assert state.state == SubscriptionState.INACTIVE

    def test_invalid_transition_logged_no_crash(self) -> None:
        state = SubscriptionState()
        # Can't go from INACTIVE to UNSUBSCRIBING directly
        state.transition_to(SubscriptionState.UNSUBSCRIBING)
        assert state.state == SubscriptionState.INACTIVE  # Unchanged


class TestSubscriptionManager:
    """SubscriptionManager reference counting and callback management."""

    @pytest.fixture
    def mock_adapter(self) -> MagicMock:
        adapter = MagicMock()
        adapter.subscribe = MagicMock()
        adapter.unsubscribe = MagicMock()
        return adapter

    @pytest.fixture
    def manager(self, mock_adapter: MagicMock) -> SubscriptionManager:
        return SubscriptionManager(stream_adapter=mock_adapter)

    # ── Reference Counting ────────────────────────────────────────────

    def test_first_subscriber_actually_subscribes(
        self,
        manager: SubscriptionManager,
        mock_adapter: MagicMock,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        mock_adapter.subscribe.assert_called_once_with("NSE:RELIANCE", "NSE")
        assert manager.ref_count("NSE:RELIANCE") == 1

    def test_second_subscriber_does_not_resubscribe(
        self,
        manager: SubscriptionManager,
        mock_adapter: MagicMock,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.subscribe("NSE:RELIANCE", "NSE")
        # subscribe should only be called once
        mock_adapter.subscribe.assert_called_once_with("NSE:RELIANCE", "NSE")
        assert manager.ref_count("NSE:RELIANCE") == 2

    def test_last_unsubscriber_actually_unsubscribes(
        self,
        manager: SubscriptionManager,
        mock_adapter: MagicMock,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.unsubscribe("NSE:RELIANCE", "NSE")
        # Still has 1 ref, should NOT unsubscribe yet
        mock_adapter.unsubscribe.assert_not_called()
        manager.unsubscribe("NSE:RELIANCE", "NSE")
        # Now last ref, should unsubscribe
        mock_adapter.unsubscribe.assert_called_once_with("NSE:RELIANCE", "NSE")

    def test_subscribe_multiple_keys_independent(
        self,
        manager: SubscriptionManager,
        mock_adapter: MagicMock,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.subscribe("NSE:TCS", "NSE")
        assert mock_adapter.subscribe.call_count == 2
        assert manager.ref_count("NSE:RELIANCE") == 1
        assert manager.ref_count("NSE:TCS") == 1

    def test_unsubscribe_unknown_key_does_not_raise(
        self,
        manager: SubscriptionManager,
    ) -> None:
        # Should not raise
        manager.unsubscribe("nonexistent:key")
        # Should be safe to call twice
        manager.unsubscribe("nonexistent:key")

    def test_ref_count_returns_zero_for_unknown_key(
        self,
        manager: SubscriptionManager,
    ) -> None:
        assert manager.ref_count("unknown:key") == 0

    # ── Callbacks ─────────────────────────────────────────────────────

    def test_callback_registration_and_invocation(
        self,
        manager: SubscriptionManager,
    ) -> None:
        received: list[dict] = []

        def callback(data: dict) -> None:
            received.append(data)

        manager.subscribe("NSE:RELIANCE", "NSE", callback=callback)
        manager.dispatch_tick("NSE:RELIANCE", {"ltp": 2500})
        assert len(received) == 1
        assert received[0]["ltp"] == 2500

    def test_callback_removal_on_unsubscribe(
        self,
        manager: SubscriptionManager,
    ) -> None:
        received: list[dict] = []

        def callback(data: dict) -> None:
            received.append(data)

        manager.subscribe("NSE:RELIANCE", "NSE", callback=callback)
        manager.unsubscribe("NSE:RELIANCE", "NSE", callback=callback)
        manager.dispatch_tick("NSE:RELIANCE", {"ltp": 2500})
        assert len(received) == 0

    def test_dispatch_tick_to_multiple_callbacks(
        self,
        manager: SubscriptionManager,
    ) -> None:
        received1: list[dict] = []
        received2: list[dict] = []

        def cb1(data: dict) -> None:
            received1.append(data)

        def cb2(data: dict) -> None:
            received2.append(data)

        manager.subscribe("NSE:RELIANCE", "NSE", callback=cb1)
        manager.subscribe("NSE:RELIANCE", "NSE", callback=cb2)
        manager.dispatch_tick("NSE:RELIANCE", {"ltp": 100})
        assert len(received1) == 1
        assert len(received2) == 1

    def test_dispatch_tick_to_correct_key_only(
        self,
        manager: SubscriptionManager,
    ) -> None:
        received_reliance: list[dict] = []
        received_tcs: list[dict] = []

        def cb_r(data: dict) -> None:
            received_reliance.append(data)

        def cb_t(data: dict) -> None:
            received_tcs.append(data)

        manager.subscribe("NSE:RELIANCE", "NSE", callback=cb_r)
        manager.subscribe("NSE:TCS", "NSE", callback=cb_t)
        manager.dispatch_tick("NSE:RELIANCE", {"ltp": 100})
        assert len(received_reliance) == 1
        assert len(received_tcs) == 0

    def test_callback_error_does_not_crash_dispatcher(
        self,
        manager: SubscriptionManager,
    ) -> None:
        """A crashing callback should not prevent other callbacks from running."""

        def crashing_cb(data: dict) -> None:
            raise ValueError("crash")

        received: list[dict] = []

        def good_cb(data: dict) -> None:
            received.append(data)

        manager.subscribe("NSE:RELIANCE", "NSE", callback=crashing_cb)
        manager.subscribe("NSE:RELIANCE", "NSE", callback=good_cb)
        # This should not raise despite crashing_cb failing
        manager.dispatch_tick("NSE:RELIANCE", {"ltp": 100})
        assert len(received) == 1

    # ── Query Methods ─────────────────────────────────────────────────

    def test_is_subscribed_after_subscribe(
        self,
        manager: SubscriptionManager,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        assert manager.is_subscribed("NSE:RELIANCE")

    def test_is_subscribed_after_unsubscribe(
        self,
        manager: SubscriptionManager,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.unsubscribe("NSE:RELIANCE", "NSE")
        assert not manager.is_subscribed("NSE:RELIANCE")

    def test_is_subscribed_returns_false_for_unknown_key(
        self,
        manager: SubscriptionManager,
    ) -> None:
        assert not manager.is_subscribed("unknown:key")

    def test_active_subscriptions_property(
        self,
        manager: SubscriptionManager,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.subscribe("NSE:TCS", "NSE")
        active = manager.active_subscriptions
        assert "NSE:RELIANCE" in active
        assert "NSE:TCS" in active
        assert len(active) == 2

    def test_total_ref_counts(
        self,
        manager: SubscriptionManager,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.subscribe("NSE:RELIANCE", "NSE")  # second ref
        manager.subscribe("NSE:TCS", "NSE")
        assert manager.total_ref_counts == 3

    # ── Clear ─────────────────────────────────────────────────────────

    def test_clear_removes_all_and_unsubscribes_all(
        self,
        manager: SubscriptionManager,
        mock_adapter: MagicMock,
    ) -> None:
        manager.subscribe("NSE:RELIANCE", "NSE")
        manager.subscribe("NSE:TCS", "NSE")
        manager.clear()
        assert mock_adapter.unsubscribe.call_count == 2
        assert manager.total_ref_counts == 0
        assert manager.active_subscriptions == []

    # ── Thread Safety ─────────────────────────────────────────────────

    def test_thread_safety_concurrent_subscribe(
        self,
        mock_adapter: MagicMock,
    ) -> None:
        manager = SubscriptionManager(stream_adapter=mock_adapter)
        results: list[int] = []
        lock = threading.Lock()

        def subscribe_thread() -> None:
            manager.subscribe("NSE:RELIANCE", "NSE")
            with lock:
                results.append(1)

        threads = [threading.Thread(target=subscribe_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Even with 10 concurrent subscribes, adapter.subscribe called exactly once
        assert mock_adapter.subscribe.call_count == 1
        assert manager.ref_count("NSE:RELIANCE") == 10

    def test_thread_safety_concurrent_subscribe_unsubscribe(
        self,
        mock_adapter: MagicMock,
    ) -> None:
        manager = SubscriptionManager(stream_adapter=mock_adapter)
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                for _ in range(20):
                    manager.subscribe("NSE:RELIANCE", "NSE")
                    manager.unsubscribe("NSE:RELIANCE", "NSE")
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # Final ref count should be 0 since we did equal subscribe/unsubscribe
        assert manager.ref_count("NSE:RELIANCE") == 0
        assert not manager.is_subscribed("NSE:RELIANCE")
