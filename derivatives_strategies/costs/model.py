"""
Transaction cost model for options trading.

Implements conservative pricing assumptions:
- Selling options: assume fill at bid (or bid + improvement factor)
- Buying options: assume fill at ask
- Includes commissions, exchange fees, and slippage estimation
"""

from dataclasses import dataclass, field
from typing import Optional
from derivatives_strategies.data.models import (
    OptionQuote,
    TransactionCosts,
)


@dataclass
class CostModel:
    """
    Transaction cost model configuration.

    All fees are per contract unless otherwise noted.
    """
    # Commission per contract
    commission_per_contract: float = 0.65

    # Exchange and regulatory fees per contract
    exchange_fee_per_contract: float = 0.05
    orf_fee_per_contract: float = 0.03  # Options Regulatory Fee
    sec_fee_rate: float = 0.0000278  # SEC fee per dollar of sale proceeds

    # Price improvement factor (0 = no improvement, 1 = full spread improvement)
    # Conservative default: 0.1 = 10% of spread improvement
    price_improvement_factor: float = 0.10

    # Slippage model
    slippage_per_contract: float = 0.02  # Base slippage per contract
    slippage_volume_factor: float = 0.001  # Additional slippage per contract for large orders

    # Contract multiplier
    multiplier: int = 100

    def compute_costs(
        self,
        quote: OptionQuote,
        quantity: int,
        is_buy: bool,
        order_size_warning_threshold: int = 100
    ) -> TransactionCosts:
        """
        Compute all transaction costs for an order.

        Args:
            quote: Option quote with bid/ask
            quantity: Number of contracts (positive)
            is_buy: True if buying, False if selling
            order_size_warning_threshold: Log warning for orders above this size

        Returns:
            TransactionCosts breakdown
        """
        abs_qty = abs(quantity)

        # Spread cost
        if is_buy:
            # Buying: pay full spread from mid to ask
            spread_cost = (quote.ask - quote.mid) * abs_qty * self.multiplier
        else:
            # Selling: lose full spread from mid to bid
            # But with price improvement
            full_spread = quote.mid - quote.bid
            improvement = full_spread * self.price_improvement_factor
            spread_cost = (full_spread - improvement) * abs_qty * self.multiplier

        # Commission
        commission = self.commission_per_contract * abs_qty

        # Exchange fees
        exchange_fees = (
            self.exchange_fee_per_contract +
            self.orf_fee_per_contract
        ) * abs_qty

        # SEC fee (only on sales)
        if not is_buy:
            proceeds = quote.bid * abs_qty * self.multiplier
            sec_fee = proceeds * self.sec_fee_rate
            exchange_fees += sec_fee

        # Slippage estimation. Both terms are per-contract dollar amounts —
        # no contract multiplier, matching commission and exchange fees.
        base_slippage = self.slippage_per_contract * abs_qty
        volume_slippage = self.slippage_volume_factor * abs_qty * abs_qty
        slippage = base_slippage + volume_slippage

        total = spread_cost + commission + exchange_fees + slippage

        return TransactionCosts(
            spread_cost=spread_cost,
            commission=commission,
            exchange_fees=exchange_fees,
            slippage=slippage,
            total=total,
        )


def compute_transaction_costs(
    quote: OptionQuote,
    quantity: int,
    is_buy: bool,
    model: Optional[CostModel] = None
) -> TransactionCosts:
    """
    Convenience function to compute transaction costs.

    Args:
        quote: Option quote
        quantity: Number of contracts
        is_buy: True if buying, False if selling
        model: Cost model (uses default if not provided)

    Returns:
        TransactionCosts breakdown
    """
    if model is None:
        model = CostModel()
    return model.compute_costs(quote, quantity, is_buy)


def conservative_fill_price(
    quote: OptionQuote,
    is_buy: bool,
    price_improvement_factor: float = 0.10
) -> float:
    """
    Calculate conservative fill price for an option order.

    Conservative pricing:
    - If buying: assume fill at ask
    - If selling: assume fill at bid + small improvement

    Args:
        quote: Option quote
        is_buy: True if buying, False if selling
        price_improvement_factor: Fraction of spread as improvement (selling only)

    Returns:
        Conservative fill price per share
    """
    if is_buy:
        return quote.ask
    else:
        improvement = (quote.ask - quote.bid) * price_improvement_factor
        return quote.bid + improvement


def compute_all_in_economics(
    current_position_quote: Optional[OptionQuote],
    target_quote: Optional[OptionQuote],
    current_quantity: int,
    target_quantity: int,
    model: Optional[CostModel] = None
) -> dict:
    """
    Compute all-in economics for a position change.

    Handles:
    - Close only (target_quote is None)
    - Open only (current_position_quote is None)
    - Roll (both quotes provided)

    Args:
        current_position_quote: Current option quote (if closing)
        target_quote: Target option quote (if opening)
        current_quantity: Current position size (negative for short)
        target_quantity: Target position size
        model: Cost model

    Returns:
        Dictionary with gross/net premium and cost breakdown
    """
    if model is None:
        model = CostModel()

    gross_premium = 0.0
    total_costs = TransactionCosts(
        spread_cost=0, commission=0, exchange_fees=0, slippage=0, total=0
    )

    # Closing existing position
    if current_position_quote and current_quantity != 0:
        if current_quantity < 0:
            # Short position: buy to close
            is_buy = True
            fill = conservative_fill_price(current_position_quote, True)
            gross_premium -= fill * abs(current_quantity) * model.multiplier
        else:
            # Long position: sell to close
            is_buy = False
            fill = conservative_fill_price(current_position_quote, False)
            gross_premium += fill * abs(current_quantity) * model.multiplier

        costs = model.compute_costs(
            current_position_quote,
            abs(current_quantity),
            is_buy
        )
        total_costs = TransactionCosts(
            spread_cost=total_costs.spread_cost + costs.spread_cost,
            commission=total_costs.commission + costs.commission,
            exchange_fees=total_costs.exchange_fees + costs.exchange_fees,
            slippage=total_costs.slippage + costs.slippage,
            total=total_costs.total + costs.total,
        )

    # Opening new position
    if target_quote and target_quantity != 0:
        if target_quantity < 0:
            # Opening short: sell to open
            is_buy = False
            fill = conservative_fill_price(target_quote, False)
            gross_premium += fill * abs(target_quantity) * model.multiplier
        else:
            # Opening long: buy to open
            is_buy = True
            fill = conservative_fill_price(target_quote, True)
            gross_premium -= fill * abs(target_quantity) * model.multiplier

        costs = model.compute_costs(
            target_quote,
            abs(target_quantity),
            is_buy
        )
        total_costs = TransactionCosts(
            spread_cost=total_costs.spread_cost + costs.spread_cost,
            commission=total_costs.commission + costs.commission,
            exchange_fees=total_costs.exchange_fees + costs.exchange_fees,
            slippage=total_costs.slippage + costs.slippage,
            total=total_costs.total + costs.total,
        )

    net_premium = gross_premium - total_costs.total

    return {
        "gross_premium": gross_premium,
        "transaction_costs": total_costs,
        "net_premium": net_premium,
    }
