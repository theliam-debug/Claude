"""
Tests for policy engine and gate evaluation.
"""


from derivatives_strategies.policy.engine import (
    PolicyEngine,
    Policy,
    create_default_policy,
)
from derivatives_strategies.policy.gates import (
    GateContext,
    LiquidityGate,
    EventGate,
    MarginGate,
    ConcentrationGate,
    DTEGate,
    GateStatus,
)
from derivatives_strategies.data.models import (
    OptionQuote,
    OptionType,
)


class TestLiquidityGate:
    """Test suite for LiquidityGate."""

    def test_passes_liquid_option(self):
        """Test that liquid options pass the gate."""
        gate = LiquidityGate(max_spread_pct=0.20, min_open_interest=100)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.80,
            ask=5.00,  # 4% spread
            last=4.90,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.PASS

    def test_blocks_wide_spread(self):
        """Test that wide spreads block."""
        gate = LiquidityGate(max_spread_pct=0.10, hard=True)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.00,
            ask=5.00,  # 22% spread
            last=4.50,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.BLOCK
        assert "spread" in result.message.lower()

    def test_blocks_low_open_interest(self):
        """Test that low OI blocks."""
        gate = LiquidityGate(min_open_interest=500, hard=True)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=50,  # Low OI
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.BLOCK
        assert "oi" in result.message.lower()


class TestEventGate:
    """Test suite for EventGate."""

    def test_blocks_during_earnings_blackout(self):
        """Test that trading is blocked during earnings blackout."""
        gate = EventGate(blackout_days_before=2, blackout_days_after=1, hard=True)

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-26",  # 2 days before earnings
            rate=0.05,
        )
        context.event_calendar = {
            "2025-01-28": ["TEST Earnings"],
        }

        result = gate.evaluate(context)
        assert result.status == GateStatus.BLOCK
        assert "earnings" in result.message.lower()

    def test_passes_outside_blackout(self):
        """Test that trading passes outside blackout window."""
        gate = EventGate(blackout_days_before=2, blackout_days_after=1, hard=True)

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-20",  # 8 days before earnings
            rate=0.05,
        )
        context.event_calendar = {
            "2025-01-28": ["TEST Earnings"],
        }

        result = gate.evaluate(context)
        assert result.status == GateStatus.PASS

    def test_passes_with_no_calendar(self):
        """Test that gate passes when no calendar is provided."""
        gate = EventGate(hard=True)

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.PASS


class TestMarginGate:
    """Test suite for MarginGate."""

    def test_passes_adequate_margin(self):
        """Test that adequate margin passes."""
        gate = MarginGate(max_margin_utilization=0.80, min_margin_buffer=0.20)

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            margin_used=50000.0,
            margin_available=50000.0,  # 50% utilization
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.PASS

    def test_blocks_high_utilization(self):
        """Test that high margin utilization blocks."""
        gate = MarginGate(max_margin_utilization=0.80, hard=True)

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            margin_used=90000.0,
            margin_available=10000.0,  # 90% utilization
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.BLOCK
        assert "utilization" in result.message.lower()


class TestConcentrationGate:
    """Test suite for ConcentrationGate."""

    def test_passes_small_position(self):
        """Test that small positions pass."""
        gate = ConcentrationGate(max_position_pct=0.10)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            portfolio_value=500000.0,  # Large portfolio
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.PASS

    def test_blocks_concentrated_position(self):
        """Test that concentrated positions block."""
        gate = ConcentrationGate(max_position_pct=0.05, hard=True)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            portfolio_value=50000.0,  # Small portfolio: 20% concentration
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.BLOCK


class TestDTEGate:
    """Test suite for DTEGate."""

    def test_passes_appropriate_dte(self):
        """Test that appropriate DTE passes."""
        gate = DTEGate(min_dte=7, max_dte=45, hard=False)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",  # ~37 days from Jan 15
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.PASS

    def test_warns_short_dte(self):
        """Test that short DTE warns (soft gate)."""
        gate = DTEGate(min_dte=14, max_dte=45, hard=False)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-01-24",  # 9 days from Jan 15
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        result = gate.evaluate(context)
        assert result.status == GateStatus.WARN
        assert "dte" in result.message.lower()


class TestPolicyEngine:
    """Test suite for PolicyEngine."""

    def test_evaluates_all_gates(self):
        """Test that engine evaluates all gates."""
        policy = create_default_policy()
        engine = PolicyEngine(policy)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            portfolio_value=100000.0,
            margin_used=20000.0,
            margin_available=30000.0,
        )

        results = engine.evaluate(context)

        # Should have results for each gate
        assert len(results) == len(policy.gates)

    def test_deterministic_evaluation(self):
        """Test that gate evaluation is deterministic."""
        policy = create_default_policy()
        engine = PolicyEngine(policy)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
            delta=0.30,
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            portfolio_value=100000.0,
        )

        # Evaluate multiple times
        results1 = engine.evaluate(context)
        results2 = engine.evaluate(context)

        # Results should be identical
        for r1, r2 in zip(results1, results2):
            assert r1.gate_name == r2.gate_name
            assert r1.status == r2.status
            assert r1.message == r2.message

    def test_is_blocked_with_hard_gate_failure(self):
        """Test blocking detection."""
        policy = Policy(
            name="test",
            version="1.0",
            gates=[
                LiquidityGate(max_spread_pct=0.01, hard=True),  # Will fail
            ],
        )
        engine = PolicyEngine(policy)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.50,
            ask=5.00,  # 10% spread
            last=4.75,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        results = engine.evaluate(context)
        assert engine.is_blocked(results)
        assert "LiquidityGate" in engine.get_blocking_gates(results)

    def test_warnings_collected(self):
        """Test warning message collection."""
        policy = Policy(
            name="test",
            version="1.0",
            gates=[
                DTEGate(min_dte=30, max_dte=60, hard=False),  # Will warn
            ],
        )
        engine = PolicyEngine(policy)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-01-31",  # 16 days
            strike=100.0,
            option_type=OptionType.CALL,
            bid=4.90,
            ask=5.00,
            last=4.95,
            volume=200,
            open_interest=1000,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=100.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
        )

        results = engine.evaluate(context)
        warnings = engine.get_warnings(results)

        assert len(warnings) > 0
        assert any("dte" in w.lower() for w in warnings)
