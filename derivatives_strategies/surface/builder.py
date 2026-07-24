"""
Implied volatility surface builder.

Constructs volatility surface from option chain with:
- Per-expiry smile fitting via piecewise linear interpolation in log-moneyness
- Time interpolation between expiries
- Greeks computation using surface IV
"""

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from derivatives_strategies.data.models import (
    Chain,
    OptionQuote,
    OptionType,
    Greeks,
)
from derivatives_strategies.surface.iv_solver import iv_from_quote
from derivatives_strategies.options.greeks import compute_all_greeks


@dataclass
class SmilePoint:
    """Single point on a volatility smile."""
    log_moneyness: float  # ln(K/F) where F is forward
    strike: float
    iv: float
    option_type: OptionType


@dataclass
class ExpirySmile:
    """Volatility smile for a single expiry."""
    expiry: str
    days_to_expiry: int
    forward: float
    points: list[SmilePoint] = field(default_factory=list)

    # Cached ascending log-moneyness keys for O(log n) bracketing. Rebuilt
    # whenever the point count changes (the builder appends then sorts).
    _keys: list = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self):
        # Sort by log-moneyness
        self.points.sort(key=lambda p: p.log_moneyness)
        self._keys = []

    def _moneyness_keys(self) -> list:
        if len(self._keys) != len(self.points):
            self._keys = [p.log_moneyness for p in self.points]
        return self._keys

    def get_iv(self, strike: float) -> Optional[float]:
        """
        Interpolate IV for a given strike.

        Uses piecewise linear interpolation in log-moneyness space, with
        binary search for the bracketing points (O(log n) per lookup).
        """
        if not self.points:
            return None

        if len(self.points) == 1:
            return self.points[0].iv

        log_m = math.log(strike / self.forward)

        # Bracket: left = last point <= log_m, right = first point >= log_m.
        keys = self._moneyness_keys()
        n = len(keys)
        i = bisect_right(keys, log_m)
        left_idx = i - 1 if i > 0 else 0
        j = bisect_left(keys, log_m)
        right_idx = j if j < n else n - 1

        left = self.points[left_idx]
        right = self.points[right_idx]

        # Extrapolation: use flat vol at boundaries
        if log_m <= left.log_moneyness:
            return left.iv
        if log_m >= right.log_moneyness:
            return right.iv

        # Linear interpolation
        if abs(right.log_moneyness - left.log_moneyness) < 1e-10:
            return left.iv

        weight = (log_m - left.log_moneyness) / (right.log_moneyness - left.log_moneyness)
        return left.iv + weight * (right.iv - left.iv)

    def atm_iv(self) -> Optional[float]:
        """Get ATM implied volatility."""
        return self.get_iv(self.forward)


