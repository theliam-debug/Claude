"""
Recommendation engine for covered call strategy.

Evaluates positions and generates recommendations for:
- Hold existing positions
- Close positions (buy to close)
- Roll to new strikes/expiries
- Open new covered calls (if enabled)
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
import uuid

from derivatives_strategies.data.models import (
    Position,
    OptionQuote,
    Chain,
    Recommendation,
    ActionType,
    GateStatus,
    OptionType,
    Economics,
    Greeks,
    OrderIntent,
)
from derivatives_strategies.data.provider import DataProvider
from derivatives_strategies.policy.engine import Policy, PolicyEngine
from derivatives_strategies.policy.gates import GateContext
from derivatives_strategies.costs.model import (
    CostModel,
    compute_all_in_economics,
    conservative_fill_price,
)
from derivatives_strategies.options.greeks import compute_all_greeks
from derivatives_strategies.surface.builder import build_surface


@dataclass
class CandidateOption:
    """A candidate option for a roll or new position."""
    quote: OptionQuote
    economics: Economics
    greeks: Optional[Greeks]
    score: float  # Higher is better
    reason: str


class RecommendationEngine:
    """
    Engine for generating covered call recommendations.

    Evaluates existing positions and generates optimal actions
    subject to policy constraints.
    """

    def __init__(
        self,
        provider: DataProvider,
        policy: Policy,
        cost_model: Optional[CostModel] = None,
        run_id: Optional[str] = None,
    ):
        """
        Initialize recommendation engine.

        Args:
            provider: Data provider
            policy: Policy configuration
            cost_model: Transaction cost model
            run_id: Run identifier (generated if not provided)
        """
        self.provider = provider
        self.policy = policy
        self.policy_engine = PolicyEngine(policy)
        self.cost_model = cost_model or CostModel(
            commission_per_contract=policy.cost_commission,
            price_improvement_factor=policy.cost_price_improvement,
        )
        self.run_id = run_id or str(uuid.uuid4())
        self.as_of = provider.get_as_of_date()

    def analyze_position(
        self,
        position: Position,
        portfolio_value: float = 0.0,
        margin_used: float = 0.0,
        margin_available: float = 0.0,
    ) -> Recommendation:
        """
        Analyze a single position and generate recommendation.

        Args:
            position: Position to analyze
            portfolio_value: Total portfolio value
            margin_used: Current margin used
            margin_available: Available margin

        Returns:
            Recommendation for the position
        """
        timestamp = datetime.utcnow().isoformat() + 'Z'

        # Get market data
        chain = self.provider.get_chain(position.symbol)
        if chain is None:
            return Recommendation(
                run_id=self.run_id,
                timestamp=timestamp,
                position=position,
                action=ActionType.HOLD,
                reason="No market data available",
                approved=False,
                blocked_by="NoData",
            )

        rate = self.provider.get_risk_free_rate().rate
        dividends = self.provider.get_dividends(
            position.symbol,
            start_date=self.as_of,
        )

        # Get current option quote if position is an option
        current_quote = None
        if position.is_option and position.strike and position.expiry:
            current_quote = chain.get_option(
                position.expiry,
                position.strike,
                position.option_type,
            )

        # Build gate context
        context = GateContext(
            symbol=position.symbol,
            spot=chain.spot.mid,
            as_of=self.as_of,
            rate=rate,
            chain=chain,
            position=position,
            target_quote=current_quote,
            dividends=dividends,
            portfolio_value=portfolio_value,
            margin_used=margin_used,
            margin_available=margin_available,
        )

        # Determine best action
        if position.is_option and position.quantity < 0:
            # Short option - evaluate hold/close/roll
            return self._evaluate_short_option(
                position, chain, current_quote, context, timestamp
            )
        elif position.position_type == "stock" and position.quantity > 0:
            # Long stock without covered call - potentially open
            return self._evaluate_uncovered_stock(
                position, chain, context, timestamp
            )
        else:
            # Other positions - hold
            return Recommendation(
                run_id=self.run_id,
                timestamp=timestamp,
                position=position,
                action=ActionType.HOLD,
                reason="Position type not supported for recommendations",
                approved=True,
            )

    def _evaluate_short_option(
        self,
        position: Position,
        chain: Chain,
        current_quote: Optional[OptionQuote],
        context: GateContext,
        timestamp: str,
    ) -> Recommendation:
        """Evaluate short option position for hold/close/roll."""
        rate = context.rate

        # Check if option is near expiry
        expiry_date = date.fromisoformat(position.expiry)
        as_of_date = date.fromisoformat(self.as_of)
        dte = (expiry_date - as_of_date).days

        # Default to hold
        best_action = ActionType.HOLD
        best_target: Optional[CandidateOption] = None
        alternatives = []

        current_greeks = None
        if current_quote:
            T = dte / 365.0 if dte > 0 else 0.001

            # Get IV from surface or estimate
            surface = build_surface(chain, rate, self.as_of)
            iv = surface.get_iv(position.expiry, position.strike)
            if iv and T > 0:
                current_greeks = compute_all_greeks(
                    chain.spot.mid, position.strike, T, rate, iv,
                    position.option_type,
                )

        # Evaluate close if near expiry or ITM
        if dte <= 3 or (current_quote and current_quote.mid < 0.10):
            # Close the position
            if current_quote:
                close_cost = current_quote.ask * abs(position.quantity) * 100
                costs = self.cost_model.compute_costs(
                    current_quote, abs(position.quantity), is_buy=True
                )

                economics = Economics(
                    gross_premium=-close_cost / 100,
                    transaction_costs=costs,
                    net_premium=(-close_cost - costs.total) / 100,
                    max_profit=0,
                    max_loss=close_cost + costs.total,
                )

                best_action = ActionType.CLOSE
                best_target = CandidateOption(
                    quote=current_quote,
                    economics=economics,
                    greeks=current_greeks,
                    score=0,
                    reason="Position near expiry or minimal value remaining",
                )

        # Evaluate roll candidates
        roll_candidates = self._find_roll_candidates(
            position, chain, current_quote, context
        )

        if roll_candidates:
            # Score and sort candidates
            roll_candidates.sort(key=lambda c: c.score, reverse=True)
            best_roll = roll_candidates[0]

            # Check if roll is better than close or hold
            if best_action != ActionType.CLOSE or (
                best_roll.economics.net_premium > 0 and
                best_roll.score > 0
            ):
                best_action = ActionType.ROLL
                best_target = best_roll
                alternatives = [
                    {
                        "strike": c.quote.strike,
                        "expiry": c.quote.expiry,
                        "net_premium": c.economics.net_premium,
                        "score": c.score,
                    }
                    for c in roll_candidates[1:4]  # Top 3 alternatives
                ]

        # Evaluate gates with target
        if best_target:
            context.target_quote = best_target.quote
        gate_results = self.policy_engine.evaluate(context)

        # Check for blocks
        blocked_by = None
        warnings = []
        for result in gate_results:
            if result.status == GateStatus.BLOCK:
                blocked_by = result.gate_name
            elif result.status == GateStatus.WARN:
                warnings.append(result.message)

        # Build recommendation
        rec = Recommendation(
            run_id=self.run_id,
            timestamp=timestamp,
            position=position,
            action=best_action,
            target_strike=best_target.quote.strike if best_target else None,
            target_expiry=best_target.quote.expiry if best_target else None,
            target_quantity=position.quantity if best_target else None,
            gate_results=gate_results,
            economics=best_target.economics if best_target else None,
            greeks=best_target.greeks if best_target else current_greeks,
            reason=best_target.reason if best_target else "Maintain current position",
            alternatives_considered=alternatives,
            approved=blocked_by is None,
            blocked_by=blocked_by,
            warnings=warnings,
        )

        return rec

    def _find_roll_candidates(
        self,
        position: Position,
        chain: Chain,
        current_quote: Optional[OptionQuote],
        context: GateContext,
    ) -> list[CandidateOption]:
        """Find roll candidates for a short option."""
        candidates = []
        rate = context.rate

        # Get expiries within policy range
        as_of_date = date.fromisoformat(self.as_of)

        for expiry in chain.get_expiries():
            exp_date = date.fromisoformat(expiry)
            dte = (exp_date - as_of_date).days

            # Check DTE constraints
            if dte < self.policy.default_dte_min:
                continue
            if dte > self.policy.default_dte_max:
                continue

            T = dte / 365.0

            # Get strikes for this expiry
            for strike in chain.get_strikes(expiry):
                # Skip current position strike/expiry
                if (strike == position.strike and expiry == position.expiry):
                    continue

                quote = chain.get_option(expiry, strike, position.option_type)
                if not quote:
                    continue

                # Check basic liquidity
                if quote.spread_pct > 0.30:
                    continue

                # Calculate economics
                economics_data = compute_all_in_economics(
                    current_position_quote=current_quote,
                    target_quote=quote,
                    current_quantity=position.quantity,
                    target_quantity=position.quantity,
                    model=self.cost_model,
                )

                net_premium = economics_data['net_premium']

                # Skip if doesn't meet credit preference
                if self.policy.prefer_roll_credit and net_premium < 0:
                    if not self.policy.allow_roll_debit:
                        continue
                    if abs(net_premium) > self.policy.max_roll_debit * 100:
                        continue

                # Calculate Greeks
                surface = build_surface(chain, rate, self.as_of)
                iv = surface.get_iv(expiry, strike)
                greeks = None
                if iv and T > 0:
                    greeks = compute_all_greeks(
                        chain.spot.mid, strike, T, rate, iv,
                        position.option_type,
                    )

                # Check delta constraints
                if greeks:
                    abs_delta = abs(greeks.delta)
                    if abs_delta < self.policy.default_delta_min:
                        continue
                    if abs_delta > self.policy.default_delta_max:
                        continue

                # Build economics
                costs = economics_data['transaction_costs']
                economics = Economics(
                    gross_premium=economics_data['gross_premium'] / 100,
                    transaction_costs=costs,
                    net_premium=net_premium / 100,
                    max_profit=net_premium if net_premium > 0 else 0,
                    max_loss=abs(net_premium) if net_premium < 0 else 0,
                    annualized_return=(
                        net_premium / (chain.spot.mid * 100) * (365 / dte)
                        if dte > 0 else 0
                    ),
                )

                # Score the candidate
                score = self._score_candidate(
                    quote, economics, greeks, dte, chain.spot.mid
                )

                candidates.append(CandidateOption(
                    quote=quote,
                    economics=economics,
                    greeks=greeks,
                    score=score,
                    reason=f"Roll to {expiry} ${strike:.2f} for net ${net_premium/100:.2f}",
                ))

        return candidates

    def _score_candidate(
        self,
        quote: OptionQuote,
        economics: Economics,
        greeks: Optional[Greeks],
        dte: int,
        spot: float,
    ) -> float:
        """Score a roll candidate (higher is better)."""
        score = 0.0

        # Premium component (normalized to spot)
        if economics.net_premium > 0:
            score += economics.net_premium / spot * 100

        # Annualized return component
        if economics.annualized_return:
            score += economics.annualized_return * 20

        # Delta preference (prefer 0.25-0.30)
        if greeks:
            delta_pref = 0.275
            delta_penalty = abs(abs(greeks.delta) - delta_pref) * 10
            score -= delta_penalty

        # DTE preference (prefer 30-45 days)
        dte_pref = 35
        dte_penalty = abs(dte - dte_pref) / 10
        score -= dte_penalty

        # Liquidity bonus
        if quote.spread_pct < 0.10:
            score += 2
        elif quote.spread_pct < 0.15:
            score += 1

        return score

    def _evaluate_uncovered_stock(
        self,
        position: Position,
        chain: Chain,
        context: GateContext,
        timestamp: str,
    ) -> Recommendation:
        """Evaluate uncovered stock for potential new covered call."""
        # For now, just recommend hold
        # Full implementation would find optimal strike/expiry
        return Recommendation(
            run_id=self.run_id,
            timestamp=timestamp,
            position=position,
            action=ActionType.HOLD,
            reason="Stock position without active covered call",
            approved=True,
            gate_results=self.policy_engine.evaluate(context),
        )

    def generate_order_intents(
        self,
        recommendations: list[Recommendation]
    ) -> list[OrderIntent]:
        """
        Generate order intents from approved recommendations.

        Args:
            recommendations: List of recommendations

        Returns:
            List of order intents
        """
        intents = []
        timestamp = datetime.utcnow().isoformat() + 'Z'

        for rec in recommendations:
            if not rec.approved:
                continue

            if rec.action == ActionType.HOLD:
                continue

            if rec.action == ActionType.CLOSE:
                # Buy to close
                intents.append(OrderIntent(
                    run_id=self.run_id,
                    timestamp=timestamp,
                    recommendation_hash=rec.inputs_hash(),
                    symbol=rec.position.symbol,
                    action="buy_to_close",
                    quantity=abs(rec.position.quantity),
                    expiry=rec.position.expiry,
                    strike=rec.position.strike,
                    option_type=rec.position.position_type,
                    limit_price=rec.economics.gross_premium if rec.economics else None,
                ))

            elif rec.action == ActionType.ROLL:
                # Sell to close current
                intents.append(OrderIntent(
                    run_id=self.run_id,
                    timestamp=timestamp,
                    recommendation_hash=rec.inputs_hash(),
                    symbol=rec.position.symbol,
                    action="buy_to_close",
                    quantity=abs(rec.position.quantity),
                    expiry=rec.position.expiry,
                    strike=rec.position.strike,
                    option_type=rec.position.position_type,
                ))

                # Sell to open new
                intents.append(OrderIntent(
                    run_id=self.run_id,
                    timestamp=timestamp,
                    recommendation_hash=rec.inputs_hash(),
                    symbol=rec.position.symbol,
                    action="sell_to_open",
                    quantity=abs(rec.target_quantity or rec.position.quantity),
                    expiry=rec.target_expiry,
                    strike=rec.target_strike,
                    option_type=rec.position.position_type,
                ))

            elif rec.action == ActionType.OPEN:
                # Sell to open new covered call
                intents.append(OrderIntent(
                    run_id=self.run_id,
                    timestamp=timestamp,
                    recommendation_hash=rec.inputs_hash(),
                    symbol=rec.position.symbol,
                    action="sell_to_open",
                    quantity=abs(rec.target_quantity or 1),
                    expiry=rec.target_expiry,
                    strike=rec.target_strike,
                    option_type="call",
                ))

        return intents


def evaluate_covered_call_candidates(
    chain: Chain,
    rate: float,
    as_of: str,
    min_dte: int = 7,
    max_dte: int = 45,
    min_delta: float = 0.15,
    max_delta: float = 0.35,
) -> list[CandidateOption]:
    """
    Evaluate covered call candidates for a stock.

    Convenience function for finding optimal strikes/expiries.

    Args:
        chain: Option chain
        rate: Risk-free rate
        as_of: As-of date
        min_dte: Minimum days to expiry
        max_dte: Maximum days to expiry
        min_delta: Minimum delta
        max_delta: Maximum delta

    Returns:
        Sorted list of candidates (best first)
    """
    from derivatives_strategies.costs.model import CostModel

    candidates = []
    cost_model = CostModel()
    as_of_date = date.fromisoformat(as_of[:10])
    surface = build_surface(chain, rate, as_of)

    for expiry in chain.get_expiries():
        exp_date = date.fromisoformat(expiry)
        dte = (exp_date - as_of_date).days

        if dte < min_dte or dte > max_dte:
            continue

        T = dte / 365.0

        for quote in chain.get_calls(expiry):
            # Check liquidity
            if quote.spread_pct > 0.25:
                continue

            # Get IV and Greeks
            iv = surface.get_iv(expiry, quote.strike)
            if not iv:
                continue

            greeks = compute_all_greeks(
                chain.spot.mid, quote.strike, T, rate, iv, OptionType.CALL
            )

            # Check delta
            if greeks.delta < min_delta or greeks.delta > max_delta:
                continue

            # Calculate economics for selling the call
            costs = cost_model.compute_costs(quote, 1, is_buy=False)
            fill_price = conservative_fill_price(quote, is_buy=False)
            net_premium = fill_price * 100 - costs.total

            economics = Economics(
                gross_premium=fill_price,
                transaction_costs=costs,
                net_premium=net_premium / 100,
                max_profit=net_premium,
                max_loss=0,  # Covered by stock
                annualized_return=net_premium / (chain.spot.mid * 100) * (365 / dte),
            )

            # Score
            score = (
                economics.annualized_return * 100 +
                (1 - abs(greeks.delta - 0.275) * 10) +
                (1 - quote.spread_pct * 5)
            )

            candidates.append(CandidateOption(
                quote=quote,
                economics=economics,
                greeks=greeks,
                score=score,
                reason=f"Sell {expiry} ${quote.strike:.2f} call for ${net_premium/100:.2f}",
            ))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
