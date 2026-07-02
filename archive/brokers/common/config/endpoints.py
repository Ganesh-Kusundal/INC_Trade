"""Central broker endpoints registry.

Consolidates all Dhan and Upstox API URLs / WebSocket endpoints / asset URLs
into one place so that any file that needs a broker URL imports from here
rather than defining its own hard-coded string.

Usage::

    from config.endpoints import Dhan, Upstox

    # Dhan REST
    client = DhanHttpClient(base_url=Dhan.REST_BASE)

    # Dhan WebSocket
    feed = DhanDepth20Feed(endpoint=Dhan.WS_DEPTH_20)

    # Upstox — production vs sandbox
    prod = Upstox.production()
    sandbox = Upstox.sandbox()

    orders = UpstoxRestOrderClient(http, prod)
    url = orders.place_order_v3_url()

    # Static (non-host-dependent)
    auth_url = f"{prod.base_v2}/v2/login/authorization/dialog"
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Shared host-independent constants ────────────────────────────────────────
_UPSTOX_ASSET_INSTRUMENTS_JSON = (
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Dhan API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


class Dhan:
    """Dhan broker API endpoints — constants and defaults."""

    # ── REST API ────────────────────────────────────────────────────────
    REST_BASE: str = "https://api.dhan.co/v2"
    SANDBOX_REST_BASE: str = "https://sandbox.dhan.co/v2"

    @classmethod
    def production(cls) -> str:
        """Return production REST base URL."""
        return cls.REST_BASE

    @classmethod
    def sandbox(cls) -> str:
        """Return sandbox REST base URL."""
        return cls.SANDBOX_REST_BASE

    # ── Auth ────────────────────────────────────────────────────────────
    GENERATE_TOKEN_URL: str = "https://auth.dhan.co/app/generateAccessToken"

    # ── WebSocket Feeds ─────────────────────────────────────────────────
    WS_DEPTH_20: str = "wss://depth-api-feed.dhan.co/twentydepth"
    WS_DEPTH_200: str = "wss://full-depth-api.dhan.co/twohundreddepth"

    # ── Instrument Data ─────────────────────────────────────────────────
    INSTRUMENT_CSV: str = "https://images.dhan.co/api-data/api-scrip-master.csv"
    INSTRUMENT_MCX_DETAILED: str = f"{REST_BASE}/instrument/MCX_COMM"

    # ── REST Endpoint Paths ─────────────────────────────────────────────
    # Market feed
    MARKETFEED_LTP: str = "/marketfeed/ltp"
    MARKETFEED_QUOTE: str = "/marketfeed/quote"
    MARKETFEED_OHLC: str = "/marketfeed/ohlc"

    # Charts
    CHARTS_HISTORICAL: str = "/charts/historical"
    CHARTS_INTRADAY: str = "/charts/intraday"

    # Options
    OPTION_CHAIN: str = "/optionchain"

    # Orders
    ORDERS: str = "/orders"
    SLICE_ORDER: str = "/sliceorder"

    # Kill switch
    KILL_SWITCH: str = "/killswitch"

    # Instruments
    INSTRUMENTS: str = "/instruments"

    # Market status
    MARKET_STATUS: str = "/marketstatus"


# ═══════════════════════════════════════════════════════════════════════════════
# Upstox API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _UpstoxUrls:
    """Frozen dataclass holding all Upstox URL resolver methods.

    Two hosts:
    * ``base_v2`` — api.upstox.com (v2) for market data REST, option chain,
      profile, positions, holdings, funds, GTT authorize, news, etc.
    * ``base_hft`` — api-hft.upstox.com (v3) for order place/modify/cancel,
      GTT place/modify/cancel, feed authorize, token-request v3.

    Sandbox variants are ``sandbox-api.upstox.com`` and
    ``sandbox-api-hft.upstox.com``.
    """

    base_v2: str
    base_hft: str
    is_sandbox: bool = False

    # ── Host shortcuts ──────────────────────────────────────────────────
    def _v2(self) -> str:
        return f"{self.base_v2}/v2"

    def _v3(self) -> str:
        return f"{self.base_v2}/v3"

    def _hft(self) -> str:
        return f"{self.base_hft}/v3"

    # ── Asset (host-independent) ────────────────────────────────────────
    ASSET_INSTRUMENTS_JSON: str = _UPSTOX_ASSET_INSTRUMENTS_JSON

    # ── Auth ────────────────────────────────────────────────────────────
    def auth_dialog_url(self) -> str:
        return f"{self._v2()}/login/authorization/dialog"

    def auth_token_url(self) -> str:
        return f"{self._v2()}/login/authorization/token"

    def token_request_v3_url(self, client_id: str) -> str:
        return f"{self._v3()}/login/auth/token/request/{client_id}"

    def logout_url(self) -> str:
        return f"{self._v2()}/logout"

    def profile_url(self) -> str:
        return f"{self._v2()}/user/profile"

    # ── Market data (v2) ────────────────────────────────────────────────
    def market_quote_ltp_url(self) -> str:
        return f"{self._v2()}/market-quote/ltp"

    def market_quote_full_url(self) -> str:
        return f"{self._v2()}/market-quote/quotes"

    def market_quote_ohlc_url(self) -> str:
        return f"{self._v2()}/market-quote/ohlc"

    def market_quote_order_book_url(self) -> str:
        return f"{self._v2()}/market-quote/quotes"

    def historical_candle_url(
        self, instrument_key: str, interval: str, to_date: str, from_date: str | None = None
    ) -> str:
        url = f"{self._v2()}/historical-candle/{instrument_key}/{interval}/{to_date}"
        if from_date:
            url += f"/{from_date}"
        return url

    def market_status_url(self, exchange: str = "NSE") -> str:
        return f"{self._v2()}/market/status/{exchange}"

    def market_holidays_url(self) -> str:
        return f"{self._v2()}/market/holidays"

    # ── V3 market quote (Plus plan) ─────────────────────────────────────
    def market_quote_full_v3_url(self) -> str:
        return f"{self._v3()}/market-quote/full"

    def market_quote_option_greeks_v3_url(self) -> str:
        return f"{self._v3()}/market-quote/option-greeks"

    def market_quote_ltp_v3_url(self) -> str:
        return f"{self._v3()}/market-quote/ltp"

    # ── V3 historical candles (Plus plan) ──────────────────────────────
    def historical_candle_v3_url(
        self,
        instrument_key: str,
        unit: str,
        interval: int,
        to_date: str,
        from_date: str | None = None,
    ) -> str:
        """Build the v3 historical-candle URL.

        V3 supports custom intervals: 1-300 minutes, 1-5 hours,
        days/weeks/months. The unit/interval pair is part of the
        path. The resolver URL-encodes the instrument key for you.
        """
        from urllib.parse import quote

        encoded_key = quote(instrument_key, safe="")
        url = f"{self._v3()}/historical-candle/{encoded_key}/{unit}/{interval}/{to_date}"
        if from_date:
            url += f"/{from_date}"
        return url

    def intraday_candle_v3_url(
        self,
        instrument_key: str,
        unit: str,
        interval: int,
        to_date: str,
    ) -> str:
        """Build the v3 intraday-candle URL.

        V3 intraday differs from v2 in that it accepts arbitrary
        units (minutes/hours/days) and intervals. The resolver
        URL-encodes the instrument key for you.
        """
        from urllib.parse import quote

        encoded_key = quote(instrument_key, safe="")
        return f"{self._v3()}/intraday-candle/{encoded_key}/{unit}/{interval}/{to_date}"

    # ── WebSocket authorize (v2 / v3 HFT) ───────────────────────────────
    def feed_authorize_v2_url(self) -> str:
        return f"{self._v2()}/feed/market-data-feed/authorize"

    def feed_authorize_v3_url(self) -> str:
        return f"{self._v3()}/feed/market-data-feed/authorize"

    def portfolio_stream_authorize_url(self) -> str:
        return f"{self._v2()}/feed/portfolio-stream-feed/authorize"

    # ── Orders (v3 HFT) ─────────────────────────────────────────────────
    def place_order_v3_url(self) -> str:
        return f"{self._hft()}/order/place"

    def modify_order_v3_url(self) -> str:
        return f"{self._hft()}/order/modify"

    def cancel_order_v3_url(self) -> str:
        return f"{self._hft()}/order/cancel"

    def multi_order_v2_url(self) -> str:
        return f"{self._v2()}/order/multi/place"

    def order_book_url(self) -> str:
        return f"{self._v2()}/order/retrieve-all"

    def order_details_url(self) -> str:
        return f"{self._hft()}/order/details"

    def order_history_url(self) -> str:
        return f"{self._hft()}/order/history"

    def trades_for_day_url(self) -> str:
        return f"{self._v2()}/order/trades/get-trades-for-day"

    # ── Orders (v2 legacy) ──────────────────────────────────────────────
    def place_order_v2_url(self) -> str:
        return f"{self._v2()}/order/place"

    def modify_order_v2_url(self) -> str:
        return f"{self._v2()}/order/modify"

    def cancel_order_v2_url(self) -> str:
        return f"{self._v2()}/order/cancel"

    # ── GTT (v3 HFT) ────────────────────────────────────────────────────
    def gtt_place_url(self) -> str:
        return f"{self._hft()}/order/gtt/place"

    def gtt_modify_url(self) -> str:
        return f"{self._hft()}/order/gtt/modify"

    def gtt_cancel_url(self) -> str:
        return f"{self._hft()}/order/gtt/cancel"

    def gtt_orders_url(self) -> str:
        return f"{self._v3()}/order/gtt"

    def gtt_order_details_url(self) -> str:
        return f"{self._hft()}/order/gtt/order-details"

    # ── Portfolio (v2) ──────────────────────────────────────────────────
    def positions_url(self) -> str:
        return f"{self._v2()}/portfolio/short-term-positions"

    def holdings_url(self) -> str:
        return f"{self._v2()}/portfolio/long-term-holdings"

    def funds_url(self) -> str:
        return f"{self._v2()}/user/get-funds-and-margin"

    def convert_position_url(self) -> str:
        return f"{self._v2()}/portfolio/convert-position"

    def mtf_positions_v3_url(self) -> str:
        return f"{self._v3()}/portfolio/mtf-positions"

    # ── Options (v2) ────────────────────────────────────────────────────
    def option_contracts_url(self) -> str:
        return f"{self._v2()}/option/contracts"

    def option_chain_url(self) -> str:
        return f"{self._v2()}/option/chain"

    def option_expiry_url(self) -> str:
        return f"{self._v2()}/option/expiry"

    def option_greeks_url(self) -> str:
        return f"{self._v2()}/option/greeks"

    # ── Margin (v2) ─────────────────────────────────────────────────────
    def margin_requirement_url(self) -> str:
        return f"{self._v2()}/margin/requirement"

    def charges_brokerage_url(self) -> str:
        return f"{self._v2()}/charges/brokerage"

    def charges_margin_url(self) -> str:
        return f"{self._v2()}/charges/margin"

    # ── Expired instruments (Plus plan, v2) ─────────────────────────────
    def expired_expiries_url(self) -> str:
        return f"{self._v2()}/expired-instruments/expiries"

    def expired_option_contract_url(self) -> str:
        return f"{self._v2()}/expired-instruments/option/contract"

    def expired_historical_candle_url(
        self, key: str, interval: str, to_date: str, from_date: str
    ) -> str:
        return (
            f"{self._v2()}/expired-instruments/historical-candle/{key}"
            f"/{interval}/{to_date}/{from_date}"
        )

    def expired_future_contracts_url(self) -> str:
        return f"{self._v2()}/expired-instruments/future/contract"

    # ── News (v2) ───────────────────────────────────────────────────────
    def news_url(self) -> str:
        return f"{self._v2()}/news"

    # ── Market intelligence (v2) ────────────────────────────────────────
    def pcr_url(self) -> str:
        return f"{self._v2()}/market/pcr"

    def max_pain_url(self) -> str:
        return f"{self._v2()}/market/max-pain"

    def oi_url(self) -> str:
        return f"{self._v2()}/market/oi"

    def fii_url(self) -> str:
        return f"{self._v2()}/market/fii"

    def dii_url(self) -> str:
        return f"{self._v2()}/market/dii"

    def smartlist_futures_url(self) -> str:
        return f"{self._v2()}/market/smartlist/futures"

    def smartlist_options_url(self) -> str:
        return f"{self._v2()}/market/smartlist/options"

    # ── Instruments (v2) ────────────────────────────────────────────────
    def instrument_master_url(self, segment: str) -> str:
        return f"{self._v2()}/instrument/master/{segment}"

    def instrument_search_url(self) -> str:
        return f"{self._v2()}/instrument/search"

    def instrument_complete_url(self) -> str:
        return self.ASSET_INSTRUMENTS_JSON

    # ── User / risk (v2 / v3) ───────────────────────────────────────────
    def kill_switch_url(self) -> str:
        return f"{self._v2()}/user/kill-switch"

    def static_ip_url(self) -> str:
        return f"{self._v2()}/user/ip"

    def user_fund_margin_v3_url(self) -> str:
        return f"{self._v3()}/user/fund-margin"

    # ── Payments (v2) ───────────────────────────────────────────────────
    def payouts_url(self) -> str:
        return f"{self._v2()}/payments/payouts"

    # ── IPO / MF / Fundamentals (v2) ────────────────────────────────────
    def ipo_url(self) -> str:
        return f"{self._v2()}/ipos"

    def mutual_funds_holdings_url(self) -> str:
        return f"{self._v2()}/mutual-funds/holdings"

    def mutual_funds_order_url(self) -> str:
        return f"{self._v2()}/mutual-funds/order"

    def fundamentals_financials_url(self, isin: str, statement: str) -> str:
        return f"{self._v2()}/fundamentals/{isin}/{statement}"


class Upstox:
    """Upstox broker endpoint registry.

    Provides both production and sandbox :class:`_UpstoxUrls` instances
    so callers can pick the right environment at construction time.

    Usage::

        from config.endpoints import Upstox

        urls = Upstox.production()
        # or urls = Upstox.sandbox()

        client = UpstoxRestOrderClient(http, urls)
        url = urls.place_order_v3_url()
    """

    # ── Base hosts (used by _UpstoxUrls) ────────────────────────────────
    _PROD_V2: str = "https://api.upstox.com"
    _PROD_HFT: str = "https://api-hft.upstox.com"
    _SANDBOX_V2: str = "https://sandbox-api.upstox.com"
    _SANDBOX_HFT: str = "https://sandbox-api-hft.upstox.com"

    # ── Asset (host-independent) ────────────────────────────────────────
    ASSET_INSTRUMENTS_JSON: str = _UPSTOX_ASSET_INSTRUMENTS_JSON

    # ── Auth URL builder (standalone, no instance needed) ───────────────
    @staticmethod
    def auth_dialog_url(is_sandbox: bool = False) -> str:
        """Build the OAuth authorization dialog URL without an instance."""
        base = Upstox._SANDBOX_V2 if is_sandbox else Upstox._PROD_V2
        return f"{base}/v2/login/authorization/dialog"

    # ── Instance factories ──────────────────────────────────────────────
    @classmethod
    def production(cls) -> _UpstoxUrls:
        """Return a frozen URL resolver for the production environment."""
        return _UpstoxUrls(base_v2=cls._PROD_V2, base_hft=cls._PROD_HFT, is_sandbox=False)

    @classmethod
    def sandbox(cls) -> _UpstoxUrls:
        """Return a frozen URL resolver for the sandbox environment."""
        return _UpstoxUrls(base_v2=cls._SANDBOX_V2, base_hft=cls._SANDBOX_HFT, is_sandbox=True)
