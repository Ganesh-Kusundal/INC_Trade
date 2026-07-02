"""Unified broker contract test suite — Dhan implementation.

Every test in ``DhanBrokerContractSuite`` validates a contract that ANY broker
adapter (Dhan, Upstox, future brokers) must satisfy.  The suite is split into:

* **Offline tests** — use ``FakeHttpClient`` + ``SymbolResolver`` loaded with
  ``SAMPLE_ROWS``.  These run in CI with zero network access.
* **Live tests** — use ``BrokerFactory.create()`` and are guarded by
  ``@pytest.mark.skipif`` when ``.env.local`` is absent.  Rate-limit sleeps
  are inserted between API calls (1.5 s for quotes, 3.5 s for option chain).

Both Dhan and Upstox must pass equivalent contract suites to guarantee that
any future broker can be added safely behind the ``BrokerGateway`` facade.
"""

from __future__ import annotations

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running from any cwd
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.connection import DhanConnection
from brokers.dhan.domain import (
    Exchange,
)
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.orders import IdempotencyCache
from brokers.dhan.tests.conftest import SAMPLE_ROWS, FakeHttpClient
from domain import MarketDepth, OrderStatus, Quote

# ---------------------------------------------------------------------------
# Live-skip guard
# ---------------------------------------------------------------------------
ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


def _should_skip_live() -> bool:
    """Skip live tests if credentials missing, token expired, or market is closed."""
    if not _live_env_loaded:
        return True
    # Validate token is not expired by checking JWT exp claim
    token = os.environ.get("DHAN_ACCESS_TOKEN", "")
    import time as _time

    from brokers.common.auth.jwt_expiry import JwtExpiry

    exp_ms = JwtExpiry.parse_expiry_epoch_ms(token)
    if exp_ms > 0 and exp_ms < _time.time() * 1000:
        return True
    from tests.market_hours import is_market_open

    return not is_market_open()


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason="Live API tests require .env.local credentials and open market hours",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def offline_gateway() -> BrokerGateway:
    """BrokerGateway backed by FakeHttpClient — no network access needed."""
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    return BrokerGateway(conn)


@pytest.fixture(scope="module")
def live_gateway() -> BrokerGateway:
    """BrokerGateway backed by the real Dhan API — requires .env.local."""
    gw = BrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    gw.close()


# ===========================================================================
# Contract Suite
# ===========================================================================


