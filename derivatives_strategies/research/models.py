"""
Normalized, network-free data models for equity & futures research.

Each model includes a parser (``from_*_payload``) that accepts the raw JSON
returned by the corresponding MCP tool, so research analytics depend only on
these stable shapes rather than on any provider's wire format.

All parsers are defensive: missing fields degrade to ``None`` or ``0.0``
rather than raising, because upstream payloads vary by asset type and by the
``fields`` requested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any


def _f(value: Any) -> Optional[float]:
    """Coerce to float, returning None on failure/empty."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _epoch_ms_to_date(value: Any) -> Optional[str]:
    """Convert epoch milliseconds to an ISO date string (UTC)."""
    ms = _f(value)
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date().isoformat()


@dataclass(frozen=True)
class EquityQuote:
    """Normalized equity/ETF quote (from get_quotes)."""
    symbol: str
    last: Optional[float]
    mark: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]
    volume: Optional[float]
    week52_high: Optional[float]
    week52_low: Optional[float]
    pe_ratio: Optional[float]
    eps: Optional[float]
    div_yield: Optional[float]      # percent, e.g. 0.36 means 0.36%
    div_amount: Optional[float]
    div_ex_date: Optional[str]
    shortable: Optional[bool]
    hard_to_borrow: Optional[bool]
    description: Optional[str] = None
    timestamp: Optional[str] = None

    @classmethod
    def from_quote_payload(cls, symbol: str, data: dict) -> "EquityQuote":
        return cls(
            symbol=data.get("symbol", symbol),
            last=_f(data.get("lastPrice")),
            mark=_f(data.get("mark")),
            bid=_f(data.get("bid")),
            ask=_f(data.get("ask")),
            change=_f(data.get("change")),
            change_pct=_f(data.get("changePct")),
            volume=_f(data.get("volume")),
            week52_high=_f(data.get("52wHigh")),
            week52_low=_f(data.get("52wLow")),
            pe_ratio=_f(data.get("peRatio")),
            eps=_f(data.get("eps")),
            div_yield=_f(data.get("divYield")),
            div_amount=_f(data.get("divAmount")),
            div_ex_date=data.get("divExDate"),
            shortable=data.get("isShortable"),
            hard_to_borrow=data.get("isHardToBorrow"),
            description=data.get("description"),
            timestamp=data.get("quoteTime") or data.get("tradeTime"),
        )

    @property
    def reference_price(self) -> Optional[float]:
        """Best available price: mark, else last, else mid."""
        if self.mark is not None and self.mark > 0:
            return self.mark
        if self.last is not None and self.last > 0:
            return self.last
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        return None

    @property
    def earnings_yield(self) -> Optional[float]:
        """EPS / price as a percent. Inverse of P/E, robust to missing PE."""
        px = self.reference_price
        if px and self.eps is not None and px > 0:
            return 100.0 * self.eps / px
        return None

    @property
    def range_position(self) -> Optional[float]:
        """Where price sits in the 52-week range, 0.0 (low) to 1.0 (high)."""
        px = self.reference_price
        if (px is None or self.week52_high is None or self.week52_low is None
                or self.week52_high <= self.week52_low):
            return None
        pos = (px - self.week52_low) / (self.week52_high - self.week52_low)
        return max(0.0, min(1.0, pos))

    @property
    def pct_off_52w_high(self) -> Optional[float]:
        """Percent below the 52-week high (negative number when below)."""
        px = self.reference_price
        if px is None or not self.week52_high:
            return None
        return 100.0 * (px - self.week52_high) / self.week52_high

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "last": self.last,
            "mark": self.mark,
            "reference_price": self.reference_price,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "week52_high": self.week52_high,
            "week52_low": self.week52_low,
            "range_position": _round(self.range_position),
            "pct_off_52w_high": _round(self.pct_off_52w_high),
            "pe_ratio": self.pe_ratio,
            "eps": self.eps,
            "earnings_yield": _round(self.earnings_yield),
            "div_yield": self.div_yield,
            "div_amount": self.div_amount,
            "div_ex_date": self.div_ex_date,
            "shortable": self.shortable,
            "description": self.description,
        }


@dataclass(frozen=True)
class FuturesQuote:
    """Normalized futures quote (from get_quotes, assetType FUTURE)."""
    symbol: str
    last: Optional[float]
    mark: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    change: Optional[float]
    close: Optional[float]
    volume: Optional[float]
    exchange: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_quote_payload(cls, symbol: str, data: dict) -> "FuturesQuote":
        return cls(
            symbol=data.get("symbol", symbol),
            last=_f(data.get("lastPrice")),
            mark=_f(data.get("mark")),
            bid=_f(data.get("bid")),
            ask=_f(data.get("ask")),
            change=_f(data.get("change")),
            close=_f(data.get("close")),
            volume=_f(data.get("volume")),
            exchange=data.get("exchange"),
            description=data.get("description"),
        )

    @property
    def reference_price(self) -> Optional[float]:
        for candidate in (self.mark, self.last):
            if candidate is not None and candidate > 0:
                return candidate
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        return self.close

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "reference_price": self.reference_price,
            "last": self.last,
            "mark": self.mark,
            "change": self.change,
            "close": self.close,
            "volume": self.volume,
            "exchange": self.exchange,
            "description": self.description,
        }


