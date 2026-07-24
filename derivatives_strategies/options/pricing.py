"""
Option pricing functions using Black-Scholes model.

Implements European option pricing with continuous dividend yield adjustment.
All functions use annualized continuously compounded rates.
"""

import math
from typing import Optional
from derivatives_strategies.data.models import OptionType


def norm_cdf(x: float) -> float:
    """
    Standard normal cumulative distribution function.

    Uses error function for accurate calculation.
    """
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def d1(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    """
    Calculate d1 in Black-Scholes formula.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate (annualized, continuous)
        sigma: Volatility (annualized)
        q: Continuous dividend yield (annualized)

    Returns:
        d1 value
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    return (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))


def d2(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    """
    Calculate d2 in Black-Scholes formula.

    d2 = d1 - sigma * sqrt(T)
    """
    if T <= 0 or sigma <= 0:
        return 0.0
    return d1(S, K, T, r, sigma, q) - sigma * math.sqrt(T)


def black_scholes_call(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Black-Scholes European call option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate (annualized, continuous)
        sigma: Volatility (annualized)
        q: Continuous dividend yield (annualized)

    Returns:
        Call option price
    """
    if T <= 0:
        return max(0.0, S - K)

    if sigma <= 0:
        # Zero vol: deterministic forward
        return max(0.0, S * math.exp(-q * T) - K * math.exp(-r * T))

    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d2(S, K, T, r, sigma, q)

    call = S * math.exp(-q * T) * norm_cdf(d1_val) - K * math.exp(-r * T) * norm_cdf(d2_val)
    return max(0.0, call)


def black_scholes_put(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Black-Scholes European put option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate (annualized, continuous)
        sigma: Volatility (annualized)
        q: Continuous dividend yield (annualized)

    Returns:
        Put option price
    """
    if T <= 0:
        return max(0.0, K - S)

    if sigma <= 0:
        # Zero vol: deterministic forward
        return max(0.0, K * math.exp(-r * T) - S * math.exp(-q * T))

    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d2(S, K, T, r, sigma, q)

    put = K * math.exp(-r * T) * norm_cdf(-d2_val) - S * math.exp(-q * T) * norm_cdf(-d1_val)
    return max(0.0, put)


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0
) -> float:
    """
    Black-Scholes option price for call or put.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate (annualized, continuous)
        sigma: Volatility (annualized)
        option_type: Call or put
        q: Continuous dividend yield (annualized)

    Returns:
        Option price
    """
    if option_type == OptionType.CALL:
        return black_scholes_call(S, K, T, r, sigma, q)
    else:
        return black_scholes_put(S, K, T, r, sigma, q)


def intrinsic_value(
    S: float,
    K: float,
    option_type: OptionType
) -> float:
    """
    Calculate intrinsic value of an option.

    Args:
        S: Spot price
        K: Strike price
        option_type: Call or put

    Returns:
        Intrinsic value (non-negative)
    """
    if option_type == OptionType.CALL:
        return max(0.0, S - K)
    else:
        return max(0.0, K - S)


def extrinsic_value(
    option_price: float,
    S: float,
    K: float,
    option_type: OptionType
) -> float:
    """
    Calculate extrinsic (time) value of an option.

    Args:
        option_price: Current option price
        S: Spot price
        K: Strike price
        option_type: Call or put

    Returns:
        Extrinsic value
    """
    intrinsic = intrinsic_value(S, K, option_type)
    return max(0.0, option_price - intrinsic)


def option_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0,
    dividends: Optional[list[tuple[float, float]]] = None
) -> float:
    """
    Option price with optional discrete dividend adjustments.

    For discrete dividends, uses spot adjustment method:
    S_adjusted = S - PV(dividends before expiry)

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate (annualized, continuous)
        sigma: Volatility (annualized)
        option_type: Call or put
        q: Continuous dividend yield (annualized)
        dividends: List of (time_to_ex_date, amount) tuples

    Returns:
        Option price
    """
    S_adj = S

    # Adjust spot for discrete dividends.
    # Convention: the window is strictly (0, T) — a dividend going ex exactly
    # AT expiry does not reduce the option's value, because the option holder
    # never receives it and the ex-drop happens at settlement. This matches
    # american.binomial_tree_american. Note the resulting discontinuity is
    # real: a dividend at T-epsilon is priced, one at T is not.
    if dividends:
        for t_div, amount in dividends:
            if 0 < t_div < T:
                # PV of dividend
                pv = amount * math.exp(-r * t_div)
                S_adj -= pv

    # Dividends worth as much as the stock are bad inputs, not a pricing
    # case — silently clamping would return a near-zero-spot price with no
    # signal that the inputs were impossible.
    if S_adj <= 0:
        raise ValueError(
            f"PV of dividends ({S - S_adj:.4f}) >= spot ({S:.4f}); "
            "check dividend inputs"
        )

    return black_scholes_price(S_adj, K, T, r, sigma, option_type, q)


def forward_price(
    S: float,
    T: float,
    r: float,
    q: float = 0.0,
    dividends: Optional[list[tuple[float, float]]] = None
) -> float:
    """
    Calculate forward price of the underlying.

    Args:
        S: Spot price
        T: Time to expiry (years)
        r: Risk-free rate
        q: Continuous dividend yield
        dividends: Discrete dividends as (time, amount) tuples

    Returns:
        Forward price
    """
    S_adj = S

    # Adjust for discrete dividends
    if dividends:
        for t_div, amount in dividends:
            if 0 < t_div < T:
                pv = amount * math.exp(-r * t_div)
                S_adj -= pv

    return S_adj * math.exp((r - q) * T)
