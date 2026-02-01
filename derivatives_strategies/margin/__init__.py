"""
Margin module - Margin calculation hooks and models.
"""

from derivatives_strategies.margin.model import (
    MarginModel,
    RegTMargin,
    PortfolioMarginStub,
    compute_covered_call_margin,
)

__all__ = [
    "MarginModel",
    "RegTMargin",
    "PortfolioMarginStub",
    "compute_covered_call_margin",
]
