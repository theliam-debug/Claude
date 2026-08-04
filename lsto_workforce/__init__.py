"""
lsto_workforce — the LsTo Agent Workforce operating system.

A governance harness for AI-agent-assisted decision making:
- Charter: roles, decision rights, ethics standards, registered data sources
- Evidence: provenance-tracked, tiered, hashed claims
- Gates: enforceable accountability standards (PASS/WARN/BLOCK)
- Ledger: tamper-evident hash-chained audit trail
- Decision records and briefs: what the decision maker actually reads
- Metrics: process integrity and forecast calibration (Brier)

Agents advise; named humans decide. Every step is auditable.
"""

__version__ = "1.0.0"

from lsto_workforce.models import (
    Assessment,
    DecisionRecord,
    DecisionStatus,
    Dissent,
    DissentSeverity,
    Evidence,
    Forecast,
    GateResult,
    GateStatus,
    ImpactTier,
    Override,
    RoleType,
    SourceTier,
)
from lsto_workforce.charter import Charter, default_charter, load_charter
from lsto_workforce.gates import default_gates
from lsto_workforce.ledger import HashChainLedger
from lsto_workforce.orchestrator import Workforce, WorkforceError
from lsto_workforce.brief import render_brief
from lsto_workforce.metrics import compute_scorecard, render_scorecard

__all__ = [
    "Assessment",
    "Charter",
    "DecisionRecord",
    "DecisionStatus",
    "Dissent",
    "DissentSeverity",
    "Evidence",
    "Forecast",
    "GateResult",
    "GateStatus",
    "HashChainLedger",
    "ImpactTier",
    "Override",
    "RoleType",
    "SourceTier",
    "Workforce",
    "WorkforceError",
    "compute_scorecard",
    "default_charter",
    "default_gates",
    "load_charter",
    "render_brief",
    "render_scorecard",
]
