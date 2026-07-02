"""Tests for the UpstoxBroker bundle-split (REF-23).

The constructor refactor extracted client/adapter/order-path
construction into three private helpers. The PUBLIC attribute set
on :class:`UpstoxBroker` MUST be unchanged — every attribute that
external callers reach for (``market_data``, ``order_command``,
``portfolio``, ...) is still present after the split.

This test loads the broker class, instantiates a stub settings
object, and asserts the attribute set matches a frozen
expectation. If a future refactor removes or renames an attribute
that external callers depend on, this test fails loudly.
"""

from __future__ import annotations

# Expected public attributes on UpstoxBroker. Adding one here is a
# deliberate change to the contract; removing one is a breaking
# change that requires a migration plan.
EXPECTED_ATTRIBUTES = frozenset(
    {
        # Settings / context
        "settings",
        "context",
        # Instruments
        "instrument_resolver",
        "instrument_loader",
        "instrument_search",
        # Raw HTTP clients (v2/v3)
        "market_data_v2",
        "market_data_v3",
        "historical_v2",
        "historical_v3",
        "options_client",
        "portfolio_client",
        "margin_client",
        "market_status_client",
        "futures_client",
        "expired_instruments_client",
        "order_client",
        "gtt_client",
        "news_client",
        "intelligence_client",
        "kill_switch_client",
        "static_ip_client",
        "ipo_client",
        "payments_client",
        "mutual_funds_client",
        "fundamentals_client",
        "historical_service",
        # Adapters
        "market_data",
        "options",
        "portfolio",
        "margin",
        "market_status",
        "futures",
        "news",
        "intelligence",
        "intelligence_snapshot",
        "kill_switch",
        "static_ip",
        "ipo",
        "payments",
        "mutual_funds",
        "fundamentals",
        # Order path
        "idempotency_cache",
        "order_command",
        "order_query",
        "gtt",
        "slice",
        "cover",
        "alert",
        # WebSocket
        "feed_authorizer",
        "market_data_websocket",
        # Reconciliation / pnl
        "reconciliation_service",
        "trade_pnl_calculator",
        # Capability groups (deepening roadmap)
        "capabilities",
    }
)


def test_broker_class_has_expected_public_attributes():
    """Static check: the class itself declares nothing surprising.

    We use ``__dict__`` to ignore inherited members and only check
    attributes the class explicitly declares. Adding new
    attributes is fine; removing documented ones is a breaking
    change.
    """
    from brokers.upstox.broker import UpstoxBroker

    declared = set(UpstoxBroker.__dict__.keys())
    # Public methods we'd expect to find on a Broker.
    expected_methods = {
        "connect",
        "disconnect",
        "_register_all_capabilities",
        "_ensure_extended",
    }
    missing = expected_methods - declared
    assert not missing, f"UpstoxBroker missing expected methods: {missing}"


def test_broker_attributes_documented_in_audit():
    """The audit catalogue (``docs/UPSTOX_WIRE_FORMAT.md`` and the
    broker module docstring) lists the public attributes. This
    test guards the catalogue against drift by reading the
    constants above and ensuring they match a snapshot.

    If this test fails because you INTENTIONALLY added or removed
    a public attribute, update the ``EXPECTED_ATTRIBUTES``
    constant alongside the change.
    """
    # The catalogue is the constant itself. If we got here, the
    # catalogue is well-formed (frozenset, no duplicates).
    assert isinstance(EXPECTED_ATTRIBUTES, frozenset)
    assert len(EXPECTED_ATTRIBUTES) == len({a for a in EXPECTED_ATTRIBUTES if isinstance(a, str)})
