"""Canonical capability names for broker feature discovery.

Used by capability discovery and extension registry to determine
which features are supported by each broker.
"""

# Core capabilities (supported by most brokers)
FEATURE_ORDERS = "orders"
FEATURE_MARKET_DATA = "market_data"
FEATURE_PORTFOLIO = "portfolio"
FEATURE_HISTORICAL = "historical"
FEATURE_INSTRUMENTS = "instruments"
FEATURE_AUTH = "auth"
FEATURE_STREAMING = "streaming"

# Broker-specific capabilities
FEATURE_GTT = "gtt"  # Good Till Triggered
FEATURE_BASKET_ORDERS = "basket_orders"
FEATURE_DEPTH200 = "depth200"
FEATURE_FOREVER_ORDERS = "forever_orders"
FEATURE_SUPER_ORDERS = "super_orders"
FEATURE_BRACKET_ORDERS = "bracket_orders"
FEATURE_COVER_ORDERS = "cover_orders"
FEATURE_EDIS = "edis"  # Electronic Debit Instruction Slip
FEATURE_MARGIN_CALCULATOR = "margin_calculator"
FEATURE_ALERTS = "alerts"
FEATURE_NEWS = "news"
FEATURE_IP_MANAGEMENT = "ip_management"
FEATURE_EXIT_ALL = "exit_all"  # Panic button
FEATURE_MTF = "mtf"  # Margin Trading Facility
FEATURE_SLICE_ORDERS = "slice_orders"  # Broker-managed quantity splitting

# Exchange-specific capabilities
FEATURE_NSE = "nse"
FEATURE_BSE = "bse"
FEATURE_NFO = "nfo"  # NSE F&O
FEATURE_BFO = "bfo"  # BSE F&O
FEATURE_MCX = "mcx"  # Multi Commodity Exchange
FEATURE_CDSL_EDIS = "cdsl_edis"

# Product-specific capabilities
FEATURE_EQUITY = "equity"
FEATURE_FUTURES = "futures"
FEATURE_OPTIONS = "options"
FEATURE_COMMODITIES = "commodities"
FEATURE_CURRENCY = "currency"
FEATURE_MUTUAL_FUNDS = "mutual_funds"

# Advanced features
FEATURE_OPTION_CHAIN = "option_chain"
FEATURE_EXPIRY_LIST = "expiry_list"
FEATURE_GREEKS = "greeks"
FEATURE_HISTORICAL_OPTION_DATA = "historical_option_data"
FEATURE_INTRADAY_CANDLES = "intraday_candles"
FEATURE_DEPTH_MARKET_DATA = "depth_market_data"

# All capabilities (for validation)
ALL_CAPABILITIES = {
    FEATURE_ORDERS,
    FEATURE_MARKET_DATA,
    FEATURE_PORTFOLIO,
    FEATURE_HISTORICAL,
    FEATURE_INSTRUMENTS,
    FEATURE_AUTH,
    FEATURE_STREAMING,
    FEATURE_GTT,
    FEATURE_BASKET_ORDERS,
    FEATURE_DEPTH200,
    FEATURE_FOREVER_ORDERS,
    FEATURE_SUPER_ORDERS,
    FEATURE_BRACKET_ORDERS,
    FEATURE_COVER_ORDERS,
    FEATURE_EDIS,
    FEATURE_MARGIN_CALCULATOR,
    FEATURE_ALERTS,
    FEATURE_NEWS,
    FEATURE_IP_MANAGEMENT,
    FEATURE_EXIT_ALL,
    FEATURE_MTF,
    FEATURE_SLICE_ORDERS,
    FEATURE_NSE,
    FEATURE_BSE,
    FEATURE_NFO,
    FEATURE_BFO,
    FEATURE_MCX,
    FEATURE_CDSL_EDIS,
    FEATURE_EQUITY,
    FEATURE_FUTURES,
    FEATURE_OPTIONS,
    FEATURE_COMMODITIES,
    FEATURE_CURRENCY,
    FEATURE_MUTUAL_FUNDS,
    FEATURE_OPTION_CHAIN,
    FEATURE_EXPIRY_LIST,
    FEATURE_GREEKS,
    FEATURE_HISTORICAL_OPTION_DATA,
    FEATURE_INTRADAY_CANDLES,
    FEATURE_DEPTH_MARKET_DATA,
}