@dataclass(frozen=True)
class Bar:
    """A single OHLCV candle."""
    date: str          # ISO date
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_candle(cls, candle: dict) -> "Bar":
        d = candle.get("date") or _epoch_ms_to_date(candle.get("datetime"))
        return cls(
            date=d or "",
            open=_f(candle.get("open")) or 0.0,
            high=_f(candle.get("high")) or 0.0,
            low=_f(candle.get("low")) or 0.0,
            close=_f(candle.get("close")) or 0.0,
            volume=_f(candle.get("volume")) or 0.0,
        )


@dataclass
class PriceSeries:
    """An ordered series of OHLCV bars with technical analytics."""
    symbol: str
    bars: list[Bar] = field(default_factory=list)

    @classmethod
    def from_price_history_payload(cls, symbol: str, data: dict) -> "PriceSeries":
        candles = data.get("candles", data if isinstance(data, list) else [])
        bars = [Bar.from_candle(c) for c in candles]
        bars = [b for b in bars if b.close > 0]
        bars.sort(key=lambda b: b.date)
        return cls(symbol=data.get("symbol", symbol), bars=bars)

    @property
    def closes(self) -> list[float]:
        return [b.close for b in self.bars]

    def daily_returns(self) -> list[float]:
        """Simple period-over-period returns."""
        closes = self.closes
        out = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                out.append(closes[i] / closes[i - 1] - 1.0)
        return out

    def total_return(self) -> Optional[float]:
        closes = self.closes
        if len(closes) < 2 or closes[0] <= 0:
            return None
        return closes[-1] / closes[0] - 1.0

    def trailing_return(self, periods: int) -> Optional[float]:
        """Return over the last ``periods`` bars (e.g. ~21 = 1 month daily)."""
        closes = self.closes
        if len(closes) <= periods or closes[-1 - periods] <= 0:
            return None
        return closes[-1] / closes[-1 - periods] - 1.0

    def annualized_vol(self, periods_per_year: int = 252) -> Optional[float]:
        """Annualized volatility of daily returns."""
        rets = self.daily_returns()
        if len(rets) < 2:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(var) * math.sqrt(periods_per_year)

    def max_drawdown(self) -> Optional[float]:
        """Largest peak-to-trough decline (negative number)."""
        closes = self.closes
        if len(closes) < 2:
            return None
        peak = closes[0]
        mdd = 0.0
        for px in closes:
            peak = max(peak, px)
            if peak > 0:
                mdd = min(mdd, px / peak - 1.0)
        return mdd

    def sma(self, window: int) -> Optional[float]:
        closes = self.closes
        if len(closes) < window:
            return None
        return sum(closes[-window:]) / window

    def rsi(self, period: int = 14) -> Optional[float]:
        """Wilder's RSI on closes."""
        closes = self.closes
        if len(closes) <= period:
            return None
        gains, losses = 0.0, 0.0
        for i in range(1, period + 1):
            change = closes[i] - closes[i - 1]
            gains += max(change, 0.0)
            losses += max(-change, 0.0)
        avg_gain = gains / period
        avg_loss = losses / period
        for i in range(period + 1, len(closes)):
            change = closes[i] - closes[i - 1]
            avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)


@dataclass(frozen=True)
class ShortInterest:
    """Consolidated short interest snapshot (from finra_short_interest)."""
    symbol: str
    settlement_date: Optional[str]
    short_quantity: Optional[float]
    days_to_cover: Optional[float]
    change_pct: Optional[float]
    avg_daily_volume: Optional[float] = None

    @classmethod
    def from_finra_payload(cls, symbol: str, data: dict) -> "ShortInterest":
        return cls(
            symbol=data.get("symbolCode", symbol),
            settlement_date=data.get("settlementDate"),
            short_quantity=_f(data.get("currentShortPositionQuantity")),
            days_to_cover=_f(data.get("daysToCoverQuantity")),
            change_pct=_f(data.get("changePercent")),
            avg_daily_volume=_f(data.get("averageDailyVolumeQuantity")),
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "settlement_date": self.settlement_date,
            "short_quantity": self.short_quantity,
            "days_to_cover": self.days_to_cover,
            "change_pct": self.change_pct,
            "avg_daily_volume": self.avg_daily_volume,
        }


@dataclass(frozen=True)
class VolRegime:
    """Volatility regime snapshot (from vol_regime)."""
    current_vix: Optional[float]
    percentile_rank: Optional[float]
    average: Optional[float]
    minimum: Optional[float]
    maximum: Optional[float]
    vix3m: Optional[float]
    term_structure_ratio: Optional[float]
    regime: Optional[str]

    @classmethod
    def from_payload(cls, data: dict) -> "VolRegime":
        return cls(
            current_vix=_f(data.get("current_vix")),
            percentile_rank=_f(data.get("percentile_rank")),
            average=_f(data.get("average")),
            minimum=_f(data.get("min")),
            maximum=_f(data.get("max")),
            vix3m=_f(data.get("vix3m")),
            term_structure_ratio=_f(data.get("term_structure_ratio")),
            regime=data.get("regime"),
        )

    @property
    def is_backwardation(self) -> Optional[bool]:
        """VIX > VIX3M (ratio < 1.0) signals near-term stress."""
        if self.term_structure_ratio is None:
            return None
        return self.term_structure_ratio < 1.0

    def to_dict(self) -> dict:
        return {
            "current_vix": self.current_vix,
            "percentile_rank": self.percentile_rank,
            "average": self.average,
            "min": self.minimum,
            "max": self.maximum,
            "vix3m": self.vix3m,
            "term_structure_ratio": self.term_structure_ratio,
            "regime": self.regime,
            "is_backwardation": self.is_backwardation,
        }


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    """Round, tolerating None."""
    return round(value, digits) if value is not None else None
