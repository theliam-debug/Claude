"""
Discrete dividend analysis and early assignment risk.

For American equity calls, early assignment may be optimal just before
ex-dividend date when the option is deep ITM and has little extrinsic value.
"""

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional
from derivatives_strategies.data.models import (
    DividendEvent,
    OptionQuote,
    OptionType,
)
from derivatives_strategies.options.pricing import (
    intrinsic_value,
    extrinsic_value,
)


@dataclass
class EarlyAssignmentResult:
    """Result of early assignment risk analysis."""
    at_risk: bool
    message: str
    intrinsic: float
    extrinsic: float
    dividend_pv: float
    days_to_ex: int
    assignment_probability_estimate: float  # 0-1 rough estimate

    def to_dict(self) -> dict:
        return {
            "at_risk": self.at_risk,
            "message": self.message,
            "intrinsic": round(self.intrinsic, 4),
            "extrinsic": round(self.extrinsic, 4),
            "dividend_pv": round(self.dividend_pv, 4),
            "days_to_ex": self.days_to_ex,
            "assignment_probability_estimate": round(self.assignment_probability_estimate, 4),
        }


def compute_dividend_pv(
    dividend: DividendEvent,
    as_of: str,
    rate: float,
    daycount_convention: str = "act/365"
) -> float:
    """
    Compute present value of a dividend.

    Args:
        dividend: Dividend event
        as_of: Valuation date (ISO format)
        rate: Risk-free rate (annualized, continuous)
        daycount_convention: Day count convention (currently only "act/365" supported)

    Returns:
        Present value of the dividend
    """
    as_of_date = date.fromisoformat(as_of[:10])
    ex_date = date.fromisoformat(dividend.ex_date)

    days_to_ex = (ex_date - as_of_date).days

    if days_to_ex <= 0:
        return 0.0

    # Day count fraction
    if daycount_convention == "act/365":
        dcf = days_to_ex / 365.0
    elif daycount_convention == "act/360":
        dcf = days_to_ex / 360.0
    else:
        dcf = days_to_ex / 365.0

    return dividend.amount * math.exp(-rate * dcf)


def early_assignment_risk(
    spot: float,
    option_price: float,
    strike: float,
    option_type: OptionType,
    as_of: str,
    expiry: str,
    dividend: Optional[DividendEvent],
    rate: float,
    window_days: int = 7
) -> EarlyAssignmentResult:
    """
    Analyze early assignment risk for an American equity call.

    Early assignment is rational for a call holder when:
    1. Option is ITM
    2. Extrinsic value < PV(dividend)
    3. Dividend ex-date is within the window before expiry

    For short call positions, this means risk of being assigned.

    Args:
        spot: Current spot price
        option_price: Current option mid price
        strike: Option strike
        option_type: Call or put
        as_of: Current date (ISO format)
        expiry: Option expiry (ISO format)
        dividend: Next dividend event (if any)
        rate: Risk-free rate
        window_days: Days before expiry to consider dividend risk

    Returns:
        EarlyAssignmentResult with risk assessment
    """
    as_of_date = date.fromisoformat(as_of[:10])
    expiry_date = date.fromisoformat(expiry)

    # Only calls have material early assignment risk for dividends
    if option_type != OptionType.CALL:
        return EarlyAssignmentResult(
            at_risk=False,
            message="Early assignment risk only applies to calls",
            intrinsic=0.0,
            extrinsic=0.0,
            dividend_pv=0.0,
            days_to_ex=0,
            assignment_probability_estimate=0.0,
        )

    # Calculate intrinsic and extrinsic
    intrinsic = intrinsic_value(spot, strike, option_type)
    extrinsic = extrinsic_value(option_price, spot, strike, option_type)

    # Not ITM - no immediate risk
    if intrinsic <= 0:
        return EarlyAssignmentResult(
            at_risk=False,
            message="Option is not in-the-money",
            intrinsic=intrinsic,
            extrinsic=extrinsic,
            dividend_pv=0.0,
            days_to_ex=0,
            assignment_probability_estimate=0.0,
        )

    # No dividend event
    if dividend is None:
        return EarlyAssignmentResult(
            at_risk=False,
            message="No upcoming dividend",
            intrinsic=intrinsic,
            extrinsic=extrinsic,
            dividend_pv=0.0,
            days_to_ex=0,
            assignment_probability_estimate=0.0,
        )

    ex_date = date.fromisoformat(dividend.ex_date)
    days_to_ex = (ex_date - as_of_date).days

    # Ex-date not before expiry
    if ex_date > expiry_date:
        return EarlyAssignmentResult(
            at_risk=False,
            message="Dividend ex-date is after option expiry",
            intrinsic=intrinsic,
            extrinsic=extrinsic,
            dividend_pv=0.0,
            days_to_ex=days_to_ex,
            assignment_probability_estimate=0.0,
        )

    # Ex-date already passed
    if days_to_ex <= 0:
        return EarlyAssignmentResult(
            at_risk=False,
            message="Dividend ex-date has passed",
            intrinsic=intrinsic,
            extrinsic=extrinsic,
            dividend_pv=0.0,
            days_to_ex=days_to_ex,
            assignment_probability_estimate=0.0,
        )

    # Compute dividend PV
    div_pv = compute_dividend_pv(dividend, as_of, rate)

    # Early assignment condition: extrinsic < PV(dividend) implies rational
    # early exercise — but only imminently, when the ex-date is inside the
    # monitoring window. Further out, extrinsic will evolve before the
    # exercise decision is actually made.
    condition_met = extrinsic < div_pv
    at_risk = condition_met and days_to_ex <= window_days

    # Estimate assignment probability (rough heuristic)
    if condition_met:
        # Deep ITM with tiny extrinsic: high probability
        if extrinsic < 0.5 * div_pv:
            prob = 0.90
        elif extrinsic < 0.75 * div_pv:
            prob = 0.70
        else:
            prob = 0.50

        # Adjust for time to ex-date
        if days_to_ex <= 2:
            prob = min(0.95, prob * 1.2)
        elif days_to_ex > window_days:
            prob *= 0.7
    else:
        # Not at risk based on formula, but could still happen
        ratio = extrinsic / div_pv if div_pv > 0 else float('inf')
        if ratio < 1.5:
            prob = 0.20
        elif ratio < 2.0:
            prob = 0.10
        else:
            prob = 0.05

    if at_risk:
        message = (
            f"HIGH early assignment risk: extrinsic ({extrinsic:.2f}) < "
            f"dividend PV ({div_pv:.2f}), {days_to_ex} days to ex-date"
        )
    elif condition_met:
        message = (
            f"Extrinsic ({extrinsic:.2f}) < dividend PV ({div_pv:.2f}) but "
            f"ex-date is {days_to_ex} days out (window {window_days}); monitor"
        )
    else:
        message = (
            f"Low early assignment risk: extrinsic ({extrinsic:.2f}) >= "
            f"dividend PV ({div_pv:.2f}), {days_to_ex} days to ex-date"
        )

    return EarlyAssignmentResult(
        at_risk=at_risk,
        message=message,
        intrinsic=intrinsic,
        extrinsic=extrinsic,
        dividend_pv=div_pv,
        days_to_ex=days_to_ex,
        assignment_probability_estimate=prob,
    )


