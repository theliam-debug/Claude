"""
Core data models for the LsTo Agent Workforce system.

Design principles mirrored from derivatives_strategies:
- Frozen dataclasses for immutable facts, mutable dataclasses for accumulating state.
- Enums with string values for stable serialization.
- Timestamps are ISO-8601 strings (UTC, 'Z' suffix); dates are YYYY-MM-DD strings.
- Every model that enters the audit trail can serialize to a canonical dict.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional, Any
import hashlib
import json
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Current UTC timestamp as ISO-8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id(prefix: str) -> str:
    """Generate a prefixed unique identifier."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def canonical_json(data: Any) -> str:
    """Deterministic JSON serialization for hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(text: str) -> str:
    """Full SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(data: Any) -> str:
    """SHA-256 of canonical JSON — used to fingerprint payloads."""
    return sha256_hex(canonical_json(data))


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RoleType(Enum):
    """Workforce roles. Agents fill these; humans own decisions."""
    RESEARCH_ANALYST = "research_analyst"    # gathers and interprets evidence
    DATA_STEWARD = "data_steward"            # validates sources, freshness, provenance
    RISK_OFFICER = "risk_officer"            # sizes downside, reversibility, exposure
    ETHICS_REVIEWER = "ethics_reviewer"      # screens for ethical/legal/fairness issues
    RED_TEAM = "red_team"                    # argues against the recommendation
    SYNTHESIZER = "synthesizer"              # integrates assessments into a brief
    AUDITOR = "auditor"                      # verifies ledger and process compliance


class SourceTier(Enum):
    """Reliability tier of an evidence source."""
    PRIMARY = "primary"                # official/origin data (regulator, issuer, exchange)
    SECONDARY = "secondary"            # reputable aggregator or press
    INTERNAL = "internal"              # our own systems' outputs (e.g. analytics runs)
    MODEL_ESTIMATE = "model_estimate"  # model/LLM inference — never presented as measurement


class ImpactTier(Enum):
    """Impact tier of a decision — drives required rigor and decision rights."""
    LOW = "low"            # cheap to reverse, small blast radius
    MEDIUM = "medium"      # reversible with effort, moderate stakes
    HIGH = "high"          # hard to reverse or material stakes
    CRITICAL = "critical"  # irreversible, existential, or ethics/legal-sensitive

    @property
    def rank(self) -> int:
        """Numeric rank for ordering comparisons."""
        return _IMPACT_RANK[self]


_IMPACT_RANK = {
    ImpactTier.LOW: 0,
    ImpactTier.MEDIUM: 1,
    ImpactTier.HIGH: 2,
    ImpactTier.CRITICAL: 3,
}


class GateStatus(Enum):
    """Gate evaluation status."""
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class DecisionStatus(Enum):
    """Lifecycle status of a decision record."""
    OPEN = "open"                      # gathering evidence and assessments
    RECOMMENDED = "recommended"        # recommendation set, not yet finalized
    APPROVED = "approved"              # passed gates and required approvals
    BLOCKED = "blocked"                # a hard gate blocked and was not overridden
    PENDING_APPROVAL = "pending_approval"  # gates passed; awaiting human approval
    WITHDRAWN = "withdrawn"            # closed without a decision


class DissentSeverity(Enum):
    """How strongly a dissent objects to the recommendation."""
    NOTE = "note"          # observation worth recording
    MATERIAL = "material"  # would change the decision if true; must be resolved
    FATAL = "fatal"        # decision should not proceed; blocks until resolved


# ---------------------------------------------------------------------------
# Evidence and provenance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DataSource:
    """A registered data source the workforce is allowed to cite."""
    name: str                  # e.g. "SEC EDGAR", "FRED", "derivatives_strategies"
    tier: SourceTier
    description: str = ""
    access: str = ""           # how it is reached, e.g. "mcp:SEC_EDGAR_Personal"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tier": self.tier.value,
            "description": self.description,
            "access": self.access,
        }


