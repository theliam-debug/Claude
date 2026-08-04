"""
Option Greeks calculations.

All Greeks are calculated analytically using Black-Scholes formulas.
"""

import math
from derivatives_strategies.data.models import OptionType, Greeks
from derivatives_strategies.options.pricing import d1, d2, norm_cdf, norm_pdf


def delta(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0
) -> float:
    """
    Calculate option delta.

    Delta measures the rate of change of option price with respect to
    changes in the underlying price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        q: Continuous dividend yield

    Returns:
        Delta value (between -1 and 1)
    """
    if T <= 0:
        # At expiry
        if option_type == OptionType.CALL:
            return 1.0 if S > K else (0.5 if S == K else 0.0)
        else:
            return -1.0 if S < K else (-0.5 if S == K else 0.0)

    if sigma <= 0:
        # Zero vol
        forward = S * math.exp((r - q) * T)
        if option_type == OptionType.CALL:
            return math.exp(-q * T) if forward > K else 0.0
        else:
            return -math.exp(-q * T) if forward < K else 0.0

    d1_val = d1(S, K, T, r, sigma, q)

    if option_type == OptionType.CALL:
        return math.exp(-q * T) * norm_cdf(d1_val)
    else:
        return -math.exp(-q * T) * norm_cdf(-d1_val)


def gamma(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Calculate option gamma.

    Gamma measures the rate of change of delta with respect to
    changes in the underlying price. Same for calls and puts.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        q: Continuous dividend yield

    Returns:
        Gamma value (non-negative)
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0

    d1_val = d1(S, K, T, r, sigma, q)
    return math.exp(-q * T) * norm_pdf(d1_val) / (S * sigma * math.sqrt(T))


def theta(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0
) -> float:
    """
    Calculate option theta (per day).

    Theta measures the rate of change of option price with respect to
    time passage. Returns the expected daily decay.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        q: Continuous dividend yield

    Returns:
        Theta value (typically negative, per day)
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d2(S, K, T, r, sigma, q)

    # First term: time decay from volatility
    term1 = -S * math.exp(-q * T) * norm_pdf(d1_val) * sigma / (2 * math.sqrt(T))

    # Black-Scholes theta with continuous dividend yield q:
    #   call: term1 + q*S*e^(-qT)*N(d1)  - r*K*e^(-rT)*N(d2)
    #   put:  term1 - q*S*e^(-qT)*N(-d1) + r*K*e^(-rT)*N(-d2)
    if option_type == OptionType.CALL:
        term2 = q * S * math.exp(-q * T) * norm_cdf(d1_val)
        term3 = -r * K * math.exp(-r * T) * norm_cdf(d2_val)
        theta_annual = term1 + term2 + term3
    else:
        term2 = -q * S * math.exp(-q * T) * norm_cdf(-d1_val)
        term3 = r * K * math.exp(-r * T) * norm_cdf(-d2_val)
        theta_annual = term1 + term2 + term3

    # Convert to per-day
    return theta_annual / 365.0


def vega(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0
) -> float:
    """
    Calculate option vega (per 1% vol move).

    Vega measures the rate of change of option price with respect to
    changes in implied volatility. Same for calls and puts.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        q: Continuous dividend yield

    Returns:
        Vega value (per 1% volatility change)
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d1_val = d1(S, K, T, r, sigma, q)
    # Vega per 1 unit change in sigma
    vega_full = S * math.exp(-q * T) * norm_pdf(d1_val) * math.sqrt(T)

    # Return per 0.01 (1%) change in vol
    return vega_full / 100.0


def rho(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0
) -> float:
    """
    Calculate option rho (per 1% rate move).

    Rho measures the rate of change of option price with respect to
    changes in the risk-free interest rate.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        q: Continuous dividend yield

    Returns:
        Rho value (per 1% rate change)
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d2_val = d2(S, K, T, r, sigma, q)

    if option_type == OptionType.CALL:
        rho_full = K * T * math.exp(-r * T) * norm_cdf(d2_val)
    else:
        rho_full = -K * T * math.exp(-r * T) * norm_cdf(-d2_val)

    # Return per 0.01 (1%) change in rate
    return rho_full / 100.0


def compute_all_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    q: float = 0.0
) -> Greeks:
    """
    Compute all Greeks for an option.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        q: Continuous dividend yield

    Returns:
        Greeks dataclass with all values
    """
    return Greeks(
        delta=delta(S, K, T, r, sigma, option_type, q),
        gamma=gamma(S, K, T, r, sigma, q),
        theta=theta(S, K, T, r, sigma, option_type, q),
        vega=vega(S, K, T, r, sigma, q),
        rho=rho(S, K, T, r, sigma, option_type, q),
    )


def position_greeks(
    greeks: Greeks,
    quantity: int,
    multiplier: int = 100
) -> Greeks:
    """
    Scale Greeks for a position.

    Args:
        greeks: Per-contract Greeks
        quantity: Number of contracts (negative for short)
        multiplier: Contract multiplier (typically 100)

    Returns:
        Position-level Greeks
    """
    scale = quantity * multiplier
    return Greeks(
        delta=greeks.delta * scale,
        gamma=greeks.gamma * scale,
        theta=greeks.theta * scale,
        vega=greeks.vega * scale,
        rho=greeks.rho * scale if greeks.rho is not None else None,
    )


def aggregate_greeks(greeks_list: list[Greeks]) -> Greeks:
    """
    Aggregate multiple Greeks into portfolio-level Greeks.

    Args:
        greeks_list: List of Greeks to aggregate

    Returns:
        Sum of all Greeks
    """
    if not greeks_list:
        return Greeks(delta=0, gamma=0, theta=0, vega=0, rho=0)

    total_delta = sum(g.delta for g in greeks_list)
    total_gamma = sum(g.gamma for g in greeks_list)
    total_theta = sum(g.theta for g in greeks_list)
    total_vega = sum(g.vega for g in greeks_list)
    total_rho = sum(g.rho or 0 for g in greeks_list)

    return Greeks(
        delta=total_delta,
        gamma=total_gamma,
        theta=total_theta,
        vega=total_vega,
        rho=total_rho,
    )
