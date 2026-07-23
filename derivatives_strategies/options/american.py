"""
American option pricing using binomial tree model.

Supports discrete dividends and early exercise for equity calls.

Discrete dividends use the escrowed-dividend convention: the tree is built
on the "risky" component S* = S - PV(dividends before expiry), and the cash
price at any node adds back the present value of the dividends not yet
paid. This keeps the tree internally consistent (one stock price per node)
and makes its European limit agree with the escrowed Black-Scholes price
in pricing.option_price.
"""

import math
from typing import Optional
from derivatives_strategies.data.models import OptionType


def _intrinsic(S: float, K: float, option_type: OptionType) -> float:
    if option_type == OptionType.CALL:
        return max(0.0, S - K)
    return max(0.0, K - S)


def binomial_tree_american(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    steps: int = 100,
    q: float = 0.0,
    dividends: Optional[list[tuple[float, float]]] = None
) -> float:
    """
    Price American option using Cox-Ross-Rubinstein binomial tree.

    Supports both continuous dividend yield and discrete dividends
    (escrowed-dividend convention; see module docstring).

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        steps: Number of time steps
        q: Continuous dividend yield
        dividends: List of (time_to_ex_date, amount) tuples

    Returns:
        American option price

    Raises:
        ValueError: For non-positive sigma/steps, or if the CRR
            risk-neutral probability falls outside [0, 1] (increase steps).
    """
    if T <= 0:
        return _intrinsic(S, K, option_type)
    if sigma <= 0:
        raise ValueError("sigma must be positive for the binomial tree")
    if steps < 1:
        raise ValueError("steps must be >= 1")

    # Time step
    dt = T / steps

    # Up and down factors
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u

    # Risk-neutral probability
    exp_term = math.exp((r - q) * dt)
    p = (exp_term - d) / (u - d)
    if not (0.0 <= p <= 1.0):
        raise ValueError(
            f"CRR risk-neutral probability {p:.4f} outside [0, 1] "
            f"(sigma={sigma}, r={r}, q={q}, dt={dt:.6f}); "
            "increase steps or check inputs"
        )

    # Discount factor per step
    disc = math.exp(-r * dt)

    # Escrowed-dividend split: tree evolves S* = S - PV(dividends in (0, T]).
    # Dividends exactly at expiry are excluded by convention (the holder of
    # the option receives no dividend at expiry).
    divs = [
        (t_div, amount) for t_div, amount in (dividends or [])
        if 0 < t_div < T and amount > 0
    ]
    pv_all_divs = sum(a * math.exp(-r * t_div) for t_div, a in divs)
    if pv_all_divs >= S:
        raise ValueError(
            f"PV of dividends ({pv_all_divs:.4f}) >= spot ({S:.4f}); "
            "inputs are not economically meaningful"
        )
    S_star = S - pv_all_divs

    # Escrow value at each step: PV (at that step's time) of dividends still
    # unpaid. Cash stock price at a node = risky node price + escrow.
    escrow = [0.0] * (steps + 1)
    for step in range(steps + 1):
        t = step * dt
        escrow[step] = sum(
            a * math.exp(-r * (t_div - t))
            for t_div, a in divs if t_div > t
        )

    # Option values at expiry (escrow is 0 at T)
    option_values = [0.0] * (steps + 1)
    node = S_star * (u ** steps)
    dd = d * d
    for i in range(steps + 1):
        option_values[i] = _intrinsic(node, K, option_type)
        node *= dd

    # Backward induction through the tree
    for step in range(steps - 1, -1, -1):
        step_escrow = escrow[step]
        node = S_star * (u ** step)
        for i in range(step + 1):
            # Continuation value
            continuation = disc * (
                p * option_values[i] + (1 - p) * option_values[i + 1]
            )
            # Exercise uses the full cash stock price at the node
            exercise = _intrinsic(node + step_escrow, K, option_type)
            option_values[i] = max(continuation, exercise)
            node *= dd

    return option_values[0]


def american_call_with_dividends(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    dividends: list[tuple[float, float]],
    steps: int = 100
) -> tuple[float, float, bool]:
    """
    Price American call with discrete dividends and analyze early exercise.

    For calls on dividend-paying stocks, early exercise may be optimal
    just before the ex-dividend date.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility
        dividends: List of (time_to_ex_date, amount) tuples
        steps: Number of tree steps

    Returns:
        Tuple of (american_price, european_price, early_exercise_likely)
    """
    from derivatives_strategies.options.pricing import option_price

    # American price with tree (escrowed-dividend convention, consistent
    # with the European comparator below)
    american = binomial_tree_american(
        S, K, T, r, sigma, OptionType.CALL,
        steps=steps, dividends=dividends
    )

    # European price (Black-Scholes with escrowed dividend adjustment)
    european = option_price(
        S, K, T, r, sigma, OptionType.CALL,
        dividends=dividends
    )

    # Early exercise is likely if American > European by meaningful amount
    early_exercise_likely = (american - european) > 0.01 * S

    return american, european, early_exercise_likely


def early_exercise_boundary(
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: OptionType,
    steps: int = 20,
    q: float = 0.0,
    tree_steps: int = 60,
    tol: float = 1e-4,
) -> list[tuple[float, float]]:
    """
    Compute the early exercise boundary for an American option under a
    continuous dividend yield.

    For each time-to-expiry gridpoint, bisects on region membership:
    a spot S is in the exercise region when the American value equals
    intrinsic (within tol, relative to K). Puts exercise below the
    boundary; calls (which need q > 0) exercise above it.

    Time steps where no boundary exists inside the search bracket (e.g. a
    call with q = 0, which is never exercised early) are omitted from the
    result.

    Args:
        K: Strike price
        T: Time to expiry
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        steps: Number of time gridpoints
        q: Continuous dividend yield
        tree_steps: Binomial steps for each valuation (cost/accuracy knob)
        tol: Exercise-region tolerance, relative to K

    Returns:
        List of (time_to_expiry, boundary_stock_price) tuples
    """
    abs_tol = tol * K

    def in_exercise_region(S: float, t: float) -> bool:
        intrinsic = _intrinsic(S, K, option_type)
        if intrinsic <= 0:
            return False
        american = binomial_tree_american(
            S, K, t, r, sigma, option_type, steps=tree_steps, q=q
        )
        return (american - intrinsic) <= abs_tol

    dt = T / steps
    boundary = []

    for step in range(steps):
        t = T - step * dt
        if t <= 0:
            continue

        if option_type == OptionType.PUT:
            low, high = 0.05 * K, K
            # Exercise region is [*, boundary]: low must be inside,
            # high (at-the-money) outside.
            if not in_exercise_region(low, t):
                continue  # No exercise region at this time step
            if in_exercise_region(high, t):
                boundary.append((t, high))
                continue
        else:
            low, high = K, 5 * K
            # Exercise region is [boundary, *]: high must be inside.
            if not in_exercise_region(high, t):
                continue  # No exercise region (e.g. q = 0 call)
            if in_exercise_region(low, t):
                boundary.append((t, low))
                continue

        # Bisect the membership transition. For puts the region is below
        # the boundary; for calls it is above.
        for _ in range(30):
            mid = (low + high) / 2
            inside = in_exercise_region(mid, t)
            if option_type == OptionType.PUT:
                if inside:
                    low = mid  # boundary is above mid
                else:
                    high = mid
            else:
                if inside:
                    high = mid  # boundary is below mid
                else:
                    low = mid
            if high - low < 1e-4 * K:
                break

        boundary.append((t, (low + high) / 2))

    return boundary