@dataclass(frozen=True)
class Evidence:
    """
    A single sourced claim.

    Every factual input to a decision must be an Evidence item. Claims without
    a registered source, retrieval time, and content hash do not pass the
    ProvenanceGate.
    """
    evidence_id: str
    claim: str                 # the factual statement being relied on
    source_name: str           # must match a registered DataSource
    source_tier: SourceTier
    retrieved_at: str          # ISO timestamp when we fetched it
    as_of: str                 # YYYY-MM-DD the data itself refers to
    ref: str = ""              # URL, file path, ledger ref, or query string
    method: str = ""           # e.g. "api", "file", "manual", "analytics_run"
    payload_hash: str = ""     # hash of the raw payload backing the claim
    added_by: RoleType = RoleType.RESEARCH_ANALYST

    @staticmethod
    def create(
        claim: str,
        source_name: str,
        source_tier: SourceTier,
        as_of: str,
        ref: str = "",
        method: str = "",
        raw_payload: Any = None,
        added_by: RoleType = RoleType.RESEARCH_ANALYST,
    ) -> "Evidence":
        """Create evidence with generated id, timestamp, and payload hash."""
        return Evidence(
            evidence_id=new_id("ev"),
            claim=claim,
            source_name=source_name,
            source_tier=source_tier,
            retrieved_at=utc_now_iso(),
            as_of=as_of,
            ref=ref,
            method=method,
            payload_hash=content_hash(raw_payload) if raw_payload is not None else "",
            added_by=added_by,
        )

    def age_days(self, as_of_date: str) -> int:
        """Age of the underlying data relative to a reference date."""
        d_ref = date.fromisoformat(as_of_date)
        d_data = date.fromisoformat(self.as_of)
        return (d_ref - d_data).days

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "claim": self.claim,
            "source_name": self.source_name,
            "source_tier": self.source_tier.value,
            "retrieved_at": self.retrieved_at,
            "as_of": self.as_of,
            "ref": self.ref,
            "method": self.method,
            "payload_hash": self.payload_hash,
            "added_by": self.added_by.value,
        }

    @staticmethod
    def from_dict(d: dict) -> "Evidence":
        return Evidence(
            evidence_id=d["evidence_id"],
            claim=d["claim"],
            source_name=d["source_name"],
            source_tier=SourceTier(d["source_tier"]),
            retrieved_at=d["retrieved_at"],
            as_of=d["as_of"],
            ref=d.get("ref", ""),
            method=d.get("method", ""),
            payload_hash=d.get("payload_hash", ""),
            added_by=RoleType(d.get("added_by", "research_analyst")),
        )