class DhanBrokerContractSuite:
    """Contract tests that every broker adapter must pass.

    The tests are grouped into six contract areas:
    1. Instrument Resolution
    2. Market Data
    3. Orders
    4. Portfolio
    5. Options
    6. Futures
    """

    # ── 1. Instrument Resolution Contract ──────────────────────────────

    def test_resolver_loaded(self, offline_gateway: BrokerGateway) -> None:
        """After loading, instruments.stats()['loaded'] must be True."""
        stats = offline_gateway.extended.instruments.stats()
        assert stats["loaded"] is True

    def test_resolve_equity(self, offline_gateway: BrokerGateway) -> None:
        """resolve('RELIANCE', 'NSE') must return an Instrument with a security_id."""
        inst = offline_gateway.extended.instruments.resolve("RELIANCE", "NSE")
        assert inst.security_id, "security_id must be non-empty"
        assert inst.exchange == Exchange.NSE

    def test_resolve_index(self, offline_gateway: BrokerGateway) -> None:
        """resolve('NIFTY', 'INDEX') must return an Instrument."""
        inst = offline_gateway.extended.instruments.resolve("NIFTY", "INDEX")
        assert inst.security_id, "security_id must be non-empty"
        assert inst.exchange == Exchange.INDEX

    def test_resolve_unknown_raises(self, offline_gateway: BrokerGateway) -> None:
        """resolve('DOESNOTEXIST', 'NSE') must raise InstrumentNotFoundError."""
        with pytest.raises(InstrumentNotFoundError):
            offline_gateway.extended.instruments.resolve("DOESNOTEXIST", "NSE")

    # ── 2. Market Data Contract (live) ─────────────────────────────────

    @skip_live
    def test_quote_returns_quote_type(self, live_gateway: BrokerGateway) -> None:
        """Gateway.quote() must return a Quote-like object with ltp > 0."""
        quote = live_gateway.quote("RELIANCE", "NSE")
        assert isinstance(quote, Quote)
        assert quote.ltp > 0
        time.sleep(1.5)

    @skip_live
    def test_depth_returns_bids_asks(self, live_gateway: BrokerGateway) -> None:
        """Gateway.depth() must return an object with bids and asks."""
        depth = live_gateway.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth)
        assert hasattr(depth, "bids")
        assert hasattr(depth, "asks")
        assert len(depth.bids) > 0, "bids must be non-empty for a liquid stock"
        assert len(depth.asks) > 0, "asks must be non-empty for a liquid stock"
        time.sleep(1.5)

    @skip_live
    def test_ltp_returns_decimal(self, live_gateway: BrokerGateway) -> None:
        """Gateway.ltp() must return a Decimal > 0."""
        ltp = live_gateway.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        assert ltp > 0
        time.sleep(1.5)

    # ── 3. Order Contract ──────────────────────────────────────────────

    def test_order_status_normalize(self) -> None:
        """OrderStatus.normalize('COMPLETE') must map to FILLED.

        This is a broker-agnostic domain contract — every adapter relies on
        the same normalization mapping.
        """
        assert OrderStatus.normalize("COMPLETE") == OrderStatus.FILLED
        assert OrderStatus.normalize("EXECUTED") == OrderStatus.FILLED
        assert OrderStatus.normalize("TRANSIT") == OrderStatus.OPEN
        assert OrderStatus.normalize("TRIGGER PENDING") == OrderStatus.OPEN
        assert OrderStatus.normalize("PARTIALLY_EXECUTED") == OrderStatus.PARTIALLY_FILLED

    def test_order_validation_rejects_bad_lot(self, offline_gateway: BrokerGateway) -> None:
        """validate_order with wrong lot size must return errors.

        NIFTY 26 JUN FUT has lot_size=75; quantity=10 is not a valid multiple.
        """
        errors = offline_gateway.extended.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=10,
            order_type="MARKET",
            product_type="INTRADAY",
        )
        assert len(errors) > 0, "Expected validation errors for non-lot-aligned quantity"
        assert any("lot size" in e.lower() or "multiple" in e.lower() for e in errors)

    def test_order_validation_rejects_bad_product(self, offline_gateway: BrokerGateway) -> None:
        """validate_order with CNC on NFO must return errors.

        CNC is an equity-only product type and is not valid for derivatives (NSE_FNO).
        """
        errors = offline_gateway.extended.validate_order(
            symbol="NIFTY 26 JUN FUT",
            exchange="NFO",
            quantity=75,
            order_type="MARKET",
            product_type="CNC",
        )
        assert len(errors) > 0, "Expected validation errors for CNC on derivative segment"
        assert any("CNC" in e or "product" in e.lower() for e in errors)

    def test_idempotency_cache_exists(self, offline_gateway: BrokerGateway) -> None:
        """The extended orders adapter must expose an idempotency cache to prevent duplicate orders."""
        assert hasattr(offline_gateway.extended.orders, "_idempotency")
        cache = offline_gateway.extended.orders._idempotency
        assert isinstance(cache, IdempotencyCache)

    # ── 4. Portfolio Contract (live) ───────────────────────────────────

    @skip_live
    def test_positions_returns_list(self, live_gateway: BrokerGateway) -> None:
        """extended.get_positions() must return a list."""
        positions = live_gateway.extended.get_positions()
        assert isinstance(positions, list)

    @skip_live
    def test_holdings_returns_list(self, live_gateway: BrokerGateway) -> None:
        """extended.get_holdings() must return a list."""
        holdings = live_gateway.extended.get_holdings()
        assert isinstance(holdings, list)

    @skip_live
    def test_balance_returns_balance(self, live_gateway: BrokerGateway) -> None:
        """extended.get_balance() must return a Balance-like object with available_balance."""
        balance = live_gateway.extended.get_balance()
        # Accept either the Dhan-specific Balance or the canonical Balance
        assert hasattr(balance, "available_balance")
        assert isinstance(balance.available_balance, Decimal)

    # ── 5. Options Contract (live) ─────────────────────────────────────

    @skip_live
    def test_expiries_returns_list(self, live_gateway: BrokerGateway) -> None:
        """extended.get_expiries('NIFTY', 'INDEX') must return a non-empty list."""
        expiries = live_gateway.extended.get_expiries("NIFTY", "INDEX")
        assert isinstance(expiries, list)
        assert len(expiries) > 0, "NIFTY must have at least one expiry"

    @skip_live
    def test_option_chain_has_strikes(self, live_gateway: BrokerGateway) -> None:
        """Option chain must have strikes, each with 'call' and 'put' dicts."""
        expiries = live_gateway.extended.get_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

        time.sleep(3.5)

        chain = live_gateway.extended.get_option_chain("NIFTY", "INDEX", expiries[0])
        assert "strikes" in chain
        assert len(chain["strikes"]) > 0

        first_strike = chain["strikes"][0]
        assert "call" in first_strike, "Each strike must have a 'call' leg"
        assert "put" in first_strike, "Each strike must have a 'put' leg"
        assert isinstance(first_strike["call"], dict)
        assert isinstance(first_strike["put"], dict)

    # ── 6. Futures Contract (offline) ──────────────────────────────────

    def test_futures_returns_contracts(self, offline_gateway: BrokerGateway) -> None:
        """futures.get_contracts('GOLD', 'MCX') must return a list of contract dicts."""
        contracts = offline_gateway.extended.get_futures_contracts("GOLD", "MCX")
        assert isinstance(contracts, list)
        assert len(contracts) > 0, "GOLD must have at least one futures contract in cache"
        # Each contract must expose the standard keys
        for contract in contracts:
            assert "security_id" in contract
            assert "expiry" in contract
            assert "lot_size" in contract

    def test_is_commodity(self, offline_gateway: BrokerGateway) -> None:
        """futures.is_commodity('GOLD') must be True; is_commodity('RELIANCE') must be False."""
        assert offline_gateway.extended.is_commodity("GOLD") is True
        assert offline_gateway.extended.is_commodity("SILVER") is True
        assert offline_gateway.extended.is_commodity("CRUDEOIL") is True
        assert offline_gateway.extended.is_commodity("RELIANCE") is False
        assert offline_gateway.extended.is_commodity("NIFTY") is False


# ---------------------------------------------------------------------------
# Pytest-collectable subclass — inherits every contract test above.
#
# ``DhanBrokerContractSuite`` is the canonical suite name (mirrors the
# ``BrokerContractSuite`` base class pattern in brokers.common.contracts).
# Pytest requires a ``Test*``-prefixed class for collection, so this thin
# subclass bridges the two conventions without duplicating any logic.
# ---------------------------------------------------------------------------


class TestDhanBrokerContract(DhanBrokerContractSuite):
    pass
