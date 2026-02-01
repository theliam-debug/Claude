"""
Tests for dividend gate and early assignment risk.
"""

import pytest
from datetime import date, timedelta

from derivatives_strategies.dividends.analysis import (
    early_assignment_risk,
    compute_dividend_pv,
    EarlyAssignmentResult,
)
from derivatives_strategies.data.models import (
    DividendEvent,
    OptionQuote,
    OptionType,
)
from derivatives_strategies.policy.gates import DividendGate, GateContext, GateStatus


class TestEarlyAssignmentRisk:
    """Test suite for early assignment risk analysis."""

    def test_deep_itm_call_with_tiny_extrinsic_triggers_risk(self):
        """
        Test that a deep ITM call with extrinsic < dividend PV
        triggers early assignment risk.
        """
        spot = 180.0
        strike = 160.0  # Deep ITM
        option_price = 20.50  # Intrinsic = 20, extrinsic = 0.50

        as_of = "2025-01-15"
        expiry = "2025-02-21"

        # Dividend of $0.75 ex-date Jan 20 (5 days away)
        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-01-20",
            amount=0.75,
        )

        result = early_assignment_risk(
            spot=spot,
            option_price=option_price,
            strike=strike,
            option_type=OptionType.CALL,
            as_of=as_of,
            expiry=expiry,
            dividend=dividend,
            rate=0.05,
        )

        assert result.at_risk is True
        assert result.intrinsic == 20.0
        assert result.extrinsic == 0.50
        assert result.days_to_ex == 5
        assert result.assignment_probability_estimate > 0.5

    def test_otm_call_no_risk(self):
        """Test that OTM calls have no early assignment risk."""
        spot = 100.0
        strike = 110.0  # OTM
        option_price = 2.00  # All extrinsic

        as_of = "2025-01-15"
        expiry = "2025-02-21"

        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-01-20",
            amount=0.50,
        )

        result = early_assignment_risk(
            spot=spot,
            option_price=option_price,
            strike=strike,
            option_type=OptionType.CALL,
            as_of=as_of,
            expiry=expiry,
            dividend=dividend,
            rate=0.05,
        )

        assert result.at_risk is False
        assert result.intrinsic == 0.0
        assert "not in-the-money" in result.message.lower()

    def test_no_dividend_no_risk(self):
        """Test that no dividend means no early assignment risk."""
        result = early_assignment_risk(
            spot=180.0,
            option_price=25.0,
            strike=160.0,
            option_type=OptionType.CALL,
            as_of="2025-01-15",
            expiry="2025-02-21",
            dividend=None,
            rate=0.05,
        )

        assert result.at_risk is False
        assert "no upcoming dividend" in result.message.lower()

    def test_dividend_after_expiry_no_risk(self):
        """Test that dividend after expiry has no risk."""
        as_of = "2025-01-15"
        expiry = "2025-01-24"  # Expiry before dividend

        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-02-01",  # After expiry
            amount=0.50,
        )

        result = early_assignment_risk(
            spot=180.0,
            option_price=22.0,
            strike=160.0,
            option_type=OptionType.CALL,
            as_of=as_of,
            expiry=expiry,
            dividend=dividend,
            rate=0.05,
        )

        assert result.at_risk is False
        assert "after option expiry" in result.message.lower()

    def test_itm_with_adequate_extrinsic_safe(self):
        """Test that ITM call with high extrinsic is safe."""
        spot = 110.0
        strike = 100.0  # ITM
        option_price = 15.0  # Intrinsic = 10, extrinsic = 5

        as_of = "2025-01-15"
        expiry = "2025-02-21"

        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-01-20",
            amount=0.25,  # Small dividend
        )

        result = early_assignment_risk(
            spot=spot,
            option_price=option_price,
            strike=strike,
            option_type=OptionType.CALL,
            as_of=as_of,
            expiry=expiry,
            dividend=dividend,
            rate=0.05,
        )

        # Extrinsic (5) >> dividend PV (~0.25), so safe
        assert result.at_risk is False
        assert result.extrinsic > result.dividend_pv

    def test_put_options_no_dividend_risk(self):
        """Test that puts don't have dividend-based early exercise risk."""
        result = early_assignment_risk(
            spot=100.0,
            option_price=15.0,
            strike=110.0,  # ITM put
            option_type=OptionType.PUT,
            as_of="2025-01-15",
            expiry="2025-02-21",
            dividend=DividendEvent(symbol="TEST", ex_date="2025-01-20", amount=1.0),
            rate=0.05,
        )

        assert result.at_risk is False
        assert "only applies to calls" in result.message.lower()


