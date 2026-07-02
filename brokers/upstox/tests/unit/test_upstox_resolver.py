"""Unit tests for UpstoxInstrumentResolver robust lookup and alternate key generation.

Tests cover:
- Primary instrument_key lookup
- Symbol + exchange_segment lookup
- Alternate key generation for options (CE/PE, weekly, monthly)
- Alternate key generation for futures
- CALL/PUT normalization in resolve()
- search() prefix queries
- Thread-safety basics
"""

from __future__ import annotations

from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver, _generate_alternate_keys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _defn(
    instrument_key: str,
    symbol: str = "",
    name: str = "",
    exchange_segment: str = "NSE_FO",
    instrument_type: str = "OPTION",
    expiry: str | None = None,
    strike: float | None = None,
    option_type: str | None = None,
    underlying_symbol: str | None = None,
) -> UpstoxInstrumentDefinition:
    return UpstoxInstrumentDefinition(
        instrument_key=instrument_key,
        symbol=symbol,
        name=name,
        exchange=exchange_segment.split("_")[0],
        exchange_segment=exchange_segment,
        instrument_type=instrument_type,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        underlying_symbol=underlying_symbol,
    )


# ---------------------------------------------------------------------------
# Basic resolution
# ---------------------------------------------------------------------------


class TestResolverBasicLookup:
    def test_resolve_by_instrument_key(self):
        resolver = UpstoxInstrumentResolver()
        d = _defn(
            "NSE_EQ|RELIANCE",
            symbol="RELIANCE",
            exchange_segment="NSE_EQ",
            instrument_type="EQUITY",
        )
        resolver.register(d)

        result = resolver.resolve(instrument_key="NSE_EQ|RELIANCE")
        assert result is not None
        assert result.instrument_key == "NSE_EQ|RELIANCE"

    def test_resolve_by_symbol_and_segment(self):
        resolver = UpstoxInstrumentResolver()
        d = _defn("NSE_EQ|INFY", symbol="INFY", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        resolver.register(d)

        result = resolver.resolve(symbol="INFY", exchange_segment="NSE_EQ")
        assert result is not None
        assert result.symbol == "INFY"

    def test_resolve_case_insensitive(self):
        resolver = UpstoxInstrumentResolver()
        d = _defn("NSE_EQ|TCS", symbol="TCS", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        resolver.register(d)

        result = resolver.resolve(symbol="tcs", exchange_segment="nse_eq")
        assert result is not None

    def test_resolve_missing_returns_none(self):
        resolver = UpstoxInstrumentResolver()
        result = resolver.resolve(symbol="MISSING", exchange_segment="NSE_EQ")
        assert result is None

    def test_resolve_call_normalised_to_ce(self):
        resolver = UpstoxInstrumentResolver()
        d = _defn(
            "NSE_FO|NIFTY22MAY2524000CE",
            symbol="NIFTY22MAY2524000CE",
            exchange_segment="NSE_FO",
            instrument_type="OPTION",
            expiry="2025-05-22",
            strike=24000.0,
            option_type="CE",
            underlying_symbol="NIFTY",
        )
        resolver.register(d)

        # User passes "CALL" suffix — should still resolve
        result = resolver.resolve(symbol="NIFTY22MAY2524000CALL", exchange_segment="NSE_FO")
        assert result is not None
        assert result.instrument_key == "NSE_FO|NIFTY22MAY2524000CE"

    def test_resolve_put_normalised_to_pe(self):
        resolver = UpstoxInstrumentResolver()
        d = _defn(
            "NSE_FO|NIFTY22MAY2524000PE",
            symbol="NIFTY22MAY2524000PE",
            exchange_segment="NSE_FO",
            instrument_type="OPTION",
            expiry="2025-05-22",
            strike=24000.0,
            option_type="PE",
            underlying_symbol="NIFTY",
        )
        resolver.register(d)

        result = resolver.resolve(symbol="NIFTY22MAY2524000PUT", exchange_segment="NSE_FO")
        assert result is not None
        assert result.instrument_key == "NSE_FO|NIFTY22MAY2524000PE"

    def test_is_loaded_after_register(self):
        resolver = UpstoxInstrumentResolver()
        assert not resolver.is_loaded()
        d = _defn("NSE_EQ|X", symbol="X", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        resolver.register(d)
        assert resolver.is_loaded()

    def test_reset_clears_all(self):
        resolver = UpstoxInstrumentResolver()
        d = _defn("NSE_EQ|Y", symbol="Y", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        resolver.register(d)
        resolver.reset()
        assert not resolver.is_loaded()
        assert resolver.resolve(symbol="Y", exchange_segment="NSE_EQ") is None


# ---------------------------------------------------------------------------
# Alternate key generation
# ---------------------------------------------------------------------------


class TestGenerateAlternateKeys:
    def test_equity_produces_basic_keys(self):
        keys = _generate_alternate_keys(
            symbol="RELIANCE",
            inst_type="EQUITY",
            expiry=None,
            strike=None,
            option_type=None,
            underlying=None,
            canonical_symbol="RELIANCE",
        )
        assert "RELIANCE" in keys

    def test_option_generates_spaced_and_compact(self):
        keys = _generate_alternate_keys(
            symbol="NIFTY22MAY2524000CE",
            inst_type="OPTION",
            expiry="2025-05-22",
            strike=24000.0,
            option_type="CE",
            underlying="NIFTY",
            canonical_symbol="NIFTY 22 MAY 25 24000 CE",
        )
        # Compact forms
        assert "NIFTY22MAY2524000CE" in keys
        # Spaced forms
        assert "NIFTY 22 MAY 25 24000 CE" in keys

    def test_option_put_alternate_keys(self):
        keys = _generate_alternate_keys(
            symbol="BANKNIFTY29MAY2551000PE",
            inst_type="OPTION",
            expiry="2025-05-29",
            strike=51000.0,
            option_type="PE",
            underlying="BANKNIFTY",
            canonical_symbol="BANKNIFTY 29 MAY 25 51000 PE",
        )
        assert "BANKNIFTY 29 MAY 25 51000 PE" in keys
        assert "BANKNIFTY29MAY2551000PE" in keys

    def test_future_generates_fut_keys(self):
        keys = _generate_alternate_keys(
            symbol="NIFTYFUT",
            inst_type="FUTURE",
            expiry="2025-05-29",
            strike=None,
            option_type=None,
            underlying="NIFTY",
            canonical_symbol=None,
        )
        assert any("FUT" in k for k in keys)

    def test_no_duplicates(self):
        keys = _generate_alternate_keys(
            symbol="RELIANCE",
            inst_type="EQUITY",
            expiry=None,
            strike=None,
            option_type=None,
            underlying=None,
            canonical_symbol="RELIANCE",
        )
        assert len(keys) == len(set(keys))

    def test_no_empty_keys(self):
        keys = _generate_alternate_keys(
            symbol="INFY",
            inst_type="EQUITY",
            expiry=None,
            strike=None,
            option_type=None,
            underlying=None,
            canonical_symbol=None,
        )
        assert all(k for k in keys)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestResolverSearch:
    def test_prefix_search(self):
        resolver = UpstoxInstrumentResolver()
        for sym in ("RELIANCE", "RELIANCEETF", "TCS", "TATA"):
            resolver.register(
                _defn(
                    f"NSE_EQ|{sym}", symbol=sym, exchange_segment="NSE_EQ", instrument_type="EQUITY"
                )
            )

        results = resolver.search("RELIAN")
        syms = {r.symbol for r in results}
        assert "RELIANCE" in syms
        assert "RELIANCEETF" in syms
        assert "TCS" not in syms

    def test_search_with_segment_filter(self):
        resolver = UpstoxInstrumentResolver()
        resolver.register(
            _defn("NSE_EQ|TCS", symbol="TCS", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        )
        resolver.register(
            _defn("BSE_EQ|TCS", symbol="TCS", exchange_segment="BSE_EQ", instrument_type="EQUITY")
        )

        results = resolver.search("TCS", exchange_segment="NSE_EQ")
        assert all(r.exchange_segment.upper() == "NSE_EQ" for r in results)

    def test_search_empty_prefix(self):
        resolver = UpstoxInstrumentResolver()
        resolver.register(
            _defn("NSE_EQ|X", symbol="X", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        )
        assert resolver.search("") == []

    def test_search_limit(self):
        resolver = UpstoxInstrumentResolver()
        for i in range(20):
            sym = f"STOCK{i:02d}"
            resolver.register(
                _defn(
                    f"NSE_EQ|{sym}", symbol=sym, exchange_segment="NSE_EQ", instrument_type="EQUITY"
                )
            )

        results = resolver.search("STOCK", limit=5)
        assert len(results) <= 5


# ---------------------------------------------------------------------------
# register_many / len
# ---------------------------------------------------------------------------


class TestResolverBulk:
    def test_register_many(self):
        resolver = UpstoxInstrumentResolver()
        defns = [
            _defn(
                f"NSE_EQ|S{i}", symbol=f"S{i}", exchange_segment="NSE_EQ", instrument_type="EQUITY"
            )
            for i in range(10)
        ]
        resolver.register_many(defns)
        assert len(resolver) == 10

    def test_keys_returns_all_instrument_keys(self):
        resolver = UpstoxInstrumentResolver()
        resolver.register(
            _defn("NSE_EQ|A", symbol="A", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        )
        resolver.register(
            _defn("NSE_EQ|B", symbol="B", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        )
        assert set(resolver.keys()) == {"NSE_EQ|A", "NSE_EQ|B"}


# ---------------------------------------------------------------------------
# Option expiry derivation (replaces deprecated /v2/option/expiry)
# ---------------------------------------------------------------------------
class TestListOptionExpiries:
    def test_derives_sorted_future_expiries(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=7)).isoformat()
        farther = (date.today() + timedelta(days=30)).isoformat()
        resolver = UpstoxInstrumentResolver()
        resolver.register(
            _defn(
                "NSE_FO|NIFTY 24JUN26 25000 CE",
                symbol="NIFTY 24JUN26 25000 CE",
                exchange_segment="NSE_FO",
                instrument_type="OPTION",
                expiry=future,
                strike=25000,
                option_type="CE",
                underlying_symbol="NIFTY",
            )
        )
        resolver.register(
            _defn(
                "NSE_FO|NIFTY 30JUL26 25000 CE",
                symbol="NIFTY 30JUL26 25000 CE",
                exchange_segment="NSE_FO",
                instrument_type="OPTION",
                expiry=farther,
                strike=25000,
                option_type="CE",
                underlying_symbol="NIFTY",
            )
        )
        result = resolver.list_option_expiries("NIFTY")
        assert result == sorted(result)
        assert future in result
        assert farther in result

    def test_filters_past_expiries(self):
        from datetime import date, timedelta

        past = (date.today() - timedelta(days=14)).isoformat()
        future = (date.today() + timedelta(days=14)).isoformat()
        resolver = UpstoxInstrumentResolver()
        resolver.register(
            _defn(
                "NSE_FO|NIFTY PAST CE",
                symbol="NIFTY PAST CE",
                exchange_segment="NSE_FO",
                instrument_type="OPTION",
                expiry=past,
                option_type="CE",
                underlying_symbol="NIFTY",
            )
        )
        resolver.register(
            _defn(
                "NSE_FO|NIFTY FUTURE CE",
                symbol="NIFTY FUTURE CE",
                exchange_segment="NSE_FO",
                instrument_type="OPTION",
                expiry=future,
                option_type="CE",
                underlying_symbol="NIFTY",
            )
        )
        result = resolver.list_option_expiries("NIFTY")
        assert past not in result
        assert future in result

    def test_unknown_underlying_returns_empty(self):
        resolver = UpstoxInstrumentResolver()
        # Register an unrelated instrument so the resolver is "loaded".
        resolver.register(
            _defn("NSE_EQ|TCS", symbol="TCS", exchange_segment="NSE_EQ", instrument_type="EQUITY")
        )
        assert resolver.list_option_expiries("NIFTY") == []

    def test_unloaded_raises(self):
        # An empty resolver that has never been registered against is not
        # "loaded" — get_expiries must surface this clearly.
        resolver = UpstoxInstrumentResolver()
        with __import__("pytest").raises(RuntimeError):
            resolver.list_option_expiries("NIFTY")

    def test_resets_expiry_index(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=7)).isoformat()
        resolver = UpstoxInstrumentResolver()
        resolver.register(
            _defn(
                "NSE_FO|NIFTY 24JUN26 25000 CE",
                symbol="NIFTY 24JUN26 25000 CE",
                exchange_segment="NSE_FO",
                instrument_type="OPTION",
                expiry=future,
                option_type="CE",
                underlying_symbol="NIFTY",
            )
        )
        assert len(resolver.list_option_expiries("NIFTY")) == 1
        resolver.reset()
        with __import__("pytest").raises(RuntimeError):
            resolver.list_option_expiries("NIFTY")
