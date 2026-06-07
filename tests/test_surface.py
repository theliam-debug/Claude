"""
Tests for volatility surface building and interpolation.
"""


from derivatives_strategies.surface.builder import (
    build_surface,
    ExpirySmile,
    SmilePoint,
    VolSurface,
    validate_surface,
)
from derivatives_strategies.data.models import (
    Chain,
    SpotQuote,
    OptionQuote,
    OptionType,
)


class TestExpirySmile:
    """Test suite for expiry smile interpolation."""

    def test_single_point_returns_constant(self):
        """Test that single point smile returns constant IV."""
        smile = ExpirySmile(
            expiry="2025-02-21",
            days_to_expiry=30,
            forward=100.0,
            points=[
                SmilePoint(log_moneyness=0.0, strike=100.0, iv=0.20, option_type=OptionType.CALL),
            ],
        )

        assert smile.get_iv(90.0) == 0.20
        assert smile.get_iv(100.0) == 0.20
        assert smile.get_iv(110.0) == 0.20

    def test_linear_interpolation(self):
        """Test linear interpolation between points."""
        smile = ExpirySmile(
            expiry="2025-02-21",
            days_to_expiry=30,
            forward=100.0,
            points=[
                SmilePoint(log_moneyness=-0.10, strike=90.48, iv=0.25, option_type=OptionType.PUT),
                SmilePoint(log_moneyness=0.0, strike=100.0, iv=0.20, option_type=OptionType.CALL),
                SmilePoint(log_moneyness=0.10, strike=110.52, iv=0.22, option_type=OptionType.CALL),
            ],
        )

        # At the points
        assert abs(smile.get_iv(90.48) - 0.25) < 0.01
        assert abs(smile.get_iv(100.0) - 0.20) < 0.01
        assert abs(smile.get_iv(110.52) - 0.22) < 0.01

        # ATM should be ~0.20
        atm_iv = smile.atm_iv()
        assert abs(atm_iv - 0.20) < 0.01

    def test_extrapolation_flat(self):
        """Test that extrapolation is flat beyond bounds."""
        smile = ExpirySmile(
            expiry="2025-02-21",
            days_to_expiry=30,
            forward=100.0,
            points=[
                SmilePoint(log_moneyness=-0.05, strike=95.12, iv=0.22, option_type=OptionType.PUT),
                SmilePoint(log_moneyness=0.05, strike=105.13, iv=0.21, option_type=OptionType.CALL),
            ],
        )

        # Far left extrapolation
        assert smile.get_iv(70.0) == 0.22

        # Far right extrapolation
        assert smile.get_iv(150.0) == 0.21

    def test_monotonic_smile_interpolation(self):
        """Test that interpolation preserves monotonicity within segments."""
        smile = ExpirySmile(
            expiry="2025-02-21",
            days_to_expiry=30,
            forward=100.0,
            points=[
                SmilePoint(log_moneyness=-0.20, strike=81.87, iv=0.30, option_type=OptionType.PUT),
                SmilePoint(log_moneyness=-0.10, strike=90.48, iv=0.25, option_type=OptionType.PUT),
                SmilePoint(log_moneyness=0.0, strike=100.0, iv=0.20, option_type=OptionType.CALL),
                SmilePoint(log_moneyness=0.10, strike=110.52, iv=0.21, option_type=OptionType.CALL),
                SmilePoint(log_moneyness=0.20, strike=122.14, iv=0.23, option_type=OptionType.CALL),
            ],
        )

        # Generate points and check monotonicity in left wing
        left_ivs = [smile.get_iv(strike) for strike in [82, 85, 88, 91]]
        for i in range(len(left_ivs) - 1):
            assert left_ivs[i] >= left_ivs[i + 1], "Left wing should be decreasing"


