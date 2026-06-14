"""
Tests for equity research analytics.
"""

from derivatives_strategies.research.models import (
    EquityQuote,
    PriceSeries,
    ShortInterest,
    VolRegime,
)
from derivatives_strategies.research.equity import analyze_equity
from derivatives_strategies.research.sources import SampleResearchSource


def _series(prices):
    candles = [
        {
            "datetime": (1_700_000_000 + i * 86_400) * 1000,
            "open": p, "high": p * 1.01, "low": p * 0.99, "close": p, "volume": 1000,
        }
        for i, p in enumerate(prices)
    ]
    return PriceSeries.from_price_history_payload("X", {"symbol": "X", "candles": candles})


def _quote(**overrides):
    base = {
        "symbol": "X", "lastPrice": 100.0, "mark": 100.0,
        "52wHigh": 120.0, "52wLow": 80.0, "eps": 8.0, "peRatio": 12.5,
        "divYield": 1.0,
    }
    base.update(overrides)
    return EquityQuote.from_quote_payload(base["symbol"], base)


class TestAnalyzeEquity:
    def test_uptrend_cheap_stock_is_constructive_or_better(self):
        # 300 rising bars => above SMAs, positive momentum.
        prices = [80.0 * (1.003 ** i) for i in range(300)]
        quote = _quote(lastPrice=prices[-1], mark=prices[-1],
                       week52_high=prices[-1] * 1.02, week52_low=80.0,
                       eps=14.0)  # high earnings yield -> cheap
        brief = analyze_equity(quote, series=_series(prices), as_of="2026-06-14")
        assert brief.score > 0.15
        assert brief.rating in ("constructive", "bullish")
        assert any("momentum" in s.lower() or "uptrend" in s.lower() for s in brief.signals)

    def test_downtrend_expensive_stock_is_cautious_or_bearish(self):
        prices = [200.0 * (0.997 ** i) for i in range(300)]
        quote = _quote(lastPrice=prices[-1], mark=prices[-1],
                       week52_high=200.0, week52_low=prices[-1] * 0.98,
                       eps=1.0)  # low earnings yield -> rich
        brief = analyze_equity(quote, series=_series(prices), as_of="2026-06-14")
        assert brief.score < 0.0
        assert brief.rating in ("cautious", "bearish")

    def test_short_squeeze_flag(self):
        quote = _quote()
        si = ShortInterest.from_finra_payload("X", {
            "symbolCode": "X", "daysToCoverQuantity": 8.0,
            "currentShortPositionQuantity": 1, "settlementDate": "2026-05-30",
        })
        brief = analyze_equity(quote, short_interest=si)
        assert brief.positioning["squeeze_risk"] is True
        assert any("short interest" in s.lower() for s in brief.signals)

    def test_risk_off_regime_penalizes_score(self):
        quote = _quote()
        calm = VolRegime.from_payload({"regime": "normal", "term_structure_ratio": 1.1})
        crisis = VolRegime.from_payload({"regime": "crisis", "term_structure_ratio": 0.85})
        calm_brief = analyze_equity(quote, vol_regime=calm)
        crisis_brief = analyze_equity(quote, vol_regime=crisis)
        assert crisis_brief.score <= calm_brief.score
        assert any("risk-off" in s.lower() for s in crisis_brief.signals)

    def test_brief_serialization_roundtrip(self):
        brief = analyze_equity(_quote(), series=None, as_of="2026-06-14")
        d = brief.to_dict()
        assert d["symbol"] == "X"
        assert "valuation" in d
        md = brief.to_markdown()
        assert "Equity Research Brief" in md
        assert "not investment advice" in md.lower()


class TestSampleSourceEquity:
    def test_end_to_end_aapl(self):
        src = SampleResearchSource()
        quote = src.get_equity_quote("AAPL")
        brief = analyze_equity(
            quote,
            series=src.get_price_series("AAPL"),
            short_interest=src.get_short_interest("AAPL"),
            vol_regime=src.get_vol_regime(),
            as_of="2026-06-14",
        )
        assert brief.symbol == "AAPL"
        assert brief.reference_price is not None
        assert brief.rating in (
            "bullish", "constructive", "neutral", "cautious", "bearish"
        )
