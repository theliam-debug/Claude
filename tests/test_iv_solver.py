"""
Tests for implied volatility solver.
"""

import pytest
import math

from derivatives_strategies.surface.iv_solver import (
    implied_volatility,
    IVSolverError,
)
from derivatives_strategies.options.pricing import black_scholes_call, black_scholes_put
from derivatives_strategies.data.models import OptionType


class TestImpliedVolatility:
    """Test suite for implied volatility solver."""

    def test_iv_solver_converges_on_known_call_price(self):
        """Test that IV solver converges on known call prices."""
        S = 100.0
        K = 100.0
        T = 0.25  # 3 months
        r = 0.05
        true_vol = 0.20

        # Calculate price at known vol
        price = black_scholes_call(S, K, T, r, true_vol)

        # Solve for IV
        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.CALL,
        )

        assert abs(solved_vol - true_vol) < 1e-4, \
            f"Expected vol {true_vol}, got {solved_vol}"

    def test_iv_solver_converges_on_known_put_price(self):
        """Test that IV solver converges on known put prices."""
        S = 100.0
        K = 100.0
        T = 0.5
        r = 0.05
        true_vol = 0.30

        price = black_scholes_put(S, K, T, r, true_vol)

        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.PUT,
        )

        assert abs(solved_vol - true_vol) < 1e-4

    def test_iv_solver_handles_otm_call(self):
        """Test IV solver for OTM call."""
        S = 100.0
        K = 120.0  # 20% OTM
        T = 0.25
        r = 0.05
        true_vol = 0.25

        price = black_scholes_call(S, K, T, r, true_vol)

        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.CALL,
        )

        assert abs(solved_vol - true_vol) < 1e-4

    def test_iv_solver_handles_itm_put(self):
        """Test IV solver for ITM put."""
        S = 100.0
        K = 120.0  # ITM put
        T = 0.25
        r = 0.05
        true_vol = 0.25

        price = black_scholes_put(S, K, T, r, true_vol)

        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.PUT,
        )

        assert abs(solved_vol - true_vol) < 1e-4

    def test_iv_solver_with_high_volatility(self):
        """Test IV solver with high volatility."""
        S = 100.0
        K = 100.0
        T = 1.0
        r = 0.05
        true_vol = 1.50  # 150% vol

        price = black_scholes_call(S, K, T, r, true_vol)

        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.CALL,
        )

        assert abs(solved_vol - true_vol) < 1e-3

    def test_iv_solver_with_low_volatility(self):
        """Test IV solver with low volatility."""
        S = 100.0
        K = 100.0
        T = 0.5
        r = 0.05
        true_vol = 0.05  # 5% vol

        price = black_scholes_call(S, K, T, r, true_vol)

        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.CALL,
        )

        assert abs(solved_vol - true_vol) < 1e-4

    def test_iv_solver_with_dividend_yield(self):
        """Test IV solver with continuous dividend yield."""
        S = 100.0
        K = 100.0
        T = 0.5
        r = 0.05
        q = 0.02  # 2% dividend yield
        true_vol = 0.25

        from derivatives_strategies.options.pricing import black_scholes_price
        price = black_scholes_price(S, K, T, r, true_vol, OptionType.CALL, q)

        solved_vol = implied_volatility(
            price=price,
            S=S,
            K=K,
            T=T,
            r=r,
            option_type=OptionType.CALL,
            q=q,
        )

        assert abs(solved_vol - true_vol) < 1e-4

    def test_iv_solver_rejects_arbitrage_price(self):
        """Test that IV solver rejects prices below lower bound."""
        S = 100.0
        K = 90.0  # ITM call
        T = 0.25
        r = 0.05

        # Lower bound for European call: S - K*exp(-rT) ≈ 11.11
        lower_bound = S - K * math.exp(-r * T)
        price = 5.0  # Below lower bound

        with pytest.raises(IVSolverError):
            implied_volatility(
                price=price,
                S=S,
                K=K,
                T=T,
                r=r,
                option_type=OptionType.CALL,
            )

    def test_iv_solver_rejects_expired_option(self):
        """Test that IV solver rejects expired options."""
        with pytest.raises(IVSolverError):
            implied_volatility(
                price=5.0,
                S=100.0,
                K=100.0,
                T=0,  # Expired
                r=0.05,
                option_type=OptionType.CALL,
            )

    def test_iv_solver_deterministic(self):
        """Test that IV solver produces deterministic results."""
        S = 100.0
        K = 105.0
        T = 0.25
        r = 0.05
        price = 3.50

        # Run solver multiple times
        results = []
        for _ in range(10):
            vol = implied_volatility(
                price=price,
                S=S,
                K=K,
                T=T,
                r=r,
                option_type=OptionType.CALL,
            )
            results.append(vol)

        # All results should be identical
        assert all(abs(r - results[0]) < 1e-10 for r in results)
