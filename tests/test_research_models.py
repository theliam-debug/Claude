"""
Tests for research model parsers against the real MCP payload shapes.

The payload fixtures here mirror the exact JSON shapes returned by the live
MCP tools (get_quotes, get_price_history, finra_short_interest, vol_regime),
so the normalizers are tested against the contracts they must support.
"""

import pytest

from derivatives_strategies.research.models import (
    EquityQuote,
    FuturesQuote,
    PriceSeries,
    ShortInterest,
    VolRegime,
)


# Real get_quotes shape observed for AAPL.
AAPL_PAYLOAD = {
    "symbol": "AAPL", "assetType": "EQUITY", "description": "APPLE INC",
    "lastPrice": 291.5789, "mark": 291.13, "bid": 291.52, "ask": 291.58,
    "change": -4.0511, "changePct": -1.37032777, "volume": 38784789,
    "open": 296.03, "high": 297.14, "low": 289.62, "close": 295.63,
    "52wHigh": 317.4, "52wLow": 195.07,
    "peRatio": 35.29255, "eps": 7.46,
    "divYield": 0.36532, "divAmount": 1.08, "divExDate": "2026-05-11T00:00:00Z",
    "isShortable": True, "isHardToBorrow": False,
}

ES_PAYLOAD = {
    "symbol": "/ESM26", "assetType": "FUTURE",
    "description": "E-mini S&P 500 Index Futures,Jun-2026,ETH",
    "exchange": "XCME", "lastPrice": 7436.25, "mark": 7436.25,
    "change": 40.25, "bid": 7436.25, "ask": 7436.75, "close": 7396, "volume": 0,
}


class TestEquityQuote:
    def test_parses_core_fields(self):
        q = EquityQuote.from_quote_payload("AAPL", AAPL_PAYLOAD)
        assert q.symbol == "AAPL"
        assert q.last == pytest.approx(291.5789)
        assert q.mark == pytest.approx(291.13)
        assert q.week52_high == 317.4
        assert q.pe_ratio == pytest.approx(35.29255)
        assert q.shortable is True

    def test_reference_price_prefers_mark(self):
        q = EquityQuote.from_quote_payload("AAPL", AAPL_PAYLOAD)
        assert q.reference_price == pytest.approx(291.13)

    def test_earnings_yield(self):
        q = EquityQuote.from_quote_payload("AAPL", AAPL_PAYLOAD)
        # 7.46 / 291.13 * 100 ~= 2.56%
        assert q.earnings_yield == pytest.approx(2.56, abs=0.05)

    def test_range_position_within_bounds(self):
        q = EquityQuote.from_quote_payload("AAPL", AAPL_PAYLOAD)
        pos = q.range_position
        assert 0.0 <= pos <= 1.0
        # 291 is near the top of 195-317 range
        assert pos > 0.7

    def test_missing_fields_degrade_gracefully(self):
        q = EquityQuote.from_quote_payload("XYZ", {"symbol": "XYZ"})
        assert q.last is None
        assert q.earnings_yield is None
        assert q.range_position is None


class TestFuturesQuote:
    def test_parses_future(self):
        q = FuturesQuote.from_quote_payload("/ESM26", ES_PAYLOAD)
        assert q.symbol == "/ESM26"
        assert q.reference_price == pytest.approx(7436.25)
        assert q.exchange == "XCME"

    def test_reference_falls_back_to_close(self):
        q = FuturesQuote.from_quote_payload("/X", {"symbol": "/X", "close": 100.0})
        assert q.reference_price == 100.0


class TestPriceSeries:
    def _ramp(self, n=60, start=100.0, step=1.0):
        candles = []
        px = start
        for i in range(n):
            candles.append({
                "datetime": (1_700_000_000 + i * 86_400) * 1000,
                "open": px, "high": px + 1, "low": px - 1,
                "close": px, "volume": 1000,
            })
            px += step
        return {"symbol": "RAMP", "candles": candles}

    def test_parse_sorts_and_filters(self):
        ps = PriceSeries.from_price_history_payload("RAMP", self._ramp())
        assert len(ps.bars) == 60
        assert ps.bars[0].date < ps.bars[-1].date
        assert ps.bars[0].date  # epoch ms converted to ISO date

    def test_total_and_trailing_return(self):
        ps = PriceSeries.from_price_history_payload("RAMP", self._ramp(n=60, start=100.0, step=1.0))
        # 100 -> 159
        assert ps.total_return() == pytest.approx(0.59, abs=0.001)
        assert ps.trailing_return(10) is not None

    def test_vol_and_drawdown(self):
        ps = PriceSeries.from_price_history_payload("RAMP", self._ramp())
        assert ps.annualized_vol() is not None
        # Monotonic uptrend => no drawdown
        assert ps.max_drawdown() == pytest.approx(0.0)

    def test_rsi_strong_uptrend_high(self):
        ps = PriceSeries.from_price_history_payload("RAMP", self._ramp())
        # All-up series => RSI saturates at 100
        assert ps.rsi() == pytest.approx(100.0)

    def test_sma(self):
        ps = PriceSeries.from_price_history_payload("RAMP", self._ramp(n=60, start=100.0, step=1.0))
        assert ps.sma(10) is not None
        assert ps.sma(1000) is None


class TestShortInterest:
    def test_parse(self):
        payload = {
            "symbolCode": "GME", "settlementDate": "2026-05-30",
            "currentShortPositionQuantity": 50_000_000,
            "daysToCoverQuantity": 6.5, "changePercent": 12.0,
            "averageDailyVolumeQuantity": 7_700_000,
        }
        si = ShortInterest.from_finra_payload("GME", payload)
        assert si.symbol == "GME"
        assert si.days_to_cover == 6.5
        assert si.short_quantity == 50_000_000


class TestVolRegime:
    def test_parse_and_term_structure(self):
        payload = {
            "current_vix": 19.44, "percentile_rank": 77, "average": 18.09,
            "min": 13.47, "max": 31.05, "vix3m": 21.42,
            "term_structure_ratio": 1.102, "regime": "normal",
        }
        vr = VolRegime.from_payload(payload)
        assert vr.regime == "normal"
        assert vr.is_backwardation is False

    def test_backwardation_detected(self):
        vr = VolRegime.from_payload({"term_structure_ratio": 0.92})
        assert vr.is_backwardation is True
