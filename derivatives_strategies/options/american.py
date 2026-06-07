"""
American option pricing using binomial tree model.

Supports discrete dividends and early exercise for equity calls.
"""

import math
from typing import Optional
from derivatives_strategies.data.models import OptionType


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

    Supports both continuous dividend yield and discrete dividends.
    For discrete dividends, uses the method of adjusting the stock price
    at the ex-dividend date step.

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
    """
    if T <= 0:
        # At expiry
        if option_type == OptionType.CALL:
            return max(0.0, S - K)
        else:
            return max(0.0, K - S)

    # Time step
    dt = T / steps

    # Up and down factors
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u

    # Risk-neutral probability
    exp_term = math.exp((r - q) * dt)
    p = (exp_term - d) / (u - d)

    # Discount factor per step
    disc = math.exp(-r * dt)

    # Find dividend steps if any
    div_steps: dict[int, float] = {}
    if dividends:
        for t_div, amount in dividends:
            if 0 < t_div < T:
                step = int(t_div / dt)
                if step < steps:
                    if step in div_steps:
                        div_steps[step] += amount
                    else:
                        div_steps[step] = amount

    # Build stock price tree at expiry (step N)
    # We'll use backward induction
    stock_prices = [0.0] * (steps + 1)

    # Calculate stock price at each node at expiry
    # Account for dividends by tracking adjusted spot
    S_adj = S
    for step in range(steps):
        if step in div_steps:
            S_adj -= div_steps[step]
            S_adj = max(0.01, S_adj)

    # Now build final stock prices
    for i in range(steps + 1):
        stock_prices[i] = S_adj * (u ** (steps - i)) * (d ** i)

    # Option values at expiry
    option_values = [0.0] * (steps + 1)
    for i in range(steps + 1):
        if option_type == OptionType.CALL:
            option_values[i] = max(0.0, stock_prices[i] - K)
        else:
            option_values[i] = max(0.0, K - stock_prices[i])

    # Backward induction through the tree
    for step in range(steps - 1, -1, -1):
        for i in range(step + 1):
            # Stock price at this node
            # We need to calculate based on original spot and path
            # Simpler approach: recalculate from S_adj at this step
            S_node = S
            # Subtract PV of dividends that occur after this step
            for div_step, div_amt in div_steps.items():
                if div_step <= step:
                    S_node -= div_amt
            S_node = max(0.01, S_node)
            S_node = S_node * (u ** (step - i)) * (d ** i)

            # Add back dividend if at ex-date (for exercise value)
            if step in div_steps:
                S_node += div_steps[step]

            # Continuation value
            continuation = disc * (p * option_values[i] + (1 - p) * option_values[i + 1])

            # Exercise value
            if option_type == OptionType.CALL:
                exercise = max(0.0, S_node - K)
            else:
                exercise = max(0.0, K - S_node)

            # American: max of continuation and exercise
            option_values[i] = max(continuation, exercise)

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

    # American price with tree
    american = binomial_tree_american(
        S, K, T, r, sigma, OptionType.CALL,
        steps=steps, dividends=dividends
    )

    # European price (Black-Scholes with dividend adjustment)
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
    steps: int = 50,
    q: float = 0.0
) -> list[tuple[float, float]]:
    """
    Compute early exercise boundary for American option.

    Returns stock price levels at each time step where early exercise
    becomes optimal.

    Args:
        K: Strike price
        T: Time to expiry
        r: Risk-free rate
        sigma: Volatility
        option_type: Call or put
        steps: Number of time steps
        q: Continuous dividend yield

    Returns:
        List of (time_to_expiry, boundary_stock_price) tuples
    """
    dt = T / steps
    boundary = []

    for step in range(steps):
        t = T - step * dt
        if t <= 0:
            continue

        # Binary search for boundary
        if option_type == OptionType.PUT:
            # Put: find S where exercise value = continuation
            low, high = 0.1 * K, K
        else:
            # Call: find S where exercise value = continuation
            low, high = K, 3 * K

        for _ in range(30):  # Binary search iterations
            mid = (low + high) / 2

            # Price at this node
            american = binomial_tree_american(
                mid, K, t, r, sigma, option_type,
                steps=max(10, step), q=q
            )

            # Exercise value
            if option_type == OptionType.CALL:
                exercise = max(0, mid - K)
            else:
                exercise = max(0, K - mid)

            # At boundary, American = exercise
            if abs(american - exercise) < 0.001:
                break

            if american > exercise:
                if option_type == OptionType.PUT:
                    high = mid
                else:
                    low = mid
            else:
                if option_type == OptionType.PUT:
                    low = mid
                else:
                    high = mid

        boundary.append((t, mid))

    return boundary
