"""
Regression tests for the 2026-07 audit's quantitative findings: theta with
dividend yield, escrowed-dividend American trees, solver guards, IV solver
honesty, and dividend-risk window logic.
"""

import math

import pytest

from derivatives_strategies.data.models import DividendEvent, OptionType
from derivatives_strategies.dividends.analysis import (
    early_assignment_risk,
    should_roll_before_dividend,
)
from derivatives_strategies.options.american import (
    american_call_with_dividends,
    binomial_tree_american,
    early_exercise_boundary,
)
from derivatives_strategies.options.greeks import Greeks, position_greeks, theta
from derivatives_strategies.options.pricing import black_scholes_price, option_price
from derivatives_strategies.surface.iv_solver import (
    IVSolverError,
    implied_volatility,
    newton_iv,
)
from derivatives_strategies.data.models import OptionQuote


class TestThetaWithDividendYield:
    """Theta previously had the q-term sign flipped in both branches."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    @pytest.mark.parametrize("q", [0.0, 0.02, 0.04, 0.08])
    def test_theta_matches_finite_difference(self, option_type, q):
        S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.20
        h = 1e-5
        fd = (
            black_scholes_price(S, K, T - h, r, sigma, option_type, q)
            - black_scholes_price(S, K, T + h, r, sigma, option_type, q)
        ) / (2 * h) / 365.0
        assert theta(S, K, T, r, sigma, option_type, q) == pytest.approx(
            fd, abs=1e-8
        )

    def test_put_theta_sign_at_high_yield(self):
        # The broken formula reported +0.375/365 annualized here.
        value = theta(100, 100, 1.0, 0.05, 0.20, OptionType.PUT, q=0.04)
        assert value < 0


class TestAmericanTree:
    def test_converges_to_bs_for_european_case(self):
        bs = black_scholes_price(100, 100, 1.0, 0.05, 0.2, OptionType.CALL)
        tree = binomial_tree_american(100, 100, 1.0, 0.05, 0.2,
                                      OptionType.CALL, steps=1000)
        assert tree == pytest.approx(bs, abs=5e-3)

    def test_escrowed_dividend_reference_value(self):
        # Audit reference: correct escrowed CRR gives 1.1121 at 2000 steps
        # for S=100, K=150, T=1, r=0, sigma=0.30, D=5 @ t=0.9.
        # The broken tree gave 1.2778.
        price = binomial_tree_american(
            100, 150, 1.0, 0.0, 0.30, OptionType.CALL,
            steps=2000, dividends=[(0.9, 5.0)],
        )
        assert price == pytest.approx(1.1121, abs=2e-3)

    def test_american_put_premium_positive(self):
        bs = black_scholes_price(100, 100, 1.0, 0.05, 0.2, OptionType.PUT)
        tree = binomial_tree_american(100, 100, 1.0, 0.05, 0.2,
                                      OptionType.PUT, steps=500)
        assert tree > bs + 0.1

    def test_american_geq_european_with_dividends(self):
        american, european, _ = american_call_with_dividends(
            100, 100, 0.5, 0.05, 0.25, dividends=[(0.25, 2.0)], steps=500,
        )
        assert american >= european - 1e-9

    def test_sigma_zero_raises(self):
        with pytest.raises(ValueError, match="sigma"):
            binomial_tree_american(100, 100, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_degenerate_probability_raises(self):
        # sigma=0.01, r=0.10, 10 steps -> p > 1; previously priced an ATM
        # call at 140 (worth more than the stock).
        with pytest.raises(ValueError, match="probability"):
            binomial_tree_american(100, 100, 1.0, 0.10, 0.01,
                                   OptionType.CALL, steps=10)

    def test_dividends_exceeding_spot_raise(self):
        with pytest.raises(ValueError, match="dividends"):
            binomial_tree_american(10, 10, 1.0, 0.05, 0.2, OptionType.CALL,
                                   dividends=[(0.5, 50.0)])


class TestEarlyExerciseBoundary:
    """Previously returned the first bisection midpoint everywhere."""

    def test_put_boundary_shape(self):
        boundary = early_exercise_boundary(
            100, 1.0, 0.05, 0.20, OptionType.PUT, steps=5, tree_steps=60,
        )
        assert boundary, "put with r>0 must have an exercise boundary"
        levels = {round(s, 1) for _, s in boundary}
        assert len(levels) > 1, "boundary must vary over time"
        for t, s in boundary:
            assert 50 < s < 100, f"put boundary {s} outside sane range at t={t}"
        # Boundary rises toward the strike as expiry approaches.
        by_time = sorted(boundary)  # ascending time-to-expiry
        assert by_time[0][1] > by_time[-1][1]

    def test_call_without_yield_has_no_boundary(self):
        boundary = early_exercise_boundary(
            100, 1.0, 0.05, 0.20, OptionType.CALL, steps=4, tree_steps=40,
        )
        assert boundary == []

    def test_call_with_yield_has_boundary_above_strike(self):
        boundary = early_exercise_boundary(
            100, 1.0, 0.02, 0.20, OptionType.CALL,
            steps=4, q=0.08, tree_steps=60,
        )
        assert boundary
        for _, s in boundary:
            assert s > 100


class TestIVSolverHonesty:
    def test_impossible_price_raises_not_clamps(self):
        # Price just under S but far above BS(sigma=5): previously
        # returned exactly 5.0 as a plausible-looking IV.
        with pytest.raises(IVSolverError):
            implied_volatility(
                price=99.999999, S=100, K=100, T=0.5, r=0.05,
                option_type=OptionType.CALL,
            )

    def test_round_trip_accuracy(self):
        for sigma in (0.10, 0.35, 0.80):
            price = black_scholes_price(100, 105, 0.4, 0.05, sigma, OptionType.CALL)
            iv = implied_volatility(price, 100, 105, 0.4, 0.05, OptionType.CALL)
            assert iv == pytest.approx(sigma, abs=1e-5)

    def test_tiny_vega_round_trip_stays_accurate(self):
        # 1-day 20%-ITM call: price-space-only convergence returned IV
        # errors ~1e-3; the vol-bracket criterion keeps it tight.
        sigma_true = 1.0
        S, K, T, r = 100, 80, 1 / 365, 0.05
        price = black_scholes_price(S, K, T, r, sigma_true, OptionType.CALL)
        iv = implied_volatility(price, S, K, T, r, OptionType.CALL)
        assert iv == pytest.approx(sigma_true, abs=1e-4)

    def test_newton_does_not_return_unmoved_initial_guess(self):
        # Deep ITM short-dated: every sigma reprices within tol, so Newton
        # previously "converged" to whatever guess it started with.
        S, K, T, r = 100, 50, 0.1, 0.05
        price = black_scholes_price(S, K, T, r, 0.30, OptionType.CALL)
        with pytest.raises(IVSolverError):
            newton_iv(price, S, K, T, r, OptionType.CALL, initial_guess=0.20)


class TestSurfaceLookupAndDedup:
    """Audit M10/M11: order-dependent smiles and O(n) lookups."""

    def _smile(self, forward=100.0):
        from derivatives_strategies.surface.builder import ExpirySmile, SmilePoint
        pts = [
            SmilePoint(math.log(k / forward), float(k),
                       0.20 + 0.001 * abs(k - 100), OptionType.CALL)
            for k in range(60, 161, 5)
        ]
        return ExpirySmile("2025-03-21", 60, forward, pts)

    def _linear_reference(self, smile, strike):
        """The original O(n) scan, kept as an oracle."""
        if not smile.points:
            return None
        if len(smile.points) == 1:
            return smile.points[0].iv
        log_m = math.log(strike / smile.forward)
        left_idx, right_idx = 0, len(smile.points) - 1
        for i, p in enumerate(smile.points):
            if p.log_moneyness <= log_m:
                left_idx = i
            if p.log_moneyness >= log_m:
                right_idx = i
                break
        left, right = smile.points[left_idx], smile.points[right_idx]
        if log_m <= left.log_moneyness:
            return left.iv
        if log_m >= right.log_moneyness:
            return right.iv
        if abs(right.log_moneyness - left.log_moneyness) < 1e-10:
            return left.iv
        w = ((log_m - left.log_moneyness)
             / (right.log_moneyness - left.log_moneyness))
        return left.iv + w * (right.iv - left.iv)

    def test_bisect_lookup_matches_linear_scan(self):
        smile = self._smile()
        probes = [30.0, 59.9, 60.0, 62.5, 100.0, 137.5, 160.0, 160.1, 500.0]
        probes += [float(k) for k in range(61, 160, 3)]
        for strike in probes:
            assert smile.get_iv(strike) == pytest.approx(
                self._linear_reference(smile, strike), abs=1e-15
            )

    def test_lookup_cache_tracks_appended_points(self):
        from derivatives_strategies.surface.builder import SmilePoint
        smile = self._smile()
        before = smile.get_iv(100.0)
        assert before is not None
        # Appending a point must invalidate the cached keys.
        smile.points.append(
            SmilePoint(math.log(200.0 / smile.forward), 200.0, 0.9, OptionType.CALL)
        )
        smile.points.sort(key=lambda p: p.log_moneyness)
        assert smile.get_iv(200.0) == pytest.approx(0.9)

    def test_smile_construction_is_order_independent(self):
        # Previously an exactly-ATM strike (both call and put survive the
        # prefer_otm filter) resolved to whichever appeared first in the chain.
        from derivatives_strategies.surface.builder import build_surface
        from derivatives_strategies.data.demo_provider import DemoProvider
        from derivatives_strategies.data.models import Chain

        provider = DemoProvider()
        chain = provider.get_chain("AAPL")
        expiry = chain.get_expiries()[1]
        atm = round(chain.spot.mid, 2)
        extra = [
            OptionQuote("AAPL", expiry, atm, OptionType.CALL,
                        3.00, 3.10, 3.05, 900, 5000, chain.as_of),
            OptionQuote("AAPL", expiry, atm, OptionType.PUT,
                        2.50, 2.80, 2.65, 900, 5000, chain.as_of),
        ]
        options = list(chain.options) + extra
        forward = Chain("AAPL", chain.spot, options, chain.as_of)
        reversed_chain = Chain("AAPL", chain.spot, list(reversed(options)), chain.as_of)

        s1 = build_surface(forward, 0.0525, provider.get_as_of_date())
        s2 = build_surface(reversed_chain, 0.0525, provider.get_as_of_date())

        assert s1.get_expiries() == s2.get_expiries()
        for exp in s1.get_expiries():
            a = [(p.strike, p.iv, p.option_type) for p in s1.smiles[exp].points]
            b = [(p.strike, p.iv, p.option_type) for p in s2.smiles[exp].points]
            assert a == b
        # Tightest spread wins the contested ATM strike (call: 0.10 vs 0.30).
        atm_pts = [p for p in s1.smiles[expiry].points if abs(p.strike - atm) < 1e-9]
        assert atm_pts and atm_pts[0].option_type == OptionType.CALL

    def test_year_fraction_is_memoized_and_correct(self):
        from derivatives_strategies.surface.builder import VolSurface
        surface = VolSurface(symbol="AAPL", spot=100.0, as_of="2025-01-15",
                             rate=0.05, dividend_yield=0.0)
        # 2025-01-15 -> 2025-03-16 is 60 days
        assert surface.year_fraction("2025-03-16") == pytest.approx(60 / 365.0)
        assert surface.year_fraction("2025-03-16") == pytest.approx(60 / 365.0)
        assert "2025-03-16" in surface._tenor_cache

    def test_validate_surface_flags_non_convex_smile(self):
        from derivatives_strategies.surface.builder import (
            ExpirySmile, SmilePoint, VolSurface, validate_surface,
        )
        surface = VolSurface(symbol="X", spot=100.0, as_of="2025-01-15",
                             rate=0.05, dividend_yield=0.0)
        # Sharply concave: slope drops far more than the 0.5 tolerance.
        pts = [
            SmilePoint(-0.2, 80.0, 0.20, OptionType.PUT),
            SmilePoint(0.0, 100.0, 0.60, OptionType.CALL),
            SmilePoint(0.2, 120.0, 0.21, OptionType.CALL),
        ]
        surface.smiles["2025-03-21"] = ExpirySmile("2025-03-21", 65, 100.0, pts)
        assert any("non-convex" in w for w in validate_surface(surface))


class TestGreeksHygiene:
    def test_zero_rho_preserved_in_position_greeks(self):
        scaled = position_greeks(
            Greeks(delta=0.5, gamma=0.01, theta=-0.05, vega=0.2, rho=0.0),
            quantity=10,
        )
        assert scaled.rho == 0.0

    def test_dividends_exceeding_spot_raise_in_pricing(self):
        with pytest.raises(ValueError, match="dividends"):
            option_price(10, 10, 1.0, 0.05, 0.2, OptionType.CALL,
                         dividends=[(0.5, 50.0)])


class TestDividendRiskWindows:
    def _quote(self, bid, ask, strike=90.0):
        return OptionQuote(
            symbol="AAPL", expiry="2025-03-21", strike=strike,
            option_type=OptionType.CALL, bid=bid, ask=ask,
            last=(bid + ask) / 2, volume=100, open_interest=500,
            timestamp="2025-01-15T15:00:00",
        )

    def test_far_ex_date_is_not_at_risk(self):
        # Extrinsic < div PV but ex-date 40 days out (window 7): previously
        # flagged HIGH risk.
        result = early_assignment_risk(
            spot=100.0, option_price=10.05, strike=90.0,
            option_type=OptionType.CALL,
            as_of="2025-01-15", expiry="2025-03-21",
            dividend=DividendEvent(symbol="AAPL", ex_date="2025-02-24",
                                   amount=0.30),
            rate=0.05, window_days=7,
        )
        assert not result.at_risk
        assert "monitor" in result.message

    def test_imminent_ex_date_is_at_risk(self):
        result = early_assignment_risk(
            spot=100.0, option_price=10.05, strike=90.0,
            option_type=OptionType.CALL,
            as_of="2025-01-15", expiry="2025-03-21",
            dividend=DividendEvent(symbol="AAPL", ex_date="2025-01-18",
                                   amount=0.30),
            rate=0.05, window_days=7,
        )
        assert result.at_risk

    def test_no_roll_recommended_after_ex_date(self):
        # Previously recommended a roll for a dividend already paid.
        should_roll, reason = should_roll_before_dividend(
            current_quote=self._quote(10.4, 10.6),
            spot=100.0,
            dividend=DividendEvent(symbol="AAPL", ex_date="2025-01-12",
                                   amount=0.25),
            as_of="2025-01-15",
            rate=0.05,
        )
        assert not should_roll
        assert "passed" in reason
