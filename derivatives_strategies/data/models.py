"""
Core data models for derivatives_strategies v3.

All models use dataclasses for clarity and immutability where appropriate.
Timestamps are ISO format strings. All monetary values are in base currency units.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, Any
import hashlib
import json


class OptionType(Enum):
    """Option type enumeration."""
    CALL = "call"
    PUT = "put"


class ActionType(Enum):
    """Recommended action types."""
    HOLD = "hold"
    CLOSE = "close"
    ROLL = "roll"
    OPEN = "open"


class GateStatus(Enum):
    """Gate evaluation status."""
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True)
class SpotQuote:
    """Spot price quote for an underlying."""
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: str  # ISO format

    @property
    def mid(self) -> float:
        """Mid-market price."""
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class RateData:
    """Risk-free rate data."""
    rate: float  # Annualized continuously compounded rate
    as_of_date: str  # ISO format date
    tenor_days: Optional[int] = None  # None means flat rate


@dataclass(frozen=True)
class OptionQuote:
    """Single option contract quote with market data."""
    symbol: str  # Underlying symbol
    expiry: str  # ISO format date (YYYY-MM-DD)
    strike: float
    option_type: OptionType
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    timestamp: str  # ISO format datetime

    # Optional greeks if provided by data source
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    implied_vol: Optional[float] = None

    @property
    def mid(self) -> float:
        """Mid-market price."""
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """Spread as percentage of mid."""
        if self.mid <= 0:
            return float('inf')
        return self.spread / self.mid

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type.value,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "timestamp": self.timestamp,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "implied_vol": self.implied_vol,
        }


@dataclass
class Chain:
    """Option chain for a single underlying."""
    symbol: str
    spot: SpotQuote
    options: list[OptionQuote]
    as_of: str  # ISO format datetime

    def get_expiries(self) -> list[str]:
        """Get sorted list of unique expiry dates."""
        return sorted(set(opt.expiry for opt in self.options))

    def get_strikes(self, expiry: str) -> list[float]:
        """Get sorted list of strikes for an expiry."""
        return sorted(set(
            opt.strike for opt in self.options
            if opt.expiry == expiry
        ))

    def get_option(
        self,
        expiry: str,
        strike: float,
        option_type: OptionType
    ) -> Optional[OptionQuote]:
        """Find a specific option in the chain."""
        for opt in self.options:
            if (opt.expiry == expiry and
                abs(opt.strike - strike) < 0.01 and
                opt.option_type == option_type):
                return opt
        return None

    def get_calls(self, expiry: Optional[str] = None) -> list[OptionQuote]:
        """Get all calls, optionally filtered by expiry."""
        return [
            opt for opt in self.options
            if opt.option_type == OptionType.CALL and
            (expiry is None or opt.expiry == expiry)
        ]

    def get_puts(self, expiry: Optional[str] = None) -> list[OptionQuote]:
        """Get all puts, optionally filtered by expiry."""
        return [
            opt for opt in self.options
            if opt.option_type == OptionType.PUT and
            (expiry is None or opt.expiry == expiry)
        ]


@dataclass(frozen=True)
class DividendEvent:
    """Discrete dividend event."""
    symbol: str
    ex_date: str  # ISO format date
    amount: float
    record_date: Optional[str] = None
    pay_date: Optional[str] = None
    declared_date: Optional[str] = None

    def pv(self, as_of: str, rate: float) -> float:
        """
        Present value of dividend using simple discounting.

        Args:
            as_of: Valuation date (ISO format)
            rate: Risk-free rate (annualized, continuous)

        Returns:
            Present value of the dividend
        """
        import math
        ex_dt = date.fromisoformat(self.ex_date)
        as_of_dt = date.fromisoformat(as_of)
        days_to_ex = (ex_dt - as_of_dt).days
        if days_to_ex <= 0:
            return 0.0
        years = days_to_ex / 365.0
        return self.amount * math.exp(-rate * years)


@dataclass
class Position:
    """Existing position in the portfolio."""
    symbol: str
    quantity: int  # Positive for long, negative for short
    position_type: str  # "stock", "call", "put"

    # For options only
    strike: Optional[float] = None
    expiry: Optional[str] = None

    # Cost basis and tracking
    cost_basis: Optional[float] = None  # Per share/contract
    open_date: Optional[str] = None

    @property
    def is_option(self) -> bool:
        return self.position_type in ("call", "put")

    @property
    def option_type(self) -> Optional[OptionType]:
        if self.position_type == "call":
            return OptionType.CALL
        elif self.position_type == "put":
            return OptionType.PUT
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "position_type": self.position_type,
            "strike": self.strike,
            "expiry": self.expiry,
            "cost_basis": self.cost_basis,
            "open_date": self.open_date,
        }


@dataclass(frozen=True)
class GateResult:
    """Result of a policy gate evaluation."""
    gate_name: str
    status: GateStatus
    message: str
    details: dict = field(default_factory=dict)
    threshold: Optional[float] = None
    actual_value: Optional[float] = None
    override_allowed: bool = True
    override_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "threshold": self.threshold,
            "actual_value": self.actual_value,
            "override_allowed": self.override_allowed,
            "override_reason": self.override_reason,
        }


@dataclass
class Greeks:
    """Option Greeks."""
    delta: float
    gamma: float
    theta: float  # Per day
    vega: float  # Per 1% vol move
    rho: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "delta": round(self.delta, 6),
            "gamma": round(self.gamma, 6),
            "theta": round(self.theta, 4),
            "vega": round(self.vega, 4),
            "rho": round(self.rho, 4) if self.rho else None,
        }


@dataclass
class TransactionCosts:
    """Breakdown of transaction costs."""
    spread_cost: float  # Cost from crossing bid/ask
    commission: float
    exchange_fees: float
    slippage: float
    total: float

    def to_dict(self) -> dict:
        return {
            "spread_cost": round(self.spread_cost, 4),
            "commission": round(self.commission, 4),
            "exchange_fees": round(self.exchange_fees, 4),
            "slippage": round(self.slippage, 4),
            "total": round(self.total, 4),
        }


@dataclass
class Economics:
    """Full economics of a recommendation."""
    gross_premium: float  # Before costs
    transaction_costs: TransactionCosts
    net_premium: float  # After costs
    max_profit: float
    max_loss: float
    breakeven: Optional[float] = None
    annualized_return: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "gross_premium": round(self.gross_premium, 4),
            "transaction_costs": self.transaction_costs.to_dict(),
            "net_premium": round(self.net_premium, 4),
            "max_profit": round(self.max_profit, 4),
            "max_loss": round(self.max_loss, 4),
            "breakeven": round(self.breakeven, 4) if self.breakeven else None,
            "annualized_return": round(self.annualized_return, 4) if self.annualized_return else None,
        }


@dataclass
class Recommendation:
    """A complete recommendation with audit trail."""
    run_id: str
    timestamp: str
    position: Position
    action: ActionType

    # For rolls or new positions
    target_strike: Optional[float] = None
    target_expiry: Optional[str] = None
    target_quantity: Optional[int] = None

    # Analysis
    gate_results: list[GateResult] = field(default_factory=list)
    economics: Optional[Economics] = None
    greeks: Optional[Greeks] = None

    # Rationale
    reason: str = ""
    alternatives_considered: list[dict] = field(default_factory=list)

    # Approval status
    approved: bool = False
    blocked_by: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def inputs_hash(self) -> str:
        """Hash of inputs for audit trail."""
        data = {
            "position": self.position.to_dict(),
            "action": self.action.value,
            "target_strike": self.target_strike,
            "target_expiry": self.target_expiry,
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "position": self.position.to_dict(),
            "action": self.action.value,
            "target_strike": self.target_strike,
            "target_expiry": self.target_expiry,
            "target_quantity": self.target_quantity,
            "gate_results": [g.to_dict() for g in self.gate_results],
            "economics": self.economics.to_dict() if self.economics else None,
            "greeks": self.greeks.to_dict() if self.greeks else None,
            "reason": self.reason,
            "alternatives_considered": self.alternatives_considered,
            "approved": self.approved,
            "blocked_by": self.blocked_by,
            "warnings": self.warnings,
            "inputs_hash": self.inputs_hash(),
        }


@dataclass
class OrderIntent:
    """Order intent generated from recommendation."""
    run_id: str
    timestamp: str
    recommendation_hash: str

    symbol: str
    action: str  # "buy_to_open", "sell_to_open", "buy_to_close", "sell_to_close"
    quantity: int

    # For options
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[str] = None

    # Pricing
    limit_price: Optional[float] = None
    conservative_fill: float = 0.0  # Expected fill based on conservative assumptions

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "recommendation_hash": self.recommendation_hash,
            "symbol": self.symbol,
            "action": self.action,
            "quantity": self.quantity,
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type,
            "limit_price": self.limit_price,
            "conservative_fill": round(self.conservative_fill, 4),
        }


@dataclass
class LedgerEntry:
    """Append-only ledger entry for audit trail."""
    run_id: str
    timestamp: str
    action: str
    inputs_hash: str
    policy_hash: str
    details: dict = field(default_factory=dict)

    def to_json_line(self) -> str:
        data = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "inputs_hash": self.inputs_hash,
            "policy_hash": self.policy_hash,
            "details": self.details,
        }
        return json.dumps(data)
