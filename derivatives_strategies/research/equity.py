"""
Equity research analytics.

Turns a normalized quote, price history, and (optional) short-interest and
volatility-regime data into a deterministic research brief covering valuation,
technicals, and positioning. The brief is advisory analytics only - it does
not place orders or constitute investment advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from derivatives_strategies.research.models import (
    EquityQuote,
    PriceSeries,
    ShortInterest,
    VolRegime,
    _round,
)

# Approximate trading-day lookbacks
_M1 = 21
_M3 = 63
_M6 = 126
_M12 = 252


@dataclass
class EquityResearchBrief:
    """Structured equity research output."""
    symbol: str
    as_of: str
    reference_price: Optional[float]
    valuation: dict = field(default_factory=dict)
    technicals: dict = field(default_factory=dict)
    positioning: dict = field(default_factory=dict)
    market_context: dict = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    score: float = 0.0          # composite, -1.0 (bearish) .. +1.0 (bullish)
    rating: str = "neutral"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of,
            "reference_price": self.reference_price,
            "valuation": self.valuation,
            "technicals": self.technicals,
            "positioning": self.positioning,
            "market_context": self.market_context,
            "signals": self.signals,
            "score": _round(self.score, 3),
            "rating": self.rating,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Equity Research Brief: {self.symbol}",
            f"_As of {self.as_of}_",
            "",
            f"**Reference price:** {_fmt(self.reference_price)}  ",
            f"**Composite rating:** {self.rating.upper()} "
            f"(score {_round(self.score, 2)})",
            "",
            "## Valuation",
        ]
        lines += _kv_lines(self.valuation)
        lines += ["", "## Technicals"]
        lines += _kv_lines(self.technicals)
        lines += ["", "## Positioning"]
        lines += _kv_lines(self.positioning)
        lines += ["", "## Market context"]
        lines += _kv_lines(self.market_context)
        lines += ["", "## Signals"]
        if self.signals:
            lines += [f"- {s}" for s in self.signals]
        else:
            lines += ["- (none)"]
        lines += ["", "_Analytics only; not investment advice._"]
        return "\n".join(lines)


def analyze_equity(
    quote: EquityQuote,
    series: Optional[PriceSeries] = None,
    short_interest: Optional[ShortInterest] = None,
    vol_regime: Optional[VolRegime] = None,
    as_of: str = "",
) -> EquityResearchBrief:
    """Produce an equity research brief from normalized inputs."""
    brief = EquityResearchBrief(
        symbol=quote.symbol,
        as_of=as_of,
        reference_price=quote.reference_price,
    )
    score = 0.0
    weight = 0.0

    # --- Valuation ---
    brief.valuation = {
        "pe_ratio": quote.pe_ratio,
        "earnings_yield_pct": _round(quote.earnings_yield, 2),
        "eps": quote.eps,
        "dividend_yield_pct": quote.div_yield,
        "next_ex_date": quote.div_ex_date,
    }
    if quote.earnings_yield is not None:
        # Cheap (>6% earnings yield) is mildly bullish; rich (<3%) bearish.
        ey = quote.earnings_yield
        v = _clamp((ey - 4.5) / 4.5)
        score += 0.25 * v
        weight += 0.25
        if ey >= 6.0:
            brief.signals.append(f"Attractive earnings yield ({ey:.1f}%)")
        elif ey <= 3.0:
            brief.signals.append(f"Rich valuation: earnings yield only {ey:.1f}%")

    # --- Technicals ---
    if series is not None and series.bars:
        ret_3m = series.trailing_return(_M3)
        ret_6m = series.trailing_return(_M6)
        ret_12m = series.trailing_return(_M12)
        vol = series.annualized_vol()
        mdd = series.max_drawdown()
        rsi = series.rsi()
        sma50 = series.sma(50)
        sma200 = series.sma(200)
        px = quote.reference_price or series.closes[-1]
        above_50 = (px > sma50) if (sma50 is not None and px) else None
        above_200 = (px > sma200) if (sma200 is not None and px) else None

        brief.technicals = {
            "return_3m_pct": _pct(ret_3m),
            "return_6m_pct": _pct(ret_6m),
            "return_12m_pct": _pct(ret_12m),
            "annualized_vol_pct": _pct(vol),
            "max_drawdown_pct": _pct(mdd),
            "rsi_14": _round(rsi, 1),
            "range_position": _round(quote.range_position, 2),
            "pct_off_52w_high": _round(quote.pct_off_52w_high, 2),
            "above_sma50": above_50,
            "above_sma200": above_200,
        }

        # Momentum: blend of 3m and 6m trailing returns.
        mom = [r for r in (ret_3m, ret_6m) if r is not None]
        if mom:
            m = sum(mom) / len(mom)
            v = _clamp(m / 0.15)  # +/-15% maps to full scale
            score += 0.30 * v
            weight += 0.30
            if m > 0.10:
                brief.signals.append(f"Strong positive momentum ({m*100:.0f}% avg 3-6m)")
            elif m < -0.10:
                brief.signals.append(f"Negative momentum ({m*100:.0f}% avg 3-6m)")

        # Trend confirmation via moving averages.
        if above_50 is not None and above_200 is not None:
            trend = (1.0 if above_50 else -1.0) * 0.5 + (1.0 if above_200 else -1.0) * 0.5
            score += 0.20 * trend
            weight += 0.20
            if above_50 and above_200:
                brief.signals.append("Uptrend: price above 50- and 200-day SMA")
            elif not above_50 and not above_200:
                brief.signals.append("Downtrend: price below 50- and 200-day SMA")

        # Overbought / oversold flags (informational, light weight).
        if rsi is not None:
            if rsi >= 70:
                brief.signals.append(f"Overbought (RSI {rsi:.0f})")
                score -= 0.05
                weight += 0.05
            elif rsi <= 30:
                brief.signals.append(f"Oversold (RSI {rsi:.0f})")
                score += 0.05
                weight += 0.05

    # --- Positioning (short interest) ---
    if short_interest is not None:
        brief.positioning = short_interest.to_dict()
        dtc = short_interest.days_to_cover
        if dtc is not None:
            if dtc >= 5:
                brief.signals.append(
                    f"Elevated short interest: {dtc:.1f} days to cover (squeeze risk)"
                )
            brief.positioning["squeeze_risk"] = dtc >= 5
    else:
        brief.positioning = {"short_interest": "n/a"}

    # --- Market context (vol regime) ---
    if vol_regime is not None:
        brief.market_context = vol_regime.to_dict()
        if vol_regime.regime in ("elevated", "crisis"):
            brief.signals.append(
                f"Risk-off backdrop: volatility regime '{vol_regime.regime}'"
            )
            score -= 0.10
            weight += 0.10
        if vol_regime.is_backwardation:
            brief.signals.append("VIX in backwardation: near-term equity stress")

    # --- Composite ---
    brief.score = (score / weight) if weight > 0 else 0.0
    brief.rating = _rating(brief.score)
    return brief


def _rating(score: float) -> str:
    if score >= 0.4:
        return "bullish"
    if score >= 0.15:
        return "constructive"
    if score <= -0.4:
        return "bearish"
    if score <= -0.15:
        return "cautious"
    return "neutral"


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _pct(x: Optional[float]) -> Optional[float]:
    return _round(x * 100.0, 2) if x is not None else None


def _fmt(x: Optional[float]) -> str:
    return f"{x:,.2f}" if x is not None else "n/a"


def _kv_lines(d: dict) -> list[str]:
    if not d:
        return ["- (no data)"]
    return [f"- **{k}:** {v}" for k, v in d.items()]