class TestDividendPV:
    """Test suite for dividend present value calculation."""

    def test_pv_positive_days_to_ex(self):
        """Test PV calculation with positive time to ex-date."""
        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-01-20",
            amount=1.00,
        )

        pv = compute_dividend_pv(dividend, "2025-01-15", rate=0.05)

        # 5 days to ex, so slight discount
        assert pv < 1.00
        assert pv > 0.99

    def test_pv_zero_for_past_dividend(self):
        """Test PV is zero for past dividends."""
        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-01-10",
            amount=1.00,
        )

        pv = compute_dividend_pv(dividend, "2025-01-15", rate=0.05)

        assert pv == 0.0

    def test_pv_longer_term(self):
        """Test PV for longer-term dividend."""
        dividend = DividendEvent(
            symbol="TEST",
            ex_date="2025-04-15",
            amount=1.00,
        )

        pv = compute_dividend_pv(dividend, "2025-01-15", rate=0.05)

        # ~90 days, ~1.2% discount
        assert 0.98 < pv < 0.995


class TestDividendGate:
    """Test suite for the DividendGate policy gate."""

    def test_gate_blocks_high_risk_position(self):
        """Test that gate blocks positions with high early assignment risk."""
        gate = DividendGate(days_before_ex=5, hard=True)

        # Deep ITM call with tiny extrinsic
        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=160.0,
            option_type=OptionType.CALL,
            bid=20.40,
            ask=20.60,
            last=20.50,
            volume=100,
            open_interest=500,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=180.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            dividends=[
                DividendEvent(symbol="TEST", ex_date="2025-01-20", amount=0.75)
            ],
        )

        result = gate.evaluate(context)

        assert result.status == GateStatus.BLOCK
        assert "early assignment risk" in result.message.lower()

    def test_gate_passes_safe_position(self):
        """Test that gate passes positions with adequate protection."""
        gate = DividendGate(days_before_ex=5, hard=True)

        # OTM call
        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=190.0,  # OTM
            option_type=OptionType.CALL,
            bid=2.40,
            ask=2.60,
            last=2.50,
            volume=100,
            open_interest=500,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=180.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            dividends=[
                DividendEvent(symbol="TEST", ex_date="2025-01-20", amount=0.25)
            ],
        )

        result = gate.evaluate(context)

        assert result.status == GateStatus.PASS

    def test_gate_passes_when_no_dividend(self):
        """Test that gate passes when no dividend is present."""
        gate = DividendGate(days_before_ex=5, hard=True)

        quote = OptionQuote(
            symbol="TEST",
            expiry="2025-02-21",
            strike=160.0,
            option_type=OptionType.CALL,
            bid=20.40,
            ask=20.60,
            last=20.50,
            volume=100,
            open_interest=500,
            timestamp="2025-01-15T10:00:00Z",
        )

        context = GateContext(
            symbol="TEST",
            spot=180.0,
            as_of="2025-01-15",
            rate=0.05,
            target_quote=quote,
            dividends=[],  # No dividends
        )

        result = gate.evaluate(context)

        assert result.status == GateStatus.PASS
        assert "no upcoming" in result.message.lower()
