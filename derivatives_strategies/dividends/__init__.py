"""
Dividends module - Discrete dividend handling and early exercise analysis.
"""

from derivatives_strategies.dividends.analysis import (
    compute_dividend_pv,
    early_assignment_risk,
    EarlyAssignmentResult,
)

__all__ = [
    "compute_dividend_pv",
    "early_assignment_risk",
    "EarlyAssignmentResult",
]
