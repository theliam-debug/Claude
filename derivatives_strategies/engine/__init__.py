"""
Engine module - Core recommendation engine and CLI runner.
"""

from derivatives_strategies.engine.recommender import (
    RecommendationEngine,
    evaluate_covered_call_candidates,
)
from derivatives_strategies.engine.runner import (
    Engine,
    EngineConfig,
    RunResult,
)

__all__ = [
    "RecommendationEngine",
    "evaluate_covered_call_candidates",
    "Engine",
    "EngineConfig",
    "RunResult",
]
