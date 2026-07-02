"""Upstox API URL resolver.

Thin wrapper around :class:`config.endpoints._UpstoxUrls` — all URL
logic lives in the central endpoint registry. This class exists solely
to bridge the existing ``UpstoxApiUrlResolver(settings)`` constructor
pattern (used across 12+ client classes) to the new canonical resolver.

Upstox splits its API across two hosts:

* ``api.upstox.com`` (v2) — market data REST, option chain, profile, positions,
  holdings, funds, GTT authorize, news, etc.
* ``api-hft.upstox.com`` (v3) — order place/modify/cancel/details, GTT
  place/modify/cancel, feed authorize, token-request v3.

Sandbox uses ``sandbox-api.upstox.com`` and ``sandbox-api-hft.upstox.com``.
"""

from __future__ import annotations

from typing import Any

from config.endpoints import _UpstoxUrls


class UpstoxApiUrlResolver:
    """Build full URLs for every Upstox endpoint.

    Delegates all URL construction to the canonical
    :class:`config.endpoints._UpstoxUrls` dataclass.

    Usage (unchanged)::

        resolver = UpstoxApiUrlResolver(settings)
        url = resolver.place_order_v3_url()
    """

    def __init__(self, settings: Any) -> None:
        self._delegate = _UpstoxUrls(
            base_v2=settings.base_v2,
            base_hft=settings.base_hft,
            is_sandbox=settings.is_sandbox,
        )

    # ── Internal shortcuts (accessed externally by order_client.py) ──
    def _v2(self) -> str:
        return self._delegate._v2()

    def _v3(self) -> str:
        return self._delegate._v3()

    def _hft(self) -> str:
        return self._delegate._hft()

    # ── Auth ────────────────────────────────────────────────────────
    def auth_dialog_url(self) -> str:
        return self._delegate.auth_dialog_url()

    def auth_token_url(self) -> str:
        return self._delegate.auth_token_url()

    def token_request_v3_url(self, client_id: str) -> str:
        return self._delegate.token_request_v3_url(client_id)

    def logout_url(self) -> str:
        return self._delegate.logout_url()

    def profile_url(self) -> str:
        return self._delegate.profile_url()

    # ── Market data (v2) ────────────────────────────────────────────
    def market_quote_ltp_url(self) -> str:
        return self._delegate.market_quote_ltp_url()

    def market_quote_full_url(self) -> str:
        return self._delegate.market_quote_full_url()

    def market_quote_ohlc_url(self) -> str:
        return self._delegate.market_quote_ohlc_url()

    def market_quote_order_book_url(self) -> str:
        return self._delegate.market_quote_order_book_url()

    def historical_candle_url(
        self, instrument_key: str, interval: str, to_date: str, from_date: str | None = None
    ) -> str:
        return self._delegate.historical_candle_url(instrument_key, interval, to_date, from_date)

    def market_status_url(self, exchange: str = "NSE") -> str:
        return self._delegate.market_status_url(exchange)

    def market_holidays_url(self) -> str:
        return self._delegate.market_holidays_url()

    # ── V3 market quote (Plus plan) ─────────────────────────────────
    def market_quote_full_v3_url(self) -> str:
        return self._delegate.market_quote_full_v3_url()

    def market_quote_option_greeks_v3_url(self) -> str:
        return self._delegate.market_quote_option_greeks_v3_url()

    def market_quote_ltp_v3_url(self) -> str:
        return self._delegate.market_quote_ltp_v3_url()

    # ── WebSocket authorize (v2/v3, HFT) ───────────────────────────
    def feed_authorize_v2_url(self) -> str:
        return self._delegate.feed_authorize_v2_url()

    def feed_authorize_v3_url(self) -> str:
        return self._delegate.feed_authorize_v3_url()

    def portfolio_stream_authorize_url(self) -> str:
        return self._delegate.portfolio_stream_authorize_url()

    # ── Orders (v3, HFT) ────────────────────────────────────────────
    def place_order_v3_url(self) -> str:
        return self._delegate.place_order_v3_url()

    def modify_order_v3_url(self) -> str:
        return self._delegate.modify_order_v3_url()

    def cancel_order_v3_url(self) -> str:
        return self._delegate.cancel_order_v3_url()

    def multi_order_v2_url(self) -> str:
        return self._delegate.multi_order_v2_url()

    def order_book_url(self) -> str:
        return self._delegate.order_book_url()

    def order_details_url(self) -> str:
        return self._delegate.order_details_url()

    def order_history_url(self) -> str:
        return self._delegate.order_history_url()

    def trades_for_day_url(self) -> str:
        return self._delegate.trades_for_day_url()

    # ── Orders (v2 legacy) ──────────────────────────────────────────
    def place_order_v2_url(self) -> str:
        return self._delegate.place_order_v2_url()

    def modify_order_v2_url(self) -> str:
        return self._delegate.modify_order_v2_url()

    def cancel_order_v2_url(self) -> str:
        return self._delegate.cancel_order_v2_url()

    # ── GTT (v3, HFT) ───────────────────────────────────────────────
    def gtt_place_url(self) -> str:
        return self._delegate.gtt_place_url()

    def gtt_modify_url(self) -> str:
        return self._delegate.gtt_modify_url()

    def gtt_cancel_url(self) -> str:
        return self._delegate.gtt_cancel_url()

    def gtt_orders_url(self) -> str:
        return self._delegate.gtt_orders_url()

    def gtt_order_details_url(self) -> str:
        return self._delegate.gtt_order_details_url()

    # ── Portfolio (v2) ──────────────────────────────────────────────
    def positions_url(self) -> str:
        return self._delegate.positions_url()

    def holdings_url(self) -> str:
        return self._delegate.holdings_url()

    def funds_url(self) -> str:
        return self._delegate.funds_url()

    def convert_position_url(self) -> str:
        return self._delegate.convert_position_url()

    def mtf_positions_v3_url(self) -> str:
        return self._delegate.mtf_positions_v3_url()

    # ── Options (v2) ────────────────────────────────────────────────
    def option_contracts_url(self) -> str:
        return self._delegate.option_contracts_url()

    def option_chain_url(self) -> str:
        return self._delegate.option_chain_url()

    def option_expiry_url(self) -> str:
        return self._delegate.option_expiry_url()

    def option_greeks_url(self) -> str:
        return self._delegate.option_greeks_url()

    # ── Margin (v2) ─────────────────────────────────────────────────
    def margin_requirement_url(self) -> str:
        return self._delegate.margin_requirement_url()

    def charges_brokerage_url(self) -> str:
        return self._delegate.charges_brokerage_url()

    def charges_margin_url(self) -> str:
        return self._delegate.charges_margin_url()

    # ── Expired instruments (Plus plan, v2) ─────────────────────────
    def expired_expiries_url(self) -> str:
        return self._delegate.expired_expiries_url()

    def expired_option_contract_url(self) -> str:
        return self._delegate.expired_option_contract_url()

    def expired_historical_candle_url(
        self, key: str, interval: str, to_date: str, from_date: str
    ) -> str:
        return self._delegate.expired_historical_candle_url(key, interval, to_date, from_date)

    def expired_future_contracts_url(self) -> str:
        return self._delegate.expired_future_contracts_url()

    # ── News (v2) ───────────────────────────────────────────────────
    def news_url(self) -> str:
        return self._delegate.news_url()

    # ── Market intelligence (v2) ────────────────────────────────────
    def pcr_url(self) -> str:
        return self._delegate.pcr_url()

    def max_pain_url(self) -> str:
        return self._delegate.max_pain_url()

    def oi_url(self) -> str:
        return self._delegate.oi_url()

    def fii_url(self) -> str:
        return self._delegate.fii_url()

    def dii_url(self) -> str:
        return self._delegate.dii_url()

    def smartlist_futures_url(self) -> str:
        return self._delegate.smartlist_futures_url()

    def smartlist_options_url(self) -> str:
        return self._delegate.smartlist_options_url()

    # ── Instruments (v2) ────────────────────────────────────────────
    def instrument_master_url(self, segment: str) -> str:
        return self._delegate.instrument_master_url(segment)

    def instrument_search_url(self) -> str:
        return self._delegate.instrument_search_url()

    def instrument_complete_url(self) -> str:
        return self._delegate.instrument_complete_url()

    # ── User / risk (v2/v3) ─────────────────────────────────────────
    def kill_switch_url(self) -> str:
        return self._delegate.kill_switch_url()

    def static_ip_url(self) -> str:
        return self._delegate.static_ip_url()

    def user_fund_margin_v3_url(self) -> str:
        return self._delegate.user_fund_margin_v3_url()

    # ── Payments (v2) ───────────────────────────────────────────────
    def payouts_url(self) -> str:
        return self._delegate.payouts_url()

    # ── IPO / MF / Fundamentals (v2) ────────────────────────────────
    def ipo_url(self) -> str:
        return self._delegate.ipo_url()

    def mutual_funds_holdings_url(self) -> str:
        return self._delegate.mutual_funds_holdings_url()

    def mutual_funds_order_url(self) -> str:
        return self._delegate.mutual_funds_order_url()

    def fundamentals_financials_url(self, isin: str, statement: str) -> str:
        return self._delegate.fundamentals_financials_url(isin, statement)
