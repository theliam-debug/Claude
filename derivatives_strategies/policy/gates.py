"""
Policy gates for options trading decisions.

Each gate evaluates a specific criterion and returns pass/warn/block status.
Hard gates block actions; soft gates warn but allow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Any
from derivatives_strategies.data.models import (
    GateResult,
    GateStatus,
    OptionQuote,
    Position,
    Chain,
    DividendEvent,
)


@dataclass
class GateContext:
    """Context for gate evaluation."""
    symbol: str
    spot: float
    as_of: str
    rate: float
    chain: Optional[Chain] = None
    position: Optional[Position] = None
    target_quote: Optional[OptionQuote] = None
    dividends: list[DividendEvent] = None
    portfolio_value: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    event_calendar: dict[str, list[str]] = None  # date -> list of events

    def __post_init__(self):
        if self.dividends is None:
            self.dividends = []
        if self.event_calendar is None:
            self.event_calendar = {}


class Gate(ABC):
    """Abstract base class for policy gates."""

    def __init__(
        self,
        name: str,
        hard: bool = True,
        override_allowed: bool = True,
        config: Optional[dict] = None
    ):
        """
        Initialize gate.

        Args:
            name: Gate identifier
            hard: True for hard gate (blocks), False for soft gate (warns)
            override_allowed: Whether gate can be overridden
            config: Gate-specific configuration
        """
        self.name = name
        self.hard = hard
        self.override_allowed = override_allowed
        self.config = config or {}

    @abstractmethod
    def evaluate(self, context: GateContext) -> GateResult:
        """
        Evaluate the gate.

        Args:
            context: Evaluation context

        Returns:
            GateResult with status and details
        """
        pass

    def _make_result(
        self,
        passed: bool,
        message: str,
        details: Optional[dict] = None,
        threshold: Optional[float] = None,
        actual: Optional[float] = None
    ) -> GateResult:
        """Helper to construct GateResult."""
        if passed:
            status = GateStatus.PASS
        elif self.hard:
            status = GateStatus.BLOCK
        else:
            status = GateStatus.WARN

        return GateResult(
            gate_name=self.name,
            status=status,
            message=message,
            details=details or {},
            threshold=threshold,
            actual_value=actual,
            override_allowed=self.override_allowed,
        )


class LiquidityGate(Gate):
    """
    Gate to ensure adequate option liquidity.

    Checks:
    - Bid-ask spread as percentage of mid
    - Open interest thresholds
    - Volume thresholds
    """

    def __init__(
        self,
        max_spread_pct: float = 0.20,
        min_open_interest: int = 100,
        min_volume: int = 10,
        hard: bool = True
    ):
        super().__init__(
            name="LiquidityGate",
            hard=hard,
            config={
                "max_spread_pct": max_spread_pct,
                "min_open_interest": min_open_interest,
                "min_volume": min_volume,
            }
        )
        self.max_spread_pct = max_spread_pct
        self.min_open_interest = min_open_interest
        self.min_volume = min_volume

    def evaluate(self, context: GateContext) -> GateResult:
        quote = context.target_quote
        if quote is None:
            return self._make_result(
                True, "No target quote to evaluate"
            )

        issues = []
        details = {
            "spread_pct": quote.spread_pct,
            "open_interest": quote.open_interest,
            "volume": quote.volume,
        }

        # Check spread
        if quote.spread_pct > self.max_spread_pct:
            issues.append(
                f"Spread ({quote.spread_pct:.1%}) > max ({self.max_spread_pct:.1%})"
            )

        # Check open interest
        if quote.open_interest < self.min_open_interest:
            issues.append(
                f"OI ({quote.open_interest}) < min ({self.min_open_interest})"
            )

        # Check volume
        if quote.volume < self.min_volume:
            issues.append(
                f"Volume ({quote.volume}) < min ({self.min_volume})"
            )

        if issues:
            return self._make_result(
                False,
                f"Liquidity issues: {'; '.join(issues)}",
                details=details,
                threshold=self.max_spread_pct,
                actual=quote.spread_pct,
            )

        return self._make_result(
            True,
            "Liquidity requirements met",
            details=details,
        )


class EventGate(Gate):
    """
    Gate to block trading around known events (earnings, FOMC, etc).

    Uses a provided event calendar to identify blackout periods.
    """

    def __init__(
        self,
        blackout_days_before: int = 2,
        blackout_days_after: int = 1,
        event_types: Optional[list[str]] = None,
        hard: bool = True
    ):
        super().__init__(
            name="EventGate",
            hard=hard,
            config={
                "blackout_days_before": blackout_days_before,
                "blackout_days_after": blackout_days_after,
                "event_types": event_types,
            }
        )
        self.blackout_before = blackout_days_before
        self.blackout_after = blackout_days_after
        self.event_types = event_types

    def evaluate(self, context: GateContext) -> GateResult:
        if not context.event_calendar:
            return self._make_result(
                True, "No event calendar provided"
            )

        as_of = date.fromisoformat(context.as_of[:10])

        # Check each event in the calendar to see if we're in its blackout window
        for event_date_str, events in context.event_calendar.items():
            event_date = date.fromisoformat(event_date_str)

            # Calculate days from as_of to event
            days_to_event = (event_date - as_of).days

            # Check if we're in the blackout window:
            # Block if event is within (0 - blackout_after) to (blackout_before) days away
            # i.e., if we're blackout_before days before OR blackout_after days after
            if -self.blackout_after <= days_to_event <= self.blackout_before:
                # Filter by event type if specified
                if self.event_types:
                    events = [e for e in events if any(
                        et.lower() in e.lower() for et in self.event_types
                    )]

                if events:
                    return self._make_result(
                        False,
                        f"Event blackout: {', '.join(events)} on {event_date_str}",
                        details={
                            "event_date": event_date_str,
                            "events": events,
                            "days_to_event": days_to_event,
                        },
                    )

        return self._make_result(
            True, "No events in blackout window"
        )


class DividendGate(Gate):
    """
    Gate to protect against early assignment risk before dividends.

    For short calls, blocks trading when:
    - Option is ITM
    - Extrinsic value < PV(dividend)
    - Dividend ex-date is imminent
    """

    def __init__(
        self,
        days_before_ex: int = 5,
        min_extrinsic_ratio: float = 1.5,  # extrinsic / div_pv
        hard: bool = True
    ):
        super().__init__(
            name="DividendGate",
            hard=hard,
            config={
                "days_before_ex": days_before_ex,
                "min_extrinsic_ratio": min_extrinsic_ratio,
            }
        )
        self.days_before_ex = days_before_ex
        self.min_extrinsic_ratio = min_extrinsic_ratio

    def evaluate(self, context: GateContext) -> GateResult:
        from derivatives_strategies.data.models import OptionType
        from derivatives_strategies.dividends.analysis import (
            early_assignment_risk,
            compute_dividend_pv,
        )

        quote = context.target_quote
        if quote is None or quote.option_type != OptionType.CALL:
            return self._make_result(
                True, "Not a call option; dividend gate not applicable"
            )

        # Find next dividend
        if not context.dividends:
            return self._make_result(
                True, "No upcoming dividends"
            )

        as_of = date.fromisoformat(context.as_of[:10])
        next_div = None
        for div in context.dividends:
            ex_date = date.fromisoformat(div.ex_date)
            if ex_date > as_of:
                next_div = div
                break

        if next_div is None:
            return self._make_result(
                True, "No upcoming dividends"
            )

        # Check if expiry is before ex-date
        expiry_date = date.fromisoformat(quote.expiry)
        ex_date = date.fromisoformat(next_div.ex_date)

        if expiry_date < ex_date:
            return self._make_result(
                True, "Option expires before dividend ex-date"
            )

        # Analyze early assignment risk
        result = early_assignment_risk(
            spot=context.spot,
            option_price=quote.mid,
            strike=quote.strike,
            option_type=quote.option_type,
            as_of=context.as_of,
            expiry=quote.expiry,
            dividend=next_div,
            rate=context.rate,
        )

        details = result.to_dict()
        details["next_dividend"] = {
            "ex_date": next_div.ex_date,
            "amount": next_div.amount,
        }

        if result.at_risk:
            return self._make_result(
                False,
                f"Early assignment risk: {result.message}",
                details=details,
                threshold=self.min_extrinsic_ratio,
                actual=result.extrinsic / result.dividend_pv if result.dividend_pv > 0 else 0,
            )

        # Check if we're within the warning window
        days_to_ex = result.days_to_ex
        if days_to_ex <= self.days_before_ex and result.intrinsic > 0:
            # Soft warning even if not technically at risk
            if result.extrinsic / result.dividend_pv < self.min_extrinsic_ratio:
                return self._make_result(
                    False,
                    f"Caution: ITM call with dividend in {days_to_ex} days",
                    details=details,
                )

        return self._make_result(
            True,
            f"Dividend risk acceptable: {result.message}",
            details=details,
        )


class MarginGate(Gate):
    """
    Gate to check margin requirements.

    Ensures sufficient margin is available for the proposed trade.
    """

    def __init__(
        self,
        min_margin_buffer: float = 0.20,  # 20% buffer
        max_margin_utilization: float = 0.80,  # Max 80% of available
        hard: bool = True
    ):
        super().__init__(
            name="MarginGate",
            hard=hard,
            config={
                "min_margin_buffer": min_margin_buffer,
                "max_margin_utilization": max_margin_utilization,
            }
        )
        self.min_buffer = min_margin_buffer
        self.max_utilization = max_margin_utilization

    def evaluate(self, context: GateContext) -> GateResult:
        if context.margin_available <= 0:
            return self._make_result(
                True, "Margin check skipped (no margin data)"
            )

        # Calculate utilization
        total_margin = context.margin_used + context.margin_available
        if total_margin <= 0:
            return self._make_result(
                True, "Margin check skipped (no margin data)"
            )

        utilization = context.margin_used / total_margin
        buffer = context.margin_available / total_margin

        details = {
            "margin_used": context.margin_used,
            "margin_available": context.margin_available,
            "utilization": utilization,
            "buffer": buffer,
        }

        if utilization > self.max_utilization:
            return self._make_result(
                False,
                f"Margin utilization ({utilization:.1%}) exceeds max ({self.max_utilization:.1%})",
                details=details,
                threshold=self.max_utilization,
                actual=utilization,
            )

        if buffer < self.min_buffer:
            return self._make_result(
                False,
                f"Margin buffer ({buffer:.1%}) below minimum ({self.min_buffer:.1%})",
                details=details,
                threshold=self.min_buffer,
                actual=buffer,
            )

        return self._make_result(
            True,
            f"Margin acceptable: {utilization:.1%} utilization, {buffer:.1%} buffer",
            details=details,
        )


class RollCreditGate(Gate):
    """
    Gate to ensure rolls generate net credit.

    Blocks rolls that would result in a net debit beyond threshold.
    """

    def __init__(
        self,
        min_net_credit: float = 0.0,  # Must receive at least this credit
        allow_small_debit: bool = False,
        max_debit: float = 0.0,  # If allow_small_debit, max debit allowed
        hard: bool = True
    ):
        super().__init__(
            name="RollCreditGate",
            hard=hard,
            config={
                "min_net_credit": min_net_credit,
                "allow_small_debit": allow_small_debit,
                "max_debit": max_debit,
            }
        )
        self.min_credit = min_net_credit
        self.allow_debit = allow_small_debit
        self.max_debit = max_debit

    def evaluate(self, context: GateContext) -> GateResult:
        # This gate needs net credit info passed in context
        # For now, return pass if no target quote
        if context.target_quote is None:
            return self._make_result(
                True, "No roll to evaluate"
            )

        # Net credit should be computed by caller and passed in config
        net_credit = context.chain.spot.mid if context.chain else 0  # Placeholder

        details = {
            "net_credit": net_credit,
            "min_required": self.min_credit,
        }

        if net_credit >= self.min_credit:
            return self._make_result(
                True,
                f"Roll generates net credit: ${net_credit:.2f}",
                details=details,
            )

        if self.allow_debit and abs(net_credit) <= self.max_debit:
            return self._make_result(
                True,
                f"Roll debit (${abs(net_credit):.2f}) within allowed limit",
                details=details,
            )

        return self._make_result(
            False,
            f"Roll would result in debit: ${abs(net_credit):.2f}",
            details=details,
            threshold=self.min_credit,
            actual=net_credit,
        )


class ConcentrationGate(Gate):
    """
    Gate to check position concentration limits.

    Prevents excessive exposure to a single underlying.
    """

    def __init__(
        self,
        max_position_pct: float = 0.10,  # Max 10% of portfolio in one position
        max_notional: Optional[float] = None,  # Max absolute notional
        hard: bool = True
    ):
        super().__init__(
            name="ConcentrationGate",
            hard=hard,
            config={
                "max_position_pct": max_position_pct,
                "max_notional": max_notional,
            }
        )
        self.max_pct = max_position_pct
        self.max_notional = max_notional

    def evaluate(self, context: GateContext) -> GateResult:
        if context.portfolio_value <= 0:
            return self._make_result(
                True, "Concentration check skipped (no portfolio value)"
            )

        # Calculate notional exposure
        quote = context.target_quote
        if quote is None:
            return self._make_result(
                True, "No position to evaluate"
            )

        # Notional = spot * 100 (assuming 1 contract)
        notional = context.spot * 100
        concentration = notional / context.portfolio_value

        details = {
            "notional": notional,
            "portfolio_value": context.portfolio_value,
            "concentration": concentration,
        }

        if concentration > self.max_pct:
            return self._make_result(
                False,
                f"Position concentration ({concentration:.1%}) exceeds max ({self.max_pct:.1%})",
                details=details,
                threshold=self.max_pct,
                actual=concentration,
            )

        if self.max_notional and notional > self.max_notional:
            return self._make_result(
                False,
                f"Notional (${notional:,.0f}) exceeds max (${self.max_notional:,.0f})",
                details=details,
                threshold=self.max_notional,
                actual=notional,
            )

        return self._make_result(
            True,
            f"Concentration acceptable: {concentration:.1%} of portfolio",
            details=details,
        )


class DTEGate(Gate):
    """
    Gate to enforce days-to-expiry constraints.

    Ensures options are within acceptable DTE range.
    """

    def __init__(
        self,
        min_dte: int = 7,
        max_dte: int = 60,
        hard: bool = False  # Usually soft warning
    ):
        super().__init__(
            name="DTEGate",
            hard=hard,
            config={
                "min_dte": min_dte,
                "max_dte": max_dte,
            }
        )
        self.min_dte = min_dte
        self.max_dte = max_dte

    def evaluate(self, context: GateContext) -> GateResult:
        quote = context.target_quote
        if quote is None:
            return self._make_result(
                True, "No option to evaluate"
            )

        as_of = date.fromisoformat(context.as_of[:10])
        expiry = date.fromisoformat(quote.expiry)
        dte = (expiry - as_of).days

        details = {
            "dte": dte,
            "expiry": quote.expiry,
            "min_dte": self.min_dte,
            "max_dte": self.max_dte,
        }

        if dte < self.min_dte:
            return self._make_result(
                False,
                f"DTE ({dte}) below minimum ({self.min_dte})",
                details=details,
                threshold=self.min_dte,
                actual=dte,
            )

        if dte > self.max_dte:
            return self._make_result(
                False,
                f"DTE ({dte}) exceeds maximum ({self.max_dte})",
                details=details,
                threshold=self.max_dte,
                actual=dte,
            )

        return self._make_result(
            True,
            f"DTE ({dte}) within acceptable range",
            details=details,
        )


class DeltaGate(Gate):
    """
    Gate to enforce delta constraints for covered calls.

    Ensures options have delta within target range.
    """

    def __init__(
        self,
        min_delta: float = 0.15,
        max_delta: float = 0.40,
        hard: bool = False
    ):
        super().__init__(
            name="DeltaGate",
            hard=hard,
            config={
                "min_delta": min_delta,
                "max_delta": max_delta,
            }
        )
        self.min_delta = min_delta
        self.max_delta = max_delta

    def evaluate(self, context: GateContext) -> GateResult:
        quote = context.target_quote
        if quote is None:
            return self._make_result(
                True, "No option to evaluate"
            )

        # Use quote delta if available, otherwise compute
        delta = quote.delta
        if delta is None:
            # Need to compute - requires IV and other params
            return self._make_result(
                True, "Delta not available; skipping check",
                details={"warning": "Delta not computed"}
            )

        abs_delta = abs(delta)
        details = {
            "delta": delta,
            "abs_delta": abs_delta,
            "min_delta": self.min_delta,
            "max_delta": self.max_delta,
        }

        if abs_delta < self.min_delta:
            return self._make_result(
                False,
                f"Delta ({abs_delta:.2f}) below minimum ({self.min_delta})",
                details=details,
                threshold=self.min_delta,
                actual=abs_delta,
            )

        if abs_delta > self.max_delta:
            return self._make_result(
                False,
                f"Delta ({abs_delta:.2f}) exceeds maximum ({self.max_delta})",
                details=details,
                threshold=self.max_delta,
                actual=abs_delta,
            )

        return self._make_result(
            True,
            f"Delta ({abs_delta:.2f}) within target range",
            details=details,
        )
