"""
Tests for futures research analytics.
"""

import pytest

from derivatives_strategies.research.models import FuturesQuote, VolRegime
from derivatives_strategies.research.futures import (
    parse_future_symbol,
    annualized_roll_yield,
    analyze_futures,
)
from derivatives_strategies.research.sources import SampleResearchSource
from datetime import date


class TestParseFutureSymbol:
    def test_parses_es(self):
        c = parse_future_symbol("/ESM26")
        assert c is not None
        assert c.root == "/ES"
        assert c.month == 6
        assert c.year == 2026

    def test_parses_without_slash(self):
        c = parse_future_symbol("CLZ27")
        assert c.root == "/CL"
        assert c.month == 12
        assert c.year == 2027

    def test_rejects_garbage(self):
        assert parse_future_symbol("AAPL") is None
        assert parse_future_symbol("/ES") is None


class TestRollYield:
    def test_contango_negative_roll(self):
        # Far richer than near over ~90 days => negative roll yield.
        ry = annualized_roll_yield(
            near_price=100.0, far_price=102.0,
            near_expiry=date(2026, 3, 15), far_expiry=date(2026, 6, 15),
        )
        assert ry < 0

    def test_backwardation_positive_roll(self):
        ry = annualized_roll_yield(
            near_price=102.0, far_price=100.0,
            near_expiry=date(2026, 3, 15), far_expiry=date(2026, 6, 15),
        )
        assert ry > 0

    def test_invalid_returns_none(self):
        assert annualized_roll_yield(100, 100, date(2026, 6, 15), date(2026, 6, 15)) is None

    def test_non_finite_prices_return_none(self):
        # Regression: stress test surfaced inf roll yields from bad prices.
        inf = float("inf")
        nan = float("nan")
        assert annualized_roll_yield(inf, 100, date(2026, 3, 15), date(2026, 6, 15)) is None
        assert annualized_roll_yield(100, nan, date(2026, 3, 15), date(2026, 6, 15)) is None

    def test_brief_roll_yield_always_finite_with_garbage_prices(self):
        bad = [
            FuturesQuote.from_quote_payload("/ESM26", {"symbol": "/ESM26", "mark": float("inf")}),
            FuturesQuote.from_quote_payload("/ESU26", {"symbol": "/ESU26", "mark": 1e-12}),
            FuturesQuote.from_quote_payload("/ESZ26", {"symbol": "/ESZ26", "mark": 7500.0}),
        ]
        brief = analyze_futures(bad)
        ry = brief.annualized_roll_yield_pct
        assert ry is None or (isinstance(ry, float) and ry == ry and ry not in (float("inf"), float("-inf")))


class TestAnalyzeFutures:
    def _q(self, sym, price):
        return FuturesQuote.from_quote_payload(sym, {"symbol": sym, "mark": price})

    def test_contango_curve(self):
        quotes = [
            self._q("/ESM26", 7436.25),
            self._q("/ESU26", 7472.00),
            self._q("/ESZ26", 7509.50),
        ]
        brief = analyze_futures(quotes, as_of="2026-06-14")
        assert brief.root == "/ES"
        assert brief.shape == "contango"
        assert brief.front_price == pytest.approx(7436.25)
        assert len(brief.term_structure) == 3
        assert len(brief.calendar_spreads) == 2
        assert brief.annualized_roll_yield_pct < 0
        assert any("contango" in s.lower() for s in brief.signals)

    def test_backwardation_curve(self):
        quotes = [
            self._q("/CLN26", 80.0),
            self._q("/CLQ26", 78.5),
            self._q("/CLU26", 77.0),
        ]
        brief = analyze_futures(quotes)
        assert brief.shape == "backwardation"
        assert brief.annualized_roll_yield_pct > 0

    def test_curve_sorted_by_expiry_regardless_of_input_order(self):
        quotes = [
            self._q("/ESZ26", 7509.50),
            self._q("/ESM26", 7436.25),
            self._q("/ESU26", 7472.00),
        ]
        brief = analyze_futures(quotes)
        contracts = [p["contract"] for p in brief.term_structure]
        assert contracts == ["/ESM26", "/ESU26", "/ESZ26"]

    def test_single_contract(self):
        brief = analyze_futures([self._q("/ESM26", 7436.25)])
        assert brief.shape == "single-contract"

    def test_vol_regime_context(self):
        vr = VolRegime.from_payload({"regime": "crisis", "term_structure_ratio": 0.9})
        brief = analyze_futures([self._q("/ESM26", 7436.25), self._q("/ESU26", 7472.0)], vol_regime=vr)
        assert brief.market_context["regime"] == "crisis"
        assert any("volatility regime" in s.lower() for s in brief.signals)


class TestSampleSourceFutures:
    def test_futures_curve_end_to_end(self):
        src = SampleResearchSource()
        quotes = src.futures_curve("/ES")
        assert len(quotes) == 3
        brief = analyze_futures(quotes, vol_regime=src.get_vol_regime(), as_of="2026-06-14")
        assert brief.root == "/ES"
        assert brief.shape in ("contango", "backwardation", "flat")
        md = brief.to_markdown()
        assert "Futures Research Brief" in md
