"""
derivatives_strategies v3 - Institutional Policy-Driven Options Overlay Toolkit

A packaged, testable, auditable engine for options strategy analysis supporting:
- Market data ingestion via pluggable providers
- Implied volatility surface building
- Discrete dividends and early exercise gating
- Transaction cost modeling
- Policy engine with hard/soft gates
- Margin model hooks
- Deterministic recommendations and audit logging
"""

__version__ = "3.0.0"
__author__ = "Derivatives Strategies Team"

from derivatives_strategies.engine.runner import Engine
from derivatives_strategies.data.models import (
    OptionQuote,
    Chain,
    DividendEvent,
    Position,
    Recommendation,
    GateResult,
)

__all__ = [
    "Engine",
    "OptionQuote",
    "Chain",
    "DividendEvent",
    "Position",
    "Recommendation",
    "GateResult",
]
