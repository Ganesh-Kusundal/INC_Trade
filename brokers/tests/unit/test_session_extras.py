"""Unit tests for BrokerSession.scanner, replay, and degraded_mode accessors."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSessionExtras:
    def _make_session_with_market(self) -> object:
        from brokers.market.context import MarketDataContext
        from brokers.market.instrument_registry import InstrumentRegistry
        from brokers.services.broker_session import BrokerSession

        registry = InstrumentRegistry()
        market = MarketDataContext(
            registry=registry,
            market_data=MagicMock(),
        )
        return BrokerSession(broker_id="paper", market=market)

    def test_scanner_returns_scanner_instance(self) -> None:
        session = self._make_session_with_market()
        scanner = session.scanner
        assert scanner is not None
        from brokers.market.scanner import Scanner

        assert isinstance(scanner, Scanner)

    def test_replay_returns_replay_engine(self) -> None:
        session = self._make_session_with_market()
        replay = session.replay
        assert replay is not None
        from brokers.adapters.replay import ReplayEngine

        assert isinstance(replay, ReplayEngine)
        # Same instance returned on second call
        assert session.replay is replay

    def test_degraded_mode_returns_degraded_mode(self) -> None:
        session = self._make_session_with_market()
        dm = session.degraded_mode
        assert dm is not None
        from brokers.market.degraded_mode import DegradedMode

        assert isinstance(dm, DegradedMode)
        # Same instance on second call
        assert session.degraded_mode is dm

    def test_scanner_none_when_no_market(self) -> None:
        from brokers.services.broker_session import BrokerSession

        session = BrokerSession(broker_id="paper")
        assert session.scanner is None

    def test_replay_none_when_no_market_is_fine(self) -> None:
        """Replay works even without a market context (it's standalone)."""
        from brokers.services.broker_session import BrokerSession

        session = BrokerSession(broker_id="paper")
        # Replay has no dependency on market context — should work
        replay = session.replay
        assert replay is not None

    def test_degraded_mode_none_when_no_market(self) -> None:
        from brokers.services.broker_session import BrokerSession

        session = BrokerSession(broker_id="paper")
        assert session.degraded_mode is None

    def test_analytics_returns_namespace(self) -> None:
        session = self._make_session_with_market()
        analytics = session.analytics
        assert analytics is not None
        assert hasattr(analytics, "vwap")
        assert hasattr(analytics, "greeks")
        assert hasattr(analytics, "atr")
        assert hasattr(analytics, "volume_profile")

    def test_analytics_works_without_market(self) -> None:
        from brokers.services.broker_session import BrokerSession

        session = BrokerSession(broker_id="paper")
        # Analytics has no dependency on market context
        analytics = session.analytics
        assert analytics is not None

    def test_analytics_exposes_order_flow_class(self) -> None:
        from brokers.market.analytics import OrderFlowAnalyzer

        session = self._make_session_with_market()
        analytics = session.analytics
        assert hasattr(analytics, "order_flow")
        # ``order_flow`` is the class itself (callers instantiate).
        assert analytics.order_flow is OrderFlowAnalyzer

    def test_analytics_make_order_flow_analyzer_factory(self) -> None:
        from brokers.market.analytics import OrderFlowAnalyzer

        session = self._make_session_with_market()
        analytics = session.analytics
        of = analytics.make_order_flow_analyzer(large_trade_threshold=500)
        assert isinstance(of, OrderFlowAnalyzer)
        # Default threshold honored.
        of_default = analytics.make_order_flow_analyzer()
        assert isinstance(of_default, OrderFlowAnalyzer)
        # Each call returns a fresh instance.
        assert of is not of_default

    def test_analytics_order_flow_works_without_market(self) -> None:
        from brokers.services.broker_session import BrokerSession

        session = BrokerSession(broker_id="paper")
        # No market context, but analytics still works.
        analytics = session.analytics
        assert analytics.order_flow is not None
        of = analytics.make_order_flow_analyzer()
        assert of.snapshot().trade_count == 0
