"""
Margin model hooks for Reg-T approximation and portfolio margin stub.

Note: These are approximations for analysis purposes only.
Actual margin requirements are determined by your broker and may differ.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from derivatives_strategies.data.models import (
    Position,
    OptionQuote,
    OptionType,
)


@dataclass
class MarginRequirement:
    """Margin requirement for a position."""
    initial_margin: float  # Required to open
    maintenance_margin: float  # Required to maintain
    buying_power_effect: float  # Impact on buying power
    margin_type: str  # "covered", "naked", "spread", etc.
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def to_dict(self) -> dict:
        return {
            "initial_margin": round(self.initial_margin, 2),
            "maintenance_margin": round(self.maintenance_margin, 2),
            "buying_power_effect": round(self.buying_power_effect, 2),
            "margin_type": self.margin_type,
            "details": self.details,
        }


class MarginModel(ABC):
    """Abstract margin model interface."""

    @abstractmethod
    def calculate_margin(
        self,
        position: Position,
        quote: Optional[OptionQuote],
        spot: float,
        portfolio_value: float,
    ) -> MarginRequirement:
        """
        Calculate margin requirement for a position.

        Args:
            position: Current position
            quote: Option quote (for options positions)
            spot: Current spot price
            portfolio_value: Total portfolio value

        Returns:
            MarginRequirement with initial and maintenance margins
        """
        pass


class RegTMargin(MarginModel):
    """
    Regulation T margin approximation.

    Standard margin rules for options:
    - Covered calls: No additional margin (stock covers assignment)
    - Naked calls: 20% of underlying + premium - OTM amount
    - Naked puts: Greater of 20% or 10% rule
    """

    # Reg-T parameters
    STOCK_INITIAL_MARGIN = 0.50  # 50% for stocks
    STOCK_MAINTENANCE_MARGIN = 0.25  # 25% maintenance

    NAKED_OPTION_PCT = 0.20  # 20% of underlying
    NAKED_OPTION_MIN_PCT = 0.10  # 10% minimum

    def __init__(self, multiplier: int = 100):
        self.multiplier = multiplier

    def calculate_margin(
        self,
        position: Position,
        quote: Optional[OptionQuote],
        spot: float,
        portfolio_value: float,
    ) -> MarginRequirement:
        """Calculate Reg-T margin for a position."""
        if position.position_type == "stock":
            return self._stock_margin(position, spot)
        elif position.is_option:
            return self._option_margin(position, quote, spot)
        else:
            return MarginRequirement(
                initial_margin=0,
                maintenance_margin=0,
                buying_power_effect=0,
                margin_type="unknown",
            )

    def _stock_margin(
        self,
        position: Position,
        spot: float
    ) -> MarginRequirement:
        """Margin for stock position."""
        notional = abs(position.quantity) * spot

        if position.quantity >= 0:
            # Long stock
            initial = notional * self.STOCK_INITIAL_MARGIN
            maintenance = notional * self.STOCK_MAINTENANCE_MARGIN
        else:
            # Short stock
            initial = notional * self.STOCK_INITIAL_MARGIN
            maintenance = notional * 0.30  # Higher for shorts

        return MarginRequirement(
            initial_margin=initial,
            maintenance_margin=maintenance,
            buying_power_effect=-initial,
            margin_type="stock",
            details={"notional": notional},
        )

    def _option_margin(
        self,
        position: Position,
        quote: Optional[OptionQuote],
        spot: float
    ) -> MarginRequirement:
        """Margin for option position."""
        if position.quantity > 0:
            # Long options: pay premium, no margin
            premium = (quote.mid if quote else 0) * position.quantity * self.multiplier
            return MarginRequirement(
                initial_margin=0,
                maintenance_margin=0,
                buying_power_effect=-premium,
                margin_type="long_option",
                details={"premium_paid": premium},
            )

        # Short options
        abs_qty = abs(position.quantity)
        notional = spot * abs_qty * self.multiplier
        strike = position.strike or spot
        premium = (quote.mid if quote else 0) * abs_qty * self.multiplier

        if position.option_type == OptionType.CALL:
            # Naked call: 20% of underlying + premium - OTM amount
            otm_amount = max(0, strike - spot) * abs_qty * self.multiplier

            initial = (
                self.NAKED_OPTION_PCT * notional +
                premium -
                otm_amount
            )
            # Minimum: 10% of underlying + premium
            minimum = self.NAKED_OPTION_MIN_PCT * notional + premium
            initial = max(initial, minimum)

            maintenance = initial * 0.75  # Typically less than initial

            return MarginRequirement(
                initial_margin=initial,
                maintenance_margin=maintenance,
                buying_power_effect=-initial + premium,  # Credit from selling
                margin_type="naked_call",
                details={
                    "notional": notional,
                    "premium_received": premium,
                    "otm_amount": otm_amount,
                },
            )
        else:
            # Naked put: max(20% rule, 10% rule)
            otm_amount = max(0, spot - strike) * abs_qty * self.multiplier

            rule_20 = (
                self.NAKED_OPTION_PCT * notional +
                premium -
                otm_amount
            )
            rule_10 = (
                self.NAKED_OPTION_MIN_PCT * strike * abs_qty * self.multiplier +
                premium
            )
            initial = max(rule_20, rule_10)
            maintenance = initial * 0.75

            return MarginRequirement(
                initial_margin=initial,
                maintenance_margin=maintenance,
                buying_power_effect=-initial + premium,
                margin_type="naked_put",
                details={
                    "notional": notional,
                    "premium_received": premium,
                    "rule_20": rule_20,
                    "rule_10": rule_10,
                },
            )


class PortfolioMarginStub(MarginModel):
    """
    Portfolio margin stub for analysis.

    Simulates portfolio margin with lower requirements than Reg-T.
    This is a placeholder - actual portfolio margin requires
    sophisticated VaR calculation.
    """

    # PM typically requires 15% of notional with adjustments
    PM_BASE_REQUIREMENT = 0.15

    def __init__(self, multiplier: int = 100):
        self.multiplier = multiplier

    def calculate_margin(
        self,
        position: Position,
        quote: Optional[OptionQuote],
        spot: float,
        portfolio_value: float,
    ) -> MarginRequirement:
        """Calculate simplified portfolio margin."""
        if not position.is_option:
            # Stock: similar to Reg-T but potentially lower
            notional = abs(position.quantity) * spot
            initial = notional * 0.15  # PM typically lower
            return MarginRequirement(
                initial_margin=initial,
                maintenance_margin=initial * 0.90,
                buying_power_effect=-initial,
                margin_type="portfolio_margin_stock",
            )

        # Options: based on stress testing
        notional = spot * abs(position.quantity) * self.multiplier
        strike = position.strike or spot
        premium = (quote.mid if quote else 0) * abs(position.quantity) * self.multiplier

        # Simplified stress-based margin
        stress_move = 0.15  # 15% underlying move

        if position.quantity > 0:
            # Long options: premium at risk
            return MarginRequirement(
                initial_margin=0,
                maintenance_margin=0,
                buying_power_effect=-premium,
                margin_type="portfolio_margin_long_option",
            )

        # Short options
        if position.option_type == OptionType.CALL:
            # Stress: underlying up 15%
            stressed_spot = spot * (1 + stress_move)
            stressed_intrinsic = max(0, stressed_spot - strike)
            max_loss = stressed_intrinsic * abs(position.quantity) * self.multiplier

            initial = max(max_loss - premium, notional * 0.05)
        else:
            # Stress: underlying down 15%
            stressed_spot = spot * (1 - stress_move)
            stressed_intrinsic = max(0, strike - stressed_spot)
            max_loss = stressed_intrinsic * abs(position.quantity) * self.multiplier

            initial = max(max_loss - premium, notional * 0.05)

        return MarginRequirement(
            initial_margin=initial,
            maintenance_margin=initial * 0.90,
            buying_power_effect=-initial + premium,
            margin_type="portfolio_margin_short_option",
            details={
                "stress_move": stress_move,
                "notional": notional,
                "premium_received": premium,
            },
        )


def compute_covered_call_margin(
    stock_position: Position,
    call_position: Position,
    spot: float,
    call_quote: Optional[OptionQuote] = None,
    margin_model: Optional[MarginModel] = None,
) -> MarginRequirement:
    """
    Compute margin for a covered call position.

    Covered calls (long stock + short call) require stock margin only,
    as the stock covers potential assignment.

    Args:
        stock_position: Long stock position
        call_position: Short call position
        spot: Current spot price
        call_quote: Call option quote
        margin_model: Margin model to use

    Returns:
        MarginRequirement for the covered position
    """
    if margin_model is None:
        margin_model = RegTMargin()

    # Validate covered position
    if stock_position.quantity <= 0:
        raise ValueError("Covered call requires long stock")

    if call_position.quantity >= 0:
        raise ValueError("Covered call requires short call")

    # Check coverage
    stock_shares = stock_position.quantity
    call_contracts = abs(call_position.quantity)
    covered_shares = call_contracts * 100

    if stock_shares < covered_shares:
        # Partially naked
        covered_contracts = stock_shares // 100
        naked_contracts = call_contracts - covered_contracts

        # Calculate naked portion margin
        naked_position = Position(
            symbol=call_position.symbol,
            quantity=-naked_contracts,
            position_type="call",
            strike=call_position.strike,
            expiry=call_position.expiry,
        )
        naked_margin = margin_model.calculate_margin(
            naked_position, call_quote, spot, 0
        )
    else:
        naked_margin = None

    # Stock margin
    stock_margin = margin_model.calculate_margin(
        stock_position, None, spot, 0
    )

    # Covered call: stock margin only (call is covered)
    # Premium received reduces cash requirement
    premium_received = 0
    if call_quote:
        premium_received = call_quote.mid * abs(call_position.quantity) * 100

    if naked_margin:
        # Partial coverage
        total_initial = stock_margin.initial_margin + naked_margin.initial_margin
        total_maintenance = stock_margin.maintenance_margin + naked_margin.maintenance_margin
        margin_type = "partial_covered_call"
    else:
        total_initial = stock_margin.initial_margin
        total_maintenance = stock_margin.maintenance_margin
        margin_type = "covered_call"

    return MarginRequirement(
        initial_margin=total_initial,
        maintenance_margin=total_maintenance,
        buying_power_effect=-total_initial + premium_received,
        margin_type=margin_type,
        details={
            "stock_margin": stock_margin.to_dict(),
            "premium_received": premium_received,
            "naked_margin": naked_margin.to_dict() if naked_margin else None,
        },
    )
