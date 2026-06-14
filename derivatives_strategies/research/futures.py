"""
Futures research analytics.

Covers the core futures research questions: term-structure shape
(contango vs backwardation), annualized roll yield, calendar spreads, and the
prevailing volatility regime. Inputs are normalized ``FuturesQuote`` objects
plus an optional ``VolRegime``.

Futures symbols follow the CME convention ``/<root><monthcode><yy>`` (e.g.
``/ESM26`` = E-mini S&P 500, June 2026). Month codes are the standard
F G H J K M N Q U V X Z mapping.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from derivatives_strategies.research.models import FuturesQuote, VolRegime, _round


# CME month codes -> calendar month number
MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}


@dataclass(frozen=True)
class FutureContract:
    """A parsed futures symbol."""
    symbol: str
    root: str
    month_code: str
    month: int
    year: int

    @property
    def expiry_proxy(self) -> date:
        """Mid-month proxy date for ordering and day-count math."""
        return date(self.year, self.month, 15)


def parse_future_symbol(symbol: str) -> Optional[FutureContract]:
    """
    Parse a CME-style futures symbol such as '/ESM26' or 'ESM26'.

    Returns None if the symbol does not match the expected pattern.
    """
    s = symbol.strip().lstrip("/").upper()
    if len(s) < 4 or not s[-2:].isdigit():
        return None
    year_2 = int(s[-2:])
    month_code = s[-3]
    if month_code not in MONTH_CODES:
        return None
    root = s[:-3]
    if not root:
        return None
    year = 2000 + year_2
    return FutureContract(
        symbol=symbol,
        root="/" + root,
        month_code=month_code,
        month=MONTH_CODES[month_code],
        year=year,
    )


@dataclass
class TermStructurePoint:
    contract: str
    expiry: str
    price: float


@dataclass
class FuturesResearchBrief:
    """Structured futures research output."""
    root: str
    as_of: str
    front_price: Optional[float]
    shape: str = "unknown"             # contango / backwardation / flat
    annualized_roll_yield_pct: Optional[float] = None
    term_structure: list[dict] = field(default_factory=list)
    calendar_spreads: list[dict] = field(default_factory=list)
    market_context: dict = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "as_of": self.as_of,
            "front_price": self.front_price,
            "shape": self.shape,
            "annualized_roll_yield_pct": self.annualized_roll_yield_pct,
            "term_structure": self.term_structure,
            "calendar_spreads": self.calendar_spreads,
            "market_context": self.market_context,
            "signals": self.signals,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Futures Research Brief: {self.root}",
            f"_As of {self.as_of}_",
            "",
            f"**Front price:** {_fmt(self.front_price)}  ",
            f"**Curve shape:** {self.shape.upper()}  ",
            f"**Annualized roll yield:** {_fmt(self.annualized_roll_yield_pct)}%",
            "",
            "## Term structure",
        ]
        if self.term_structure:
            lines += ["| Contract | Expiry | Price |", "|---|---|---|"]
            lines += [
                f"| {p['contract']} | {p['expiry']} | {_fmt(p['price'])} |"
                for p in self.term_structure
            ]
        else:
            lines += ["- (no contracts)"]
        lines += ["", "## Calendar spreads"]
        if self.calendar_spreads:
            for s in self.calendar_spreads:
                lines.append(
                    f"- {s['near']} -> {s['far']}: spread {_fmt(s['spread'])} "
                    f"({_fmt(s['annualized_pct'])}% annualized)"
                )
        else:
            lines += ["- (need >= 2 contracts)"]
        lines += ["", "## Market context"]
        lines += [f"- **{k}:** {v}" for k, v in self.market_context.items()] or ["- (no data)"]
        lines += ["", "## Signals"]
        lines += [f"- {s}" for s in self.signals] if self.signals else ["- (none)"]
        lines += ["", "_Analytics only; not investment advice._"]
        return "\n".join(lines)


def _curve_points(quotes: list[FuturesQuote]) -> list[tuple[FutureContract, float]]:
    """Parse, price, and sort quotes into an ordered curve."""
    points = []
    for q in quotes:
        contract = parse_future_symbol(q.symbol)
        price = q.reference_price
        if (contract is not None and price is not None
                and math.isfinite(price) and price > 0):
            points.append((contract, price))
    points.sort(key=lambda cp: cp[0].expiry_proxy)
    return points


def annualized_roll_yield(
    near_price: float,
    far_price: float,
    near_expiry: date,
    far_expiry: date,
) -> Optional[float]:
    """
    Annualized roll yield between two contracts, as a percent.

    Positive = backwardation (front richer than deferred): a long roll earns
    carry. Negative = contango: a long roll bleeds carry. Computed as the
    near/far price ratio annualized over the time between expiries.
    """
    days = (far_expiry - near_expiry).days
    if days <= 0 or far_price <= 0:
        return None
    if not (math.isfinite(near_price) and math.isfinite(far_price)):
        return None
    period_yield = near_price / far_price - 1.0
    result = 100.0 * period_yield * (365.0 / days)
    return result if math.isfinite(result) else None


def analyze_futures(
    quotes: list[FuturesQuote],
    vol_regime: Optional[VolRegime] = None,
    as_of: str = "",
) -> FuturesResearchBrief:
    """Produce a futures research brief from a set of contract quotes."""
    points = _curve_points(quotes)
    root = points[0][0].root if points else (
        (parse_future_symbol(quotes[0].symbol).root if quotes and parse_future_symbol(quotes[0].symbol) else "?")
    )
    brief = FuturesResearchBrief(
        root=root,
        as_of=as_of,
        front_price=points[0][1] if points else None,
    )

    brief.term_structure = [
        {
            "contract": c.symbol,
            "expiry": c.expiry_proxy.isoformat(),
            "price": _round(price, 4),
        }
        for c, price in points
    ]

    # Calendar spreads between adjacent contracts.
    for (c1, p1), (c2, p2) in zip(points, points[1:]):
        ann = annualized_roll_yield(p1, p2, c1.expiry_proxy, c2.expiry_proxy)
        brief.calendar_spreads.append({
            "near": c1.symbol,
            "far": c2.symbol,
            "spread": _round(p1 - p2, 4),
            "annualized_pct": _round(ann, 3),
        })

    # Curve shape & headline roll yield from front two contracts.
    if len(points) >= 2:
        (c1, p1), (c2, p2) = points[0], points[1]
        ann = annualized_roll_yield(p1, p2, c1.expiry_proxy, c2.expiry_proxy)
        brief.annualized_roll_yield_pct = _round(ann, 3)
        if p2 > p1 * 1.0005:
            brief.shape = "contango"
            brief.signals.append(
                "Curve in contango: deferred contracts richer; long roll costs carry"
            )
        elif p2 < p1 * 0.9995:
            brief.shape = "backwardation"
            brief.signals.append(
                "Curve in backwardation: front richer; long roll earns carry"
            )
        else:
            brief.shape = "flat"
    elif len(points) == 1:
        brief.shape = "single-contract"
        brief.signals.append("Only one contract available; term structure unavailable")

    # Volatility regime context.
    if vol_regime is not None:
        brief.market_context = vol_regime.to_dict()
        if vol_regime.regime in ("elevated", "crisis"):
            brief.signals.append(
                f"Volatility regime '{vol_regime.regime}': size and margin with caution"
            )
        if vol_regime.is_backwardation:
            brief.signals.append("VIX backwardation: equity-index futures stress signal")

    return brief


def _fmt(x: Optional[float]) -> str:
    return f"{x:,.2f}" if x is not None else "n/a"