@dataclass
class VolSurface:
    """
    Complete implied volatility surface.

    Supports IV and Greeks lookup by (expiry, strike).
    """
    symbol: str
    spot: float
    as_of: str
    rate: float
    dividend_yield: float
    smiles: dict[str, ExpirySmile] = field(default_factory=dict)
    # Memoized expiry -> year-fraction, so repeated IV/Greeks lookups don't
    # re-parse the same ISO date strings on every call.
    _tenor_cache: dict = field(default_factory=dict, repr=False, compare=False)

    def year_fraction(self, expiry: str) -> float:
        """Years from as_of to expiry (ACT/365), memoized."""
        cached = self._tenor_cache.get(expiry)
        if cached is None:
            as_of_date = date.fromisoformat(self.as_of[:10])
            exp_date = date.fromisoformat(expiry[:10])
            cached = (exp_date - as_of_date).days / 365.0
            self._tenor_cache[expiry] = cached
        return cached

    def get_expiries(self) -> list[str]:
        """Get sorted list of expiry dates."""
        return sorted(self.smiles.keys())

    def get_iv(self, expiry: str, strike: float) -> Optional[float]:
        """
        Get implied volatility for a specific expiry and strike.

        Args:
            expiry: Expiry date (ISO format)
            strike: Strike price

        Returns:
            Implied volatility, or None if not available
        """
        if expiry in self.smiles:
            return self.smiles[expiry].get_iv(strike)

        # Try time interpolation between expiries
        expiries = self.get_expiries()
        if not expiries:
            return None

        # Find bracketing expiries
        left_exp = None
        right_exp = None

        for exp in expiries:
            if exp <= expiry:
                left_exp = exp
            if exp >= expiry and right_exp is None:
                right_exp = exp

        if left_exp is None:
            left_exp = expiries[0]
        if right_exp is None:
            right_exp = expiries[-1]

        if left_exp == right_exp:
            return self.smiles[left_exp].get_iv(strike)

        # Interpolate in time (variance-weighted)
        left_smile = self.smiles[left_exp]
        right_smile = self.smiles[right_exp]

        left_iv = left_smile.get_iv(strike)
        right_iv = right_smile.get_iv(strike)

        if left_iv is None or right_iv is None:
            return left_iv or right_iv

        # Time to each expiry (memoized)
        t_target = self.year_fraction(expiry)
        t_left = self.year_fraction(left_exp)
        t_right = self.year_fraction(right_exp)

        if t_right <= t_left:
            return left_iv

        # Linear interpolation in total variance
        var_left = left_iv**2 * t_left
        var_right = right_iv**2 * t_right

        weight = (t_target - t_left) / (t_right - t_left)
        var_target = var_left + weight * (var_right - var_left)

        if t_target <= 0:
            return left_iv

        return math.sqrt(var_target / t_target)

    def get_delta(
        self,
        expiry: str,
        strike: float,
        option_type: OptionType
    ) -> Optional[float]:
        """
        Get delta for a specific option.

        Args:
            expiry: Expiry date
            strike: Strike price
            option_type: Call or put

        Returns:
            Delta value, or None if IV not available
        """
        iv = self.get_iv(expiry, strike)
        if iv is None:
            return None

        T = self.year_fraction(expiry)

        if T <= 0:
            return None

        from derivatives_strategies.options.greeks import delta
        return delta(
            self.spot, strike, T, self.rate, iv,
            option_type, self.dividend_yield
        )

    def get_greeks(
        self,
        expiry: str,
        strike: float,
        option_type: OptionType
    ) -> Optional[Greeks]:
        """
        Get all Greeks for a specific option.

        Args:
            expiry: Expiry date
            strike: Strike price
            option_type: Call or put

        Returns:
            Greeks object, or None if IV not available
        """
        iv = self.get_iv(expiry, strike)
        if iv is None:
            return None

        T = self.year_fraction(expiry)

        if T <= 0:
            return None

        return compute_all_greeks(
            self.spot, strike, T, self.rate, iv,
            option_type, self.dividend_yield
        )

    def get_atm_term_structure(self) -> list[tuple[str, float, float]]:
        """
        Get ATM vol term structure.

        Returns:
            List of (expiry, days_to_expiry, atm_iv) tuples
        """
        result = []
        for expiry in self.get_expiries():
            smile = self.smiles[expiry]
            atm_iv = smile.atm_iv()
            if atm_iv is not None:
                result.append((expiry, smile.days_to_expiry, atm_iv))
        return result

    def is_valid(self) -> bool:
        """Check if surface has valid data."""
        return len(self.smiles) > 0 and all(
            len(s.points) > 0 for s in self.smiles.values()
        )

    def summary(self) -> dict:
        """Get summary statistics for the surface."""
        all_ivs = []
        for smile in self.smiles.values():
            all_ivs.extend(p.iv for p in smile.points)

        if not all_ivs:
            return {"valid": False}

        return {
            "valid": True,
            "num_expiries": len(self.smiles),
            "num_points": len(all_ivs),
            "min_iv": min(all_ivs),
            "max_iv": max(all_ivs),
            "avg_iv": sum(all_ivs) / len(all_ivs),
        }