class TestVolSurface:
    """Test suite for complete volatility surface."""

    def create_test_surface(self) -> VolSurface:
        """Create a test surface with multiple expiries."""
        surface = VolSurface(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            dividend_yield=0.0,
        )

        # Add two expiries
        surface.smiles["2025-02-21"] = ExpirySmile(
            expiry="2025-02-21",
            days_to_expiry=37,
            forward=100.0,
            points=[
                SmilePoint(log_moneyness=-0.10, strike=90.48, iv=0.25, option_type=OptionType.PUT),
                SmilePoint(log_moneyness=0.0, strike=100.0, iv=0.20, option_type=OptionType.CALL),
                SmilePoint(log_moneyness=0.10, strike=110.52, iv=0.22, option_type=OptionType.CALL),
            ],
        )

        surface.smiles["2025-03-21"] = ExpirySmile(
            expiry="2025-03-21",
            days_to_expiry=65,
            forward=100.0,
            points=[
                SmilePoint(log_moneyness=-0.10, strike=90.48, iv=0.24, option_type=OptionType.PUT),
                SmilePoint(log_moneyness=0.0, strike=100.0, iv=0.19, option_type=OptionType.CALL),
                SmilePoint(log_moneyness=0.10, strike=110.52, iv=0.21, option_type=OptionType.CALL),
            ],
        )

        return surface

    def test_get_iv_existing_expiry(self):
        """Test IV retrieval for existing expiry."""
        surface = self.create_test_surface()

        iv = surface.get_iv("2025-02-21", 100.0)
        assert abs(iv - 0.20) < 0.01

    def test_get_iv_time_interpolation(self):
        """Test IV retrieval with time interpolation."""
        surface = self.create_test_surface()

        # Date between the two expiries
        iv = surface.get_iv("2025-03-07", 100.0)

        # Should be between the two ATM vols (0.20 and 0.19)
        assert 0.19 < iv < 0.20

    def test_get_delta_returns_value(self):
        """Test delta calculation from surface."""
        surface = self.create_test_surface()

        delta = surface.get_delta("2025-02-21", 100.0, OptionType.CALL)

        # ATM call delta should be around 0.5
        assert 0.45 < delta < 0.55

    def test_get_greeks_returns_all(self):
        """Test Greeks calculation from surface."""
        surface = self.create_test_surface()

        greeks = surface.get_greeks("2025-02-21", 100.0, OptionType.CALL)

        assert greeks is not None
        assert 0.45 < greeks.delta < 0.55
        assert greeks.gamma > 0
        assert greeks.theta < 0  # Time decay
        assert greeks.vega > 0

    def test_atm_term_structure(self):
        """Test ATM term structure extraction."""
        surface = self.create_test_surface()

        term = surface.get_atm_term_structure()

        assert len(term) == 2
        assert term[0][0] == "2025-02-21"
        assert term[1][0] == "2025-03-21"
        assert abs(term[0][2] - 0.20) < 0.01
        assert abs(term[1][2] - 0.19) < 0.01

    def test_surface_validation(self):
        """Test surface validation."""
        surface = self.create_test_surface()

        warnings = validate_surface(surface)

        # Clean surface should have no critical warnings
        assert len(warnings) == 0 or all(
            "very" not in w.lower() for w in warnings
        )


class TestSurfaceBuilder:
    """Test suite for surface building from chain."""

    def create_test_chain(self) -> Chain:
        """Create a test option chain."""
        spot = SpotQuote(
            symbol="TEST",
            bid=99.95,
            ask=100.05,
            last=100.0,
            timestamp="2025-01-15T10:00:00Z",
        )

        options = []

        # Add options for two expiries
        for expiry in ["2025-02-21", "2025-03-21"]:
            for strike in [90.0, 95.0, 100.0, 105.0, 110.0]:
                # Calls
                options.append(OptionQuote(
                    symbol="TEST",
                    expiry=expiry,
                    strike=strike,
                    option_type=OptionType.CALL,
                    bid=max(0.01, 10.0 - abs(strike - 100) / 5),
                    ask=max(0.05, 10.5 - abs(strike - 100) / 5),
                    last=max(0.03, 10.2 - abs(strike - 100) / 5),
                    volume=100,
                    open_interest=500,
                    timestamp="2025-01-15T10:00:00Z",
                ))

                # Puts
                options.append(OptionQuote(
                    symbol="TEST",
                    expiry=expiry,
                    strike=strike,
                    option_type=OptionType.PUT,
                    bid=max(0.01, 10.0 - abs(strike - 100) / 5),
                    ask=max(0.05, 10.5 - abs(strike - 100) / 5),
                    last=max(0.03, 10.2 - abs(strike - 100) / 5),
                    volume=100,
                    open_interest=500,
                    timestamp="2025-01-15T10:00:00Z",
                ))

        return Chain(
            symbol="TEST",
            spot=spot,
            options=options,
            as_of="2025-01-15T10:00:00Z",
        )

    def test_build_surface_creates_smiles(self):
        """Test that surface builder creates smiles for each expiry."""
        chain = self.create_test_chain()

        surface = build_surface(chain, rate=0.05, as_of="2025-01-15")

        assert surface.is_valid()
        assert len(surface.smiles) >= 1

    def test_build_surface_filters_illiquid(self):
        """Test that surface builder filters illiquid options."""
        chain = self.create_test_chain()

        # Build with strict liquidity requirements
        surface = build_surface(
            chain,
            rate=0.05,
            as_of="2025-01-15",
            max_spread_pct=0.01,  # Very tight
        )

        # Should have fewer points due to filtering
        total_points = sum(len(s.points) for s in surface.smiles.values())
        assert total_points < 10  # Most filtered out

    def test_surface_ivs_non_negative(self):
        """Test that all IVs are non-negative."""
        chain = self.create_test_chain()

        surface = build_surface(chain, rate=0.05, as_of="2025-01-15")

        for smile in surface.smiles.values():
            for point in smile.points:
                assert point.iv >= 0, f"Negative IV found: {point.iv}"

    def test_surface_deterministic(self):
        """Test that surface building is deterministic."""
        chain = self.create_test_chain()

        surface1 = build_surface(chain, rate=0.05, as_of="2025-01-15")
        surface2 = build_surface(chain, rate=0.05, as_of="2025-01-15")

        for expiry in surface1.get_expiries():
            assert expiry in surface2.smiles

            smile1 = surface1.smiles[expiry]
            smile2 = surface2.smiles[expiry]

            assert len(smile1.points) == len(smile2.points)

            for p1, p2 in zip(smile1.points, smile2.points):
                assert p1.strike == p2.strike
                assert abs(p1.iv - p2.iv) < 1e-10