# ---------------------------------------------------------------------------
# Assessments and dissent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Assessment:
    """One role's analysis of the decision question."""
    assessment_id: str
    role: RoleType
    summary: str
    confidence: float                    # 0.0 - 1.0 in the assessment's conclusion
    evidence_ids: tuple = ()             # evidence relied upon
    declared_conflicts: tuple = ()       # conflicts of interest, empty if none
    created_at: str = ""

    @staticmethod
    def create(
        role: RoleType,
        summary: str,
        confidence: float,
        evidence_ids: Optional[list[str]] = None,
        declared_conflicts: Optional[list[str]] = None,
    ) -> "Assessment":
        return Assessment(
            assessment_id=new_id("as"),
            role=role,
            summary=summary,
            confidence=confidence,
            evidence_ids=tuple(evidence_ids or ()),
            declared_conflicts=tuple(declared_conflicts or ()),
            created_at=utc_now_iso(),
        )

    def to_dict(self) -> dict:
        return {
            "assessment_id": self.assessment_id,
            "role": self.role.value,
            "summary": self.summary,
            "confidence": self.confidence,
            "evidence_ids": list(self.evidence_ids),
            "declared_conflicts": list(self.declared_conflicts),
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Assessment":
        return Assessment(
            assessment_id=d["assessment_id"],
            role=RoleType(d["role"]),
            summary=d["summary"],
            confidence=d["confidence"],
            evidence_ids=tuple(d.get("evidence_ids", ())),
            declared_conflicts=tuple(d.get("declared_conflicts", ())),
            created_at=d.get("created_at", ""),
        )


@dataclass
class Dissent:
    """
    A recorded objection. Dissents are never deleted — only resolved with a
    written response. MATERIAL and FATAL dissents block finalization until
    resolved.
    """
    dissent_id: str
    role: RoleType
    objection: str
    severity: DissentSeverity
    created_at: str = ""
    resolution: str = ""          # written response; empty means unresolved
    resolved_at: str = ""
    resolved_by: str = ""         # named human or role that resolved it

    @staticmethod
    def create(role: RoleType, objection: str, severity: DissentSeverity) -> "Dissent":
        return Dissent(
            dissent_id=new_id("di"),
            role=role,
            objection=objection,
            severity=severity,
            created_at=utc_now_iso(),
        )

    @property
    def resolved(self) -> bool:
        return bool(self.resolution)

    def to_dict(self) -> dict:
        return {
            "dissent_id": self.dissent_id,
            "role": self.role.value,
            "objection": self.objection,
            "severity": self.severity.value,
            "created_at": self.created_at,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
        }

    @staticmethod
    def from_dict(d: dict) -> "Dissent":
        di = Dissent(
            dissent_id=d["dissent_id"],
            role=RoleType(d["role"]),
            objection=d["objection"],
            severity=DissentSeverity(d["severity"]),
            created_at=d.get("created_at", ""),
        )
        di.resolution = d.get("resolution", "")
        di.resolved_at = d.get("resolved_at", "")
        di.resolved_by = d.get("resolved_by", "")
        return di


# ---------------------------------------------------------------------------
# Forecasts (calibration accountability)
# ---------------------------------------------------------------------------

@dataclass
class Forecast:
    """
    A falsifiable prediction attached to a decision, so the workforce's
    calibration can be scored after the fact (Brier score in metrics).
    """
    statement: str          # what we predict will be true
    probability: float      # 0.0 - 1.0
    resolve_by: str         # YYYY-MM-DD by which it can be judged
    resolved: Optional[bool] = None   # None until judged
    resolved_at: str = ""

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "probability": self.probability,
            "resolve_by": self.resolve_by,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Forecast":
        return Forecast(
            statement=d["statement"],
            probability=d["probability"],
            resolve_by=d["resolve_by"],
            resolved=d.get("resolved"),
            resolved_at=d.get("resolved_at", ""),
        )


# ---------------------------------------------------------------------------
# Gate results and overrides
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GateResult:
    """Result of one accountability gate evaluation."""
    gate_name: str
    status: GateStatus
    message: str
    details: dict = field(default_factory=dict)
    override_allowed: bool = True

    def to_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "override_allowed": self.override_allowed,
        }

    @staticmethod
    def from_dict(d: dict) -> "GateResult":
        return GateResult(
            gate_name=d["gate_name"],
            status=GateStatus(d["status"]),
            message=d["message"],
            details=d.get("details", {}),
            override_allowed=d.get("override_allowed", True),
        )


