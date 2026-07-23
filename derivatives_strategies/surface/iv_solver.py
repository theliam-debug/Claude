"""
Implied volatility solver using robust bracketing method.

Uses a combination of Brent's method and bisection for reliable convergence.
"""

import math
from typing import Optional
from derivatives_strategies.data.models import OptionType, OptionQuote
from derivatives_strategies.options.pricing import (
    black_scholes_price,
    intrinsic_value,
)


class IVSolverError(Exception):
    """Error during implied volatility calculation."""
    pass


def implied_volatility(
    price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType,
    q: float = 0.0,
    tol: float = 1e-6,
    max_iter: int = 100,
    vol_bounds: tuple[float, float] = (0.001, 5.0)
) -> float:
    """
    Calculate implied volatility using Brent's method with bisection fallback.

    Args:
        price: Market price of the option
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        option_type: Call or put
        q: Continuous dividend yield
        tol: Convergence tolerance
        max_iter: Maximum iterations
        vol_bounds: (min_vol, max_vol) search bounds

    Returns:
        Implied volatility

    Raises:
        IVSolverError: If solver fails to converge
    """
    if T <= 0:
        raise IVSolverError("Cannot compute IV for expired option")

    # Check for arbitrage violations (European option bounds)
    # For European options, the lower bound is discounted intrinsic
    if option_type == OptionType.CALL:
        # Call: max(0, S*exp(-qT) - K*exp(-rT))
        lower_bound = max(0.0, S * math.exp(-q * T) - K * math.exp(-r * T))
        max_price = S * math.exp(-q * T)
    else:
        # Put: max(0, K*exp(-rT) - S*exp(-qT))
        lower_bound = max(0.0, K * math.exp(-r * T) - S * math.exp(-q * T))
        max_price = K * math.exp(-r * T)

    if price < lower_bound - tol:
        raise IVSolverError(
            f"Price {price:.4f} below lower bound {lower_bound:.4f}"
        )

    if price > max_price + tol:
        raise IVSolverError(
            f"Price {price:.4f} exceeds maximum theoretical value {max_price:.4f}"
        )

    # If price equals lower bound, vol is effectively 0
    if abs(price - lower_bound) < tol:
        return vol_bounds[0]

    # Objective function: model price - market price
    def objective(sigma: float) -> float:
        model_price = black_scholes_price(S, K, T, r, sigma, option_type, q)
        return model_price - price

    vol_low, vol_high = vol_bounds

    # Verify bracket
    f_low = objective(vol_low)
    f_high = objective(vol_high)

    if f_low > 0:
        # Price sits between discounted intrinsic and BS(min_vol): the
        # implied vol is below the minimum bound; min bound is the honest
        # answer (error bounded by vol_bounds[0]).
        return vol_low

    if f_high < 0:
        # Price above BS(max_vol): the quote implies a volatility beyond
        # the search bound. Silently returning max_vol would launder a bad
        # quote into a plausible IV — fail loudly instead.
        raise IVSolverError(
            f"Price {price:.4f} implies volatility above the "
            f"{vol_high:.1f} search bound (BS(max_vol)={f_high + price:.4f}); "
            "quote is likely bad data"
        )

    # Brent's method
    a, b = vol_low, vol_high
    fa, fb = f_low, f_high

    c = a
    fc = fa
    d = b - a
    e = d

    for iteration in range(max_iter):
        if fb * fc > 0:
            c = a
            fc = fa
            d = b - a
            e = d

        if abs(fc) < abs(fb):
            a, b, c = b, c, b
            fa, fb, fc = fb, fc, fb

        # Convergence check. Price-space closeness alone is NOT sufficient:
        # for tiny-vega options (deep ITM, short expiry) a wide range of
        # vols reprices within tol, so we also require the vol bracket to
        # be tight before accepting.
        tol1 = 2 * 1e-12 * abs(b) + 0.5 * tol
        xm = 0.5 * (c - b)

        if abs(xm) <= tol1:
            return b
        if abs(fb) < tol and abs(xm) <= 1e-6:
            return b

        if abs(e) >= tol1 and abs(fa) > abs(fb):
            # Attempt inverse quadratic interpolation
            s = fb / fa
            if abs(a - c) < 1e-12:
                p = 2 * xm * s
                q_val = 1 - s
            else:
                q_val = fa / fc
                r_val = fb / fc
                p = s * (2 * xm * q_val * (q_val - r_val) - (b - a) * (r_val - 1))
                q_val = (q_val - 1) * (r_val - 1) * (s - 1)

            if p > 0:
                q_val = -q_val
            p = abs(p)

            if 2 * p < min(3 * xm * q_val - abs(tol1 * q_val), abs(e * q_val)):
                e = d
                d = p / q_val
            else:
                d = xm
                e = d
        else:
            # Bisection
            d = xm
            e = d

        a = b
        fa = fb

        if abs(d) > tol1:
            b += d
        else:
            b += tol1 if xm >= 0 else -tol1

        fb = objective(b)

    raise IVSolverError(
        f"Brent's method did not converge after {max_iter} iterations "
        f"(last iterate {b:.6f}, residual {fb:.2e})"
    )


def iv_from_quote(
    quote: OptionQuote,
    spot: float,
    r: float,
    T: float,
    q: float = 0.0,
    use_mid: bool = True
) -> Optional[float]:
    """
    Calculate implied volatility from an option quote.

    Args:
        quote: Option quote
        spot: Spot price
        r: Risk-free rate
        T: Time to expiry (years)
        q: Continuous dividend yield
        use_mid: Use mid price (True) or last price (False)

    Returns:
        Implied volatility, or None if calculation fails
    """
    price = quote.mid if use_mid else quote.last

    if price <= 0 or T <= 0:
        return None

    try:
        return implied_volatility(
            price=price,
            S=spot,
            K=quote.strike,
            T=T,
            r=r,
            option_type=quote.option_type,
            q=q,
        )
    except IVSolverError:
        return None


def newton_iv(
    price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: OptionType,
    q: float = 0.0,
    initial_guess: float = 0.20,
    tol: float = 1e-6,
    max_iter: int = 50
) -> float:
    """
    Calculate implied volatility using Newton-Raphson method.

    Faster than bracketing methods when initial guess is good,
    but can fail for extreme cases.

    Args:
        price: Market price
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        option_type: Call or put
        q: Continuous dividend yield
        initial_guess: Starting volatility
        tol: Convergence tolerance
        max_iter: Maximum iterations

    Returns:
        Implied volatility

    Raises:
        IVSolverError: If solver fails to converge
    """
    from derivatives_strategies.options.greeks import vega as calc_vega

    sigma = initial_guess

    for _ in range(max_iter):
        model_price = black_scholes_price(S, K, T, r, sigma, option_type, q)
        diff = model_price - price

        # Vega for Newton step (convert from per 1% to per 1.0)
        v = calc_vega(S, K, T, r, sigma, q) * 100

        if abs(v) < 1e-10:
            raise IVSolverError("Vega too small for Newton's method")

        # Newton step
        step = diff / v
        sigma_new = max(0.001, min(5.0, sigma - step))

        # Converged only when the price matches AND the vol iterate has
        # stabilized — price closeness alone is meaningless for tiny-vega
        # options, where any sigma reprices within tol.
        if abs(diff) < tol and abs(sigma_new - sigma) < 1e-8:
            return sigma_new

        sigma = sigma_new

    raise IVSolverError(f"Newton's method did not converge after {max_iter} iterations")