def build_surface(
    chain: Chain,
    rate: float,
    as_of: str,
    dividend_yield: float = 0.0,
    min_dte: int = 1,
    max_spread_pct: float = 0.50,
    min_volume: int = 0,
    prefer_otm: bool = True
) -> VolSurface:
    """
    Build implied volatility surface from option chain.

    Filters and processes options to create a clean vol surface:
    - Filters by spread, volume, and time to expiry
    - Prefers OTM options (calls above spot, puts below) for cleaner IVs
    - Fits piecewise linear smile per expiry

    Args:
        chain: Option chain
        rate: Risk-free rate
        as_of: As-of date (ISO format)
        dividend_yield: Continuous dividend yield
        min_dte: Minimum days to expiry
        max_spread_pct: Maximum bid-ask spread as percent of mid
        min_volume: Minimum option volume
        prefer_otm: Prefer OTM options for IV calculation

    Returns:
        VolSurface object
    """
    surface = VolSurface(
        symbol=chain.symbol,
        spot=chain.spot.mid,
        as_of=as_of,
        rate=rate,
        dividend_yield=dividend_yield,
    )

    as_of_date = date.fromisoformat(as_of[:10])

    # Group options by expiry
    expiry_options: dict[str, list[OptionQuote]] = {}
    for opt in chain.options:
        if opt.expiry not in expiry_options:
            expiry_options[opt.expiry] = []
        expiry_options[opt.expiry].append(opt)

    for expiry, options in expiry_options.items():
        exp_date = date.fromisoformat(expiry)
        dte = (exp_date - as_of_date).days

        if dte < min_dte:
            continue

        T = dte / 365.0

        # Calculate forward price
        forward = chain.spot.mid * math.exp((rate - dividend_yield) * T)

        smile = ExpirySmile(
            expiry=expiry,
            days_to_expiry=dte,
            forward=forward,
        )

        # Group qualifying quotes by strike. At an exactly-ATM strike both
        # the call and the put survive the prefer_otm filter, so a strike can
        # have two candidates; picking whichever appeared first in the chain
        # made the smile depend on input ordering.
        candidates: dict[float, list[OptionQuote]] = {}

        for opt in options:
            # Filter by spread
            if opt.spread_pct > max_spread_pct:
                continue

            # Filter by volume
            if opt.volume < min_volume:
                continue

            # Prefer OTM options
            if prefer_otm:
                if opt.option_type == OptionType.CALL and opt.strike < chain.spot.mid:
                    continue
                if opt.option_type == OptionType.PUT and opt.strike > chain.spot.mid:
                    continue

            candidates.setdefault(opt.strike, []).append(opt)

        for strike in sorted(candidates):
            # Deterministic preference: tightest quoted spread first (best
            # information), calls before puts as a stable tiebreak. Falls
            # through to the next candidate if one fails to solve.
            ranked = sorted(
                candidates[strike],
                key=lambda o: (o.spread_pct, o.option_type != OptionType.CALL),
            )

            for opt in ranked:
                # Calculate IV
                iv = iv_from_quote(opt, chain.spot.mid, rate, T, dividend_yield)
                if iv is None:
                    continue

                # Sanity check IV bounds
                if iv < 0.01 or iv > 3.0:
                    continue

                log_m = math.log(strike / forward)

                smile.points.append(SmilePoint(
                    log_moneyness=log_m,
                    strike=strike,
                    iv=iv,
                    option_type=opt.option_type,
                ))
                break

        # Only add smile if we have enough points
        if len(smile.points) >= 2:
            # Sort and store
            smile.points.sort(key=lambda p: p.log_moneyness)
            surface.smiles[expiry] = smile

    return surface


def validate_surface(surface: VolSurface) -> list[str]:
    """
    Validate volatility surface for common issues.

    Returns:
        List of warning messages
    """
    warnings = []

    if not surface.is_valid():
        warnings.append("Surface has no valid data")
        return warnings

    for expiry, smile in surface.smiles.items():
        # Check for negative slopes in smile (butterfly arbitrage).
        # Segment slopes are computed once and reused: each consecutive pair
        # is both the right slope of one triple and the left slope of the
        # next.
        pts = smile.points
        slopes = []
        for i in range(len(pts) - 1):
            dx = pts[i + 1].log_moneyness - pts[i].log_moneyness
            slopes.append(
                (pts[i + 1].iv - pts[i].iv) / dx if abs(dx) > 1e-10 else 0
            )

        for i in range(len(slopes) - 1):
            # Typically smile should be convex
            if slopes[i + 1] < slopes[i] - 0.5:  # Allow some tolerance
                warnings.append(
                    f"Possible non-convex smile at {expiry} "
                    f"around strike {pts[i + 1].strike:.2f}"
                )

        # Check for very high or low IVs
        for point in smile.points:
            if point.iv > 1.5:
                warnings.append(
                    f"Very high IV ({point.iv:.2%}) at {expiry} "
                    f"strike {point.strike:.2f}"
                )
            if point.iv < 0.05:
                warnings.append(
                    f"Very low IV ({point.iv:.2%}) at {expiry} "
                    f"strike {point.strike:.2f}"
                )

    # Check term structure
    term = surface.get_atm_term_structure()
    for i in range(len(term) - 1):
        exp1, dte1, iv1 = term[i]
        exp2, dte2, iv2 = term[i + 1]

        # Check for calendar spread arbitrage (variance should increase with time)
        var1 = iv1**2 * dte1
        var2 = iv2**2 * dte2

        if var2 < var1 * 0.95:  # Allow 5% tolerance
            warnings.append(
                f"Possible calendar arbitrage between {exp1} and {exp2}: "
                f"variance decreases with time"
            )

    return warnings