def should_roll_before_dividend(
    current_quote: OptionQuote,
    spot: float,
    dividend: DividendEvent,
    as_of: str,
    rate: float,
    extrinsic_threshold: float = 0.10
) -> tuple[bool, str]:
    """
    Determine if a short call should be rolled before dividend ex-date.

    Args:
        current_quote: Current option quote
        spot: Current spot price
        dividend: Upcoming dividend
        as_of: Current date
        rate: Risk-free rate
        extrinsic_threshold: Minimum extrinsic value as fraction of spot

    Returns:
        Tuple of (should_roll, reason)
    """
    if current_quote.option_type != OptionType.CALL:
        return False, "Not a call option"

    intrinsic = intrinsic_value(spot, current_quote.strike, OptionType.CALL)
    extrinsic = extrinsic_value(current_quote.mid, spot, current_quote.strike, OptionType.CALL)

    # Not ITM
    if intrinsic <= 0:
        return False, "Option not ITM; no dividend risk"

    as_of_date = date.fromisoformat(as_of[:10])
    ex_date = date.fromisoformat(dividend.ex_date)
    days_to_ex = (ex_date - as_of_date).days

    # Ex-date already passed: the dividend no longer creates assignment risk
    if days_to_ex <= 0:
        return False, "Dividend ex-date has passed; no roll needed for this event"

    # Too far out
    if days_to_ex > 7:
        return False, f"Ex-date {days_to_ex} days away; monitor closer to date"

    div_pv = compute_dividend_pv(dividend, as_of, rate)

    # Check if extrinsic is too low
    if extrinsic < div_pv:
        return True, (
            f"Roll recommended: extrinsic ({extrinsic:.2f}) < dividend PV ({div_pv:.2f})"
        )

    if extrinsic / spot < extrinsic_threshold:
        return True, (
            f"Roll recommended: extrinsic ({extrinsic:.2f}) is very low relative to spot"
        )

    return False, f"Adequate extrinsic value ({extrinsic:.2f}) for dividend protection"


def dividends_in_range(
    dividends: list[DividendEvent],
    start_date: str,
    end_date: str
) -> list[DividendEvent]:
    """
    Filter dividends to those with ex-date in the given range.

    Args:
        dividends: List of dividend events
        start_date: Start date (ISO format, exclusive)
        end_date: End date (ISO format, inclusive)

    Returns:
        Filtered list of dividends
    """
    return [
        d for d in dividends
        if start_date < d.ex_date <= end_date
    ]


def total_dividend_pv(
    dividends: list[DividendEvent],
    as_of: str,
    rate: float
) -> float:
    """
    Compute total PV of multiple dividends.

    Args:
        dividends: List of dividend events
        as_of: Valuation date
        rate: Risk-free rate

    Returns:
        Sum of present values
    """
    return sum(compute_dividend_pv(d, as_of, rate) for d in dividends)
