"""Paper trading capabilities — BrokerCapabilities dataclass."""

from brokers_core.domain.capabilities import BrokerCapabilities
from brokers_core.domain.enums import BrokerID


def paper_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Paper broker adapter."""
    return BrokerCapabilities(
        broker_id=BrokerID.PAPER,
        supports_orders=True,
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=False,
        supports_intraday_history=False,
        supports_expired_options_history=False,
        supports_live_market_data=False,
        supports_depth=False,
        supports_depth_20_ws=False,
        supports_depth_200_ws=False,
        supports_option_chain=False,
        supports_polling_fallback=False,
        supports_order_stream=False,
        supports_portfolio_stream=False,
        supports_news=False,
        supports_fundamentals=False,
        supports_super_order=False,
        supports_forever_order=False,
        supports_native_slice_order=False,
        supports_mtf=False,
        latency_class="simulated",
        reliability_class="simulated",
    )