@dataclass(frozen=True)
class Override:
    """A logged decision to proceed past a blocking gate."""
    gate_name: str
    reason: str
    authorized_by: str      # named human — overrides are a human accountability act
    at: str

    def to_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "reason": self.reason,
            "authorized_by": self.authorized_by,
            "at": self.at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Override":
        return Override(
            gate_name=d["gate_name"],
            reason=d["reason"],
            authorized_by=d["authorized_by"],
            at=d["at"],
        )


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    """
    The complete, auditable record of one decision moving through the
    workforce: question, evidence, per-role assessments, dissent, gates,
    recommendation, and approval.
    """
    decision_id: str
    question: str
    impact: ImpactTier
    category: str                 # free-form domain, e.g. "portfolio", "hiring"
    requested_by: str             # named human who owns the decision
    opened_at: str
    as_of: str                    # YYYY-MM-DD reference date for freshness checks

    status: DecisionStatus = DecisionStatus.OPEN
    evidence: list = field(default_factory=list)         # list[Evidence]
    assessments: list = field(default_factory=list)      # list[Assessment]
    dissents: list = field(default_factory=list)         # list[Dissent]
    gate_results: list = field(default_factory=list)     # list[GateResult]
    overrides: list = field(default_factory=list)        # list[Override]

    recommendation: str = ""
    alternatives_considered: list = field(default_factory=list)  # list[str]
    what_would_change_our_mind: list = field(default_factory=list)  # list[str]
    confidence: Optional[float] = None
    forecast: Optional[Forecast] = None

    approved_by: str = ""         # named human approver (when required/granted)
    finalized_at: str = ""
    charter_hash: str = ""        # hash of the charter in force

    # -- convenience accessors -------------------------------------------------

    def evidence_by_id(self, evidence_id: str) -> Optional[Evidence]:
        for ev in self.evidence:
            if ev.evidence_id == evidence_id:
                return ev
        return None

    def roles_present(self) -> set:
        return {a.role for a in self.assessments}

    def unresolved_dissents(self) -> list:
        return [d for d in self.dissents if not d.resolved]

    def blocking_results(self) -> list:
        """Gate blocks that have not been overridden."""
        overridden = {o.gate_name for o in self.overrides}
        return [
            g for g in self.gate_results
            if g.status == GateStatus.BLOCK and g.gate_name not in overridden
        ]

    # -- serialization ----------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "question": self.question,
            "impact": self.impact.value,
            "category": self.category,
            "requested_by": self.requested_by,
            "opened_at": self.opened_at,
            "as_of": self.as_of,
            "status": self.status.value,
            "evidence": [e.to_dict() for e in self.evidence],
            "assessments": [a.to_dict() for a in self.assessments],
            "dissents": [d.to_dict() for d in self.dissents],
            "gate_results": [g.to_dict() for g in self.gate_results],
            "overrides": [o.to_dict() for o in self.overrides],
            "recommendation": self.recommendation,
            "alternatives_considered": list(self.alternatives_considered),
            "what_would_change_our_mind": list(self.what_would_change_our_mind),
            "confidence": self.confidence,
            "forecast": self.forecast.to_dict() if self.forecast else None,
            "approved_by": self.approved_by,
            "finalized_at": self.finalized_at,
            "charter_hash": self.charter_hash,
        }

    @staticmethod
    def from_dict(d: dict) -> "DecisionRecord":
        rec = DecisionRecord(
            decision_id=d["decision_id"],
            question=d["question"],
            impact=ImpactTier(d["impact"]),
            category=d.get("category", ""),
            requested_by=d.get("requested_by", ""),
            opened_at=d.get("opened_at", ""),
            as_of=d.get("as_of", ""),
        )
        rec.status = DecisionStatus(d.get("status", "open"))
        rec.evidence = [Evidence.from_dict(e) for e in d.get("evidence", [])]
        rec.assessments = [Assessment.from_dict(a) for a in d.get("assessments", [])]
        rec.dissents = [Dissent.from_dict(x) for x in d.get("dissents", [])]
        rec.gate_results = [GateResult.from_dict(g) for g in d.get("gate_results", [])]
        rec.overrides = [Override.from_dict(o) for o in d.get("overrides", [])]
        rec.recommendation = d.get("recommendation", "")
        rec.alternatives_considered = list(d.get("alternatives_considered", []))
        rec.what_would_change_our_mind = list(d.get("what_would_change_our_mind", []))
        rec.confidence = d.get("confidence")
        rec.forecast = Forecast.from_dict(d["forecast"]) if d.get("forecast") else None
        rec.approved_by = d.get("approved_by", "")
        rec.finalized_at = d.get("finalized_at", "")
        rec.charter_hash = d.get("charter_hash", "")
        return rec

    def record_hash(self) -> str:
        """Stable hash of the full record for the audit ledger."""
        return content_hash(self.to_dict())
